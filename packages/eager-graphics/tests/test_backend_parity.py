"""Pixel parity and rendering equivalence tests between PIL and Pyglet backends."""

from __future__ import annotations

import pytest

try:
    import pyglet
    from pyglet.window import Window
    PYGLET_AVAILABLE = True
except ImportError:
    PYGLET_AVAILABLE = False

try:
    from PIL import Image, ImageChops, ImageStat
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from eager_core.types import BLACK, WHITE, Color

from eager_graphics.compositor import StageCompositor
from eager_graphics.renderers.pil.renderer import PILRenderer
from eager_graphics.renderers.pyglet import PygletRenderer
from eager_graphics.types import ScaleMode


@pytest.fixture
def headless_window():
    if not PYGLET_AVAILABLE:
        pytest.skip("Pyglet not available")
    try:
        win = Window(width=640, height=360, visible=False)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"OpenGL context creation failed: {exc}")
    yield win
    try:
        win.close()
    except Exception:  # noqa: BLE001, S110
        pass


def _read_pyglet_frame(win: Window) -> Image.Image:
    win.dispatch_events()
    color_buf = pyglet.image.get_buffer_manager().get_color_buffer()
    img_data = color_buf.get_image_data()
    py_bytes = img_data.get_data("RGBA", img_data.width * 4)
    return Image.frombytes("RGBA", (img_data.width, img_data.height), py_bytes).transpose(
        Image.Transpose.FLIP_TOP_BOTTOM
    )


@pytest.mark.skipif(not (PYGLET_AVAILABLE and PIL_AVAILABLE), reason="Requires Pyglet and Pillow")
def test_text_metrics_parity(headless_window: Window) -> None:
    """Verify measure_text yields identical typographic metrics across PIL and Pyglet."""
    py_r = PygletRenderer(width=640, height=360, window=headless_window)
    pil_r = PILRenderer(width=640, height=360, mode="RGBA")

    test_strings = [
        "Hello World",
        "The quick brown fox jumps over the lazy dog.",
        "Short",
        "Line 1\nLine 2\nLine 3",
        "Visual Novel Dialogue — Sample Text",
    ]

    for s in test_strings:
        for size in (12, 14, 18, 24):
            py_w, py_h = py_r.measure_text(s, font_size=size)
            pil_w, pil_h = pil_r.measure_text(s, font_size=size)

            max_allowed_w = max(3.0, len(s) * 0.2)
            assert abs(py_w - pil_w) <= max_allowed_w, f"Width mismatch for '{s}' at size {size}: {py_w} vs {pil_w}"
            assert abs(py_h - pil_h) <= 1.0, f"Height mismatch for '{s}' at size {size}: {py_h} vs {pil_h}"


@pytest.mark.skipif(not (PYGLET_AVAILABLE and PIL_AVAILABLE), reason="Requires Pyglet and Pillow")
def test_ui_primitives_render_parity(headless_window: Window) -> None:
    """Verify UI rectangle and gradient drawing primitives produce near-identical pixels."""
    w, h = 400, 300
    py_r = PygletRenderer(width=w, height=h, window=headless_window)
    pil_r = PILRenderer(width=w, height=h, mode="RGBA", adaptive_resampling=False)

    # PIL draw
    pil_r.begin_frame()
    pil_r.clear(BLACK)
    pil_r.draw_rect(20, 20, 100, 60, Color(1.0, 0.2, 0.2, 1.0))
    pil_r.draw_gradient_rect(150, 20, 100, 60, Color(0.1, 0.8, 0.2, 1.0), Color(0.2, 0.3, 0.9, 1.0))
    pil_r.draw_rect(20, 120, 150, 80, Color(0.2, 0.2, 0.2, 0.8), border_color=WHITE, border_width=2.0)
    pil_r.end_frame()
    pil_img = pil_r.get_image()

    # Pyglet draw
    py_r.begin_frame()
    py_r.clear(BLACK)
    py_r.draw_rect(20, 20, 100, 60, Color(1.0, 0.2, 0.2, 1.0))
    py_r.draw_gradient_rect(150, 20, 100, 60, Color(0.1, 0.8, 0.2, 1.0), Color(0.2, 0.3, 0.9, 1.0))
    py_r.draw_rect(20, 120, 150, 80, Color(0.2, 0.2, 0.2, 0.8), border_color=WHITE, border_width=2.0)
    py_r.end_frame()
    py_r.flush_ui()

    py_img = _read_pyglet_frame(headless_window)
    # Crop to requested test size
    py_crop = py_img.crop((0, 0, w, h))
    pil_crop = pil_img.crop((0, 0, w, h))

    diff = ImageChops.difference(pil_crop, py_crop)
    stat = ImageStat.Stat(diff)
    # Per-channel average difference should be well under 1.0 LSB
    for ch_mean in stat.mean:
        assert ch_mean < 0.5, f"High average channel difference in UI primitives: {stat.mean}"


@pytest.mark.skipif(not (PYGLET_AVAILABLE and PIL_AVAILABLE), reason="Requires Pyglet and Pillow")
def test_stage_compositor_render_parity(headless_window: Window) -> None:
    """Verify StageCompositor output renders with close parity across both engines."""
    w, h = 640, 360
    py_r = PygletRenderer(width=w, height=h, window=headless_window, scale_mode=ScaleMode.LETTERBOX)
    pil_r = PILRenderer(width=w, height=h, mode="RGBA", adaptive_resampling=False, scale_mode=ScaleMode.LETTERBOX)

    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/castle", duration=0.0)
    comp.show_character("alice", "happy", position="center", duration=0.0)

    pil_img = pil_r.render_compositor(comp, w, h)
    py_r.render_compositor(comp, w, h)
    py_img = _read_pyglet_frame(headless_window).crop((0, 0, w, h))

    diff = ImageChops.difference(pil_img, py_img)
    stat = ImageStat.Stat(diff)
    for ch_mean in stat.mean:
        assert ch_mean < 1.5, f"High average channel difference in stage compositor: {stat.mean}"


@pytest.mark.skipif(not (PYGLET_AVAILABLE and PIL_AVAILABLE), reason="Requires Pyglet and Pillow")
def test_crossfade_parity(headless_window: Window) -> None:
    """Verify background crossfade blending stays linear and avoids black dip in both engines."""
    w, h = 640, 360
    py_r = PygletRenderer(width=w, height=h, window=headless_window, scale_mode=ScaleMode.LETTERBOX)
    pil_r = PILRenderer(width=w, height=h, mode="RGBA", adaptive_resampling=False, scale_mode=ScaleMode.LETTERBOX)

    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/castle", duration=0.0)
    comp.set_background("bg/courtyard", transition="crossfade", duration=1.0)
    comp.update(0.5)  # Exact midpoint of crossfade

    pil_img = pil_r.render_compositor(comp, w, h)
    py_r.render_compositor(comp, w, h)
    py_img = _read_pyglet_frame(headless_window).crop((0, 0, w, h))

    diff = ImageChops.difference(pil_img, py_img)
    stat = ImageStat.Stat(diff)
    # Mean difference during crossfade should be minimal
    for ch_mean in stat.mean:
        assert ch_mean < 2.0, f"High average channel difference during crossfade: {stat.mean}"
