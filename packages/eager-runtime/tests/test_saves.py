"""Unit tests for SaveManager, CheckpointHistory, SaveData, persistence, and schema migrations."""

import json
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from eager_core.input import InputAction

from eager_runtime import (
    Checkpoint,
    CheckpointHistory,
    GameSession,
    PersistentData,
    Preferences,
    SaveData,
    SaveManager,
    SaveMetadata,
    SaveMigrationError,
    StorySnapshot,
)

PERSISTENCE_SAMPLE_SCRIPT = """
## Start --- start
Alice: Welcome!
? Path A (path_a)
? Path B (path_b)

## Path A --- path_a
Alice: You took path A.

## Path B --- path_b
Alice: You took path B.
"""


# ---------------------------------------------------------------------------
# CheckpointHistory
# ---------------------------------------------------------------------------

def test_checkpoint_history_push_pop_roll_forward() -> None:
    ch = CheckpointHistory(max_history=5)
    assert not ch.can_rollback
    assert not ch.can_roll_forward
    assert ch.depth == 0

    cp1 = Checkpoint(story={"scene": "1"}, visual={}, audio={}, backlog_len=1, ui={})
    cp2 = Checkpoint(story={"scene": "2"}, visual={}, audio={}, backlog_len=2, ui={})

    ch.push(cp1)
    assert not ch.can_rollback  # depth is 1
    assert ch.depth == 1

    ch.push(cp2)
    assert ch.can_rollback  # depth is 2
    assert ch.depth == 2
    assert ch.get_latest() == cp2

    # Pop cp2 onto redo stack
    popped = ch.pop()
    assert popped == cp2
    assert ch.depth == 1
    assert not ch.can_rollback
    assert ch.can_roll_forward

    # Roll forward restores cp2
    rf = ch.roll_forward()
    assert rf == cp2
    assert ch.depth == 2
    assert ch.can_rollback
    assert not ch.can_roll_forward


def test_checkpoint_history_max_capacity() -> None:
    ch = CheckpointHistory(max_history=3)
    for i in range(5):
        ch.push(Checkpoint(story={"i": i}, visual={}, audio={}, backlog_len=i, ui={}))

    assert ch.depth == 3
    latest = ch.get_latest()
    assert latest is not None
    assert latest.story["i"] == 4


def test_checkpoint_history_clear_and_clear_redo() -> None:
    ch = CheckpointHistory(max_history=5)
    cp1 = Checkpoint(story={"s": 1}, visual={}, audio={}, backlog_len=0, ui={})
    cp2 = Checkpoint(story={"s": 2}, visual={}, audio={}, backlog_len=0, ui={})
    ch.push(cp1)
    ch.push(cp2)
    ch.pop()
    assert ch.can_roll_forward

    ch.clear_redo()
    assert not ch.can_roll_forward

    ch.clear()
    assert ch.depth == 0
    assert not ch.can_rollback


# ---------------------------------------------------------------------------
# SaveManager & Persistent System
# ---------------------------------------------------------------------------

def test_save_manager_crud(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path)
    cp = Checkpoint(
        story={"current_scene": "start", "variables": {"gold": 100}},
        visual={},
        audio={},
        backlog_len=1,
        ui={"text": "Welcome to town!"},
    )

    # Save slot
    meta = manager.save_slot("slot_1", cp)
    assert meta.slot_name == "slot_1"
    assert meta.scene_id == "start"
    assert meta.dialogue_snippet == "Welcome to town!"

    # List slots
    slots = manager.list_slots()
    assert len(slots) == 1
    assert slots[0].slot_name == "slot_1"

    # Load slot
    loaded = manager.load_slot("slot_1")
    assert loaded is not None
    assert loaded.story["variables"]["gold"] == 100

    # Delete slot
    assert manager.delete_slot("slot_1") is True
    assert manager.load_slot("slot_1") is None
    assert len(manager.list_slots()) == 0


def test_save_and_load_active_input_prompt(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path)
    prompt_data = {"var_name": "hero_name", "prompt": "Enter name:", "default": "Traveler"}
    cp = Checkpoint(
        story={"current_scene": "start"},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
        active_input_prompt=prompt_data,
    )

    manager.save_slot("input_slot", cp)
    loaded = manager.load_slot("input_slot")
    assert loaded is not None
    assert loaded.active_input_prompt == prompt_data

    # Also test SaveData directly
    save_data = SaveData(
        metadata=SaveMetadata(
            slot_name="test",
            timestamp="2026-10-21T00:00:00",
            scene_id="start",
            scene_name="Start",
            dialogue_snippet="hi",
        ),
        checkpoint=cp,
    )
    d = save_data.to_dict()
    assert d["checkpoint"]["active_input_prompt"] == prompt_data
    restored = SaveData.from_dict(d)
    assert restored.checkpoint.active_input_prompt == prompt_data


def test_quicksave_and_autosave(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path)
    cp = Checkpoint(
        story={"current_scene": "checkpoint"},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )

    meta = manager.quicksave(cp)
    assert meta.slot_name == "quick_1"
    ql = manager.quickload()
    assert ql is not None
    assert ql.story["current_scene"] == "checkpoint"

    meta_auto = manager.autosave(cp)
    assert meta_auto.slot_name == "auto_1"
    al = manager.autoload()
    assert al is not None
    assert al.story["current_scene"] == "checkpoint"


def test_quicksave_circular_rotation(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path, max_quicksaves=3)
    checkpoints = [
        Checkpoint(story={"current_scene": f"scene_{i}"}, visual={}, audio={}, backlog_len=0, ui={})
        for i in range(1, 6)
    ]

    # 1. Fill 3 slots: quick_1, quick_2, quick_3
    m1 = manager.quicksave(checkpoints[0])
    time.sleep(0.005)
    m2 = manager.quicksave(checkpoints[1])
    time.sleep(0.005)
    m3 = manager.quicksave(checkpoints[2])
    time.sleep(0.005)

    assert m1.slot_name == "quick_1"
    assert m2.slot_name == "quick_2"
    assert m3.slot_name == "quick_3"

    # Quickload should load latest (scene_3)
    ql = manager.quickload()
    assert ql is not None
    assert ql.story["current_scene"] == "scene_3"

    # 2. 4th save should rotate and overwrite oldest (quick_1)
    m4 = manager.quicksave(checkpoints[3])
    time.sleep(0.005)
    assert m4.slot_name == "quick_1"
    ql = manager.quickload()
    assert ql is not None
    assert ql.story["current_scene"] == "scene_4"

    # 3. 5th save should rotate and overwrite next oldest (quick_2)
    m5 = manager.quicksave(checkpoints[4])
    time.sleep(0.005)
    assert m5.slot_name == "quick_2"
    ql = manager.quickload()
    assert ql is not None
    assert ql.story["current_scene"] == "scene_5"


def test_autosave_circular_rotation(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path, max_autosaves=2)
    cp1 = Checkpoint(story={"current_scene": "auto_scene_1"}, visual={}, audio={}, backlog_len=0, ui={})
    cp2 = Checkpoint(story={"current_scene": "auto_scene_2"}, visual={}, audio={}, backlog_len=0, ui={})
    cp3 = Checkpoint(story={"current_scene": "auto_scene_3"}, visual={}, audio={}, backlog_len=0, ui={})

    m1 = manager.autosave(cp1)
    time.sleep(0.005)
    m2 = manager.autosave(cp2)
    time.sleep(0.005)
    assert m1.slot_name == "auto_1"
    assert m2.slot_name == "auto_2"

    al = manager.autoload()
    assert al is not None
    assert al.story["current_scene"] == "auto_scene_2"

    # Overwrite oldest (auto_1)
    m3 = manager.autosave(cp3)
    assert m3.slot_name == "auto_1"
    al = manager.autoload()
    assert al is not None
    assert al.story["current_scene"] == "auto_scene_3"


def test_legacy_unindexed_quick_and_auto_slots(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path)
    cp = Checkpoint(story={"current_scene": "legacy_quick"}, visual={}, audio={}, backlog_len=0, ui={})
    manager.save_slot("quick", cp)
    ql_legacy = manager.quickload()
    assert ql_legacy is not None
    assert ql_legacy.story["current_scene"] == "legacy_quick"

    cp_auto = Checkpoint(story={"current_scene": "legacy_auto"}, visual={}, audio={}, backlog_len=0, ui={})
    manager.save_slot("auto", cp_auto)
    al_legacy = manager.autoload()
    assert al_legacy is not None
    assert al_legacy.story["current_scene"] == "legacy_auto"

    # Quicksaving now should write to quick_1 and become the latest
    cp_new = Checkpoint(story={"current_scene": "new_quick_1"}, visual={}, audio={}, backlog_len=0, ui={})
    manager.quicksave(cp_new)
    ql_new = manager.quickload()
    assert ql_new is not None
    assert ql_new.story["current_scene"] == "new_quick_1"


def test_corrupted_persistent_data_backup(tmp_path: Path) -> None:
    p_path = tmp_path / "persistent.json"
    p_path.write_text("{this is corrupted non-json content!!", encoding="utf-8")

    # Loading corrupted file should not crash and should create backup
    p = PersistentData(p_path)
    assert len(p) == 0

    bak_path = tmp_path / "persistent.json.corrupt.bak"
    assert bak_path.exists()
    assert bak_path.read_text(encoding="utf-8") == "{this is corrupted non-json content!!"

    # Now saving new persistent data should succeed and write valid JSON
    p["recovered"] = True
    p.save()
    p2 = PersistentData(p_path)
    assert p2["recovered"] is True


def test_load_slot_corrupted_json_creates_backup(tmp_path: Path) -> None:
    """Verify SaveManager.load_slot generates slot.json.corrupt.bak on corrupt JSON."""
    manager = SaveManager(tmp_path)
    slot_path = tmp_path / "slot_corrupt.json"
    corrupt_content = '{"version": 1, "checkpoint": {broken json content...'
    slot_path.write_text(corrupt_content, encoding="utf-8")

    # Loading corrupt slot must return None without raising unhandled JSONDecodeError
    loaded = manager.load_slot("slot_corrupt")
    assert loaded is None

    # Must generate .corrupt.bak backup with exact content
    bak_path = tmp_path / "slot_corrupt.json.corrupt.bak"
    assert bak_path.exists()
    assert bak_path.read_text(encoding="utf-8") == corrupt_content


def test_load_slot_binary_garbage_creates_backup(tmp_path: Path) -> None:
    """Verify SaveManager.load_slot handles non-UTF8 binary corruption."""
    manager = SaveManager(tmp_path)
    slot_path = tmp_path / "slot_bin.json"
    raw_garbage = b"\x00\xff\xfe\x00\xaa\xbb\xcc\xdd"
    slot_path.write_bytes(raw_garbage)

    loaded = manager.load_slot("slot_bin")
    assert loaded is None

    bak_path = tmp_path / "slot_bin.json.corrupt.bak"
    assert bak_path.exists()
    assert bak_path.read_bytes() == raw_garbage


def test_save_slot_overwrites_corrupt_slot_retaining_backup(tmp_path: Path) -> None:
    """Verify player can overwrite a corrupted slot while retaining the backup for diagnostics."""
    manager = SaveManager(tmp_path)
    slot_path = tmp_path / "slot_overwrite.json"
    slot_path.write_text("{corrupt garbage", encoding="utf-8")

    # Trigger backup via load_slot
    assert manager.load_slot("slot_overwrite") is None
    bak_path = tmp_path / "slot_overwrite.json.corrupt.bak"
    assert bak_path.exists()

    # Now save valid checkpoint into the same slot
    cp = Checkpoint(story={"current_scene": "recovered"}, visual={}, audio={}, backlog_len=0, ui={})
    manager.save_slot("slot_overwrite", cp)

    # Valid slot can be reloaded
    reloaded = manager.load_slot("slot_overwrite")
    assert reloaded is not None
    assert reloaded.story["current_scene"] == "recovered"

    # Backup remains on disk
    assert bak_path.exists()
    assert bak_path.read_text(encoding="utf-8") == "{corrupt garbage"


def test_non_dict_json_root(tmp_path: Path) -> None:
    """Non-dict JSON roots (list, str, int) must safely return None and create .corrupt.bak."""
    test_cases: list[tuple[str, str]] = [
        ("slot_array", "[1, 2, 3]"),
        ("slot_string", '"plain string root"'),
        ("slot_number", "42"),
    ]
    manager = SaveManager(tmp_path)
    for slot_name, payload in test_cases:
        slot_path = tmp_path / f"{slot_name}.json"
        slot_path.write_text(payload, encoding="utf-8")

        res = manager.load_slot(slot_name)
        assert res is None

        bak_path = tmp_path / f"{slot_name}.json.corrupt.bak"
        assert bak_path.exists(), f"Backup missing for non-dict root: {slot_name}"
        assert bak_path.read_text(encoding="utf-8") == payload


def test_list_slots_skips_corrupted_metadata_cleanly(tmp_path: Path) -> None:
    """list_slots() and get_slot_metadata() must cleanly handle corrupt metadata without crashing."""
    manager = SaveManager(tmp_path)

    # Populate valid slots
    cp1 = Checkpoint(story={"current_scene": "scene_1"}, visual={}, audio={}, backlog_len=0, ui={})
    cp2 = Checkpoint(story={"current_scene": "scene_2"}, visual={}, audio={}, backlog_len=0, ui={})
    _ = manager.save_slot("valid_1", cp1)
    _ = manager.save_slot("valid_2", cp2)

    # Populate corrupted metadata slots
    corrupt_cases: list[tuple[str, str]] = [
        ("slot_broken_ver", json.dumps({"metadata": {"version": "corrupted"}, "checkpoint": {}})),
        ("slot_broken_playtime", json.dumps({"metadata": {"playtime_seconds": "not_float"}, "checkpoint": {}})),
        ("slot_int_meta", json.dumps({"metadata": 123, "checkpoint": {}})),
        ("slot_str_meta", json.dumps({"metadata": "not_a_dict", "checkpoint": {}})),
        ("slot_syntax_err", '{"metadata": {"incomplete'),
        ("slot_root_array", "[1, 2, 3]"),
    ]
    for slot_name, payload in corrupt_cases:
        slot_path = tmp_path / f"{slot_name}.json"
        slot_path.write_text(payload, encoding="utf-8")

    # get_slot_metadata returns None for corrupted slots without crashing
    for slot_name, _ in corrupt_cases:
        meta = manager.get_slot_metadata(slot_name)
        assert meta is None, f"Expected None for get_slot_metadata({slot_name})"

    # get_slot_metadata returns SaveMetadata for valid slots
    valid_meta = manager.get_slot_metadata("valid_1")
    assert valid_meta is not None
    assert isinstance(valid_meta, SaveMetadata)
    assert valid_meta.slot_name == "valid_1"

    # list_slots() returns only valid slots, cleanly skipping corrupt ones
    slots = manager.list_slots()
    assert len(slots) == 2
    slot_names = {s.slot_name for s in slots}
    assert slot_names == {"valid_1", "valid_2"}
    assert all(isinstance(s, SaveMetadata) for s in slots)


def test_persistent_data(tmp_path: Path) -> None:
    p_path = tmp_path / "persistent.json"
    p = PersistentData(p_path)
    p["seen_endings"] = ["good_end"]
    p.unlocked_gallery = True
    p.save()

    # Reload in new instance
    p2 = PersistentData(p_path)
    assert p2["seen_endings"] == ["good_end"]
    assert p2.unlocked_gallery is True


def test_gallery_and_achievements(tmp_path: Path) -> None:
    pfile = tmp_path / "persistent_gallery.json"
    p = PersistentData(pfile)

    assert not p.is_gallery_unlocked("cg_ending_1")
    p.unlock_gallery("cg_ending_1")
    assert p.is_gallery_unlocked("cg_ending_1")

    assert not p.has_achievement("ach_first_win")
    p.unlock_achievement("ach_first_win")
    assert p.has_achievement("ach_first_win")

    # Reload from disk
    p2 = PersistentData(pfile)
    assert p2.is_gallery_unlocked("cg_ending_1")
    assert p2.has_achievement("ach_first_win")


def test_preferences(tmp_path: Path) -> None:
    pref_path = tmp_path / "preferences.json"
    pref = Preferences(text_speed=100.0, music_volume=0.5, fullscreen=True)
    pref.save(pref_path)

    loaded = Preferences.load(pref_path)
    assert loaded.text_speed == 100.0
    assert loaded.music_volume == 0.5
    assert loaded.fullscreen is True
    assert loaded.sfx_volume == 1.0  # default preserved


def test_game_session_save_and_load(tmp_path: Path) -> None:
    script_path = tmp_path / "game_story.es"
    script_path.write_text(PERSISTENCE_SAMPLE_SCRIPT, encoding="utf-8")

    session = GameSession(script_path, save_dir=tmp_path / "saves")
    session.advance()  # Dialogue beat: Alice: Welcome!
    session.advance()  # Choice prompt beat
    assert session.active_choice_prompt is not None

    # Save game to slot 1
    session.save_game("slot_1")

    # Make choice
    session.choose(0)
    assert session.vm.current_scene_id == "path_a"

    # Load back slot 1
    assert session.load_game("slot_1") is True
    assert session.vm.current_scene_id == "start"
    assert session.active_choice_prompt is not None


def test_game_session_set_language_custom_save_dir(tmp_path: Path) -> None:
    script_path = tmp_path / "game_story.es"
    script_path.write_text(PERSISTENCE_SAMPLE_SCRIPT, encoding="utf-8")

    custom_dir = tmp_path / "custom_pref_save"
    custom_dir.mkdir(parents=True, exist_ok=True)
    session = GameSession(script_path, save_dir=custom_dir)
    session.set_language("ja")
    pref_file = custom_dir / "preferences.json"
    assert pref_file.exists()
    saved_pref = Preferences.load(pref_file)
    assert saved_pref.language == "ja"


def test_game_session_playtime_and_screenshot(tmp_path: Path) -> None:
    script_path = tmp_path / "game_story.es"
    script_path.write_text(PERSISTENCE_SAMPLE_SCRIPT, encoding="utf-8")

    custom_dir = tmp_path / "playtime_test"
    custom_dir.mkdir(parents=True, exist_ok=True)
    session = GameSession(script_path, save_dir=custom_dir)

    # Playtime starts at 0.0
    assert session.playtime == 0.0

    # Update accumulates dt
    session.update(2.5)
    session.update(3.5)
    assert session.playtime == pytest.approx(6.0)

    # Save preserves playtime in metadata
    meta = session.save_game("play_slot")
    assert meta.playtime_seconds == pytest.approx(6.0)
    assert meta.playtime_formatted == "00:06"

    # Loading slot restores playtime
    session2 = GameSession(script_path, save_dir=custom_dir)
    assert session2.playtime == 0.0
    assert session2.load_game("play_slot") is True
    assert session2.playtime == pytest.approx(6.0)

    # Screenshot handling with renderer.save_frame()
    mock_renderer = MagicMock()
    session.renderer = mock_renderer
    shot_path = session.handle_input(InputAction.SCREENSHOT)
    assert mock_renderer.save_frame.called
    assert shot_path.parent == custom_dir / "screenshots"
    assert shot_path.name.endswith(".png")

    # Headless screenshot fallback without renderer creates real valid PNG
    session_headless = GameSession(script_path, save_dir=custom_dir, headless=True)
    shot_headless = session_headless.handle_input(InputAction.SCREENSHOT)
    assert shot_headless.is_file()
    assert shot_headless.stat().st_size > 0


# ---------------------------------------------------------------------------
# Schema Migrations
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_migrations() -> Iterator[None]:
    StorySnapshot.clear_migrations()
    SaveManager.clear_schema_migrations()
    yield
    StorySnapshot.clear_migrations()
    SaveManager.clear_schema_migrations()


def test_story_snapshot_version_declaration() -> None:
    snap = StorySnapshot(
        current_scene="scene_1",
        beat_index=0,
        call_stack=(),
        variables={"coins": 10},
        visited_scenes=("scene_1",),
    )
    assert snap.version == 1
    d = snap.to_dict()
    assert d["version"] == 1

    restored = StorySnapshot.from_dict(d)
    assert restored.version == 1

    snap_v2 = StorySnapshot(
        current_scene="scene_1",
        beat_index=0,
        call_stack=(),
        variables={"coins": 10},
        visited_scenes=("scene_1",),
        version=2,
    )
    assert snap_v2.version == 2
    assert snap_v2.to_dict()["version"] == 2


def test_story_snapshot_migration() -> None:
    def migrate_v1_to_v2(data: dict) -> dict:
        coins = data["variables"].pop("coins", 0)
        data["variables"]["currency"] = {"gold": coins}
        data["version"] = 2
        return data

    StorySnapshot.register_migration(1, migrate_v1_to_v2)
    old_dict = {
        "version": 1,
        "current_scene": "intro",
        "beat_index": 1,
        "call_stack": [],
        "variables": {"coins": 50},
        "visited_scenes": ["intro"],
    }
    snap = StorySnapshot.from_dict(old_dict)
    assert snap.version == 2
    assert snap.variables["currency"] == {"gold": 50}
    assert "coins" not in snap.variables


def test_story_snapshot_non_monotonic_migration() -> None:
    def bad_migration(data: dict) -> dict:
        return data  # version remains 1

    StorySnapshot.register_migration(1, bad_migration)
    with pytest.raises(ValueError) as ctx:
        StorySnapshot.from_dict({"version": 1}, target_version=2)
    assert "monotonically" in str(ctx.value).lower()


def test_save_data_version_declaration() -> None:
    cp = Checkpoint(
        story={"current_scene": "start", "version": 1},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )
    meta = SaveMetadata(
        slot_name="test_slot",
        timestamp="2026-10-22T00:00:00",
        scene_id="start",
        scene_name="Start",
        dialogue_snippet="Hello",
    )
    save_data = SaveData(metadata=meta, checkpoint=cp)
    assert save_data.version == 2
    d = save_data.to_dict()
    assert d["version"] == 2
    assert d["metadata"]["version"] == 2

    restored = SaveData.from_dict(d)
    assert restored.version == 2
    assert restored.metadata.version == 2


def test_load_slot_unversioned_legacy_auto_upgrade(tmp_path: Path) -> None:
    from eager_core.storage import atomic_write_json

    manager = SaveManager(tmp_path)
    legacy_data = {
        "metadata": {
            "slot_name": "legacy",
            "timestamp": "2026-10-22T00:00:00",
            "scene_id": "intro",
            "scene_name": "Intro",
            "dialogue_snippet": "Legacy",
            "playtime_seconds": 0.0,
        },
        "checkpoint": {
            "story": {"current_scene": "intro"},
            "visual": {"layer": "bg"},
            "audio": {},
            "backlog_len": 0,
            "ui": {},
        },
    }
    slot_file = tmp_path / "legacy.json"
    atomic_write_json(slot_file, legacy_data)

    cp = manager.load_slot("legacy")
    assert cp is not None
    assert cp.story.get("current_scene") == "intro"
    assert cp.visual.get("layer") == "bg"


def test_load_slot_with_registered_migration(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path, target_version=1)
    cp = Checkpoint(
        story={"current_scene": "hallway", "version": 1},
        visual={"sprites": ["hero"]},
        audio={},
        backlog_len=0,
        ui={},
    )
    manager.save_slot("slot_1", cp)

    def migrate_v1_to_v2(data: dict) -> dict:
        sprites = data["checkpoint"]["visual"].get("sprites", [])
        data["checkpoint"]["visual"]["entities"] = [{"name": s, "scale": 1.0} for s in sprites]
        data["version"] = 2
        return data

    manager.register_migration(1, migrate_v1_to_v2)

    loaded = manager.load_slot("slot_1", target_version=2)
    assert loaded is not None
    entities = loaded.visual.get("entities")
    assert entities == [{"name": "hero", "scale": 1.0}]


def test_load_slot_v1_auto_migrates_to_v2_by_default(tmp_path: Path) -> None:
    # Save a v1 slot explicitly
    cp = Checkpoint(
        story={"current_scene": "intro", "version": 1},
        visual={"sprites": ["hero"]},
        audio={},
        backlog_len=0,
        ui={"text": "V1 save"},
    )
    SaveManager(tmp_path, target_version=1).save_slot("v1_slot", cp)

    # Load with default SaveManager (target_version=2)
    default_manager = SaveManager(tmp_path)
    assert default_manager.target_version == 2
    loaded = default_manager.load_slot("v1_slot")
    assert loaded is not None
    assert loaded.story.get("current_scene") == "intro"
    meta = default_manager.get_slot_metadata("v1_slot")
    assert meta is not None
    assert meta.dialogue_snippet == "V1 save"



def test_load_slot_with_migration_hook_arg(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path, target_version=1)
    cp = Checkpoint(
        story={"current_scene": "room", "version": 1},
        visual={"lighting": "dark"},
        audio={},
        backlog_len=0,
        ui={},
    )
    manager.save_slot("slot_hook", cp)

    def custom_hook(data: dict, src_v: int, tgt_v: int) -> dict:
        assert src_v == 1
        assert tgt_v == 2
        data["checkpoint"]["visual"]["lighting"] = "ambient"
        data["version"] = tgt_v
        return data

    loaded = manager.load_slot("slot_hook", target_version=2, migration_hook=custom_hook)
    assert loaded is not None
    assert loaded.visual.get("lighting") == "ambient"


def test_load_slot_with_manager_migration_hook(tmp_path: Path) -> None:
    def hook(data: dict, src_v: int, tgt_v: int) -> dict:
        data["checkpoint"]["story"]["hook_ran"] = True
        data["version"] = tgt_v
        return data

    manager = SaveManager(tmp_path, target_version=2, migration_hook=hook)
    cp = Checkpoint(
        story={"current_scene": "room", "version": 1},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )
    SaveManager(tmp_path, target_version=1).save_slot("slot_inst", cp)

    loaded = manager.load_slot("slot_inst")
    assert loaded is not None
    assert loaded.story["hook_ran"] is True


def test_load_slot_newer_version_raises_save_migration_error(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path, target_version=1)
    cp = Checkpoint(
        story={"current_scene": "room"},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )
    SaveManager(tmp_path, target_version=3).save_slot("slot_future", cp)

    with pytest.raises(SaveMigrationError) as ctx:
        manager.load_slot("slot_future")
    assert "newer than target" in str(ctx.value)


def test_load_slot_missing_migration_raises_save_migration_error(tmp_path: Path) -> None:
    manager = SaveManager(tmp_path, target_version=3)
    cp = Checkpoint(
        story={"current_scene": "room", "version": 1},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )
    SaveManager(tmp_path, target_version=1).save_slot("slot_gap", cp)

    # target_version is 3, but no migration registered for v1
    with pytest.raises(SaveMigrationError) as ctx:
        manager.load_slot("slot_gap")
    assert "No migration registered" in str(ctx.value)


def test_quickload_and_autoload_with_migration(tmp_path: Path) -> None:
    def hook(data: dict, src_v: int, tgt_v: int) -> dict:
        data["checkpoint"]["migrated"] = True
        data["version"] = tgt_v
        return data

    manager = SaveManager(tmp_path, target_version=2, migration_hook=hook)
    cp = Checkpoint(
        story={"current_scene": "room", "version": 1},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )
    # Quicksave at v1
    SaveManager(tmp_path, target_version=1).quicksave(cp)
    SaveManager(tmp_path, target_version=1).autosave(cp)

    # quickload & autoload through manager (target_version=2)
    loaded_quick = manager.quickload()
    assert loaded_quick is not None
    assert loaded_quick.story is not None

    loaded_auto = manager.autoload()
    assert loaded_auto is not None
