"""Reusable frame-time benchmark harness for the PIL renderer.

Runs a set of realistic visual-novel scenarios (static idle, character fades,
background crossfades, screen fades, flashes, shake, zoom, rotation, UI
overlay, frame presentation) and reports per-frame timings.

Usage::

    python benchmarks/pil_benchmark.py                      # current renderer
    python benchmarks/pil_benchmark.py --module old_pil.py  # A/B a snapshot
    python benchmarks/pil_benchmark.py -s char_fade -s ui_overlay -n 240

Assets are generated on the fly (opaque JPEG backgrounds and transparent PNG
character sprites) so the numbers reflect real alpha-channel workloads rather
than the opaque procedural placeholders.
"""

from __future__ import annotations

import argparse
import importlib.util
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from PIL import Image, ImageDraw

from eager_graphics import Color, ScaleMode, StageCompositor
from eager_graphics.ui_components import UIOverlay
from eager_graphics.ui_state import UIState

Scenario = Callable[[ModuleType, Path, int, int, int], list[float]]


# --------------------------------------------------------------------------- #
# Asset generation
# --------------------------------------------------------------------------- #


def make_assets(root: Path) -> Path:
    """Create realistic assets: 1920x1080 opaque backgrounds, 600x1200 RGBA sprites."""
    (root / "bg").mkdir(parents=True, exist_ok=True)
    for i, name in enumerate(("bg1", "bg2")):
        img = Image.linear_gradient("L").resize((1920, 1080)).convert("RGB")
        img = Image.merge("RGB", (img.getchannel(0), img.getchannel(0).point(lambda p, i=i: (p + 80 * i) % 256), img.getchannel(0)))
        img.save(root / "bg" / f"{name}.jpg", quality=90)
    for name in ("alice", "bob"):
        (root / name).mkdir(exist_ok=True)
        spr = Image.new("RGBA", (600, 1200), (0, 0, 0, 0))
        d = ImageDraw.Draw(spr)
        d.ellipse((50, 0, 550, 500), fill=(240, 200, 180, 255))
        d.rectangle((100, 450, 500, 1200), fill=(60, 90, 160, 255))
        d.ellipse((40, 440, 560, 560), fill=(60, 90, 160, 180))  # soft semi-alpha edge
        spr.save(root / name / "default.png")
    return root


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _base_compositor() -> StageCompositor:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", transition="cut", duration=0.0)
    comp.show_character("alice", position="left", transition="cut", duration=0.0)
    comp.show_character("bob", position="right", transition="cut", duration=0.0)
    return comp


def _new_renderer(mod: ModuleType, assets: Path, w: int, h: int):
    return mod.PILRenderer(w, h, asset_dir=assets, scale_mode=ScaleMode.LETTERBOX)


def _time_frames(n: int, frame: Callable[[int], None]) -> list[float]:
    out: list[float] = []
    for i in range(n):
        t0 = time.perf_counter()
        frame(i)
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


# --------------------------------------------------------------------------- #
# Scenarios
# --------------------------------------------------------------------------- #


def sc_static(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    return _time_frames(n, lambda i: r.render_compositor(comp, w, h))


def sc_char_fade(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    comp.hide_character("bob", duration=0.0)
    comp.show_character("bob", position="right", transition="fade", duration=n / 60.0 + 1)

    def frame(i):
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def sc_bg_crossfade(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    comp.set_background("bg/bg2", transition="crossfade", duration=n / 60.0 + 1)

    def frame(i):
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def sc_bg_crossfade_only(mod, assets, w, h, n):
    """Crossfade with no characters (hits the dual-background blend fast path)."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", transition="cut", duration=0.0)
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    comp.set_background("bg/bg2", transition="crossfade", duration=n / 60.0 + 1)

    def frame(i):
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def sc_screen_fade(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    comp.fade_out(duration=n / 60.0 + 1)

    def frame(i):
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def sc_flash_loop(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)

    def frame(i):
        if i % 20 == 0:
            comp.flash(duration=0.3, color=Color(1.0, 0.9, 0.9, 1.0))
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def sc_shake(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    comp.shake(intensity=8.0, duration=n / 60.0 + 1)

    def frame(i):
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def _char_state(comp, cid):
    return comp.stage.get_layer("characters").get_element(cid).state


def sc_char_zoom(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    st = _char_state(comp, "alice")
    from eager_core.types import Vec2

    def frame(i):
        s = 1.0 + 0.002 * (i + 1)
        st.scale = Vec2(s, s)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def sc_char_rotate(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    st = _char_state(comp, "alice")

    def frame(i):
        st.rotation = (i * 1.5 + 0.7) % 360.0
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def sc_char_slide(mod, assets, w, h, n):
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    comp.move_character("alice", "right", duration=n / 60.0 + 1)

    def frame(i):
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)

    return _time_frames(n, frame)


def _ui_state() -> UIState:
    return UIState(
        speaker="Alice",
        text=(
            "The rain had not stopped for three days, and the tavern was fuller "
            "than it had any right to be. Every table creaked under elbows and "
            "tankards, and the fire spat sparks whenever the door swung open."
        ),
    )


def sc_ui_overlay_animating(mod, assets, w, h, n):
    """Stage animates (char slide) while a dialogue box is redrawn every frame."""
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    overlay = UIOverlay(width=w, height=h)
    ui = _ui_state()
    r.render_compositor(comp, w, h)
    comp.move_character("alice", "right", duration=n / 60.0 + 1)

    def frame(i):
        comp.step(1 / 60)
        r.render_compositor(comp, w, h)
        overlay.draw(r, ui, None, is_finished=False)

    return _time_frames(n, frame)


def sc_ui_overlay_static(mod, assets, w, h, n):
    """Static stage, UI redrawn every frame (e.g. text reveal / hover)."""
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    overlay = UIOverlay(width=w, height=h)
    ui = _ui_state()
    r.render_compositor(comp, w, h)

    def frame(i):
        r.render_compositor(comp, w, h)
        overlay.draw(r, ui, None, is_finished=False)

    return _time_frames(n, frame)


def sc_present(mod, assets, w, h, n):
    """Cost of producing GL-ready bytes for a frame (no GL context needed)."""
    comp = _base_compositor()
    r = _new_renderer(mod, assets, w, h)
    r.render_compositor(comp, w, h)
    present = getattr(r, "_frame_bytes_bottom_up", None)
    if present is not None:
        return _time_frames(n, lambda i: present())

    try:
        import pyglet  # noqa: F401
        from pyglet.image import ImageData
    except ImportError:
        return []

    def frame(i):
        raw = r.image.tobytes()
        data = ImageData(w, h, "RGBA", raw, pitch=-w * 4)
        data._convert("RGBA", w * 4)  # what blit_to_texture does internally

    return _time_frames(n, frame)


SCENARIOS: dict[str, Scenario] = {
    "static": sc_static,
    "char_fade": sc_char_fade,
    "char_slide": sc_char_slide,
    "bg_crossfade": sc_bg_crossfade,
    "bg_crossfade_only": sc_bg_crossfade_only,
    "screen_fade": sc_screen_fade,
    "flash_loop": sc_flash_loop,
    "shake": sc_shake,
    "char_zoom": sc_char_zoom,
    "char_rotate": sc_char_rotate,
    "ui_overlay_static": sc_ui_overlay_static,
    "ui_overlay_animating": sc_ui_overlay_animating,
    "present": sc_present,
}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def load_module(path: str | None) -> ModuleType:
    if path is None:
        from eager_graphics.renderers import pil

        return pil
    spec = importlib.util.spec_from_file_location("pil_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pil_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--module", help="Path to an alternative pil.py to benchmark")
    ap.add_argument("-s", "--scenario", action="append", choices=sorted(SCENARIOS))
    ap.add_argument("-n", "--frames", type=int, default=120)
    ap.add_argument("--size", default="1280x720", help="Window size WxH")
    ap.add_argument("-r", "--repeat", type=int, default=3, help="Take best mean of N runs")
    args = ap.parse_args(argv)

    w, h = (int(v) for v in args.size.lower().split("x"))
    mod = load_module(args.module)
    names = args.scenario or list(SCENARIOS)

    with tempfile.TemporaryDirectory() as tmp:
        assets = make_assets(Path(tmp))
        print(f"{'scenario':<22} {'mean ms':>9} {'p50':>8} {'p95':>8} {'max':>8}")
        for name in names:
            best: list[float] | None = None
            for _ in range(args.repeat):
                t = SCENARIOS[name](mod, assets, w, h, args.frames)
                if not t:
                    break
                if best is None or statistics.fmean(t) < statistics.fmean(best):
                    best = t
            if not best:
                print(f"{name:<22} {'n/a':>9}")
                continue
            s = sorted(best)
            p = lambda q, s=s: s[min(len(s) - 1, int(q * len(s)))]
            print(f"{name:<22} {statistics.fmean(s):9.3f} {p(0.5):8.3f} {p(0.95):8.3f} {s[-1]:8.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
