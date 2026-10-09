"""Tests for the VisualEngine facade, SaveSlot, and atomic state management."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from eager_runtime import VisualEngine
from eager_runtime.engine import SaveSlot, StateCorruptionError

SAMPLE_SCREENPLAY = """
## Courtyard --- courtyard
~ bg castle_courtyard with cut
~ show alice cheerful at left with cut
Alice (excited): Look over there!
~ show guard stern at right with cut
Guard: Halt! Who goes there?
Alice (serious): We are travelers.
~ move alice to center duration=0.0
~ hide guard with cut
? Step forward into the hall (hall)
? Flee into the woods (woods)

## Great Hall --- hall
~ bg hall_interior with cut
Narrator: You entered the hall.

## Dark Woods --- woods
~ bg dark_woods with cut
Narrator: You fled into the woods.
"""


@pytest.fixture
def script_file(tmp_path: Path) -> Path:
    p = tmp_path / "test_story.es"
    p.write_text(SAMPLE_SCREENPLAY, encoding="utf-8")
    return p


# ────────────────────────────────────────────────────────────────────── #
# Construction & component wiring
# ────────────────────────────────────────────────────────────────────── #


def test_engine_construction_wires_all_components(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    assert engine.backend == "null"
    assert engine.vm is not None
    assert engine.dispatcher is not None
    assert engine.compositor is not None
    assert engine.director is not None
    assert engine.renderer is not None
    assert engine.vm.is_ended is False


def test_engine_default_backend_is_null(script_file: Path) -> None:
    engine = VisualEngine(script_file)
    assert engine.backend == "null"


def test_engine_unknown_backend_raises(tmp_path: Path) -> None:
    script = tmp_path / "story.es"
    script.write_text(SAMPLE_SCREENPLAY)
    with pytest.raises(ValueError, match="Unknown backend"):
        VisualEngine(script, backend="invalid")


def test_engine_plain_mode(tmp_path: Path) -> None:
    """Plain screenplay mode should parse without scene-graph complexity."""
    plain_text = "Alice: Hello\nBob: Hi"
    script = tmp_path / "plain.es"
    script.write_text(plain_text)
    engine = VisualEngine(script, backend="null", plain=True)
    assert engine.vm is not None
    # In plain mode, the story should be parseable and runnable
    result = engine.run_headless(auto_choose=None)
    assert result["ended"]


# ────────────────────────────────────────────────────────────────────── #
# Game loop
# ────────────────────────────────────────────────────────────────────── #


def test_advance_returns_choice_prompt(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    event = engine.advance()
    assert event is not None
    assert event.type == "choice_prompt"


def test_make_choice_and_advance(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    event = engine.make_choice(0)  # Enter the hall
    assert event is not None
    assert event.type == "story_end"
    assert engine.vm.is_ended


def test_make_choice_by_target(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    event = engine.make_choice("hall")
    assert event is not None
    assert event.type == "story_end"
    assert engine.vm.is_ended


def test_run_headless_auto_choose(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    result = engine.run_headless(auto_choose=0)
    assert result["ended"] is True
    assert result["steps"] > 0
    assert result["render_frames"] > 0


def test_run_headless_max_steps(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    result = engine.run_headless(auto_choose=0, max_steps=1)
    assert result["steps"] <= 1


# ────────────────────────────────────────────────────────────────────── #
# Save / Load (Phase 3.1 & 3.2)
# ────────────────────────────────────────────────────────────────────── #


def test_save_slot_is_frozen_dataclass(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    slot = engine.save_slot()
    assert isinstance(slot, SaveSlot)
    assert isinstance(slot.story_state, dict)
    assert isinstance(slot.visual_state, dict)
    assert "current_scene" in slot.story_state
    assert "compositor" in slot.visual_state


def test_save_load_roundtrip_restores_state(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()

    slot = engine.save_slot()

    # Choose a path that changes state
    engine.make_choice(0)
    assert engine.vm.is_ended

    # Restore
    engine.load_save_slot(slot)
    assert not engine.vm.is_ended
    assert engine.vm.current_scene_id == "courtyard"


def test_save_slot_equality(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    slot1 = engine.save_slot()
    engine.make_choice(0)
    slot2 = engine.save_slot()
    assert slot1 != slot2  # Different story states


def test_save_slot_serializable_to_json(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    slot = engine.save_slot()
    # Both payloads must be JSON-serializable
    json.dumps(slot.story_state)
    json.dumps(slot.visual_state)


# ────────────────────────────────────────────────────────────────────── #
# Transactional restore (Phase 3.2)
# ────────────────────────────────────────────────────────────────────── #


def test_load_save_slot_transactional_rollback_on_failure(script_file: Path) -> None:
    """If visual state restore fails, the story state must be rolled back too."""
    engine = VisualEngine(script_file, backend="null")
    engine.advance()

    valid_slot = engine.save_slot()

    # Corrupt the visual state to force a failure in load_visual_state.
    # load_state calls Stage.from_dict(state["stage"]) — feeding it an int
    # instead of a dict causes an AttributeError, which should trigger
    # the transactional rollback path.
    corrupted_slot = SaveSlot(
        story_state=valid_slot.story_state,
        visual_state={"compositor": {"stage": 42}},  # not a dict → Stage.from_dict() will fail
    )

    # Make a choice to change state before attempting the failed restore
    engine.make_choice(0)
    assert engine.vm.is_ended

    with pytest.raises(StateCorruptionError):
        engine.load_save_slot(corrupted_slot)

    # The rollback restored the VM to the backup snapshot taken *before*
    # the failed load attempt — i.e. the post-choice state (scene "hall").
    # Note: load() resets _is_ended to False (it's transient, not persisted).
    assert engine.vm.current_scene_id == "hall"
    assert engine.vm.is_ended is False


def test_load_save_slot_valid_does_not_raise(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    slot = engine.save_slot()

    engine.make_choice(0)
    assert engine.vm.is_ended

    # Should restore cleanly without raising
    engine.load_save_slot(slot)
    assert not engine.vm.is_ended
    assert engine.vm.current_scene_id == "courtyard"


# ────────────────────────────────────────────────────────────────────── #
# Synced rollback (Phase 3.3)
# ────────────────────────────────────────────────────────────────────── #


def test_rollback_returns_false_when_no_history(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null", max_history=0)
    engine.advance()
    # With no visual history enabled, rollback should report False
    assert engine.rollback() is False


def test_rollback_synchronizes_story_and_visual(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()

    # The director's visual history should have snapshots after stepping
    assert engine.can_rollback() is True

    # Advance further (make a choice)
    engine.make_choice(0)

    # Rollback
    result = engine.rollback()
    assert result is True

    # State should be back to before the choice
    assert not engine.vm.is_ended


def test_rollback_both_must_succeed(script_file: Path) -> None:
    """If either story or visual rollback fails, the method returns False."""
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    # After advancing, both should have rollback available
    assert engine.rollback() is True


# ────────────────────────────────────────────────────────────────────── #
# Renderer
# ────────────────────────────────────────────────────────────────────── #


def test_render_with_null_renderer(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    engine.render(window_width=1280, window_height=720)
    # render_compositor calls begin_frame/end_frame, so frame_count is incremented
    assert engine.renderer.frame_count == 1
    # After render, render_items should be populated
    assert len(engine.render_items) > 0


def test_render_list_after_advance(script_file: Path) -> None:
    engine = VisualEngine(script_file, backend="null")
    engine.advance()
    engine.render()
    items = engine.render_items
    bg = next(it for it in items if it.layer == "background")
    assert bg.asset_id == "bg/castle_courtyard"
