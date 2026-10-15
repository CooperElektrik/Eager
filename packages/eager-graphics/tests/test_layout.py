"""Tests for layout resolver and viewport transforms."""

import pytest
from eager_core.types import Vec2

from eager_graphics.layout import LayoutResolver
from eager_graphics.types import ScaleMode


def test_layout_resolve_named_positions() -> None:
    layout = LayoutResolver(virtual_width=1920, virtual_height=1080, ground_y=1000.0)

    # Center character
    p_center = layout.resolve_position("center")
    assert p_center == Vec2(960.0, 1000.0)

    # Left and Right
    p_left = layout.resolve_position("left")
    assert p_left == Vec2(480.0, 1000.0)
    p_right = layout.resolve_position("right")
    assert p_right == Vec2(1440.0, 1000.0)

    # Grid positions
    p_tl = layout.resolve_position("top_left")
    assert p_tl == Vec2(0.0, 0.0)
    p_br = layout.resolve_position("bottom_right")
    assert p_br == Vec2(1920.0, 1080.0)


def test_layout_custom_positions() -> None:
    layout = LayoutResolver(virtual_width=1000, virtual_height=500)
    layout.register_position("podium", Vec2(350.0, 400.0))
    assert layout.resolve_position("podium") == Vec2(350.0, 400.0)

    # Dynamic factory position
    layout.register_position("one_third", lambda w, h: Vec2(w / 3.0, h / 2.0))
    assert layout.resolve_position("one_third") == Vec2(1000.0 / 3.0, 250.0)


def test_layout_explicit_and_tuple_positions() -> None:
    layout = LayoutResolver()
    assert layout.resolve_position(Vec2(123.0, 456.0)) == Vec2(123.0, 456.0)
    assert layout.resolve_position((789.0, 101.0)) == Vec2(789.0, 101.0)
    assert layout.resolve_position("500, 600") == Vec2(500.0, 600.0)


def test_viewport_letterbox_transform() -> None:
    layout = LayoutResolver(virtual_width=1920, virtual_height=1080)
    # Target screen is wider: 2560x1080 (21:9) -> black bars on sides (letterbox/pillarbox)
    vp = layout.compute_viewport(2560, 1080, ScaleMode.LETTERBOX)
    assert vp.scale_x == pytest.approx(1.0)
    assert vp.scale_y == pytest.approx(1.0)
    assert vp.offset_x == pytest.approx((2560 - 1920) / 2.0)  # 320.0
    assert vp.offset_y == pytest.approx(0.0)

    # Coordinate mapping
    virtual_pt = Vec2(0.0, 0.0)
    screen_pt = vp.virtual_to_screen(virtual_pt)
    assert screen_pt.x == pytest.approx(320.0)
    assert screen_pt.y == pytest.approx(0.0)

    # Invert mapping
    restored = vp.screen_to_virtual(screen_pt)
    assert restored.x == pytest.approx(0.0)
    assert restored.y == pytest.approx(0.0)


def test_viewport_stretch_transform() -> None:
    layout = LayoutResolver(virtual_width=1920, virtual_height=1080)
    vp = layout.compute_viewport(960, 540, ScaleMode.STRETCH)
    assert vp.scale_x == pytest.approx(0.5)
    assert vp.scale_y == pytest.approx(0.5)
    assert vp.offset_x == 0.0
    assert vp.offset_y == 0.0
