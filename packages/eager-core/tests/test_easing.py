import pytest

from eager_core.easing import (
    EASING_MAP,
    ease_in_cubic,
    ease_in_out_quad,
    ease_in_quad,
    ease_out_cubic,
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


def test_easing_boundaries() -> None:
    # All easing functions should evaluate to 0 at t=0 and 1 at t=1
    for name, func in EASING_MAP.items():
        val_0 = func(0.0)
        val_1 = func(1.0)
        assert val_0 == pytest.approx(0.0, abs=1e-5), f"{name}(0.0) should be 0.0, got {val_0}"
        assert val_1 == pytest.approx(1.0, abs=1e-5), f"{name}(1.0) should be 1.0, got {val_1}"


def test_easing_monotonic_progress() -> None:
    # Quad, cubic, sine should increase monotonically
    for func in [ease_in_quad, ease_out_quad, ease_in_out_quad, ease_in_cubic, ease_out_cubic]:
        prev = -1.0
        for step in range(11):
            t = step / 10.0
            val = func(t)
            assert val >= prev - 1e-6
            prev = val

