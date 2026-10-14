"""Unit tests for choice prompts and branching resolution in StoryVM."""

import unittest

import eager_script

from eager_runtime import (
    ChoicePromptEvent,
    DialogueEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
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


INLINE_CHOICE_SCRIPT = """
@default gold = 10

## Tavern --- tavern
Bartender: What will it be?
? Order an ale
    $ gold -= 3
    Bartender: Coming right up.
? Ask for water
    Bartender: Suit yourself.
Bartender: Anything else?
> nightfall

## Nightfall --- nightfall
Narrator: The night deepens.
"""

JUMP_INLINE_SCRIPT = """
## Crossroads --- crossroads
? Take the shortcut
    Narrator: You duck through the alley.
    > arrive
Narrator: Reached only when the block falls through.

## Arrive --- arrive
Narrator: You arrive early.
"""


class TestInlineChoiceBlocks(unittest.TestCase):
    """End-to-end tests for inline choice blocks lowered into anonymous scenes."""

    def _run(self, script: str, choice: int = 0) -> tuple[StoryVM, list]:
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        events: list = []
        while not vm.is_ended:
            event = vm.step()
            if event is None:
                break
            events.append(event)
            if isinstance(event, ChoicePromptEvent):
                vm.choose(choice)
        return vm, events

    def test_inline_block_executes_then_resumes_scene(self) -> None:
        vm, events = self._run(INLINE_CHOICE_SCRIPT, choice=0)

        texts = [e.text for e in events if isinstance(e, DialogueEvent)]
        self.assertEqual(
            texts,
            ["What will it be?", "Coming right up.", "Anything else?", "The night deepens."],
        )
        self.assertEqual(vm.get_variable("gold"), 7)

        entered = [e.scene_id for e in events if isinstance(e, SceneEnterEvent)]
        self.assertIn("tavern__anon_6", entered)

        returns = [e for e in events if isinstance(e, SceneExitEvent) and e.transition_kind == "return"]
        self.assertTrue(any(r.target == "tavern" for r in returns))

        self.assertIsInstance(events[-1], StoryEndEvent)
        self.assertEqual(events[-1].scene_id, "nightfall")

    def test_alternative_inline_branch_does_not_mutate_state(self) -> None:
        vm, _events = self._run(INLINE_CHOICE_SCRIPT, choice=1)
        self.assertEqual(vm.get_variable("gold"), 10)

    def test_jump_inside_inline_block_skips_continuation(self) -> None:
        _vm, events = self._run(JUMP_INLINE_SCRIPT, choice=0)
        texts = [e.text for e in events if isinstance(e, DialogueEvent)]
        self.assertEqual(texts, ["You duck through the alley.", "You arrive early."])
        self.assertNotIn("Reached only when the block falls through.", texts)

    def test_nested_inline_blocks(self) -> None:
        script = """
## Hub --- hub
? Outer reaction
    Narrator: outer start
    ? Inner reaction
        Narrator: inner beat
    Narrator: outer end
Narrator: hub end
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        texts: list[str] = []
        while not vm.is_ended:
            event = vm.step()
            if event is None:
                break
            if isinstance(event, DialogueEvent):
                texts.append(event.text)
            if isinstance(event, ChoicePromptEvent):
                vm.choose(0)
        self.assertEqual(texts, ["outer start", "inner beat", "outer end", "hub end"])

    def test_inline_option_with_condition(self) -> None:
        script = """
@default has_key = False
## Door --- door
? Pick the lock if has_key
    $ picked = True
    Narrator: The lock clicks open.
? Knock
    $ knocked = True
    Narrator: You knock politely.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # SceneEnter
        prompt = vm.step()  # ChoicePrompt
        assert isinstance(prompt, ChoicePromptEvent)
        self.assertFalse(prompt.options[0].enabled)
        self.assertTrue(prompt.options[1].enabled)

        with self.assertRaises(StoryRuntimeError):
            vm.choose(0)

        vm.choose(1)
        while not vm.is_ended:
            if vm.step() is None:
                break
        self.assertTrue(vm.get_variable("knocked"))
        self.assertIsNone(vm.get_variable("picked"))

    def test_nested_inline_jump_abandons_all_inline_frames(self) -> None:
        script = """
## Main --- main
Narrator: main start
? Option A
    Narrator: in A
    ? Option B
        Narrator: in B
        > final_scene
    Narrator: after B in A
Narrator: main end

## FinalScene --- final_scene
Narrator: in final scene
"""
        _vm, events = self._run(script, choice=0)
        texts = [e.text for e in events if isinstance(e, DialogueEvent)]
        self.assertEqual(texts, ["main start", "in A", "in B", "in final scene"])
        self.assertNotIn("main end", texts)
        self.assertNotIn("after B in A", texts)

    def test_choice_inside_inline_targeting_named_scene_abandons_inline_frames(self) -> None:
        script = """
## Main --- main
Narrator: main start
? Option A
    Narrator: in A
    ? Go away (final_scene)
Narrator: main end

## FinalScene --- final_scene
Narrator: in final scene
"""
        _vm, events = self._run(script, choice=0)
        texts = [e.text for e in events if isinstance(e, DialogueEvent)]
        self.assertEqual(texts, ["main start", "in A", "in final scene"])
        self.assertNotIn("main end", texts)
