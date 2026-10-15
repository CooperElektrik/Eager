"""Tests for timeline and tweening engine."""

import pytest
from eager_core.easing import ease_out_quad
from eager_core.types import Color, Vec2

from eager_graphics.timeline import Timeline


class DummyTarget:
    def __init__(self) -> None:
        self.opacity = 0.0
        self.position = Vec2(0.0, 0.0)
        self.color = Color(0.0, 0.0, 0.0, 1.0)


def test_tween_float_interpolation() -> None:
    target = DummyTarget()
    completed = False

    def on_done() -> None:
        nonlocal completed
        completed = True

    timeline = Timeline()
    timeline.add_tween(
        target=target,
        property_name="opacity",
        end_value=1.0,
        duration=1.0,
        on_complete=on_done,
    )
    assert timeline.active_count == 1
    assert target.opacity == 0.0

    # Step half second
    timeline.update(0.5)
    assert target.opacity == pytest.approx(0.5)
    assert not completed

    # Finish tween
    timeline.update(0.5)
    assert target.opacity == pytest.approx(1.0)
    assert completed
    assert timeline.active_count == 0


def test_tween_vec2_interpolation() -> None:
    target = DummyTarget()
    timeline = Timeline()
    timeline.add_tween(
        target=target,
        property_name="position",
        end_value=Vec2(100.0, 200.0),
        duration=2.0,
        easing=ease_out_quad,
    )

    timeline.update(1.0)
    # At t=0.5, ease_out_quad(0.5) = 0.5 * 1.5 = 0.75
    expected_factor = 0.75
    assert target.position.x == pytest.approx(100.0 * expected_factor)
    assert target.position.y == pytest.approx(200.0 * expected_factor)

    timeline.update(1.0)
    assert target.position == Vec2(100.0, 200.0)


def test_tween_cancellation() -> None:
    target = DummyTarget()
    timeline = Timeline()
    timeline.add_tween(target, "opacity", 1.0, 5.0)
    assert timeline.has_tweens(target)

    timeline.cancel_tweens_for(target, "opacity")
    assert not timeline.has_tweens(target)
    assert timeline.active_count == 0


def test_immediate_tween_duration_zero() -> None:
    target = DummyTarget()
    timeline = Timeline()
    completed = False

    def on_done() -> None:
        nonlocal completed
        completed = True

    timeline.add_tween(target, "opacity", 1.0, 0.0, on_complete=on_done)
    assert target.opacity == 1.0
    assert completed
    assert timeline.active_count == 0


def test_chained_tween_persistence() -> None:
    target = DummyTarget()
    timeline = Timeline()
    chain_completed = False

    def on_second_done() -> None:
        nonlocal chain_completed
        chain_completed = True

    def on_first_done() -> None:
        # Callback chains another tween
        timeline.add_tween(
            target=target,
            property_name="opacity",
            end_value=0.5,
            duration=1.0,
            on_complete=on_second_done,
        )

    timeline.add_tween(target, "opacity", 1.0, 1.0, on_complete=on_first_done)
    assert timeline.active_count == 1

    # Update through first tween completion
    timeline.update(1.0)
    assert target.opacity == pytest.approx(1.0)
    # Chained tween was added during first tween's on_complete and persisted
    assert timeline.active_count == 1
    assert not chain_completed

    # Progress chained tween halfway (1.0 -> 0.5 at t=0.5 => 0.75)
    timeline.update(0.5)
    assert target.opacity == pytest.approx(0.75)
    assert timeline.active_count == 1
    assert not chain_completed

    # Complete chained tween
    timeline.update(0.5)
    assert target.opacity == pytest.approx(0.5)
    assert chain_completed
    assert timeline.active_count == 0


def test_tween_cancellation_during_update_safety() -> None:
    target1 = DummyTarget()
    target2 = DummyTarget()
    timeline = Timeline()

    def cancel_second(val: float) -> None:
        timeline.cancel_tweens_for(target2)

    timeline.add_tween(target1, "opacity", 1.0, 1.0, on_update=cancel_second)
    t2 = timeline.add_tween(target2, "opacity", 1.0, 1.0)

    # Calling update invokes cancel_tweens_for during iteration without error
    timeline.update(0.5)
    assert not timeline.has_tweens(target2)
    assert t2.finished is True
    assert timeline.has_tweens(target1)
    assert timeline.active_count == 1

