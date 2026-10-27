"""Unit tests for state management, variable storage, snapshot serialization, and save system."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import eager_script
from eager_core.input import InputAction

from eager_runtime import (
    CallFrame,
    ChoicePromptEvent,
    DialogueEvent,
    GameSession,
    InputPromptEvent,
    PersistentData,
    Preferences,
    SaveManager,
    SceneEnterEvent,
    SceneExitEvent,
    StoryRuntimeError,
    StorySnapshot,
    StoryVM,
)
from eager_runtime.saves import SaveData, SaveMetadata, SaveMigrationError
from eager_runtime.state import Checkpoint

SAMPLE_SCRIPT = """
## Scene 1 --- scene_1
Narrator: Beat 1
Alice: Beat 2
Bob: Beat 3
> scene_2

## Scene 2 --- scene_2
Narrator: Beat 4
"""


class TestStateAndSave(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(SAMPLE_SCRIPT)

    def test_variable_get_and_set(self) -> None:
        vm = StoryVM(self.graph)
        vm.set_variable("player_name", "Hero")
        vm.set_variable("gold", 150)
        vm.set_variable("has_sword", True)

        self.assertEqual(vm.get_variable("player_name"), "Hero")
        self.assertEqual(vm.get_variable("gold"), 150)
        self.assertTrue(vm.get_variable("has_sword"))
        self.assertIsNone(vm.get_variable("unknown_var"))
        self.assertEqual(vm.get_variable("unknown_var", default=42), 42)

    def test_snapshot_serialization(self) -> None:
        snapshot = StorySnapshot(
            current_scene="scene_1",
            beat_index=2,
            call_stack=(CallFrame(scene_id="main", beat_index=1),),
            variables={"hp": 100, "inventory": ["potion"]},
            visited_scenes=("main", "scene_1"),
        )

        d = snapshot.to_dict()
        self.assertEqual(d["current_scene"], "scene_1")
        self.assertEqual(d["beat_index"], 2)
        self.assertEqual(len(d["call_stack"]), 1)
        self.assertEqual(d["call_stack"][0]["scene_id"], "main")
        self.assertEqual(d["variables"]["hp"], 100)

        # JSON round-trip
        json_str = snapshot.to_json(indent=2)
        parsed = StorySnapshot.from_json(json_str)
        self.assertEqual(snapshot, parsed)

    def test_save_and_load_restoration(self) -> None:
        vm = StoryVM(self.graph)
        vm.set_variable("karma", 10)

        # Step 1: enter scene_1
        vm.step()
        # Step 2: Beat 1
        vm.step()
        # Step 3: Beat 2 (Alice)
        evt = vm.step()
        assert isinstance(evt, DialogueEvent)
        self.assertEqual(evt.speaker, "Alice")

        # Save mid-scene
        saved_snapshot = vm.save()
        self.assertEqual(saved_snapshot.current_scene, "scene_1")
        self.assertEqual(saved_snapshot.variables["karma"], 10)

        # Continue playing further
        vm.set_variable("karma", -5)
        vm.step()  # Bob
        vm.step()  # Jump to scene_2
        vm.step()  # Enter scene_2

        self.assertEqual(vm.current_scene_id, "scene_2")
        self.assertEqual(vm.get_variable("karma"), -5)

        # Now restore saved state
        vm.load(saved_snapshot)
        self.assertEqual(vm.current_scene_id, "scene_1")
        self.assertEqual(vm.get_variable("karma"), 10)

        # Next beat should resume right at Bob's beat!
        next_evt = vm.step()
        assert isinstance(next_evt, DialogueEvent)
        self.assertEqual(next_evt.speaker, "Bob")

    def test_load_invalid_scene_raises_error(self) -> None:
        vm = StoryVM(self.graph)
        bad_snapshot = StorySnapshot(
            current_scene="non_existent_scene",
            beat_index=0,
            call_stack=(),
            variables={},
            visited_scenes=(),
        )

        with self.assertRaises(StoryRuntimeError):
            vm.load(bad_snapshot)

    def test_save_at_choice_load_preserves_choice(self) -> None:
        script = """
## Scene 1 --- scene_1
Narrator: Before choice
? Option A (opt_a)
? Option B (opt_b)

## Option A --- opt_a
Narrator: Picked A
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # SceneEnter
        vm.step()  # Narrator: Before choice
        choice_evt = vm.step()  # ChoicePromptEvent
        self.assertIsInstance(choice_evt, ChoicePromptEvent)
        self.assertIsNotNone(vm.pending_choice)

        # Save while choice is pending
        snap = vm.save()
        self.assertIsNotNone(snap.pending_choice_beat)

        # Create new VM or load snapshot
        vm2 = StoryVM(graph)
        vm2.load(snap)
        self.assertIsNotNone(vm2.pending_choice)
        step_evt = vm2.step()
        assert isinstance(step_evt, ChoicePromptEvent)
        self.assertIsInstance(step_evt, ChoicePromptEvent)
        self.assertEqual(len(step_evt.options), 2)

        # Can choose after load!
        vm2.choose(0)
        self.assertEqual(vm2.current_scene_id, "opt_a")

    def test_save_after_jump_exit_load_preserves_transition(self) -> None:
        vm = StoryVM(self.graph)
        vm.step()  # Enter scene_1
        vm.step()  # Narrator
        vm.step()  # Alice
        vm.step()  # Bob
        exit_evt = vm.step()  # Jump to scene_2 (SceneExitEvent)
        self.assertIsInstance(exit_evt, SceneExitEvent)

        # Save right after jump beat was executed
        snap = vm.save()
        self.assertEqual(snap.next_transition_target, "scene_2")

        vm2 = StoryVM(self.graph)
        vm2.load(snap)
        enter_evt = vm2.step()
        assert isinstance(enter_evt, SceneEnterEvent)
        self.assertIsInstance(enter_evt, SceneEnterEvent)
        self.assertEqual(enter_evt.scene_id, "scene_2")

    def test_prng_state_restoration_mersenne_twister(self) -> None:
        vm1 = StoryVM(self.graph)
        # Consume some random numbers to advance the MT state
        _ = [vm1._rng.random() for _ in range(10)]

        # Save snapshot and round-trip through JSON (which converts inner tuples to lists)
        snap = vm1.save()
        self.assertIsNotNone(snap.rng_state)
        json_str = snap.to_json()
        restored_snap = StorySnapshot.from_json(json_str)

        # Confirm that JSON deserialized the MT state vector as a list
        assert restored_snap.rng_state is not None
        self.assertIsInstance(restored_snap.rng_state[1], list)

        # Generate expected future random stream from original VM
        expected_next = [vm1._rng.random() for _ in range(10)]

        # Load snapshot into new VM - should recursively restore nested tuples for setstate
        vm2 = StoryVM(self.graph)
        vm2.load(restored_snap)

        # Verify new VM generates exactly identical numbers in sequence
        actual_next = [vm2._rng.random() for _ in range(10)]
        self.assertEqual(expected_next, actual_next)

    def test_load_pending_choice_and_input_beat_id(self) -> None:
        src = """
## Start --- start
Alice: Before choices
? Option A (a)
? Option B (b)

## Scene A --- a
Alice: Picked A
~ input hero_name What is your name?
Alice: Hero is [hero_name]
"""
        graph = eager_script.parse_graph(src)
        vm = StoryVM(graph)
        vm.step()  # SceneEnter
        vm.step()  # Alice: Before choices
        choice_evt = vm.step()  # ChoicePromptEvent
        assert isinstance(choice_evt, ChoicePromptEvent)
        self.assertIsInstance(choice_evt, ChoicePromptEvent)
        orig_choice_beat_id = choice_evt.beat_id

        # Save while choice is pending and restore into new VM
        snap = vm.save()
        vm2 = StoryVM(graph)
        vm2.load(snap)
        assert vm2.pending_choice is not None
        self.assertIsNotNone(vm2.pending_choice)
        self.assertEqual(vm2.pending_choice.beat_id, orig_choice_beat_id)

        # Proceed with choice
        vm.choose(0)
        vm.step()  # SceneEnter Scene A
        vm.step()  # Alice: Picked A
        input_evt = vm.step()  # InputPromptEvent
        assert isinstance(input_evt, InputPromptEvent)
        self.assertIsInstance(input_evt, InputPromptEvent)
        orig_input_beat_id = input_evt.beat_id
        self.assertIsNotNone(orig_input_beat_id)

        # Save while input is pending and restore into new VM
        snap_input = vm.save()
        vm3 = StoryVM(graph)
        vm3.load(snap_input)
        assert vm3.pending_input is not None
        self.assertIsNotNone(vm3.pending_input)
        self.assertEqual(vm3.pending_input.beat_id, orig_input_beat_id)
        self.assertEqual(vm3.pending_input.prompt, input_evt.prompt)
        self.assertEqual(vm3.pending_input.var_name, input_evt.var_name)


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


class TestSaveSystem(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.save_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_manager_crud(self):
        manager = SaveManager(self.save_dir)
        cp = Checkpoint(
            story={"current_scene": "start", "variables": {"gold": 100}},
            visual={},
            audio={},
            backlog_len=1,
            ui={"text": "Welcome to town!"},
        )

        # Save slot
        meta = manager.save_slot("slot_1", cp)
        self.assertEqual(meta.slot_name, "slot_1")
        self.assertEqual(meta.scene_id, "start")
        self.assertEqual(meta.dialogue_snippet, "Welcome to town!")

        # List slots
        slots = manager.list_slots()
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0].slot_name, "slot_1")

        # Load slot
        loaded = manager.load_slot("slot_1")
        assert loaded is not None
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.story["variables"]["gold"], 100)

        # Delete slot
        self.assertTrue(manager.delete_slot("slot_1"))
        self.assertIsNone(manager.load_slot("slot_1"))
        self.assertEqual(len(manager.list_slots()), 0)

    def test_save_and_load_active_input_prompt(self):
        manager = SaveManager(self.save_dir)
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
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.active_input_prompt, prompt_data)

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
        self.assertEqual(d["checkpoint"]["active_input_prompt"], prompt_data)
        restored = SaveData.from_dict(d)
        self.assertEqual(restored.checkpoint.active_input_prompt, prompt_data)

    def test_quicksave_and_autosave(self):
        manager = SaveManager(self.save_dir)
        cp = Checkpoint(
            story={"current_scene": "checkpoint"},
            visual={},
            audio={},
            backlog_len=0,
            ui={},
        )

        meta = manager.quicksave(cp)
        self.assertEqual(meta.slot_name, "quick_1")
        ql = manager.quickload()
        assert ql is not None
        self.assertIsNotNone(ql)
        self.assertEqual(ql.story["current_scene"], "checkpoint")

        meta_auto = manager.autosave(cp)
        self.assertEqual(meta_auto.slot_name, "auto_1")
        al = manager.autoload()
        assert al is not None
        self.assertIsNotNone(al)
        self.assertEqual(al.story["current_scene"], "checkpoint")

    def test_quicksave_circular_rotation(self):
        import time

        manager = SaveManager(self.save_dir, max_quicksaves=3)
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

        self.assertEqual(m1.slot_name, "quick_1")
        self.assertEqual(m2.slot_name, "quick_2")
        self.assertEqual(m3.slot_name, "quick_3")

        # Quickload should load latest (scene_3)
        ql = manager.quickload()
        assert ql is not None
        self.assertIsNotNone(ql)
        self.assertEqual(ql.story["current_scene"], "scene_3")

        # 2. 4th save should rotate and overwrite oldest (quick_1)
        m4 = manager.quicksave(checkpoints[3])
        time.sleep(0.005)
        self.assertEqual(m4.slot_name, "quick_1")
        ql = manager.quickload()
        assert ql is not None
        self.assertIsNotNone(ql)
        self.assertEqual(ql.story["current_scene"], "scene_4")

        # 3. 5th save should rotate and overwrite next oldest (quick_2)
        m5 = manager.quicksave(checkpoints[4])
        time.sleep(0.005)
        self.assertEqual(m5.slot_name, "quick_2")
        ql = manager.quickload()
        assert ql is not None
        self.assertIsNotNone(ql)
        self.assertEqual(ql.story["current_scene"], "scene_5")

    def test_autosave_circular_rotation(self):
        import time

        manager = SaveManager(self.save_dir, max_autosaves=2)
        cp1 = Checkpoint(story={"current_scene": "auto_scene_1"}, visual={}, audio={}, backlog_len=0, ui={})
        cp2 = Checkpoint(story={"current_scene": "auto_scene_2"}, visual={}, audio={}, backlog_len=0, ui={})
        cp3 = Checkpoint(story={"current_scene": "auto_scene_3"}, visual={}, audio={}, backlog_len=0, ui={})

        m1 = manager.autosave(cp1)
        time.sleep(0.005)
        m2 = manager.autosave(cp2)
        time.sleep(0.005)
        self.assertEqual(m1.slot_name, "auto_1")
        self.assertEqual(m2.slot_name, "auto_2")

        al = manager.autoload()
        assert al is not None
        self.assertIsNotNone(al)
        self.assertEqual(al.story["current_scene"], "auto_scene_2")

        # Overwrite oldest (auto_1)
        m3 = manager.autosave(cp3)
        self.assertEqual(m3.slot_name, "auto_1")
        al = manager.autoload()
        assert al is not None
        self.assertIsNotNone(al)
        self.assertEqual(al.story["current_scene"], "auto_scene_3")

    def test_legacy_unindexed_quick_and_auto_slots(self):
        manager = SaveManager(self.save_dir)
        cp = Checkpoint(story={"current_scene": "legacy_quick"}, visual={}, audio={}, backlog_len=0, ui={})
        manager.save_slot("quick", cp)
        ql_legacy = manager.quickload()
        assert ql_legacy is not None
        self.assertEqual(ql_legacy.story["current_scene"], "legacy_quick")

        cp_auto = Checkpoint(story={"current_scene": "legacy_auto"}, visual={}, audio={}, backlog_len=0, ui={})
        manager.save_slot("auto", cp_auto)
        al_legacy = manager.autoload()
        assert al_legacy is not None
        self.assertEqual(al_legacy.story["current_scene"], "legacy_auto")

        # Quicksaving now should write to quick_1 and become the latest
        cp_new = Checkpoint(story={"current_scene": "new_quick_1"}, visual={}, audio={}, backlog_len=0, ui={})
        manager.quicksave(cp_new)
        ql_new = manager.quickload()
        assert ql_new is not None
        self.assertEqual(ql_new.story["current_scene"], "new_quick_1")

    def test_corrupted_persistent_data_backup(self):
        p_path = self.save_dir / "persistent.json"
        p_path.write_text("{this is corrupted non-json content!!", encoding="utf-8")

        # Loading corrupted file should not crash and should create backup
        p = PersistentData(p_path)
        self.assertEqual(len(p), 0)

        bak_path = self.save_dir / "persistent.json.corrupt.bak"
        self.assertTrue(bak_path.exists())
        self.assertEqual(bak_path.read_text(encoding="utf-8"), "{this is corrupted non-json content!!")

        # Now saving new persistent data should succeed and write valid JSON
        p["recovered"] = True
        p.save()
        p2 = PersistentData(p_path)
        self.assertEqual(p2["recovered"], True)

    def test_load_slot_corrupted_json_creates_backup(self) -> None:
        """Verify SaveManager.load_slot generates slot.json.corrupt.bak on corrupt JSON."""
        manager = SaveManager(self.save_dir)
        slot_path = self.save_dir / "slot_corrupt.json"
        corrupt_content = '{"version": 1, "checkpoint": {broken json content...'
        slot_path.write_text(corrupt_content, encoding="utf-8")

        # Loading corrupt slot must return None without raising unhandled JSONDecodeError
        loaded = manager.load_slot("slot_corrupt")
        self.assertIsNone(loaded)

        # Must generate .corrupt.bak backup with exact content
        bak_path = self.save_dir / "slot_corrupt.json.corrupt.bak"
        self.assertTrue(bak_path.exists())
        self.assertEqual(bak_path.read_text(encoding="utf-8"), corrupt_content)

    def test_load_slot_binary_garbage_creates_backup(self) -> None:
        """Verify SaveManager.load_slot handles non-UTF8 binary corruption."""
        manager = SaveManager(self.save_dir)
        slot_path = self.save_dir / "slot_bin.json"
        raw_garbage = b"\x00\xff\xfe\x00\xaa\xbb\xcc\xdd"
        slot_path.write_bytes(raw_garbage)

        loaded = manager.load_slot("slot_bin")
        self.assertIsNone(loaded)

        bak_path = self.save_dir / "slot_bin.json.corrupt.bak"
        self.assertTrue(bak_path.exists())
        self.assertEqual(bak_path.read_bytes(), raw_garbage)

    def test_save_slot_overwrites_corrupt_slot_retaining_backup(self) -> None:
        """Verify player can overwrite a corrupted slot while retaining the backup for diagnostics."""
        manager = SaveManager(self.save_dir)
        slot_path = self.save_dir / "slot_overwrite.json"
        slot_path.write_text("{corrupt garbage", encoding="utf-8")

        # Trigger backup via load_slot
        self.assertIsNone(manager.load_slot("slot_overwrite"))
        bak_path = self.save_dir / "slot_overwrite.json.corrupt.bak"
        self.assertTrue(bak_path.exists())

        # Now save valid checkpoint into the same slot
        cp = Checkpoint(story={"current_scene": "recovered"}, visual={}, audio={}, backlog_len=0, ui={})
        manager.save_slot("slot_overwrite", cp)

        # Valid slot can be reloaded
        reloaded = manager.load_slot("slot_overwrite")
        assert reloaded is not None
        self.assertEqual(reloaded.story["current_scene"], "recovered")

        # Backup remains on disk
        self.assertTrue(bak_path.exists())
        self.assertEqual(bak_path.read_text(encoding="utf-8"), "{corrupt garbage")

    def test_non_dict_json_root(self) -> None:
        """Non-dict JSON roots (list, str, int) must safely return None and create .corrupt.bak."""
        test_cases: list[tuple[str, str]] = [
            ("slot_array", "[1, 2, 3]"),
            ("slot_string", '"plain string root"'),
            ("slot_number", "42"),
        ]
        manager = SaveManager(self.save_dir)
        for slot_name, payload in test_cases:
            slot_path = self.save_dir / f"{slot_name}.json"
            slot_path.write_text(payload, encoding="utf-8")

            res = manager.load_slot(slot_name)
            self.assertIsNone(res)

            bak_path = self.save_dir / f"{slot_name}.json.corrupt.bak"
            self.assertTrue(bak_path.exists(), f"Backup missing for non-dict root: {slot_name}")
            self.assertEqual(bak_path.read_text(encoding="utf-8"), payload)

    def test_list_slots_skips_corrupted_metadata_cleanly(self) -> None:
        """list_slots() and get_slot_metadata() must cleanly handle corrupt metadata without crashing."""
        manager = SaveManager(self.save_dir)

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
            slot_path = self.save_dir / f"{slot_name}.json"
            slot_path.write_text(payload, encoding="utf-8")

        # get_slot_metadata returns None for corrupted slots without crashing
        for slot_name, _ in corrupt_cases:
            meta = manager.get_slot_metadata(slot_name)
            self.assertIsNone(meta, f"Expected None for get_slot_metadata({slot_name})")

        # get_slot_metadata returns SaveMetadata for valid slots
        valid_meta = manager.get_slot_metadata("valid_1")
        self.assertIsNotNone(valid_meta)
        assert valid_meta is not None
        self.assertIsInstance(valid_meta, SaveMetadata)
        self.assertEqual(valid_meta.slot_name, "valid_1")

        # list_slots() returns only valid slots, cleanly skipping corrupt ones
        slots = manager.list_slots()
        self.assertEqual(len(slots), 2)
        slot_names = {s.slot_name for s in slots}
        self.assertEqual(slot_names, {"valid_1", "valid_2"})
        self.assertTrue(all(isinstance(s, SaveMetadata) for s in slots))


    def test_persistent_data(self):
        p_path = self.save_dir / "persistent.json"
        p = PersistentData(p_path)
        p["seen_endings"] = ["good_end"]
        p.unlocked_gallery = True
        p.save()

        # Reload in new instance
        p2 = PersistentData(p_path)
        self.assertEqual(p2["seen_endings"], ["good_end"])
        self.assertTrue(p2.unlocked_gallery)

    def test_gallery_and_achievements(self):
        pfile = self.save_dir / "persistent_gallery.json"
        p = PersistentData(pfile)

        self.assertFalse(p.is_gallery_unlocked("cg_ending_1"))
        p.unlock_gallery("cg_ending_1")
        self.assertTrue(p.is_gallery_unlocked("cg_ending_1"))

        self.assertFalse(p.has_achievement("ach_first_win"))
        p.unlock_achievement("ach_first_win")
        self.assertTrue(p.has_achievement("ach_first_win"))

        # Reload from disk
        p2 = PersistentData(pfile)
        self.assertTrue(p2.is_gallery_unlocked("cg_ending_1"))
        self.assertTrue(p2.has_achievement("ach_first_win"))

    def test_preferences(self):
        pref_path = self.save_dir / "preferences.json"
        pref = Preferences(text_speed=100.0, music_volume=0.5, fullscreen=True)
        pref.save(pref_path)

        loaded = Preferences.load(pref_path)
        self.assertEqual(loaded.text_speed, 100.0)
        self.assertEqual(loaded.music_volume, 0.5)
        self.assertTrue(loaded.fullscreen)
        self.assertEqual(loaded.sfx_volume, 1.0)  # default preserved

    def test_game_session_save_and_load(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".es", delete=False) as f:
            f.write(PERSISTENCE_SAMPLE_SCRIPT)
            script_path = Path(f.name)

        try:
            session = GameSession(script_path)
            session.advance()  # Dialogue beat: Alice: Welcome!
            session.advance()  # Choice prompt beat
            self.assertIsNotNone(session.active_choice_prompt)

            # Save game to slot 1
            session.save_game("slot_1")

            # Make choice
            session.choose(0)
            self.assertEqual(session.vm.current_scene_id, "path_a")

            # Load back slot 1
            self.assertTrue(session.load_game("slot_1"))
            self.assertEqual(session.vm.current_scene_id, "start")
            self.assertIsNotNone(session.active_choice_prompt)
        finally:
            script_path.unlink(missing_ok=True)

    def test_game_session_set_language_custom_save_dir(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".es", delete=False) as f:
            f.write(PERSISTENCE_SAMPLE_SCRIPT)
            script_path = Path(f.name)

        try:
            custom_dir = self.save_dir / "custom_pref_save"
            custom_dir.mkdir(parents=True, exist_ok=True)
            session = GameSession(script_path, save_dir=custom_dir)
            session.set_language("ja")
            pref_file = custom_dir / "preferences.json"
            self.assertTrue(pref_file.exists())
            saved_pref = Preferences.load(pref_file)
            self.assertEqual(saved_pref.language, "ja")
        finally:
            script_path.unlink(missing_ok=True)

    def test_game_session_playtime_and_screenshot(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".es", delete=False) as f:
            f.write(PERSISTENCE_SAMPLE_SCRIPT)
            script_path = Path(f.name)

        try:
            custom_dir = self.save_dir / "playtime_test"
            custom_dir.mkdir(parents=True, exist_ok=True)
            session = GameSession(script_path, save_dir=custom_dir)

            # Playtime starts at 0.0
            self.assertEqual(session.playtime, 0.0)

            # Update accumulates dt
            session.update(2.5)
            session.update(3.5)
            self.assertAlmostEqual(session.playtime, 6.0)

            # Save preserves playtime in metadata
            meta = session.save_game("play_slot")
            self.assertAlmostEqual(meta.playtime_seconds, 6.0)
            self.assertEqual(meta.playtime_formatted, "00:06")

            # Loading slot restores playtime
            session2 = GameSession(script_path, save_dir=custom_dir)
            self.assertEqual(session2.playtime, 0.0)
            self.assertTrue(session2.load_game("play_slot"))
            self.assertAlmostEqual(session2.playtime, 6.0)

            # Screenshot handling with renderer.save_frame()
            mock_renderer = MagicMock()
            session.renderer = mock_renderer
            shot_path = session.handle_input(InputAction.SCREENSHOT)
            self.assertTrue(mock_renderer.save_frame.called)
            self.assertEqual(shot_path.parent, custom_dir / "screenshots")
            self.assertTrue(shot_path.name.endswith(".png"))

            # Headless screenshot fallback without renderer creates real valid PNG
            session_headless = GameSession(script_path, save_dir=custom_dir, headless=True)
            shot_headless = session_headless.handle_input(InputAction.SCREENSHOT)
            self.assertTrue(shot_headless.is_file())
            self.assertGreater(shot_headless.stat().st_size, 0)
        finally:
            script_path.unlink(missing_ok=True)


class TestSaveSchemaMigration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.save_dir = Path(self.temp_dir.name)
        StorySnapshot.clear_migrations()
        SaveManager.clear_schema_migrations()

    def tearDown(self) -> None:
        StorySnapshot.clear_migrations()
        SaveManager.clear_schema_migrations()
        self.temp_dir.cleanup()

    def test_story_snapshot_version_declaration(self) -> None:
        snap = StorySnapshot(
            current_scene="scene_1",
            beat_index=0,
            call_stack=(),
            variables={"coins": 10},
            visited_scenes=("scene_1",),
        )
        self.assertEqual(snap.version, 1)
        d = snap.to_dict()
        self.assertEqual(d["version"], 1)

        restored = StorySnapshot.from_dict(d)
        self.assertEqual(restored.version, 1)

        snap_v2 = StorySnapshot(
            current_scene="scene_1",
            beat_index=0,
            call_stack=(),
            variables={"coins": 10},
            visited_scenes=("scene_1",),
            version=2,
        )
        self.assertEqual(snap_v2.version, 2)
        d_v2 = snap_v2.to_dict()
        self.assertEqual(d_v2["version"], 2)

    def test_story_snapshot_migration(self) -> None:
        def migrate_v1_to_v2(data: dict) -> dict:
            # Upgrade variable format: coins -> currency: {"gold": coins}
            coins = data["variables"].pop("coins", 0)
            data["variables"]["currency"] = {"gold": coins}
            data["version"] = 2
            return data

        StorySnapshot.register_migration(1, migrate_v1_to_v2)
        try:
            # Older snapshot dict at version 1
            old_dict = {
                "version": 1,
                "current_scene": "intro",
                "beat_index": 1,
                "call_stack": [],
                "variables": {"coins": 50},
                "visited_scenes": ["intro"],
            }
            # Restoring should run migration
            snap = StorySnapshot.from_dict(old_dict)
            self.assertEqual(snap.version, 2)
            self.assertEqual(snap.variables["currency"], {"gold": 50})
            self.assertNotIn("coins", snap.variables)
        finally:
            StorySnapshot.clear_migrations()

    def test_story_snapshot_non_monotonic_migration(self) -> None:
        StorySnapshot.clear_migrations()

        # Register buggy migration that doesn't advance version
        def bad_migration(data):
            return data  # version remains 1

        StorySnapshot.register_migration(1, bad_migration)

        with self.assertRaises(ValueError) as ctx:
            StorySnapshot.from_dict({"version": 1}, target_version=2)
        self.assertIn("monotonically", str(ctx.exception))

        StorySnapshot.clear_migrations()


    def test_save_data_version_declaration(self) -> None:
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
        self.assertEqual(save_data.version, 1)
        d = save_data.to_dict()
        self.assertEqual(d["version"], 1)
        self.assertEqual(d["metadata"]["version"], 2)

        restored = SaveData.from_dict(d)
        self.assertEqual(restored.version, 1)
        self.assertEqual(restored.metadata.version, 2)

    def test_load_slot_unversioned_legacy_auto_upgrade(self) -> None:
        from eager_core.storage import atomic_write_json

        manager = SaveManager(self.save_dir)
        # Legacy save file with NO "version" field
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
        slot_file = self.save_dir / "legacy.json"
        atomic_write_json(slot_file, legacy_data)

        # Loading legacy save should succeed and auto-upgrade to version 1
        cp = manager.load_slot("legacy")
        assert cp is not None
        self.assertIsNotNone(cp)
        self.assertEqual(cp.story.get("current_scene"), "intro")
        self.assertEqual(cp.visual.get("layer"), "bg")

    def test_load_slot_with_registered_migration(self) -> None:
        manager = SaveManager(self.save_dir)
        cp = Checkpoint(
            story={"current_scene": "hallway", "version": 1},
            visual={"sprites": ["hero"]},
            audio={},
            backlog_len=0,
            ui={},
        )
        manager.save_slot("slot_1", cp)

        # Register migration v1 -> v2
        def migrate_v1_to_v2(data: dict) -> dict:
            # Upgrade sprites representation
            sprites = data["checkpoint"]["visual"].get("sprites", [])
            data["checkpoint"]["visual"]["entities"] = [{"name": s, "scale": 1.0} for s in sprites]
            data["version"] = 2
            return data

        manager.register_migration(1, migrate_v1_to_v2)

        # Load with target_version=2
        loaded = manager.load_slot("slot_1", target_version=2)
        assert loaded is not None
        self.assertIsNotNone(loaded)
        entities = loaded.visual.get("entities")
        self.assertEqual(entities, [{"name": "hero", "scale": 1.0}])

    def test_load_slot_with_migration_hook_arg(self) -> None:
        manager = SaveManager(self.save_dir)
        cp = Checkpoint(
            story={"current_scene": "room", "version": 1},
            visual={"lighting": "dark"},
            audio={},
            backlog_len=0,
            ui={},
        )
        manager.save_slot("slot_hook", cp)

        # Provide custom migration hook to load_slot
        def custom_hook(data: dict, src_v: int, tgt_v: int) -> dict:
            self.assertEqual(src_v, 1)
            self.assertEqual(tgt_v, 2)
            data["checkpoint"]["visual"]["lighting"] = "ambient"
            data["version"] = tgt_v
            return data

        loaded = manager.load_slot("slot_hook", target_version=2, migration_hook=custom_hook)
        assert loaded is not None
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.visual.get("lighting"), "ambient")

    def test_load_slot_with_manager_migration_hook(self) -> None:
        def manager_hook(data: dict, src_v: int, tgt_v: int) -> dict:
            data["checkpoint"]["ui"]["theme"] = "dark"
            data["version"] = tgt_v
            return data

        manager = SaveManager(
            self.save_dir,
            target_version=2,
            migration_hook=manager_hook,
        )
        cp = Checkpoint(
            story={"current_scene": "room", "version": 1},
            visual={},
            audio={},
            backlog_len=0,
            ui={"theme": "default"},
        )
        # Save at v1 using an unupgraded manager
        SaveManager(self.save_dir, target_version=1).save_slot("slot_mgr", cp)

        loaded = manager.load_slot("slot_mgr")
        assert loaded is not None
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.ui.get("theme"), "dark")

    def test_load_slot_newer_version_raises_save_migration_error(self) -> None:
        from eager_core.storage import atomic_write_json

        manager = SaveManager(self.save_dir, target_version=1)
        future_save = {
            "version": 99,
            "metadata": {"slot_name": "future"},
            "checkpoint": {"story": {}, "visual": {}, "audio": {}, "backlog_len": 0, "ui": {}},
        }
        atomic_write_json(self.save_dir / "future.json", future_save)

        with self.assertRaises(SaveMigrationError) as ctx:
            manager.load_slot("future")
        self.assertIn("newer than target version", str(ctx.exception))

    def test_load_slot_missing_migration_raises_save_migration_error(self) -> None:
        manager = SaveManager(self.save_dir, target_version=3)
        cp = Checkpoint(
            story={"current_scene": "room", "version": 1},
            visual={},
            audio={},
            backlog_len=0,
            ui={},
        )
        SaveManager(self.save_dir, target_version=1).save_slot("slot_gap", cp)

        # target_version is 3, but no migration registered for v1
        with self.assertRaises(SaveMigrationError) as ctx:
            manager.load_slot("slot_gap")
        self.assertIn("No migration registered", str(ctx.exception))

    def test_quickload_and_autoload_with_migration(self) -> None:
        def hook(data: dict, src_v: int, tgt_v: int) -> dict:
            data["checkpoint"]["migrated"] = True
            data["version"] = tgt_v
            return data

        manager = SaveManager(self.save_dir, target_version=2, migration_hook=hook)
        cp = Checkpoint(
            story={"current_scene": "room", "version": 1},
            visual={},
            audio={},
            backlog_len=0,
            ui={},
        )
        # Quicksave at v1
        SaveManager(self.save_dir, target_version=1).quicksave(cp)
        SaveManager(self.save_dir, target_version=1).autosave(cp)

        # quickload & autoload through manager (target_version=2)
        loaded_quick = manager.quickload()
        assert loaded_quick is not None
        self.assertIsNotNone(loaded_quick)
        self.assertTrue(loaded_quick.story is not None)

        loaded_auto = manager.autoload()
        self.assertIsNotNone(loaded_auto)



