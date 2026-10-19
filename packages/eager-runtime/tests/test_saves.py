"""Tests for Phase 3: SaveManager, PersistentData, Preferences, and GameSession save/load."""

import tempfile
import unittest
from pathlib import Path

from eager_runtime import (
    GameSession,
    PersistentData,
    Preferences,
    SaveManager,
)
from eager_runtime.session import Checkpoint

SAMPLE_SCRIPT = """
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
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.story["variables"]["gold"], 100)

        # Delete slot
        self.assertTrue(manager.delete_slot("slot_1"))
        self.assertIsNone(manager.load_slot("slot_1"))
        self.assertEqual(len(manager.list_slots()), 0)

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
        self.assertIsNotNone(ql)
        self.assertEqual(ql.story["current_scene"], "checkpoint")

        meta_auto = manager.autosave(cp)
        self.assertEqual(meta_auto.slot_name, "auto_1")
        al = manager.autoload()
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
        self.assertIsNotNone(ql)
        self.assertEqual(ql.story["current_scene"], "scene_3")

        # 2. 4th save should rotate and overwrite oldest (quick_1)
        m4 = manager.quicksave(checkpoints[3])
        time.sleep(0.005)
        self.assertEqual(m4.slot_name, "quick_1")
        ql = manager.quickload()
        self.assertIsNotNone(ql)
        self.assertEqual(ql.story["current_scene"], "scene_4")

        # 3. 5th save should rotate and overwrite next oldest (quick_2)
        m5 = manager.quicksave(checkpoints[4])
        self.assertEqual(m5.slot_name, "quick_2")
        ql = manager.quickload()
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
        self.assertIsNotNone(al)
        self.assertEqual(al.story["current_scene"], "auto_scene_2")

        # Overwrite oldest (auto_1)
        m3 = manager.autosave(cp3)
        self.assertEqual(m3.slot_name, "auto_1")
        al = manager.autoload()
        self.assertIsNotNone(al)
        self.assertEqual(al.story["current_scene"], "auto_scene_3")

    def test_legacy_unindexed_quick_and_auto_slots(self):
        manager = SaveManager(self.save_dir)
        cp = Checkpoint(story={"current_scene": "legacy_quick"}, visual={}, audio={}, backlog_len=0, ui={})
        manager.save_slot("quick", cp)
        self.assertEqual(manager.quickload().story["current_scene"], "legacy_quick")

        cp_auto = Checkpoint(story={"current_scene": "legacy_auto"}, visual={}, audio={}, backlog_len=0, ui={})
        manager.save_slot("auto", cp_auto)
        self.assertEqual(manager.autoload().story["current_scene"], "legacy_auto")

        # Quicksaving now should write to quick_1 and become the latest
        cp_new = Checkpoint(story={"current_scene": "new_quick_1"}, visual={}, audio={}, backlog_len=0, ui={})
        manager.quicksave(cp_new)
        self.assertEqual(manager.quickload().story["current_scene"], "new_quick_1")

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
            f.write(SAMPLE_SCRIPT)
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
            f.write(SAMPLE_SCRIPT)
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


if __name__ == "__main__":
    unittest.main()
