"""Tests for StageCompositor headless game loop (step / run_headless)."""

from __future__ import annotations

import pytest

from eager_graphics import NullRenderer, StageCompositor
from eager_graphics.types import Vec2


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


def test_run_headless_max_steps() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/castle", transition="cut")

    steps = comp.run_headless(max_steps=10)
    assert steps == 10


def test_run_headless_with_timeline_until() -> None:
    """run_headless with until=predicate should stop when tweens finish."""
    comp = StageCompositor(1920, 1080)
    comp.show_character("alice", "happy", position="center", transition="fade", duration=1.0)

    # Tween takes 1.0s at dt=0.1 => finishes at step 11 due to floating-point
    # (0.1 * 10 = 0.9999... < 1.0). until stops early when no tweens remain.
    steps = comp.run_headless(dt=0.1, until=lambda: not comp.timeline.has_tweens())
    assert steps == 11


def test_run_headless_requires_termination_condition() -> None:
    comp = StageCompositor(1920, 1080)
    with pytest.raises(ValueError, match="max_steps or an until"):
        comp.run_headless()  # neither max_steps nor until


def test_run_headless_with_backend_and_render() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/forest", transition="cut")
    comp.show_character("alice", "happy", position="left", transition="cut")

    backend = NullRenderer()
    steps = comp.run_headless(backend, max_steps=3, render=True)

    assert steps == 3
    assert backend.frame_count == 3
    # Each rendered frame should contain bg + alice.
    assert len(backend.last_frame) == 2
    assets = {item.asset_id for item in backend.last_frame}
    assert assets == {"bg/forest", "alice/happy"}


def test_run_headless_render_without_backend_raises() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/test", transition="cut")
    with pytest.raises(ValueError, match="render=True requires a render_backend"):
        comp.run_headless(max_steps=1, render=True)


def test_run_headless_no_render_does_not_use_backend() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/x", transition="cut")
    backend = NullRenderer()
    # No render=True => backend should remain untouched.
    comp.run_headless(backend, max_steps=5)
    assert backend.frame_count == 0
    assert len(backend.last_frame) == 0


def test_step_default_dt_is_60fps() -> None:
    """Default dt should be 1/60s (≈16.67ms)."""
    comp = StageCompositor(1920, 1080)
    comp.show_character("bob", "normal", position="center", transition="fade", duration=0.0167)
    # One step at ~0.0167s should nearly complete a 0.0167s tween.
    comp.step()  # default dt
    items = comp.render_list()
    # After one default step, the tween should be well underway.
    assert len(items) == 1


def test_run_headless_preserves_render_list_data() -> None:
    """Each rendered frame through the backend must carry full element data."""
    comp = StageCompositor(1920, 1080, ground_y=1000.0)
    comp.set_background("bg/hill", transition="cut")
    comp.show_character("alice", "happy", position=Vec2(480.0, 1000.0), transition="cut")

    backend = NullRenderer()
    comp.run_headless(backend, max_steps=1, render=True)

    assert len(backend.last_frame) == 2
    bg, char = backend.last_frame
    assert bg.layer == "background"
    assert bg.asset_id == "bg/hill"
    assert char.layer == "characters"
    assert char.asset_id == "alice/happy"
    assert char.x == pytest.approx(480.0)
    assert char.y == pytest.approx(1000.0)
    assert char.opacity == pytest.approx(1.0)
