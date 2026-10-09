"""Unit tests for story history tracking and time-travel rollback in StoryVM."""

import unittest

import eager_script

from eager_runtime import (
    ChoicePromptEvent,
    DialogueEvent,
    NarrationEvent,
    StoryVM,
)

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


class TestRollback(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(SAMPLE_SCRIPT)
        self.vm = StoryVM(self.graph)

    def test_step_by_step_rollback(self) -> None:
        self.assertFalse(self.vm.can_rollback)

        # Step 1: enter scene
        self.vm.step()
        self.assertTrue(self.vm.can_rollback)

        # Step 2: narration
        e2 = self.vm.step()
        self.assertIsInstance(e2, NarrationEvent)

        # Step 3: Alice dialogue
        e3 = self.vm.step()
        self.assertIsInstance(e3, DialogueEvent)

        # Rollback once: should revert before Alice's line
        success = self.vm.rollback()
        self.assertTrue(success)

        # Stepping again should re-deliver Alice's line
        replay_e3 = self.vm.step()
        assert isinstance(replay_e3, DialogueEvent)
        self.assertEqual(replay_e3.text, "Are you ready to choose?")

    def test_rollback_across_choice_selection(self) -> None:
        # Step until choice prompt
        while not self.vm.is_ended:
            event = self.vm.step()
            if isinstance(event, ChoicePromptEvent):
                break

        # Select choice 0 (left_room)
        self.vm.choose(0)
        _ = self.vm.step()
        self.assertEqual(self.vm.current_scene_id, "left_room")

        # Rollback back to choice prompt!
        self.vm.rollback()  # undo enter_event
        self.vm.rollback()  # undo choose / prompt

        # We should be able to step forward and choose right_room instead
        re_prompt = self.vm.step()
        self.assertIsInstance(re_prompt, ChoicePromptEvent)

        self.vm.choose(1)  # right_room
        _ = self.vm.step()
        self.assertEqual(self.vm.current_scene_id, "right_room")
