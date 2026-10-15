"""Unit and integration tests for the render benchmark suite."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from PIL import Image

_BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "benchmarks"
if str(_BENCHMARK_DIR) not in sys.path:
    sys.path.insert(0, str(_BENCHMARK_DIR))

from render_benchmark import (  # pyright: ignore[reportMissingImports]
    ALL_BACKENDS,
    SCENARIOS,
    BenchmarkMetrics,
    NullBackendAdapter,
    check_backend_availability,
    format_markdown_table,
    format_summary_table,
    get_backend_adapter,
    make_benchmark_assets,
    run_single_benchmark,
)


class TestBenchmarkMetrics:
    """Test frame time and FPS calculations."""

    def test_compute_constant_frametimes(self) -> None:
        # 1000 frames each exactly 10ms (10,000,000 ns)
        times_ns = [10_000_000] * 1000
        m = BenchmarkMetrics.compute("test_backend", "static", times_ns)

        assert m.total_frames == 1000
        assert pytest.approx(m.total_time_s, 0.001) == 10.0
        assert pytest.approx(m.avg_fps, 0.01) == 100.0
        assert pytest.approx(m.max_fps, 0.01) == 100.0
        assert pytest.approx(m.min_fps, 0.01) == 100.0
        assert pytest.approx(m.fps_1pct_low, 0.01) == 100.0
        assert pytest.approx(m.fps_01pct_low, 0.01) == 100.0
        assert pytest.approx(m.fps_1pct_worst_avg, 0.01) == 100.0
        assert pytest.approx(m.mean_frame_time_ms, 0.01) == 10.0
        assert pytest.approx(m.median_frame_time_ms, 0.01) == 10.0
        assert pytest.approx(m.p99_frame_time_ms, 0.01) == 10.0
        assert pytest.approx(m.p999_frame_time_ms, 0.01) == 10.0

    def test_compute_stutter_distribution(self) -> None:
        # 990 frames at 10ms (100 FPS), 10 frames at 100ms (10 FPS)
        times_ns = [10_000_000] * 990 + [100_000_000] * 10
        m = BenchmarkMetrics.compute("test_backend", "dynamic", times_ns)

        assert m.total_frames == 1000
        # Total time: 990 * 0.01 + 10 * 0.1 = 9.9 + 1.0 = 10.9s
        assert pytest.approx(m.total_time_s, 0.01) == 10.9
        # Average FPS: 1000 / 10.9 = ~91.74 FPS
        assert pytest.approx(m.avg_fps, 0.01) == 1000 / 10.9
        # Max FPS: 1 / 0.01s = 100 FPS
        assert pytest.approx(m.max_fps, 0.01) == 100.0
        # Min FPS: 1 / 0.1s = 10 FPS
        assert pytest.approx(m.min_fps, 0.01) == 10.0
        # 1% Low FPS (P99): In sorted array, 990th index is the first 100ms frame
        # So 1% low is 1 / 0.1s = 10 FPS
        assert pytest.approx(m.fps_1pct_low, 0.01) == 10.0
        assert pytest.approx(m.fps_01pct_low, 0.01) == 10.0
        assert pytest.approx(m.fps_1pct_worst_avg, 0.01) == 10.0
        # P95 frame time should still be 10ms
        assert pytest.approx(m.p95_frame_time_ms, 0.01) == 10.0
        # P99 and P99.9 frame times should be 100ms
        assert pytest.approx(m.p99_frame_time_ms, 0.01) == 100.0
        assert pytest.approx(m.p999_frame_time_ms, 0.01) == 100.0

    def test_compute_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="Cannot compute metrics for 0 frames"):
            BenchmarkMetrics.compute("null", "static", [])

    def test_to_dict_roundtrip(self) -> None:
        times_ns = [10_000_000, 20_000_000]
        m = BenchmarkMetrics.compute("null", "static", times_ns)
        d = m.to_dict()
        assert d["backend"] == "null"
        assert d["scenario"] == "static"
        assert d["total_frames"] == 2
        assert d["avg_fps"] > 0.0


class TestBenchmarkAssets:
    """Test realistic asset generation."""

    def test_make_benchmark_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_benchmark_assets(root)

            # Check backgrounds
            bg1_file = root / "bg" / "bg1.jpg"
            assert bg1_file.is_file()
            with Image.open(bg1_file) as img:
                assert img.size == (1920, 1080)
                assert img.mode == "RGB"

            bg2_file = root / "backgrounds" / "bg2.jpg"
            assert bg2_file.is_file()

            # Check characters
            for name in ("alice", "bob", "charlie", "diana"):
                char_file = root / name / "default.png"
                assert char_file.is_file()
                with Image.open(char_file) as spr:
                    assert spr.size == (600, 1200)
                    assert spr.mode == "RGBA"
                    # Check that alpha channel has variation (not fully opaque or empty)
                    alpha_extrema = spr.getchannel("A").getextrema()
                    assert alpha_extrema[0] == 0  # has transparent pixels
                    assert alpha_extrema[1] == 255  # has opaque pixels


class TestScenarios:
    """Test all scenario builders and their stepping logic."""

    @pytest.mark.parametrize("sc_name", list(SCENARIOS.keys()))
    def test_scenario_creation_and_step(self, sc_name: str) -> None:
        scenario = SCENARIOS[sc_name]
        comp, ui, _choices, step_fn = scenario.create()

        assert comp.virtual_width == 1920
        assert comp.virtual_height == 1080

        # Step through 5 frames
        for i in range(5):
            step_fn(i, comp, ui)
            render_items = comp.render_list()
            assert len(render_items) > 0


class TestBackendAdapters:
    """Test adapter interfaces and single benchmark execution."""

    def test_null_adapter_run(self) -> None:
        adapter = NullBackendAdapter()
        scenario = SCENARIOS["static"]

        metrics = run_single_benchmark(
            adapter,
            scenario,
            frames=20,
            warmup=5,
            width=1280,
            height=720,
            asset_dir=None,
            stage_only=False,
        )

        assert metrics.backend == "null"
        assert metrics.scenario == "static"
        assert metrics.total_frames == 20
        assert metrics.avg_fps > 0.0
        assert metrics.max_fps >= metrics.min_fps
        assert metrics.fps_1pct_low > 0.0
        assert metrics.fps_01pct_low > 0.0

    def test_null_adapter_stage_only(self) -> None:
        adapter = NullBackendAdapter()
        scenario = SCENARIOS["dynamic"]

        metrics = run_single_benchmark(
            adapter,
            scenario,
            frames=15,
            warmup=2,
            width=1280,
            height=720,
            asset_dir=None,
            stage_only=True,
        )

        assert metrics.total_frames == 15
        assert metrics.avg_fps > 0.0

    def test_get_backend_adapter_invalid(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend: 'nonexistent'"):
            get_backend_adapter("nonexistent")

    def test_all_backends_in_list(self) -> None:
        for b in ALL_BACKENDS:
            avail, _ = check_backend_availability(b)
            assert isinstance(avail, bool)


class TestFormatting:
    """Test summary and markdown table formatters."""

    def test_format_summary_table(self) -> None:
        m1 = BenchmarkMetrics.compute("null", "static", [10_000_000] * 50)
        m2 = BenchmarkMetrics.compute("pyglet", "static", [2_000_000] * 50)
        table = format_summary_table([m1, m2])

        assert "null" in table
        assert "pyglet" in table
        assert "static" in table
        assert "Avg FPS" in table
        assert "1% Low" in table
        assert "0.1% Low" in table

    def test_format_markdown_table(self) -> None:
        m = BenchmarkMetrics.compute("null", "dynamic", [5_000_000] * 50)
        md = format_markdown_table([m])

        assert "| Backend | Scenario |" in md
        assert "| `null` | `dynamic` |" in md
        assert "**" in md  # bolded metrics


class TestWorkerSubprocess:
    """Test end-to-end execution of the benchmark CLI worker."""

    def test_worker_cli_execution(self) -> None:
        bench_script = Path(__file__).resolve().parents[1] / "benchmarks" / "render_benchmark.py"

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_out:
            tmp_json = Path(tmp_out.name)

        cmd = [
            sys.executable,
            str(bench_script),
            "--worker",
            "--backend",
            "null",
            "--scenario",
            "static",
            "--frames",
            "15",
            "--warmup",
            "2",
            "--output-json",
            str(tmp_json),
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            assert res.returncode == 0
            assert tmp_json.exists()
            data = json.loads(tmp_json.read_text(encoding="utf-8"))
            assert data["backend"] == "null"
            assert len(data["results"]) == 1
            r0 = data["results"][0]
            assert r0["scenario"] == "static"
            assert r0["total_frames"] == 15
            assert r0["avg_fps"] > 0
            assert r0["fps_1pct_low"] > 0
            assert r0["fps_01pct_low"] > 0
        finally:
            if tmp_json.exists():
                tmp_json.unlink()
