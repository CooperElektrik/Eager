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


def test_vec2_arithmetic_safety():
    v = Vec2(10.0, 20.0)

    # Incompatible operands return NotImplemented / raise TypeError
    with pytest.raises(TypeError):
        _ = v + 5  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = v - "invalid"  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = v + (1.0,)  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = v + (1.0, 2.0, 3.0)  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = v + ("a", "b")  # type: ignore[operator]

    # Valid tuple arithmetic
    assert v + (5.0, 10.0) == Vec2(15.0, 30.0)
    assert (5.0, 10.0) + v == Vec2(15.0, 30.0)
    assert v - (5.0, 10.0) == Vec2(5.0, 10.0)
    assert (20.0, 30.0) - v == Vec2(10.0, 10.0)

    # Division by zero
    with pytest.raises(ZeroDivisionError, match="Cannot divide Vec2 by zero"):
        _ = v / 0
    with pytest.raises(ZeroDivisionError, match="Cannot divide Vec2 by zero"):
        _ = v / 0.0

    # Incompatible scalar multiplication / division
    with pytest.raises(TypeError):
        _ = v / "2"  # type: ignore[operator]
    with pytest.raises(TypeError):
        _ = v * "2"  # type: ignore[operator]


def test_vec2_from_dict_validation():
    with pytest.raises(TypeError, match="expects a Mapping"):
        Vec2.from_dict(None)  # type: ignore[arg-type]

    with pytest.raises(KeyError, match="requires 'x' and 'y' keys"):
        Vec2.from_dict({"x": 1.0})

    with pytest.raises(KeyError, match="requires 'x' and 'y' keys"):
        Vec2.from_dict({})

    with pytest.raises(TypeError, match="coordinates must be numbers"):
        Vec2.from_dict({"x": None, "y": 10.0})

    with pytest.raises(ValueError, match="could not be converted to float"):
        Vec2.from_dict({"x": "not_a_num", "y": "2.0"})

    v = Vec2.from_dict({"x": "12.5", "y": "-3.25"})
    assert v.x == 12.5
    assert v.y == -3.25


def test_color_from_dict_validation():
    with pytest.raises(TypeError, match="expects a Mapping"):
        Color.from_dict(None)  # type: ignore[arg-type]

    with pytest.raises(KeyError, match="missing required keys"):
        Color.from_dict({"r": 1.0, "g": 1.0})

    with pytest.raises(TypeError, match="channels must be numbers"):
        Color.from_dict({"r": None, "g": 0.5, "b": 0.5})

    from eager_core.exceptions import ColorParseError

    with pytest.raises(ColorParseError, match="could not be converted to float"):
        Color.from_dict({"r": "invalid", "g": 0.5, "b": 0.5})

    c1 = Color.from_dict({"r": 0.2, "g": 0.4, "b": 0.6})
    assert c1.a == 1.0
    c2 = Color.from_dict({"r": "0.1", "g": "0.2", "b": "0.3", "a": "0.8"})
    assert c2.r == pytest.approx(0.1)
    assert c2.a == pytest.approx(0.8)


def test_color_hex_boundaries():
    from eager_core.exceptions import ColorParseError

    for invalid in ["", "#", "#1", "#12", "#12345", "#1234567", "#123456789", "#xyz", "###fff"]:
        with pytest.raises(ColorParseError):
            Color.from_hex(invalid)

    # 4-character hex #rgba
    c = Color.from_hex("#f008")
    assert c.r == pytest.approx(1.0)
    assert c.g == pytest.approx(0.0)
    assert c.b == pytest.approx(0.0)
    assert c.a == pytest.approx(0.5333, rel=1e-2)


def test_color_advanced_features():
    c = Color(0.2, 0.4, 0.6, 0.8)
    assert c.with_alpha(0.5).a == 0.5
    assert c.to_rgba_bytes() == (51, 102, 153, 204)
    assert Color.from_bytes(51, 102, 153, 204).to_rgba_bytes() == (51, 102, 153, 204)
    assert Color.from_hex("#12345678").to_hex(include_alpha=True) == "#12345678"
