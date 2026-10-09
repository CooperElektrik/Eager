import pytest

from eager_core.easing import (
    ease_in_cubic,
    ease_in_quad,
    ease_out_quad,
    get_easing,
    linear,
)


def test_linear():
    assert linear(0.0) == 0.0
    assert linear(0.5) == 0.5
    assert linear(1.0) == 1.0


def test_quad_and_cubic():
    assert ease_in_quad(0.0) == 0.0
    assert ease_in_quad(1.0) == 1.0
    assert ease_in_quad(0.5) == 0.25

    assert ease_out_quad(0.0) == 0.0
    assert ease_out_quad(1.0) == 1.0
    assert ease_out_quad(0.5) == 0.75

    assert ease_in_cubic(0.5) == 0.125


def test_get_easing():
    assert get_easing(None) == linear
    assert get_easing("linear") == linear
    assert get_easing("ease-in-quad") == ease_in_quad
    assert get_easing(linear) == linear

    with pytest.raises(ValueError):
        get_easing("unknown_easing")
