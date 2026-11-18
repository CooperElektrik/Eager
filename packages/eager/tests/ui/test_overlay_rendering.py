"""Tests for overlay rendering, transitions, and built-in procedural assets."""

from __future__ import annotations

from typing import Any

import pytest

from eager.core.types import WHITE, Anchor
from eager.stage import StageCompositor


def test_pyglet_builtin_color_rect_is_1x1_white() -> None:
    """PygletAssetResolver should return a 1x1 RGBA ImageData with white bytes."""
    pytest.importorskip("pyglet")
    from eager.backends.renderers.pyglet import PygletAssetResolver

    resolver = PygletAssetResolver(asset_dir=None)
    tex = resolver.get_texture("__builtin_color_rect__")

    assert tex.width == 1
    assert tex.height == 1
    image_data: Any = tex
    assert image_data.format == "RGBA"

    data = image_data.get_data("RGBA", 4)
    assert bytes(data) == bytes([255, 255, 255, 255])

    # Cache check
    assert resolver.get_texture("__builtin_color_rect__") is tex


def test_fade_in_with_custom_color() -> None:
    """fade_in should support custom colors (e.g. white fade-in from flash)."""
    comp = StageCompositor(1920, 1080)
    comp.fade_in(duration=0.4, color=WHITE)

    items = comp.render_list()
    assert len(items) == 1
    assert items[0].asset_id == "__builtin_color_rect__"
    assert items[0].tint == WHITE
    assert items[0].opacity == pytest.approx(1.0)

    comp.update(0.2)
    items_mid = comp.render_list()
    assert len(items_mid) == 1
    assert items_mid[0].opacity == pytest.approx(0.5)

    comp.update(0.2)
    assert len(comp.render_list()) == 0


def test_director_fade_in_hook_parses_color() -> None:
    """StageDirector.handle_fade_in parses optional duration and color arguments."""
    from eager.stage.director import StageDirector

    director = StageDirector(StageCompositor(1920, 1080))
    director.handle_fade_in("duration=0.5 color=#ff0000")

    items = director.compositor.render_list()
    assert len(items) == 1
    assert items[0].asset_id == "__builtin_color_rect__"
    assert items[0].tint.r == pytest.approx(1.0)
    assert items[0].tint.g == pytest.approx(0.0)
    assert items[0].tint.b == pytest.approx(0.0)


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
