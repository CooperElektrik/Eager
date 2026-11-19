"""Tests for eager.core persistent, preferences, backlog, watcher, state, and saves."""

from pathlib import Path

from eager.core.backlog import Backlog
from eager.core.persistent import PersistentData
from eager.core.preferences import Preferences
from eager.core.saves import SaveManager
from eager.core.state import Checkpoint, CheckpointHistory


def test_persistent_data(tmp_path: Path) -> None:
    p = tmp_path / "persistent.json"
    data = PersistentData(p)
    data["unlocked"] = True
    data["score"] = 42
    data.save()

    data2 = PersistentData(p)
    assert data2["unlocked"] is True
    assert data2["score"] == 42


def test_preferences(tmp_path: Path) -> None:
    p = tmp_path / "prefs.json"
    prefs = Preferences(text_speed=80.0, music_volume=0.5)
    prefs.save(p)

    loaded = Preferences.load(p)
    assert loaded.text_speed == 80.0
    assert loaded.music_volume == 0.5


def test_backlog() -> None:
    bl = Backlog(max_entries=2)
    bl.add("Alice", "Hello")
    bl.add("Bob", "Hi")
    bl.add("Charlie", "Hey")
    assert len(bl) == 2
    assert bl.entries[0].speaker == "Bob"
    assert bl.entries[1].speaker == "Charlie"


def test_state_and_history() -> None:
    cp = Checkpoint(
        story={"scene": "intro"},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )
    history = CheckpointHistory(max_history=5)
    history.push(cp)
    assert history.depth == 1
    assert history.get_latest() == cp
    popped = history.pop()
    assert popped == cp
    assert history.depth == 0


def test_saves(tmp_path: Path) -> None:
    mgr = SaveManager(tmp_path / "saves")
    cp = Checkpoint(
        story={"current_scene": "s1"},
        visual={},
        audio={},
        backlog_len=0,
        ui={"text": "Dialogue line"},
    )
    meta = mgr.save_slot("slot1", cp)
    assert meta.slot_name == "slot1"
    assert meta.scene_id == "s1"

    loaded_cp = mgr.load_slot("slot1")
    assert loaded_cp is not None
    assert loaded_cp.story["current_scene"] == "s1"


def test_save_manager_blocks_reserved_slot_names(tmp_path: Path):
    import pytest

    from eager.core.exceptions import StorageError
    from eager.core.saves import SaveManager
    from eager.core.state import Checkpoint

    mgr = SaveManager(tmp_path)
    persistent_file = tmp_path / "persistent.json"
    prefs_file = tmp_path / "preferences.json"
    persistent_file.write_text('{"unlocks": true}', encoding="utf-8")
    prefs_file.write_text('{"volume": 0.5}', encoding="utf-8")

    cp = Checkpoint(story={"current_scene": "s1"}, visual={}, audio={}, ui={}, backlog_len=0)
    for reserved in ("persistent", "preferences", "Persistent", "../preferences"):
        with pytest.raises(StorageError, match="Reserved slot name"):
            mgr.save_slot(reserved, cp)
        with pytest.raises(StorageError, match="Reserved slot name"):
            mgr.delete_slot(reserved)
        with pytest.raises(StorageError, match="Reserved slot name"):
            mgr.load_slot(reserved)

    assert persistent_file.read_text(encoding="utf-8") == '{"unlocks": true}'
    assert prefs_file.read_text(encoding="utf-8") == '{"volume": 0.5}'
