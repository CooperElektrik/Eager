"""Unit tests for CheckpointHistory, interaction checkpoints, and narrative rollback."""

import unittest

import eager_script

from eager_runtime import (
    ChoicePromptEvent,
    DialogueEvent,
    GameSession,
    NarrationEvent,
    StoryVM,
)
from eager_runtime.state import Checkpoint, CheckpointHistory

SAMPLE_SCRIPT = """
## Room --- room
You wake up in a quiet room.
Alice: Are you ready to choose?
? Go left (left_room)
? Go right (right_room)

## Left Room --- left_room
Narrator: The left room is filled with books.

## Right Room --- right_room
Narrator: The right room is empty.
"""


class TestCheckpointHistory(unittest.TestCase):
    def test_checkpoint_history_push_pop_roll_forward(self) -> None:
        ch = CheckpointHistory(max_history=5)
        self.assertFalse(ch.can_rollback)
        self.assertFalse(ch.can_roll_forward)
        self.assertEqual(ch.depth, 0)

        cp1 = Checkpoint(story={"scene": "1"}, visual={}, audio={}, backlog_len=1, ui={})
        cp2 = Checkpoint(story={"scene": "2"}, visual={}, audio={}, backlog_len=2, ui={})

        ch.push(cp1)
        self.assertFalse(ch.can_rollback)  # depth is 1
        self.assertEqual(ch.depth, 1)

        ch.push(cp2)
        self.assertTrue(ch.can_rollback)  # depth is 2
        self.assertEqual(ch.depth, 2)
        self.assertEqual(ch.get_latest(), cp2)

        # Pop cp2 onto redo stack
        popped = ch.pop()
        self.assertEqual(popped, cp2)
        self.assertEqual(ch.depth, 1)
        self.assertFalse(ch.can_rollback)
        self.assertTrue(ch.can_roll_forward)

        # Roll forward restores cp2
        rf = ch.roll_forward()
        self.assertEqual(rf, cp2)
        self.assertEqual(ch.depth, 2)
        self.assertTrue(ch.can_rollback)
        self.assertFalse(ch.can_roll_forward)

    def test_checkpoint_history_max_capacity(self) -> None:
        ch = CheckpointHistory(max_history=3)
        for i in range(5):
            ch.push(Checkpoint(story={"i": i}, visual={}, audio={}, backlog_len=i, ui={}))

        self.assertEqual(ch.depth, 3)
        latest = ch.get_latest()
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertEqual(latest.story["i"], 4)

    def test_checkpoint_history_clear_and_clear_redo(self) -> None:
        ch = CheckpointHistory(max_history=5)
        cp1 = Checkpoint(story={"s": 1}, visual={}, audio={}, backlog_len=0, ui={})
        cp2 = Checkpoint(story={"s": 2}, visual={}, audio={}, backlog_len=0, ui={})
        ch.push(cp1)
        ch.push(cp2)
        ch.pop()
        self.assertTrue(ch.can_roll_forward)

        ch.clear_redo()
        self.assertFalse(ch.can_roll_forward)

        ch.clear()
        self.assertEqual(ch.depth, 0)
        self.assertFalse(ch.can_rollback)


class TestSessionRollback(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(SAMPLE_SCRIPT)
        self.session = GameSession(self.graph, headless=True)

    def test_step_by_step_session_rollback(self) -> None:
        # Step 1: Narration
        e1 = self.session.advance()
        self.assertIsInstance(e1, NarrationEvent)
        self.assertFalse(self.session.can_rollback)  # First checkpoint

        # Step 2: Dialogue
        e2 = self.session.advance()
        self.assertIsInstance(e2, DialogueEvent)
        self.assertTrue(self.session.can_rollback)

        # Rollback reverts to before e2 (Narration)
        self.assertTrue(self.session.rollback())
        self.assertEqual(self.session.director.ui_state.text, "You wake up in a quiet room.")

        # Roll forward re-applies e2 (Dialogue)
        self.assertTrue(self.session.roll_forward())
        self.assertEqual(self.session.director.ui_state.speaker, "Alice")
        self.assertEqual(self.session.director.ui_state.text, "Are you ready to choose?")

    def test_session_rollback_across_choice(self) -> None:
        # Advance through narration and dialogue to choice prompt
        self.session.advance()  # Narration
        self.session.advance()  # Dialogue
        e3 = self.session.advance()  # Choice prompt
        self.assertIsInstance(e3, ChoicePromptEvent)

        # Choose left_room (advances onto narration in left_room)
        self.session.choose(0)
        self.assertEqual(self.session.vm.current_scene_id, "left_room")
        self.assertEqual(self.session.director.ui_state.text, "The left room is filled with books.")

        # Rollback back to choice prompt
        self.assertTrue(self.session.rollback())
        self.assertIsNotNone(self.session.active_choice_prompt)

        # Choose right_room instead
        self.session.choose(1)
        self.assertEqual(self.session.vm.current_scene_id, "right_room")
        self.assertEqual(self.session.director.ui_state.text, "The right room is empty.")


class TestStoryVMLightweight(unittest.TestCase):
    def test_vm_has_no_legacy_history_stack(self) -> None:
        graph = eager_script.parse_graph(SAMPLE_SCRIPT)
        vm = StoryVM(graph)
        self.assertFalse(hasattr(vm, "_history"))
        self.assertFalse(hasattr(vm, "enable_history"))
        self.assertFalse(hasattr(vm, "disable_history"))
        self.assertFalse(hasattr(vm, "can_rollback"))
        self.assertFalse(hasattr(vm, "rollback"))
