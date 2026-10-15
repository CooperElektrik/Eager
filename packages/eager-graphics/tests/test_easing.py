"""Tests for easing functions."""

import pytest
from eager_core.easing import (
    EASING_MAP,
    ease_in_cubic,
    ease_in_out_quad,
    ease_in_quad,
    ease_out_bounce,
    ease_out_cubic,
    ease_out_quad,
    get_easing,
    linear,
)


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


def test_get_easing_lookup() -> None:
    assert get_easing("linear") is linear
    assert get_easing("ease-in-quad") is ease_in_quad
    assert get_easing("ease_out_bounce") is ease_out_bounce
    assert get_easing(linear) is linear
    assert get_easing(None) is linear

    with pytest.raises(ValueError):
        get_easing("unknown_nonexistent_easing")
