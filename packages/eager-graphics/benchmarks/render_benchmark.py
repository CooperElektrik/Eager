"""Comprehensive unbounded-FPS benchmark suite for Eager-Graphics rendering backends.

Benchmarks each rendering backend (NullRenderer, PILRenderer, PygletRenderer,
RaylibRenderer) across realistic visual novel workloads (static scene, dynamic
animations, scene crossfades, branching choice menus, text reveal progression,
and heavy multi-character stress scenes) for 5k frames at unbounded FPS.

Metrics recorded:
  - Average FPS (harmonic mean of instantaneous frame rates / total frames / total time)
  - Max FPS (1 / min frame time)
  - 1% Low FPS (1 / 99th percentile frame time)
  - 0.1% Low FPS (1 / 99.9th percentile frame time)
  - Min FPS (1 / max frame time)
  - Worst 1% and 0.1% average FPS (harmonic mean of worst frames)
  - Frame time distributions: Mean, Median (P50), P95, P99, P99.9, Min, Max, StdDev (ms)

Architecture:
  When benchmarking multiple backends or using `--backend all`, each backend is
  executed in an isolated worker subprocess.  This prevents OpenGL/EGL/GLFW
  driver collisions (e.g. Pyglet's GTK/EGL conflicting with Raylib's GLFW context
  on Wayland) and guarantees clean memory and texture caches for every run.

Usage::

    # Run default 5k frames benchmark across all available backends & scenarios
    python packages/eager-graphics/benchmarks/render_benchmark.py

    # Run a specific backend and scenario for 5000 frames
    python packages/eager-graphics/benchmarks/render_benchmark.py -b raylib -s static -n 5000

    # Compare Raylib vs Pyglet on dynamic scene
    python packages/eager-graphics/benchmarks/render_benchmark.py -b raylib -b pyglet -s dynamic

    # Output JSON or Markdown
    python packages/eager-graphics/benchmarks/render_benchmark.py --markdown
    python packages/eager-graphics/benchmarks/render_benchmark.py --json-file results.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Ensure workspace packages are in sys.path when invoked directly
_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
for _pkg in ("eager-core", "eager-script", "eager-runtime", "eager-graphics"):
    _pkg_src = _REPO_ROOT / "packages" / _pkg / "src"
    if _pkg_src.is_dir() and str(_pkg_src) not in sys.path:
        sys.path.insert(0, str(_pkg_src))

from eager_core.events import ChoiceOption, ChoicePromptEvent
from eager_core.types import Vec2

from eager_graphics import Color, ScaleMode, StageCompositor
from eager_graphics.ui_components import UIOverlay
from eager_graphics.ui_state import UIState

# --------------------------------------------------------------------------- #
# Realistic Asset Generation
# --------------------------------------------------------------------------- #


def make_benchmark_assets(root: Path) -> Path:
    """Generate realistic high-resolution assets for visual novel workloads.

    Creates:
      - 1920x1080 JPEG backgrounds (bg1, bg2) with textured gradients and details.
      - 600x1200 RGBA PNG character sprites (alice, bob, charlie, diana) with
        anti-aliased edges, head/hair, body/coat, and semi-transparent alpha fringes.
    """
    from PIL import Image, ImageDraw

    bg_dir = root / "bg"
    bg_dir.mkdir(parents=True, exist_ok=True)
    (root / "backgrounds").mkdir(parents=True, exist_ok=True)
    (root / "characters").mkdir(parents=True, exist_ok=True)

    # 1. 1920x1080 Backgrounds
    for i, name in enumerate(("bg1", "bg2")):
        base = Image.linear_gradient("L").resize((1920, 1080)).convert("RGB")
        # Multi-hue channel separation
        r_shift = 60 * (i + 1)
        g_shift = 110 * (i + 1)
        b_shift = 160 * (i + 1)
        lut_r = [(p + r_shift) % 256 for p in range(256)]
        lut_g = [(p + g_shift) % 256 for p in range(256)]
        lut_b = [(p + b_shift) % 256 for p in range(256)]

        bg = Image.merge(
            "RGB",
            (
                base.getchannel(0).point(lut_r),
                base.getchannel(0).point(lut_g),
                base.getchannel(0).point(lut_b),
            ),
        )
        d = ImageDraw.Draw(bg)
        # Add visual interest with perspective geometry lines
        for step_y in range(150, 1050, 120):
            d.line([(0, step_y), (1920, step_y + 40)], fill=(40 + i * 20, 50, 70), width=3)
        bg.save(bg_dir / f"{name}.jpg", quality=92)
        bg.save(root / "backgrounds" / f"{name}.jpg", quality=92)

    # 2. 600x1200 RGBA Character Sprites
    palette = {
        "alice": ((245, 210, 190), (60, 95, 175), (200, 70, 70)),
        "bob": ((235, 195, 170), (45, 130, 80), (70, 90, 140)),
        "charlie": ((250, 220, 200), (160, 80, 150), (220, 180, 60)),
        "diana": ((225, 185, 160), (180, 110, 40), (50, 50, 70)),
    }
    for char_name, (skin, coat, hair) in palette.items():
        (root / char_name).mkdir(exist_ok=True)
        (root / "characters" / char_name).mkdir(parents=True, exist_ok=True)

        spr = Image.new("RGBA", (600, 1200), (0, 0, 0, 0))
        d = ImageDraw.Draw(spr)
        # Hair / silhouette
        d.ellipse((30, 20, 570, 540), fill=(*hair, 255))
        # Face / skin
        d.ellipse((70, 70, 530, 510), fill=(*skin, 255))
        # Eyes
        d.ellipse((170, 230, 240, 290), fill=(30, 30, 40, 255))
        d.ellipse((360, 230, 430, 290), fill=(30, 30, 40, 255))
        # Body / coat
        d.rectangle((100, 480, 500, 1200), fill=(*coat, 255))
        # Semi-transparent alpha fringe / shoulder cape
        d.ellipse((50, 450, 550, 620), fill=(*coat, 180))
        d.polygon([(100, 480), (500, 480), (400, 700), (200, 700)], fill=(*skin, 255))

        # Save to both candidate path variants
        spr.save(root / char_name / "default.png")
        spr.save(root / "characters" / char_name / "default.png")
        spr.save(root / f"{char_name}.png")
        spr.save(root / "characters" / f"{char_name}.png")

    return root


# --------------------------------------------------------------------------- #
# Statistics & Metrics
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class BenchmarkMetrics:
    """Detailed frame-rate and frame-time metrics for a completed scenario benchmark."""

    backend: str
    scenario: str
    total_frames: int
    total_time_s: float
    avg_fps: float
    max_fps: float
    min_fps: float
    fps_1pct_low: float  # 1 / 99th percentile frame time
    fps_01pct_low: float  # 1 / 99.9th percentile frame time
    fps_1pct_worst_avg: float  # Harmonic mean of slowest 1% frames
    fps_01pct_worst_avg: float  # Harmonic mean of slowest 0.1% frames
    mean_frame_time_ms: float
    median_frame_time_ms: float
    p95_frame_time_ms: float
    p99_frame_time_ms: float
    p999_frame_time_ms: float
    min_frame_time_ms: float
    max_frame_time_ms: float
    stddev_frame_time_ms: float

    @classmethod
    def compute(
        cls,
        backend: str,
        scenario: str,
        frame_times_ns: list[int],
    ) -> BenchmarkMetrics:
        """Compute metrics from raw per-frame execution durations in nanoseconds."""
        n = len(frame_times_ns)
        if n == 0:
            msg = "Cannot compute metrics for 0 frames"
            raise ValueError(msg)

        total_ns = sum(frame_times_ns)
        total_time_s = total_ns / 1e9

        # Convert to milliseconds for distribution stats
        times_ms = [t / 1e6 for t in frame_times_ns]
        sorted_times_ms = sorted(times_ms)

        mean_ms = total_ns / (n * 1e6)
        min_ms = sorted_times_ms[0]
        max_ms = sorted_times_ms[-1]

        median_ms = sorted_times_ms[min(int(0.50 * n), n - 1)]
        p95_ms = sorted_times_ms[min(int(0.95 * n), n - 1)]
        p99_ms = sorted_times_ms[min(int(0.99 * n), n - 1)]
        p999_ms = sorted_times_ms[min(int(0.999 * n), n - 1)]

        stddev_ms = statistics.stdev(times_ms) if n > 1 else 0.0

        # Average FPS: Total frames / total elapsed time
        avg_fps = n / total_time_s if total_time_s > 0 else 0.0

        # Max FPS: 1 / min frame time
        max_fps = (1000.0 / min_ms) if min_ms > 0 else 0.0

        # Min FPS: 1 / max frame time
        min_fps = (1000.0 / max_ms) if max_ms > 0 else 0.0

        # 1% Low FPS: 1 / 99th percentile frame duration
        fps_1pct_low = (1000.0 / p99_ms) if p99_ms > 0 else 0.0

        # 0.1% Low FPS: 1 / 99.9th percentile frame duration
        fps_01pct_low = (1000.0 / p999_ms) if p999_ms > 0 else 0.0

        # Worst 1% average FPS (harmonic mean of slowest 1% frames)
        count_1pct = max(1, int(0.01 * n))
        worst_1pct_slice = sorted_times_ms[-count_1pct:]
        worst_1pct_mean_ms = sum(worst_1pct_slice) / count_1pct
        fps_1pct_worst_avg = (1000.0 / worst_1pct_mean_ms) if worst_1pct_mean_ms > 0 else 0.0

        # Worst 0.1% average FPS (harmonic mean of slowest 0.1% frames)
        count_01pct = max(1, int(0.001 * n))
        worst_01pct_slice = sorted_times_ms[-count_01pct:]
        worst_01pct_mean_ms = sum(worst_01pct_slice) / count_01pct
        fps_01pct_worst_avg = (1000.0 / worst_01pct_mean_ms) if worst_01pct_mean_ms > 0 else 0.0

        return cls(
            backend=backend,
            scenario=scenario,
            total_frames=n,
            total_time_s=total_time_s,
            avg_fps=avg_fps,
            max_fps=max_fps,
            min_fps=min_fps,
            fps_1pct_low=fps_1pct_low,
            fps_01pct_low=fps_01pct_low,
            fps_1pct_worst_avg=fps_1pct_worst_avg,
            fps_01pct_worst_avg=fps_01pct_worst_avg,
            mean_frame_time_ms=mean_ms,
            median_frame_time_ms=median_ms,
            p95_frame_time_ms=p95_ms,
            p99_frame_time_ms=p99_ms,
            p999_frame_time_ms=p999_ms,
            min_frame_time_ms=min_ms,
            max_frame_time_ms=max_ms,
            stddev_frame_time_ms=stddev_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Scenario Definitions
# --------------------------------------------------------------------------- #


class BenchmarkScenario:
    """Configures stage and UI state and steps per-frame dynamic behavior."""

    def __init__(
        self,
        name: str,
        description: str,
        builder: Callable[
            [],
            tuple[
                StageCompositor,
                UIState | None,
                ChoicePromptEvent | None,
                Callable[[int, StageCompositor, UIState | None], None],
            ],
        ],
    ) -> None:
        self.name = name
        self.description = description
        self.builder = builder

    def create(
        self,
    ) -> tuple[
        StageCompositor,
        UIState | None,
        ChoicePromptEvent | None,
        Callable[[int, StageCompositor, UIState | None], None],
    ]:
        return self.builder()


def _build_static_scenario() -> tuple[
    StageCompositor,
    UIState | None,
    ChoicePromptEvent | None,
    Callable[[int, StageCompositor, UIState | None], None],
]:
    """1080p background, 2 characters, standard dialogue box (steady reading state)."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", duration=0.0)
    comp.show_character("alice", position="left", duration=0.0)
    comp.show_character("bob", position="right", duration=0.0)

    ui = UIState(
        speaker="Alice",
        text=(
            "The rain had not stopped for three days, and the tavern was fuller "
            "than it had any right to be. Every table creaked under elbows and "
            "tankards, and the fire spat sparks whenever the door swung open."
        ),
    )
    return comp, ui, None, lambda _i, _c, _u: None


def _build_dynamic_scenario() -> tuple[
    StageCompositor,
    UIState | None,
    ChoicePromptEvent | None,
    Callable[[int, StageCompositor, UIState | None], None],
]:
    """Action scene: character slide, pulsing scale, camera shake, and impact flashes."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", duration=0.0)
    comp.show_character("alice", position="left", duration=0.0)
    comp.show_character("bob", position="right", duration=0.0)
    comp.move_character("alice", "center", duration=2.5)
    comp.shake(intensity=5.0, duration=1000.0)

    ui = UIState(
        speaker="Bob",
        text="Brace yourselves! The fortress ramparts are giving way under the barrage!",
    )

    def step(i: int, c: StageCompositor, _u: UIState | None) -> None:
        c.step(1.0 / 60.0)
        # Pulse Bob's scale
        char_layer = c.stage.get_layer("characters")
        if char_layer is not None:
            char_elem = char_layer.get_element("bob")
            if char_elem is not None:
                s = 1.0 + 0.06 * math.sin(i * 0.08)
                char_elem.state.scale = Vec2(s, s)
        # Periodic dramatic lightning flash every 150 frames
        if i % 150 == 0:
            c.flash(duration=0.25, color=Color(1.0, 0.95, 0.9, 0.8))
        # Ping-pong Alice's slide across the stage
        if i % 180 == 0 and i > 0:
            pos = "left" if (i // 180) % 2 == 1 else "center"
            c.move_character("alice", pos, duration=2.5)

    return comp, ui, None, step


def _build_crossfade_scenario() -> tuple[
    StageCompositor,
    UIState | None,
    ChoicePromptEvent | None,
    Callable[[int, StageCompositor, UIState | None], None],
]:
    """Dual-background crossfade transition at 1080p, character alpha fades."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", duration=0.0)
    comp.show_character("alice", position="left", duration=0.0)
    comp.show_character("bob", position="right", duration=0.0)
    comp.set_background("bg/bg2", transition="crossfade", duration=2.0)
    comp.hide_character("bob", transition="fade", duration=2.0)
    comp.show_character("charlie", position="center", transition="fade", duration=2.0)

    ui = UIState(
        speaker="Narrator",
        text="The sun sank beneath the western ridge, painting the valley in crimson and shadow.",
    )

    def step(i: int, c: StageCompositor, _u: UIState | None) -> None:
        c.step(1.0 / 60.0)
        # Loop the crossfade every 120 frames (~2s)
        if i % 120 == 0 and i > 0:
            target = "bg/bg1" if (i // 120) % 2 == 1 else "bg/bg2"
            c.set_background(target, transition="crossfade", duration=2.0)

    return comp, ui, None, step


def _build_choices_scenario() -> tuple[
    StageCompositor,
    UIState | None,
    ChoicePromptEvent | None,
    Callable[[int, StageCompositor, UIState | None], None],
]:
    """Branching decision point: 3 characters on stage with 3 interactive choice buttons."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", duration=0.0)
    comp.show_character("alice", position="left", duration=0.0)
    comp.show_character("bob", position="right", duration=0.0)
    comp.show_character("charlie", position="center", duration=0.0)

    ui = UIState(
        speaker="Alice",
        text="The ancient gateway stands before us, sealed with three distinct runic inscriptions.",
    )
    choices = ChoicePromptEvent(
        options=(
            ChoiceOption(0, "Channel celestial fire to shatter the barrier"),
            ChoiceOption(1, "Decipher the ancient runes in the archives"),
            ChoiceOption(2, "Search for a forgotten subterranean passageway"),
        ),
        line_number=42,
    )
    return comp, ui, choices, lambda _i, _c, _u: None


def _build_text_reveal_scenario() -> tuple[
    StageCompositor,
    UIState | None,
    ChoicePromptEvent | None,
    Callable[[int, StageCompositor, UIState | None], None],
]:
    """Typewriter dialogue progression: visible character count increments each frame."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", duration=0.0)
    comp.show_character("alice", position="left", duration=0.0)
    comp.show_character("bob", position="right", duration=0.0)

    full_text = (
        "The archive had stood abandoned for centuries, yet every manuscript "
        "gleamed with faint luminescent glyphs. When you step closer, the words "
        "rearrange themselves upon the parchment as if reacting to your presence."
    )
    ui = UIState(speaker="Alice", text=full_text, visible_chars=1)

    def step(i: int, _c: StageCompositor, u: UIState | None) -> None:
        if u is not None:
            u.visible_chars = (i % len(full_text)) + 1

    return comp, ui, None, step


def _build_stress_scenario() -> tuple[
    StageCompositor,
    UIState | None,
    ChoicePromptEvent | None,
    Callable[[int, StageCompositor, UIState | None], None],
]:
    """Worst-case composite: 4 characters with tints, rotations, flips, shake, & 4 choices."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", duration=0.0)
    comp.show_character("alice", position="left", duration=0.0)
    comp.show_character("bob", position="right", duration=0.0, flip_h=True)
    comp.show_character("charlie", position="center", duration=0.0)
    comp.show_character("diana", position="center_left", duration=0.0)
    comp.shake(intensity=4.0, duration=1000.0)

    ui = UIState(
        speaker="Diana",
        text="All four factions have assembled at the summit. Peace hinges on this very moment.",
    )
    choices = ChoicePromptEvent(
        options=(
            ChoiceOption(0, "Propose an unconditional mutual defense pact"),
            ChoiceOption(1, "Demand the immediate disarmament of the northern legions"),
            ChoiceOption(2, "Unveil the evidence of the council's hidden treachery"),
            ChoiceOption(3, "Withdraw and prepare defenses for an inevitable siege"),
        ),
        line_number=99,
    )

    def step(i: int, c: StageCompositor, _u: UIState | None) -> None:
        c.step(1.0 / 60.0)
        # Animate characters with rotations and scales
        char_layer = c.stage.get_layer("characters")
        if char_layer is not None:
            elem_alice = char_layer.get_element("alice")
            if elem_alice is not None:
                elem_alice.state.rotation = (i * 0.4) % 360.0
            elem_bob = char_layer.get_element("bob")
            if elem_bob is not None:
                s = 1.0 + 0.08 * math.sin(i * 0.1)
                elem_bob.state.scale = Vec2(s, s)

    return comp, ui, choices, step


SCENARIOS: dict[str, BenchmarkScenario] = {
    "static": BenchmarkScenario(
        "static",
        "Realistic static dialogue scene (1080p bg, 2 characters, dialogue box)",
        _build_static_scenario,
    ),
    "dynamic": BenchmarkScenario(
        "dynamic",
        "Dynamic animations (character slide, scale pulse, camera shake, flash)",
        _build_dynamic_scenario,
    ),
    "crossfade": BenchmarkScenario(
        "crossfade",
        "Scene transition (dual-background 1080p crossfade, character alpha fades)",
        _build_crossfade_scenario,
    ),
    "choices": BenchmarkScenario(
        "choices",
        "Branching decision point (3 characters on stage, 3 choice prompt cards)",
        _build_choices_scenario,
    ),
    "text_reveal": BenchmarkScenario(
        "text_reveal",
        "Dialogue typewriter progression (incrementing visible characters)",
        _build_text_reveal_scenario,
    ),
    "stress": BenchmarkScenario(
        "stress",
        "Heavy multi-character composite (4 characters, transforms/tints, shake, 4 choices)",
        _build_stress_scenario,
    ),
}


# --------------------------------------------------------------------------- #
# Backend Adapters
# --------------------------------------------------------------------------- #


class BaseBackendAdapter:
    """Base interface for backend frame execution in the benchmark harness."""

    name: str = "base"

    def initialize(self, width: int, height: int, asset_dir: Path | None) -> None:
        raise NotImplementedError

    def render_frame(
        self,
        comp: StageCompositor,
        overlay: UIOverlay | None,
        ui_state: UIState | None,
        choices: ChoicePromptEvent | None,
    ) -> None:
        raise NotImplementedError

    def teardown(self) -> None:
        pass


class NullBackendAdapter(BaseBackendAdapter):
    name = "null"
    width: int = 1280
    height: int = 720
    renderer: Any = None

    def initialize(self, width: int, height: int, asset_dir: Path | None) -> None:
        from eager_graphics.renderers.null import NullRenderer

        self.width = width
        self.height = height
        self.renderer = NullRenderer()

    def render_frame(
        self,
        comp: StageCompositor,
        overlay: UIOverlay | None,
        ui_state: UIState | None,
        choices: ChoicePromptEvent | None,
    ) -> None:
        self.renderer.render_compositor(comp, self.width, self.height)
        if overlay is not None and ui_state is not None:
            overlay.draw(self.renderer, ui_state, choices, is_finished=False)


class PILBackendAdapter(BaseBackendAdapter):
    name = "pil"
    width: int = 1280
    height: int = 720
    renderer: Any = None

    def initialize(self, width: int, height: int, asset_dir: Path | None) -> None:
        from eager_graphics.renderers.pil import PILRenderer

        self.width = width
        self.height = height
        self.renderer = PILRenderer(width, height, asset_dir=asset_dir, scale_mode=ScaleMode.LETTERBOX)

    def render_frame(
        self,
        comp: StageCompositor,
        overlay: UIOverlay | None,
        ui_state: UIState | None,
        choices: ChoicePromptEvent | None,
    ) -> None:
        self.renderer.render_compositor(comp, self.width, self.height)
        if overlay is not None and ui_state is not None:
            overlay.draw(self.renderer, ui_state, choices, is_finished=False)

    def teardown(self) -> None:
        if hasattr(self.renderer, "asset_resolver"):
            self.renderer.asset_resolver.clear_cache()


class PygletBackendAdapter(BaseBackendAdapter):
    name = "pyglet"
    width: int = 1280
    height: int = 720
    window: Any = None
    renderer: Any = None

    def initialize(self, width: int, height: int, asset_dir: Path | None) -> None:
        import pyglet

        from eager_graphics.renderers.pyglet import PygletRenderer

        self.width = width
        self.height = height
        self.window = pyglet.window.Window(
            width=width,
            height=height,
            visible=False,
            vsync=False,
        )
        self.renderer = PygletRenderer(
            width=width,
            height=height,
            asset_dir=asset_dir,
            scale_mode=ScaleMode.LETTERBOX,
            window=self.window,
        )

    def render_frame(
        self,
        comp: StageCompositor,
        overlay: UIOverlay | None,
        ui_state: UIState | None,
        choices: ChoicePromptEvent | None,
    ) -> None:
        self.renderer.render_compositor(comp, self.width, self.height)
        if overlay is not None and ui_state is not None:
            overlay.draw(self.renderer, ui_state, choices, is_finished=False)
        self.renderer.flush_ui()
        self.window.flip()

    def teardown(self) -> None:
        try:
            self.window.close()
        except Exception:  # noqa: BLE001, S110
            pass


class RaylibBackendAdapter(BaseBackendAdapter):
    name = "raylib"
    width: int = 1280
    height: int = 720
    pyray: Any = None
    renderer: Any = None

    def initialize(self, width: int, height: int, asset_dir: Path | None) -> None:
        import pyray

        from eager_graphics.renderers.raylib import RaylibRenderer

        self.pyray = pyray
        self.width = width
        self.height = height

        log_warning = getattr(pyray, "LOG_WARNING", 3)
        win_hidden = getattr(pyray, "FLAG_WINDOW_HIDDEN", 128)
        pyray.set_trace_log_level(log_warning)
        pyray.set_config_flags(win_hidden)
        pyray.init_window(width, height, "eager_benchmark_raylib")
        pyray.set_target_fps(0)  # Uncapped / unbounded FPS

        self.renderer = RaylibRenderer(
            width=width,
            height=height,
            asset_dir=asset_dir,
            scale_mode=ScaleMode.LETTERBOX,
        )

    def render_frame(
        self,
        comp: StageCompositor,
        overlay: UIOverlay | None,
        ui_state: UIState | None,
        choices: ChoicePromptEvent | None,
    ) -> None:
        self.pyray.begin_drawing()
        self.pyray.clear_background(self.pyray.BLACK)
        self.renderer.render_compositor(comp, self.width, self.height)
        if overlay is not None and ui_state is not None:
            overlay.draw(self.renderer, ui_state, choices, is_finished=False)
        self.pyray.end_drawing()

    def teardown(self) -> None:
        try:
            if hasattr(self.renderer, "asset_resolver"):
                self.renderer.asset_resolver.unload_all()
            self.pyray.close_window()
        except Exception:  # noqa: BLE001, S110
            pass


def get_backend_adapter(backend_name: str) -> BaseBackendAdapter:
    """Instantiate adapter for backend, raising ImportError if backend library is missing."""
    match backend_name.lower():
        case "null":
            return NullBackendAdapter()
        case "pil":
            try:
                import PIL  # noqa: F401
            except ImportError as exc:
                msg = f"PIL/Pillow backend is not available: {exc}"
                raise ImportError(msg) from exc
            return PILBackendAdapter()
        case "pyglet":
            try:
                import pyglet  # noqa: F401
            except ImportError as exc:
                msg = f"Pyglet backend is not available: {exc}"
                raise ImportError(msg) from exc
            return PygletBackendAdapter()
        case "raylib":
            try:
                import pyray  # noqa: F401
            except ImportError as exc:
                msg = f"Raylib backend is not available: {exc}"
                raise ImportError(msg) from exc
            return RaylibBackendAdapter()
        case _:
            msg = f"Unknown backend: {backend_name!r}. Available: null, pil, pyglet, raylib"
            raise ValueError(msg)


def check_backend_availability(backend_name: str) -> tuple[bool, str]:
    """Check if a backend can be imported and initialized without errors."""
    try:
        get_backend_adapter(backend_name)
        return True, "Available"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


ALL_BACKENDS = ["null", "pil", "pyglet", "raylib"]


# --------------------------------------------------------------------------- #
# Benchmark Execution Engine
# --------------------------------------------------------------------------- #


def run_single_benchmark(
    adapter: BaseBackendAdapter,
    scenario: BenchmarkScenario,
    *,
    frames: int = 5000,
    warmup: int = 50,
    width: int = 1280,
    height: int = 720,
    asset_dir: Path | None = None,
    stage_only: bool = False,
) -> BenchmarkMetrics:
    """Execute a single scenario benchmark against an adapter and return computed metrics."""
    adapter.initialize(width, height, asset_dir)
    try:
        comp, ui_state, choices, step_fn = scenario.create()
        overlay = None if stage_only else UIOverlay(width, height)

        # Warmup phase (not recorded)
        for w_idx in range(warmup):
            step_fn(w_idx, comp, ui_state)
            adapter.render_frame(comp, overlay, ui_state, choices)

        # Measurement phase: measure each frame's render time at unbounded FPS
        frame_times_ns: list[int] = []
        for f_idx in range(frames):
            step_fn(warmup + f_idx, comp, ui_state)

            t0 = time.perf_counter_ns()
            adapter.render_frame(comp, overlay, ui_state, choices)
            t1 = time.perf_counter_ns()

            frame_times_ns.append(max(1, t1 - t0))

        return BenchmarkMetrics.compute(adapter.name, scenario.name, frame_times_ns)
    finally:
        adapter.teardown()


# --------------------------------------------------------------------------- #
# Subprocess Worker Mode
# --------------------------------------------------------------------------- #


def _worker_main(argv: list[str]) -> int:
    """Worker entry point invoked in an isolated subprocess for a specific backend."""
    parser = argparse.ArgumentParser(description="Benchmark worker subprocess")
    parser.add_argument("--backend", required=True, choices=ALL_BACKENDS)
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--frames", type=int, default=5000)
    parser.add_argument("--warmup", type=int, default=50)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--stage-only", action="store_true")
    parser.add_argument("--asset-dir", type=str, default="")
    parser.add_argument("--output-json", type=str, default="")
    args = parser.parse_args(argv)

    scenario_names = args.scenarios or list(SCENARIOS)
    asset_dir = Path(args.asset_dir) if args.asset_dir else None

    # Verify adapter
    try:
        adapter = get_backend_adapter(args.backend)
    except Exception as exc:  # noqa: BLE001
        err_payload = {"error": f"Failed to initialize backend {args.backend}: {exc}"}
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(err_payload), encoding="utf-8")
        else:
            print(json.dumps(err_payload))
        return 1

    results: list[dict[str, Any]] = []
    for sc_name in scenario_names:
        sc = SCENARIOS[sc_name]
        metrics = run_single_benchmark(
            adapter,
            sc,
            frames=args.frames,
            warmup=args.warmup,
            width=args.width,
            height=args.height,
            asset_dir=asset_dir,
            stage_only=args.stage_only,
        )
        results.append(metrics.to_dict())

    out_text = json.dumps({"backend": args.backend, "results": results})
    if args.output_json:
        Path(args.output_json).write_text(out_text, encoding="utf-8")
    else:
        print(out_text)
    return 0


# --------------------------------------------------------------------------- #
# Orchestrator & CLI
# --------------------------------------------------------------------------- #


def run_backend_in_worker(
    backend: str,
    scenarios: list[str],
    *,
    frames: int,
    warmup: int,
    width: int,
    height: int,
    stage_only: bool,
    asset_dir: Path,
) -> tuple[list[BenchmarkMetrics], str | None]:
    """Run a backend benchmark inside an isolated subprocess and parse JSON results."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_out:
        tmp_json_path = Path(tmp_out.name)

    cmd = [
        sys.executable,
        str(_THIS_DIR / "render_benchmark.py"),
        "--worker",
        "--backend",
        backend,
        "--frames",
        str(frames),
        "--warmup",
        str(warmup),
        "--width",
        str(width),
        "--height",
        str(height),
        "--asset-dir",
        str(asset_dir),
        "--output-json",
        str(tmp_json_path),
    ]
    if stage_only:
        cmd.append("--stage-only")
    for sc in scenarios:
        cmd.extend(["--scenario", sc])

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=3600,
        )
        if proc.returncode != 0 or not tmp_json_path.exists():
            err_msg = (proc.stderr or proc.stdout or f"Process exited with code {proc.returncode}").strip()
            return [], err_msg

        data = json.loads(tmp_json_path.read_text(encoding="utf-8"))
        if "error" in data:
            return [], data["error"]

        metrics_list = [BenchmarkMetrics(**item) for item in data.get("results", [])]
        return metrics_list, None
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)
    finally:
        if tmp_json_path.exists():
            tmp_json_path.unlink()


def format_summary_table(results: list[BenchmarkMetrics]) -> str:
    """Format benchmark results as a clean ASCII comparative summary table."""
    headers = [
        ("Backend", 10, "<"),
        ("Scenario", 14, "<"),
        ("Frames", 8, ">"),
        ("Total(s)", 9, ">"),
        ("Avg FPS", 10, ">"),
        ("Max FPS", 10, ">"),
        ("1% Low", 10, ">"),
        ("0.1% Low", 10, ">"),
        ("Min FPS", 10, ">"),
        ("Mean(ms)", 9, ">"),
        ("P99(ms)", 9, ">"),
        ("Max(ms)", 9, ">"),
    ]

    header_line = " ".join(f"{h:{align}{w}}" for h, w, align in headers)
    separator = "-" * len(header_line)

    lines = [separator, header_line, separator]
    for r in results:
        cols = [
            f"{r.backend:<10}",
            f"{r.scenario:<14}",
            f"{r.total_frames:>8d}",
            f"{r.total_time_s:>9.2f}",
            f"{r.avg_fps:>10.1f}",
            f"{r.max_fps:>10.1f}",
            f"{r.fps_1pct_low:>10.1f}",
            f"{r.fps_01pct_low:>10.1f}",
            f"{r.min_fps:>10.1f}",
            f"{r.mean_frame_time_ms:>9.3f}",
            f"{r.p99_frame_time_ms:>9.3f}",
            f"{r.max_frame_time_ms:>9.3f}",
        ]
        lines.append(" ".join(cols))
    lines.append(separator)
    return "\n".join(lines)


def format_markdown_table(results: list[BenchmarkMetrics]) -> str:
    """Format benchmark results as a GitHub Flavored Markdown table."""
    headers = [
        "Backend",
        "Scenario",
        "Frames",
        "Total Time (s)",
        "Avg FPS",
        "Max FPS",
        "1% Low FPS",
        "0.1% Low FPS",
        "Min FPS",
        "Mean (ms)",
        "P99 (ms)",
        "Max (ms)",
    ]
    md_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---" if i < 2 else "---:" for i in range(len(headers))]) + " |",
    ]
    for r in results:
        row = [
            f"`{r.backend}`",
            f"`{r.scenario}`",
            f"{r.total_frames:,}",
            f"{r.total_time_s:.2f}",
            f"**{r.avg_fps:.1f}**",
            f"{r.max_fps:.1f}",
            f"**{r.fps_1pct_low:.1f}**",
            f"**{r.fps_01pct_low:.1f}**",
            f"{r.min_fps:.1f}",
            f"{r.mean_frame_time_ms:.3f}",
            f"{r.p99_frame_time_ms:.3f}",
            f"{r.max_frame_time_ms:.3f}",
        ]
        md_lines.append("| " + " | ".join(row) + " |")
    return "\n".join(md_lines)


def format_scenario_comparison(results: list[BenchmarkMetrics]) -> str:
    """Group results by scenario to easily compare all backends head-to-head."""
    by_scenario: dict[str, list[BenchmarkMetrics]] = {}
    for r in results:
        by_scenario.setdefault(r.scenario, []).append(r)

    lines: list[str] = []
    for sc_name, sc_results in by_scenario.items():
        desc = SCENARIOS.get(sc_name, None)
        desc_str = f" - {desc.description}" if desc else ""
        lines.append(f"\n### Scenario: {sc_name}{desc_str}")
        sub_table = format_summary_table(sc_results)
        lines.append(sub_table)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI orchestrator entry point."""
    if argv is None:
        argv = sys.argv[1:]

    # Handle internal worker dispatch
    if "--worker" in argv:
        worker_args = [a for a in argv if a != "--worker"]
        return _worker_main(worker_args)

    parser = argparse.ArgumentParser(
        description="Benchmark unbounded FPS throughput and frame-time stability across render backends.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-b",
        "--backend",
        action="append",
        choices=[*ALL_BACKENDS, "all"],
        help="Backend(s) to benchmark (default: all available backends)",
    )
    parser.add_argument(
        "-s",
        "--scenario",
        action="append",
        choices=[*sorted(SCENARIOS), "all"],
        help="Scenario(s) to run (default: all scenarios)",
    )
    parser.add_argument(
        "-n",
        "--frames",
        type=int,
        default=5000,
        help="Number of frames to render and record per scenario (default: 5000)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=50,
        help="Number of warmup frames before measuring (default: 50)",
    )
    parser.add_argument(
        "--size",
        default="1280x720",
        help="Window dimensions WxH (default: 1280x720)",
    )
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Benchmark only the stage compositor (skip UI overlay drawing primitives)",
    )
    parser.add_argument(
        "--json-file",
        type=str,
        default="",
        help="Export raw results to a JSON file",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Print results formatted as GitHub Flavored Markdown",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Run directly in process instead of worker subprocess (only safe for single backend)",
    )
    args = parser.parse_args(argv)

    # Resolution parsing
    try:
        w_str, h_str = args.size.lower().split("x")
        width, height = int(w_str), int(h_str)
    except (ValueError, AttributeError):
        print(f"Invalid size format: {args.size!r}. Expected e.g. 1280x720", file=sys.stderr)
        return 1

    # Backends selection
    if not args.backend or "all" in args.backend:
        backends = list(ALL_BACKENDS)
    else:
        # Preserve order while removing duplicates
        backends = list(dict.fromkeys(args.backend))

    # Scenarios selection
    if not args.scenario or "all" in args.scenario:
        scenario_names = list(SCENARIOS)
    else:
        scenario_names = list(dict.fromkeys(args.scenario))

    print("=" * 80)
    print("Eager-Graphics Render Backend Benchmark Suite")
    print(f"Target: {args.frames:,} frames at unbounded FPS (Warmup: {args.warmup} frames)")
    print(f"Display Size: {width}x{height} | Mode: {'Stage-Only' if args.stage_only else 'Full VN (Stage + UI)'}")
    print(f"Backends to evaluate: {', '.join(backends)}")
    print(f"Scenarios: {', '.join(scenario_names)}")
    print("=" * 80)

    # Asset generation in temporary directory
    with tempfile.TemporaryDirectory() as tmp_asset_dir:
        asset_path = Path(tmp_asset_dir)
        print("Generating realistic 1080p backgrounds and RGBA character sprites...")
        make_benchmark_assets(asset_path)
        print("Assets ready.\n")

        all_results: list[BenchmarkMetrics] = []
        skipped_backends: list[tuple[str, str]] = []

        for b_name in backends:
            # Check availability
            avail, reason = check_backend_availability(b_name)
            if not avail:
                print(f"[SKIP] Backend '{b_name}' is not available: {reason}")
                skipped_backends.append((b_name, reason))
                continue

            print(f"--> Running backend: {b_name.upper()} ({len(scenario_names)} scenarios, {args.frames:,} frames each)...")

            if args.direct and len(backends) == 1:
                # Direct in-process execution (for single-backend profiling)
                adapter = get_backend_adapter(b_name)
                for sc_name in scenario_names:
                    sc = SCENARIOS[sc_name]
                    print(f"    Running scenario: {sc_name}...", end="", flush=True)
                    m = run_single_benchmark(
                        adapter,
                        sc,
                        frames=args.frames,
                        warmup=args.warmup,
                        width=width,
                        height=height,
                        asset_dir=asset_path,
                        stage_only=args.stage_only,
                    )
                    all_results.append(m)
                    print(f" done! (Avg FPS: {m.avg_fps:.1f}, 1% Low: {m.fps_1pct_low:.1f})")
            else:
                # Subprocess worker execution (safely isolates OpenGL/EGL contexts)
                metrics_list, err = run_backend_in_worker(
                    b_name,
                    scenario_names,
                    frames=args.frames,
                    warmup=args.warmup,
                    width=width,
                    height=height,
                    stage_only=args.stage_only,
                    asset_dir=asset_path,
                )
                if err or not metrics_list:
                    print(f"    [ERROR] Backend {b_name} failed: {err}")
                    skipped_backends.append((b_name, err or "Unknown execution error"))
                else:
                    for m in metrics_list:
                        print(f"    Scenario '{m.scenario}': Avg FPS = {m.avg_fps:>8.1f} | 1% Low = {m.fps_1pct_low:>8.1f} | 0.1% Low = {m.fps_01pct_low:>8.1f}")
                    all_results.extend(metrics_list)

        print("\n" + "=" * 80)
        print("BENCHMARK RESULTS")
        print("=" * 80)

        if all_results:
            if args.markdown:
                print("\n## Comparative Summary\n")
                print(format_markdown_table(all_results))
            else:
                print("\nOVERALL COMPARATIVE TABLE:")
                print(format_summary_table(all_results))
                print(format_scenario_comparison(all_results))

            # Export JSON if requested
            if args.json_file:
                out_path = Path(args.json_file)
                export_data = {
                    "config": {
                        "frames": args.frames,
                        "warmup": args.warmup,
                        "width": width,
                        "height": height,
                        "stage_only": args.stage_only,
                    },
                    "results": [r.to_dict() for r in all_results],
                    "skipped": [{"backend": b, "reason": r} for b, r in skipped_backends],
                }
                out_path.write_text(json.dumps(export_data, indent=2), encoding="utf-8")
                print(f"\nJSON results successfully exported to: {out_path.resolve()}")

        if skipped_backends:
            print("\nSkipped / Failed Backends:")
            for b, r in skipped_backends:
                print(f"  - {b}: {r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
