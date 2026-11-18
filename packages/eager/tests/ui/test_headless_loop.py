"""Tests for StageCompositor headless game loop (step)."""

from __future__ import annotations

import pytest

from eager.stage import StageCompositor


def test_step_advances_tweens() -> None:
    """step() with default dt should advance tweens like update()."""
    comp = StageCompositor(1920, 1080)
    comp.show_character("alice", "happy", position="left", transition="fade", duration=1.0)

    # At t=0, alice is invisible (opacity 0), so render_list is empty.
    assert len(comp.render_list()) == 0

    comp.step(dt=0.5)
    items = comp.render_list()
    assert len(items) == 1
    assert items[0].opacity == pytest.approx(0.5, abs=0.02)


def test_step_default_dt_is_60fps() -> None:
    """Default dt should be 1/60s (≈16.67ms)."""
    comp = StageCompositor(1920, 1080)
    comp.show_character("bob", "normal", position="center", transition="fade", duration=0.0167)
    # One step at ~0.0167s should nearly complete a 0.0167s tween.
    comp.step()  # default dt
    items = comp.render_list()
    # After one default step, the tween should be well underway.
    assert len(items) == 1
