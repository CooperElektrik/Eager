"""Tests for overlay rendering, transitions, and built-in procedural assets."""

from __future__ import annotations

import pytest

from eager_graphics import Anchor, ScaleMode, StageCompositor
from eager_graphics.renderers.pil import PIL_AVAILABLE, PILAssetResolver, PILRenderer
from eager_graphics.types import BLACK, WHITE

try:
    import pyglet

    from eager_graphics.renderers.pyglet import PygletAssetResolver

    PYGLET_AVAILABLE = True
except ImportError:
    PYGLET_AVAILABLE = False


def test_pil_builtin_color_rect_is_1x1_white() -> None:
    """PILAssetResolver should return a 1x1 RGBA Image with (255, 255, 255, 255)."""
    assert PIL_AVAILABLE, "Pillow is required for this test"
    resolver = PILAssetResolver(asset_dir=None)
    img = resolver.get_image("__builtin_color_rect__")

    assert img.size == (1, 1)
    assert img.mode == "RGBA"
    assert img.getpixel((0, 0)) == (255, 255, 255, 255)
    assert resolver.is_asset_opaque("__builtin_color_rect__") is True

    # Cache check
    assert resolver.get_image("__builtin_color_rect__") is img


def test_pyglet_builtin_color_rect_is_1x1_white() -> None:
    """PygletAssetResolver should return a 1x1 RGBA ImageData with white bytes."""
    if not PYGLET_AVAILABLE:
        pytest.skip("Pyglet is not available")

    resolver = PygletAssetResolver(asset_dir=None)
    tex = resolver.get_texture("__builtin_color_rect__")

    assert tex.width == 1
    assert tex.height == 1
    assert isinstance(tex, pyglet.image.ImageData)
    assert tex.format == "RGBA"

    data = tex.get_data("RGBA", 4)
    assert bytes(data) == bytes([255, 255, 255, 255])

    # Cache check
    assert resolver.get_texture("__builtin_color_rect__") is tex


def test_pil_flash_renders_white_not_pastel() -> None:
    """PILRenderer should render a default flash as pure white, not a tinted pastel."""
    assert PIL_AVAILABLE, "Pillow is required for this test"
    comp = StageCompositor(1920, 1080)
    # Background is black
    comp.clear_color = BLACK
    # Flash is default white
    comp.flash(duration=0.5, color=WHITE)

    renderer = PILRenderer(1920, 1080, scale_mode=ScaleMode.STRETCH)
    rendered_img = renderer.render_compositor(comp, 1920, 1080)

    # Check center and corners of the rendered frame
    coords = [(0, 0), (960, 540), (1919, 1079), (100, 100)]
    for coord in coords:
        pixel = rendered_img.getpixel(coord)
        assert pixel[:3] == (255, 255, 255), f"Expected white at {coord}, got {pixel}"


def test_pil_fade_out_does_not_hang() -> None:
    """fade_out animation should complete and not cause headless loop to hang."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/room", transition="cut")
    comp.fade_out(duration=0.3, color=BLACK)

    # Advance loop until tween completes
    steps = comp.run_headless(
        dt=0.1,
        max_steps=50,
        until=lambda: not comp.timeline.has_tweens(),
    )
    assert steps <= 5, f"Expected fade_out to finish within 5 steps at dt=0.1, took {steps}"
    assert not comp.timeline.has_tweens()

    # PILRenderer should render the full black overlay
    if PIL_AVAILABLE:
        renderer = PILRenderer(1920, 1080, scale_mode=ScaleMode.STRETCH)
        rendered_img = renderer.render_compositor(comp, 1920, 1080)
        assert rendered_img.getpixel((960, 540))[:3] == (0, 0, 0)


def test_overlay_scale_produces_stage_sized_coverage() -> None:
    """1x1 color rect scaled by stage dimensions produces full stage coverage."""
    comp = StageCompositor(1920, 1080)
    comp.flash(duration=1.0)

    items = comp.render_list()
    assert len(items) == 1
    item = items[0]
    assert item.asset_id == "__builtin_color_rect__"
    assert item.scale_x == 1920.0
    assert item.scale_y == 1080.0
    assert item.anchor == Anchor.TOP_LEFT
    assert item.x == 0.0
    assert item.y == 0.0

    if PIL_AVAILABLE:
        resolver = PILAssetResolver()
        base_tex = resolver.get_image(item.asset_id)
        assert base_tex.width == 1
        assert base_tex.height == 1

        # Effective virtual dimensions
        eff_w = base_tex.width * abs(item.scale_x)
        eff_h = base_tex.height * abs(item.scale_y)
        assert eff_w == 1920.0
        assert eff_h == 1080.0
