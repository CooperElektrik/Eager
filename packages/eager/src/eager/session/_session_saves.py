# pyright: reportImportCycles=false
"""Checkpoint capture/restore, save/load, rollback, and screenshot helpers for GameSession."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eager.core.state import Checkpoint, StorySnapshot

if TYPE_CHECKING:
    from eager.session.session import GameSession


def capture_checkpoint(session: GameSession) -> Checkpoint:
    """Generate a unified checkpoint of the current session state."""
    visual_state = session.director.save_visual_state()
    ui_state_dict = session.director.save_ui_state()

    return Checkpoint(
        story=session.vm.save().to_dict(),
        visual=visual_state,
        audio=session.audio.save_state(),
        backlog_len=len(session.backlog),
        ui=ui_state_dict,
        backlog=session.backlog.to_list(),
    )


def restore_checkpoint(session: GameSession, checkpoint: Checkpoint) -> None:
    """Restore full session state from a checkpoint."""
    snap = StorySnapshot.from_dict(checkpoint.story)
    session.vm.load(snap)
    session.director.load_visual_state(checkpoint.visual)
    session.audio.load_state(checkpoint.audio)
    session.apply_preferences()
    session.director.restore_ui_state(checkpoint.ui)
    session.director.ui_state.visible_chars = None
    session.text_reveal = None
    if checkpoint.backlog is not None:
        from eager.core.backlog import Backlog

        session.backlog = Backlog.from_list(checkpoint.backlog, max_entries=session.backlog.max_entries)
    elif len(session.backlog.entries) > checkpoint.backlog_len:
        session.backlog.entries = session.backlog.entries[: checkpoint.backlog_len]

    session.active_choice_prompt = session.vm.pending_choice
    session.is_finished = session.vm.is_ended
    session.mode = "ended" if session.is_finished else "game"

    scene_id = session.vm.current_scene_id
    if scene_id is not None:
        beat_key = f"{scene_id}:{session.vm.beat_index}"
        session._last_beat_key = beat_key
        session._current_beat_previously_seen = beat_key in session._seen_beats_set
    else:
        session._last_beat_key = None
        session._current_beat_previously_seen = False

    session.notify_state_restored()


def take_screenshot(
    session: GameSession,
    target_path: str | Path | None = None,
    renderer: Any = None,
    **kwargs: Any,
) -> Path:
    """Capture the current frame and save a timestamped PNG to save_dir / 'screenshots'."""
    r = renderer or session.renderer or session._last_renderer
    screenshot_dir = session.save_manager.save_dir / "screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    if target_path is None:
        now = datetime.datetime.now(datetime.UTC)
        now_str = now.strftime("%Y%m%d_%H%M%S")
        candidate = screenshot_dir / f"screenshot_{now_str}.png"
        if candidate.exists():
            now_str = now.strftime("%Y%m%d_%H%M%S_%f")
            candidate = screenshot_dir / f"screenshot_{now_str}.png"
        resolved_path = candidate
    else:
        resolved_path = Path(target_path)

    if r is not None and hasattr(r, "save_frame"):
        r.save_frame(resolved_path, **kwargs)
    else:
        resolved_path.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
            b"\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
        )
    return resolved_path


def save_game(session: GameSession, slot_name: str) -> Any:
    """Save current checkpoint to named slot."""
    cp = session.checkpoints.get_latest() or capture_checkpoint(session)
    return session.save_manager.save_slot(
        slot_name,
        cp,
        metadata_extra={
            "playtime_seconds": session._playtime,
        },
    )


def load_game(session: GameSession, slot_name: str) -> bool:
    """Load game from named slot."""
    meta = session.save_manager.get_slot_metadata(slot_name)
    cp = session.save_manager.load_slot(slot_name)
    if cp is None:
        return False
    if meta is not None:
        session._playtime = meta.playtime_seconds
    restore_checkpoint(session, cp)
    session.checkpoints.clear()
    session.checkpoints.push(cp)
    return True


def quicksave(session: GameSession) -> Any:
    """Quicksave current checkpoint."""
    cp = session.checkpoints.get_latest() or capture_checkpoint(session)
    result = session.save_manager.quicksave(cp, playtime_seconds=session._playtime)
    if hasattr(session.overlay, "show_toast"):
        session.overlay.show_toast("Saved to quickslot", 2.0)
    return result


def quickload(session: GameSession) -> bool:
    """Quickload from quicksave slot."""
    slot = session.save_manager._latest_rotated_slot("quick", session.save_manager.max_quicksaves)
    if slot is not None:
        meta = session.save_manager.get_slot_metadata(slot)
        if meta is not None:
            session._playtime = meta.playtime_seconds
    cp = session.save_manager.quickload()
    if cp is None:
        return False
    restore_checkpoint(session, cp)
    session.checkpoints.clear()
    session.checkpoints.push(cp)
    if hasattr(session.overlay, "show_toast"):
        session.overlay.show_toast("Loaded quickslot", 2.0)
    return True


def rollback(session: GameSession) -> bool:
    """Roll back to the previous interactive checkpoint."""
    if not session.checkpoints.can_rollback:
        return False

    session.checkpoints.pop()
    prev = session.checkpoints.get_latest()
    if prev is None:
        return False

    restore_checkpoint(session, prev)
    session.text_reveal = None
    session.director.ui_state.visible_chars = None
    return True
