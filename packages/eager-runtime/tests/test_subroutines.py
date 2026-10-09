"""Unit tests for subroutine execution, call stack frames, and nested returns in StoryVM."""

import unittest

import eager_script

from eager_runtime import (
    DialogueEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
    StoryVM,
)

SUBROUTINE_SCRIPT = """
## Main --- main
Hero: Preparing to investigate.
>> sub_inspect
Hero: Investigation concluded.
> final

## Sub Inspect --- sub_inspect
Narrator: Inspecting ancient relic.
>> sub_nested
Narrator: Relic inspection finished.
<<

## Sub Nested --- sub_nested
Narrator: Found hidden engravings!
<<

## Final --- final
Narrator: The story ends.
"""


class TestSubroutines(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(SUBROUTINE_SCRIPT)

    def test_nested_subroutine_call_stack(self) -> None:
        vm = StoryVM(self.graph)
        events = []

        while not vm.is_ended:
            event = vm.step()
            if event is not None:
                events.append(event)

        # Trace scene transitions
        enter_scenes = [e.scene_id for e in events if isinstance(e, SceneEnterEvent)]
        self.assertEqual(enter_scenes, ["main", "sub_inspect", "sub_nested", "final"])

        # Check call events
        calls = [e for e in events if isinstance(e, SceneExitEvent) and e.transition_kind == "call"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].scene_id, "main")
        self.assertEqual(calls[0].target, "sub_inspect")
        self.assertEqual(calls[1].scene_id, "sub_inspect")
        self.assertEqual(calls[1].target, "sub_nested")

        # Check return events
        returns = [e for e in events if isinstance(e, SceneExitEvent) and e.transition_kind == "return"]
        self.assertEqual(len(returns), 2)
        self.assertEqual(returns[0].scene_id, "sub_nested")
        self.assertEqual(returns[0].target, "sub_inspect")
        self.assertEqual(returns[1].scene_id, "sub_inspect")
        self.assertEqual(returns[1].target, "main")

        # Check dialogue beats order
        hero_dialogues = [e.text for e in events if isinstance(e, DialogueEvent) and e.speaker == "Hero"]
        self.assertEqual(
            hero_dialogues,
            [
                "Preparing to investigate.",
                "Investigation concluded.",
            ],
        )

        # End event
        last_event = events[-1]
        self.assertIsInstance(last_event, StoryEndEvent)
        self.assertEqual(last_event.reason, "terminal")
