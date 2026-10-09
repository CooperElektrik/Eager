"""Tests for geometry, color, and coordinate types."""

import pytest

from eager_graphics.types import (
    BLACK,
    RED,
    TRANSPARENT,
    WHITE,
    Anchor,
    Color,
    Rect,
    TransitionKind,
    Vec2,
)


def test_vec2_arithmetic() -> None:
    v1 = Vec2(10.0, 20.0)
    v2 = Vec2(5.0, 2.0)

    # Addition
    assert (v1 + v2) == Vec2(15.0, 22.0)
    assert (v1 + (2.0, 3.0)) == Vec2(12.0, 23.0)

    # Subtraction
    assert (v1 - v2) == Vec2(5.0, 18.0)
    assert (v1 - (5.0, 10.0)) == Vec2(5.0, 10.0)

    # Multiplication & Division
    assert (v1 * 2) == Vec2(20.0, 40.0)
    assert (2 * v1) == Vec2(20.0, 40.0)
    assert (v1 / 2) == Vec2(5.0, 10.0)
    assert (-v1) == Vec2(-10.0, -20.0)


def test_vec2_lerp_and_distance() -> None:
    v1 = Vec2(0.0, 0.0)
    v2 = Vec2(100.0, 200.0)

    assert v1.lerp(v2, 0.5) == Vec2(50.0, 100.0)
    assert v1.lerp(v2, 0.0) == v1
    assert v1.lerp(v2, 1.0) == v2
    assert v1.distance_to(Vec2(3.0, 4.0)) == pytest.approx(5.0)


def test_vec2_serialization() -> None:
    v = Vec2(123.5, 456.7)
    d = v.to_dict()
    assert d == {"x": 123.5, "y": 456.7}
    v_restored = Vec2.from_dict(d)
    assert v_restored == v

    # from_value
    assert Vec2.from_value((10, 20)) == Vec2(10.0, 20.0)
    assert Vec2.from_value([30, 40]) == Vec2(30.0, 40.0)
    assert Vec2.from_value(5) == Vec2(5.0, 5.0)
    assert Vec2.from_value(v) == v


def test_color_parsing_and_clamping() -> None:
    c = Color(1.5, -0.2, 0.5, 2.0)
    assert c.r == 1.0
    assert c.g == 0.0
    assert c.b == 0.5
    assert c.a == 1.0

    # Hex parsing
    c1 = Color.from_hex("#ffffff")
    assert c1 == WHITE
    c2 = Color.from_hex("#000000")
    assert c2 == BLACK
    c3 = Color.from_hex("#f00")
    assert c3.r == pytest.approx(1.0)
    assert c3.g == pytest.approx(0.0)
    assert c3.b == pytest.approx(0.0)

    # With alpha
    c4 = Color.from_hex("#ff000080")
    assert c4.r == pytest.approx(1.0)
    assert c4.a == pytest.approx(0.50196, rel=1e-3)

    # Named
    assert Color.from_hex("red") == RED
    assert Color.from_hex("transparent") == TRANSPARENT

    with pytest.raises(ValueError):
        Color.from_hex("invalid_color_123")


def test_color_lerp_and_bytes() -> None:
    c1 = Color(0.0, 0.0, 0.0, 1.0)
    c2 = Color(1.0, 1.0, 1.0, 1.0)
    mid = c1.lerp(c2, 0.5)
    assert mid.r == pytest.approx(0.5)
    assert mid.to_rgba_bytes() == (128, 128, 128, 255)
    assert mid.to_hex() == "#808080"


def test_rect_bounds_and_intersection() -> None:
    r1 = Rect(10.0, 20.0, 100.0, 50.0)
    assert r1.left == 10.0
    assert r1.top == 20.0
    assert r1.right == 110.0
    assert r1.bottom == 70.0
    assert r1.center == Vec2(60.0, 45.0)

    assert r1.contains(Vec2(50.0, 30.0))
    assert not r1.contains(Vec2(5.0, 30.0))

    r2 = Rect(50.0, 30.0, 100.0, 100.0)
    assert r1.intersects(r2)

    r3 = Rect(200.0, 200.0, 50.0, 50.0)
    assert not r1.intersects(r3)


def test_anchor_offsets_and_parsing() -> None:
    assert Anchor.TOP_LEFT.get_offset_factor() == (0.0, 0.0)
    assert Anchor.CENTER.get_offset_factor() == (0.5, 0.5)
    assert Anchor.BOTTOM_CENTER.get_offset_factor() == (0.5, 1.0)

    assert Anchor.from_str("bottom_center") == Anchor.BOTTOM_CENTER
    assert Anchor.from_str("top") == Anchor.TOP_CENTER
    assert Anchor.from_str("left") == Anchor.CENTER_LEFT
    assert Anchor.from_str("middle") == Anchor.CENTER


def test_transition_kind_parsing() -> None:
    assert TransitionKind.from_str("crossfade") == TransitionKind.CROSSFADE
    assert TransitionKind.from_str("fade") == TransitionKind.FADE
    assert TransitionKind.from_str("slide-left") == TransitionKind.SLIDE_LEFT
    assert TransitionKind.from_str("unknown_xyz") == TransitionKind.CUT
