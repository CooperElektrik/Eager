"""Easing functions for smooth parameter interpolations and transitions."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import TypeAlias

__all__ = [
    "EASING_MAP",
    "EasingFunc",
    "ease_in_back",
    "ease_in_bounce",
    "ease_in_cubic",
    "ease_in_expo",
    "ease_in_out_back",
    "ease_in_out_bounce",
    "ease_in_out_cubic",
    "ease_in_out_expo",
    "ease_in_out_quad",
    "ease_in_out_quart",
    "ease_in_out_sine",
    "ease_in_quad",
    "ease_in_quart",
    "ease_in_sine",
    "ease_out_back",
    "ease_out_bounce",
    "ease_out_cubic",
    "ease_out_expo",
    "ease_out_quad",
    "ease_out_quart",
    "ease_out_sine",
    "get_easing",
    "linear",
]

logger = logging.getLogger(__name__)

EasingFunc: TypeAlias = Callable[[float], float]


def linear(t: float) -> float:
    """Linear progression interpolation function.

    Args:
        t: Progress factor in the range [0.0, 1.0].

    Returns:
        Unmodified progress value `t`.
    """
    return t


# Quadratic
def ease_in_quad(t: float) -> float:
    """Quadratic ease-in interpolation function.

    Accelerates from zero velocity following $t^2$.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return t * t


def ease_out_quad(t: float) -> float:
    """Quadratic ease-out interpolation function.

    Decelerates to zero velocity following $t \\times (2 - t)$.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return t * (2.0 - t)


def ease_in_out_quad(t: float) -> float:
    """Quadratic ease-in-out interpolation function.

    Accelerates then decelerates using quadratic curves.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    if t < 0.5:
        return 2.0 * t * t
    return -1.0 + (4.0 - 2.0 * t) * t


# Cubic
def ease_in_cubic(t: float) -> float:
    """Cubic ease-in interpolation function.

    Accelerates from zero velocity following $t^3$.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return t * t * t


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out interpolation function.

    Decelerates to zero velocity following cubic curve.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    t1 = t - 1.0
    return t1 * t1 * t1 + 1.0


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out interpolation function.

    Accelerates then decelerates using cubic curves.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    if t < 0.5:
        return 4.0 * t * t * t
    t1 = t - 1.0
    return 1.0 + 4.0 * t1 * t1 * t1


# Quartic
def ease_in_quart(t: float) -> float:
    """Quartic ease-in interpolation function.

    Accelerates from zero velocity following $t^4$.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return t * t * t * t


def ease_out_quart(t: float) -> float:
    """Quartic ease-out interpolation function.

    Decelerates to zero velocity following quartic curve.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    t1 = t - 1.0
    return 1.0 - t1 * t1 * t1 * t1


def ease_in_out_quart(t: float) -> float:
    """Quartic ease-in-out interpolation function.

    Accelerates then decelerates using quartic curves.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    if t < 0.5:
        return 8.0 * t * t * t * t
    t1 = t - 1.0
    return 1.0 - 8.0 * t1 * t1 * t1 * t1


# Sine
def ease_in_sine(t: float) -> float:
    """Sinusoidal ease-in interpolation function.

    Accelerates following a sine curve.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return 1.0 - math.cos((t * math.pi) / 2.0)


def ease_out_sine(t: float) -> float:
    """Sinusoidal ease-out interpolation function.

    Decelerates following a sine curve.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return math.sin((t * math.pi) / 2.0)


def ease_in_out_sine(t: float) -> float:
    """Sinusoidal ease-in-out interpolation function.

    Accelerates then decelerates following a sine wave.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return -(math.cos(math.pi * t) - 1.0) / 2.0


# Exponential
def ease_in_expo(t: float) -> float:
    """Exponential ease-in interpolation function.

    Accelerates exponentially with base 2.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return 0.0 if t <= 0.0 else math.pow(2.0, 10.0 * (t - 1.0))


def ease_out_expo(t: float) -> float:
    """Exponential ease-out interpolation function.

    Decelerates exponentially towards 1.0.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return 1.0 if t >= 1.0 else 1.0 - math.pow(2.0, -10.0 * t)


def ease_in_out_expo(t: float) -> float:
    """Exponential ease-in-out interpolation function.

    Accelerates and decelerates exponentially.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return math.pow(2.0, 20.0 * t - 10.0) / 2.0
    return (2.0 - math.pow(2.0, -20.0 * t + 10.0)) / 2.0


# Back (overshooting)
def ease_in_back(t: float, s: float = 1.70158) -> float:
    """Back ease-in interpolation function with overshoot.

    Pulls back slightly before accelerating forwards.

    Args:
        t: Normalized progress in [0.0, 1.0].
        s: Overshoot magnitude constant. Defaults to 1.70158.

    Returns:
        Interpolated progress factor.
    """
    return t * t * ((s + 1.0) * t - s)


def ease_out_back(t: float, s: float = 1.70158) -> float:
    """Back ease-out interpolation function with overshoot.

    Decelerates, overshoots target slightly, then settles at 1.0.

    Args:
        t: Normalized progress in [0.0, 1.0].
        s: Overshoot magnitude constant. Defaults to 1.70158.

    Returns:
        Interpolated progress factor.
    """
    t1 = t - 1.0
    return t1 * t1 * ((s + 1.0) * t1 + s) + 1.0


def ease_in_out_back(t: float, s: float = 1.70158) -> float:
    """Back ease-in-out interpolation function with overshoot.

    Pulls back, accelerates, overshoots target, then returns to 1.0.

    Args:
        t: Normalized progress in [0.0, 1.0].
        s: Overshoot magnitude constant. Defaults to 1.70158.

    Returns:
        Interpolated progress factor.
    """
    s2 = s * 1.525
    t2 = t * 2.0
    if t2 < 1.0:
        return 0.5 * (t2 * t2 * ((s2 + 1.0) * t2 - s2))
    t3 = t2 - 2.0
    return 0.5 * (t3 * t3 * ((s2 + 1.0) * t3 + s2) + 2.0)


# Bounce
def ease_out_bounce(t: float) -> float:
    """Bounce ease-out interpolation function.

    Simulates a ball bouncing and settling at the target.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    n1 = 7.5625
    d1 = 2.75

    if t < 1.0 / d1:
        return n1 * t * t
    if t < 2.0 / d1:
        t1 = t - (1.5 / d1)
        return n1 * t1 * t1 + 0.75
    if t < 2.5 / d1:
        t2 = t - (2.25 / d1)
        return n1 * t2 * t2 + 0.9375
    t3 = t - (2.625 / d1)
    return n1 * t3 * t3 + 0.984375


def ease_in_bounce(t: float) -> float:
    """Bounce ease-in interpolation function.

    Simulates bounces at the beginning before accelerating to target.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    return 1.0 - ease_out_bounce(1.0 - t)


def ease_in_out_bounce(t: float) -> float:
    """Bounce ease-in-out interpolation function.

    Bounces at both start and finish.

    Args:
        t: Normalized progress in [0.0, 1.0].

    Returns:
        Interpolated progress factor in [0.0, 1.0].
    """
    if t < 0.5:
        return (1.0 - ease_out_bounce(1.0 - 2.0 * t)) / 2.0
    return (1.0 + ease_out_bounce(2.0 * t - 1.0)) / 2.0


EASING_MAP: dict[str, EasingFunc] = {
    "linear": linear,
    "ease_in_quad": ease_in_quad,
    "ease_out_quad": ease_out_quad,
    "ease_in_out_quad": ease_in_out_quad,
    "ease_in_cubic": ease_in_cubic,
    "ease_out_cubic": ease_out_cubic,
    "ease_in_out_cubic": ease_in_out_cubic,
    "ease_in_quart": ease_in_quart,
    "ease_out_quart": ease_out_quart,
    "ease_in_out_quart": ease_in_out_quart,
    "ease_in_sine": ease_in_sine,
    "ease_out_sine": ease_out_sine,
    "ease_in_out_sine": ease_in_out_sine,
    "ease_in_expo": ease_in_expo,
    "ease_out_expo": ease_out_expo,
    "ease_in_out_expo": ease_in_out_expo,
    "ease_in_back": ease_in_back,
    "ease_out_back": ease_out_back,
    "ease_in_out_back": ease_in_out_back,
    "ease_in_bounce": ease_in_bounce,
    "ease_out_bounce": ease_out_bounce,
    "ease_in_out_bounce": ease_in_out_bounce,
}


def get_easing(name_or_func: str | EasingFunc | None) -> EasingFunc:
    """Retrieve an easing function by name, or return the function if already callable.

    Args:
        name_or_func: Name of easing function (e.g. 'ease_in_quad', 'linear') or
            a callable EasingFunc. If None, defaults to `linear`.

    Returns:
        Resolved EasingFunc callable.

    Raises:
        ValueError: If the string name does not match any registered easing function.
    """
    if name_or_func is None:
        return linear
    if callable(name_or_func):
        return name_or_func
    clean = name_or_func.strip().lower().replace("-", "_")
    func = EASING_MAP.get(clean)
    if func is not None:
        return func
    logger.debug("Unknown easing function requested: %r (available: %s)", name_or_func, sorted(EASING_MAP))
    msg = f"Unknown easing function: '{name_or_func}'"
    raise ValueError(msg)
