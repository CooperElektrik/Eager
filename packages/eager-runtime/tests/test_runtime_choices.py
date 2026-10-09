"""Unit tests for choice prompts and branching resolution in StoryVM."""

import unittest

import eager_script

from eager_runtime import (
    ChoicePromptEvent,
    SceneEnterEvent,
    StoryRuntimeError,
    StoryVM,
)

CHOICE_SCRIPT = """
## Crossroads --- crossroads
Narrator: Two paths diverge before you.
? Take the mountain pass (mountain)
? Walk through the dark valley (valley)

## Mountain Pass --- mountain
Narrator: The air is crisp and cold.
> finish

## Dark Valley --- valley
Narrator: Shadows stretch long across the canyon.
> finish

## Finished --- finish
Narrator: Journey complete.
"""


class TestRuntimeChoices(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(CHOICE_SCRIPT)

    def test_branching_selection_numeric(self) -> None:
        vm = StoryVM(self.graph)

        # Step until choice prompt
        prompt = None
        while not vm.is_ended:
            event = vm.step()
            if isinstance(event, ChoicePromptEvent):
                prompt = event
                break

        assert isinstance(prompt, ChoicePromptEvent)
        self.assertEqual(len(prompt.options), 2)
        self.assertEqual(prompt.options[0].text, "Take the mountain pass")
        self.assertEqual(prompt.options[0].target, "mountain")
        self.assertEqual(prompt.options[1].text, "Walk through the dark valley")
        self.assertEqual(prompt.options[1].target, "valley")

        # Calling step() again while choice is pending returns the prompt without advancing
        repeat_event = vm.step()
        self.assertEqual(repeat_event, prompt)

        # Select choice 1 (valley)
        vm.choose(1)
        self.assertIsNone(vm.pending_choice)

        # Next event should enter valley scene
        next_event = vm.step()
        assert isinstance(next_event, SceneEnterEvent)
        self.assertEqual(next_event.scene_id, "valley")

    def test_branching_selection_by_target_id(self) -> None:
        vm = StoryVM(self.graph)

        while not vm.is_ended:
            event = vm.step()
            if isinstance(event, ChoicePromptEvent):
                break

        vm.choose("mountain")
        next_event = vm.step()
        assert isinstance(next_event, SceneEnterEvent)
        self.assertEqual(next_event.scene_id, "mountain")

    def test_invalid_choice_raises_error(self) -> None:
        vm = StoryVM(self.graph)
        while not vm.is_ended:
            event = vm.step()
            if isinstance(event, ChoicePromptEvent):
                break

        with self.assertRaises(StoryRuntimeError):
            vm.choose(99)  # Index out of bounds

        with self.assertRaises(StoryRuntimeError):
            vm.choose("non_existent_target")

    def test_choose_without_pending_choice_raises_error(self) -> None:
        vm = StoryVM(self.graph)
        # At start, no choice prompt active
        with self.assertRaises(StoryRuntimeError):
            vm.choose(0)
