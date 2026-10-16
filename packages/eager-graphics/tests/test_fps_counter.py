"""Tests for the FrameClock FPS utility, backend FPS integration, and compositor timing."""

from __future__ import annotations

import time

import pytest

from eager_graphics import FrameClock, NullRenderer, StageCompositor

# --------------------------------------------------------------------------- #
# FrameClock core behaviour
# --------------------------------------------------------------------------- #


class TestFrameClock:
    """Unit tests for the standalone FrameClock utility."""

    def test_first_tick_returns_zero_dt(self) -> None:
        clock = FrameClock()
        assert clock.tick() == 0.0
        assert clock.frame_count == 1

    def test_fps_zero_until_two_ticks(self) -> None:
        clock = FrameClock()
        clock.tick()
        assert clock.fps == 0.0
        assert clock.fps_avg == 0.0

    def test_fps_uses_explicit_timestamps(self) -> None:
        clock = FrameClock()
        clock.tick(now=10.0)
        clock.tick(now=10.5)  # 0.5s interval
        assert clock.dt == pytest.approx(0.5)
        assert clock.fps == pytest.approx(2.0)  # 1 / 0.5

    def test_fps_avg_rolling_window(self) -> None:
        """fps_avg should only use the last ``rolling_window`` frames."""
        clock = FrameClock(rolling_window=3)
        # 5 frames at 0.1s intervals → overall would be 10 FPS
        for i in range(5):
            clock.tick(now=float(i) * 0.1)
        # Rolling window = 3 frames → last 3 frames span 0.3s → 10 FPS
        assert clock.fps == pytest.approx(10.0)
        assert clock.fps_avg == pytest.approx(10.0)

    def test_fps_avg_trims_old_timestamps(self) -> None:
        clock = FrameClock(rolling_window=3)
        # 5 frames at 0.1s intervals, then 1 frame at 1.0s (slow)
        for i in range(5):
            clock.tick(now=float(i) * 0.1)
        clock.tick(now=1.5)  # 1.1s gap from previous (0.4)

        # Rolling window = 3 → keep last 4 timestamps: [0.2, 0.3, 0.4, 1.5]
        # dt = 1.5 - 0.4 = 1.1 → fps = 1/1.1 ≈ 0.909
        assert clock.fps == pytest.approx(1.0 / 1.1, abs=0.01)
        # fps_avg = 3 intervals / (1.5 - 0.2) = 3/1.3 ≈ 2.308
        assert clock.fps_avg == pytest.approx(3.0 / 1.3, abs=0.01)

    def test_fps_overall_total(self) -> None:
        clock = FrameClock()
        # 10 frames at 0.1s intervals → start=0.0, end=0.9, elapsed=0.9
        for i in range(10):
            clock.tick(now=float(i) * 0.1)
        assert clock.frame_count == 10
        assert clock.fps_overall == pytest.approx(10.0 / 0.9, abs=0.01)
        assert clock.elapsed == pytest.approx(0.9)

    def test_reset_clears_state(self) -> None:
        clock = FrameClock()
        for i in range(5):
            clock.tick(now=float(i))
        assert clock.frame_count == 5
        clock.reset()
        assert clock.frame_count == 0
        assert clock.fps == 0.0
        assert clock.fps_avg == 0.0
        assert clock.elapsed == 0.0

    def test_real_time_perf_counter(self) -> None:
        """Without explicit timestamps, uses time.perf_counter (smoke test)."""
        clock = FrameClock()
        clock.tick()
        time.sleep(0.02)
        dt = clock.tick()
        assert dt > 0.0
        assert clock.fps > 0.0

    def test_rolling_window_must_be_at_least_2(self) -> None:
        with pytest.raises(ValueError, match="rolling_window"):
            FrameClock(rolling_window=1)

    def test_tick_returns_dt(self) -> None:
        clock = FrameClock()
        clock.tick(now=0.0)
        dt = clock.tick(now=0.016)
        assert dt == pytest.approx(0.016)


# --------------------------------------------------------------------------- #
# NullRenderer FPS integration
# --------------------------------------------------------------------------- #


class TestNullRendererFPS:
    """Tests that NullRenderer ticks its FrameClock and exposes FPS."""

    def test_fps_zero_before_any_frame(self) -> None:
        backend = NullRenderer()
        assert backend.frame_count == 0
        assert backend.fps == 0.0

    def test_fps_after_frames(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/test", transition="cut")
        backend = NullRenderer()

        backend.begin_frame()
        backend.clear(comp.__class__.__module__ and __import__("eager_graphics").BLACK)
        backend.end_frame()
        assert backend.frame_count == 1
        assert backend.fps == 0.0  # needs ≥2 frames for instantaneous

        # Add a tiny delay so the second frame has a measurable interval
        time.sleep(0.05)
        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 2
        assert backend.fps > 0.0
        assert backend.fps_avg > 0.0
        assert backend.fps_overall > 0.0

    def test_repr_includes_fps(self) -> None:
        backend = NullRenderer()
        backend.begin_frame()
        backend.end_frame()
        backend.begin_frame()
        backend.end_frame()
        r = repr(backend)
        assert "fps=" in r

    def test_render_compositor_ticks_clock(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/fps_test", transition="cut")
        backend = NullRenderer()

        backend.render_compositor(comp, 1280, 720)
        assert backend.frame_count == 1
        assert backend.clock.frame_count == 1


# --------------------------------------------------------------------------- #
# PILRenderer FPS integration
# --------------------------------------------------------------------------- #


class TestPILRendererFPS:
    """Tests that PILRenderer and PILPlayer expose and update the FPS counter."""

    def test_fps_zero_before_any_frame(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        backend = PILRenderer(1280, 720)
        assert backend.frame_count == 0
        assert backend.fps == 0.0

    def test_fps_after_frames(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/test", transition="cut")
        backend = PILRenderer(1280, 720)

        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 1
        assert backend.fps == 0.0

        time.sleep(0.05)
        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 2
        assert backend.fps > 0.0
        assert backend.fps_avg > 0.0
        assert backend.fps_overall > 0.0

    def test_repr_includes_fps(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        backend = PILRenderer(1280, 720)
        backend.begin_frame()
        backend.end_frame()
        backend.begin_frame()
        backend.end_frame()
        r = repr(backend)
        assert "fps=" in r

    def test_render_compositor_ticks_clock(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/fps_test", transition="cut")
        backend = PILRenderer(1280, 720)

        backend.render_compositor(comp, 1280, 720)
        assert backend.frame_count == 1
        assert backend.clock.frame_count == 1

    def test_pil_player_fps_toggle(self) -> None:
        try:
            from types import SimpleNamespace

            from eager_script import parse_graph

            from eager_graphics import DebugOverlayMode
            from eager_graphics.renderers.pil import PILPlayer
        except ImportError:
            pytest.skip("Pillow is not installed")

        from eager_runtime import GameSession

        graph = parse_graph("## Start --- start\nAlice: Hi!\n")
        session = GameSession(graph)

        player = PILPlayer(
            session=session,
            width=800,
            height=600,
            visible=False,
            show_fps=True,
        )
        try:
            assert player.show_fps is True
            assert player.debug_mode == DebugOverlayMode.FPS
            # Advance tick: step compositor so FPS clock ticks
            player.tick(0.016)
            assert session.compositor.clock.frame_count == 1
            # Render frame with FPS overlay
            player.on_draw()
            assert player.renderer.frame_count == 1
            assert "FPS:" in player.get_debug_overlay_text()

            # Cycle F3: FPS -> DETAILED
            player._on_key(SimpleNamespace(keysym="F3"))
            assert player.debug_mode == DebugOverlayMode.DETAILED
            assert player.show_fps is True
            detailed_text = player.get_debug_overlay_text()
            assert "Eager Debug: PIL Backend" in detailed_text
            assert "Cache Diagnostics" in detailed_text
            player.on_draw()
            assert player.renderer.frame_count == 2

            # Cycle F3: DETAILED -> OFF
            player._on_key(SimpleNamespace(keysym="F3"))
            assert player.debug_mode == DebugOverlayMode.OFF
            assert player.show_fps is False
            assert player.get_debug_overlay_text() == ""
            player.on_draw()
            assert player.renderer.frame_count == 3

            # Cycle F3: OFF -> FPS
            player._on_key(SimpleNamespace(keysym="F3"))
            assert player.debug_mode == DebugOverlayMode.FPS
            assert player.show_fps is True
        finally:
            player.close()


# --------------------------------------------------------------------------- #
# StageCompositor FPS integration
# --------------------------------------------------------------------------- #


class TestCompositorFPS:
    """Tests that the compositor ticks its clock and reports FPS in debug_info."""

    def test_fps_zero_initially(self) -> None:
        comp = StageCompositor(1920, 1080)
        assert comp.fps == 0.0
        assert comp.fps_avg == 0.0
        assert comp.fps_overall == 0.0

    def test_step_ticks_clock(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/step_fps", transition="cut")
        comp.step(dt=0.016)
        assert comp.clock.frame_count == 1
        comp.step(dt=0.016)
        assert comp.clock.frame_count == 2
        assert comp.fps > 0.0
        assert comp.fps_avg > 0.0
        assert comp.fps_overall > 0.0

    def test_step_does_not_tick_without_call(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/nostep", transition="cut")
        comp.update(0.016)  # update() alone should NOT tick the FPS clock
        assert comp.clock.frame_count == 0
        assert comp.fps == 0.0

    def test_update_does_not_tick_clock(self) -> None:
        """Only step() ticks the clock, not update() directly."""
        comp = StageCompositor(1920, 1080)
        comp.update(0.1)
        assert comp.clock.frame_count == 0

    def test_debug_info_includes_fps_section(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/dbg_fps", transition="cut")
        comp.step()
        comp.step()

        info = comp.debug_info()
        assert "fps" in info
        fps = info["fps"]
        assert set(fps.keys()) == {
            "instantaneous",
            "avg_60",
            "overall",
            "frames_stepped",
            "elapsed",
        }
        assert fps["frames_stepped"] == 2
        assert fps["instantaneous"] > 0
        assert fps["elapsed"] >= 0.0

    def test_debug_repr_contains_fps_line(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/repr_fps", transition="cut")
        comp.step()
        comp.step()

        text = comp.debug_repr(include_layers=False)
        assert "FPS" in text
        assert "avg" in text
        assert "frames" in text

    def test_debug_info_json_serializable_with_fps(self) -> None:
        import json

        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/json_fps", transition="cut")
        for _ in range(5):
            comp.step(dt=0.01)
        info = comp.debug_info()
        json.dumps(info)  # must not raise

    def test_run_headless_updates_fps(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/run_fps", transition="cut")
        backend = NullRenderer()
        comp.run_headless(backend, max_steps=10, render=True)
        assert comp.clock.frame_count == 10
        assert backend.clock.frame_count == 10


# --------------------------------------------------------------------------- #
# FrameClock edge cases
# --------------------------------------------------------------------------- #


class TestFrameClockEdgeCases:
    """Edge-case tests for FrameClock."""

    def test_zero_dt_on_identical_timestamps(self) -> None:
        clock = FrameClock()
        clock.tick(now=1.0)
        dt = clock.tick(now=1.0)  # same timestamp
        assert dt == 0.0
        # fps should be 0 because dt is 0
        assert clock.fps == 0.0

    def test_negative_dt_guarded(self) -> None:
        clock = FrameClock()
        clock.tick(now=1.0)
        # Simulate a backwards clock
        dt = clock.tick(now=0.5)
        assert dt == 0.0
        assert clock.fps == 0.0

    def test_large_rolling_window(self) -> None:
        """With a large window, all timestamps are kept."""
        clock = FrameClock(rolling_window=1000)
        for i in range(200):
            clock.tick(now=float(i))
        assert clock.fps == pytest.approx(1.0)
        assert clock.fps_avg == pytest.approx(1.0)
        # fps_overall = 200 frames / 199.0s (start at 0.0, end at 199.0)
        assert clock.fps_overall == pytest.approx(200.0 / 199.0, abs=0.01)
