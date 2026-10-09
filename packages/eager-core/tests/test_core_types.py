import pytest

from eager_core.types import (
    BLACK,
    WHITE,
    Color,
    Rect,
    Vec2,
)


def test_vec2_math():
    v1 = Vec2(10.0, 20.0)
    v2 = Vec2(5.0, -10.0)

    assert v1 + v2 == Vec2(15.0, 10.0)
    assert v1 - v2 == Vec2(5.0, 30.0)
    assert v1 * 2.0 == Vec2(20.0, 40.0)
    assert 2.0 * v1 == Vec2(20.0, 40.0)
    assert v1 / 2.0 == Vec2(5.0, 10.0)
    assert -v1 == Vec2(-10.0, -20.0)

    assert v1.to_tuple() == (10.0, 20.0)
    assert v1.to_dict() == {"x": 10.0, "y": 20.0}
    assert Vec2.from_dict({"x": 1.0, "y": 2.0}) == Vec2(1.0, 2.0)
    assert Vec2.from_value((3.0, 4.0)) == Vec2(3.0, 4.0)
    assert Vec2.from_value(5.0) == Vec2(5.0, 5.0)


def test_vec2_lerp_and_distance():
    v1 = Vec2(0.0, 0.0)
    v2 = Vec2(10.0, 0.0)
    assert v1.lerp(v2, 0.5) == Vec2(5.0, 0.0)
    assert v1.distance_to(v2) == 10.0


def test_color_creation_and_clamping():
    c = Color(1.5, -0.5, 0.5, 2.0)
    assert c.r == 1.0
    assert c.g == 0.0
    assert c.b == 0.5
    assert c.a == 1.0


def test_color_hex_parsing():
    assert Color.from_hex("#ff0000") == Color(1.0, 0.0, 0.0, 1.0)
    assert Color.from_hex("#00ff0080").a == pytest.approx(128 / 255.0, rel=1e-2)
    assert Color.from_hex("#fff") == Color(1.0, 1.0, 1.0, 1.0)
    assert Color.from_hex("black") == BLACK
    assert Color.from_hex("white") == WHITE


def test_color_lerp_and_hex():
    c1 = Color(0.0, 0.0, 0.0, 1.0)
    c2 = Color(1.0, 1.0, 1.0, 1.0)
    mid = c1.lerp(c2, 0.5)
    assert mid.r == pytest.approx(0.5)
    assert mid.g == pytest.approx(0.5)
    assert mid.b == pytest.approx(0.5)
    assert c1.to_hex() == "#000000"


def test_rect():
    r1 = Rect(10.0, 20.0, 100.0, 50.0)
    assert r1.left == 10.0
    assert r1.top == 20.0
    assert r1.right == 110.0
    assert r1.bottom == 70.0
    assert r1.center == Vec2(60.0, 45.0)

    assert r1.contains(Vec2(50.0, 30.0))
    assert not r1.contains(Vec2(5.0, 30.0))

    r2 = Rect(50.0, 40.0, 100.0, 50.0)
    assert r1.intersects(r2)
    r3 = Rect(200.0, 200.0, 10.0, 10.0)
    assert not r1.intersects(r3)
