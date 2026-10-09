"""Unit tests for linear screenplay execution in Eager StoryVM."""

import unittest

import eager_script

from eager_runtime import (
    AppendEvent,
    DialogueEvent,
    FreshBoxEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
    StoryVM,
)

LINEAR_SCRIPT = """
## Intro --- intro
The sun rises over the quiet hills.
- The morning mist slowly clears.
/ A rooster crows in the distance.
Hero: Time to begin our adventure.
> forest

## Forest --- forest
Dense trees shade the path ahead.
Hero (determined): Let's keep moving.
"""


class TestRuntimeLinear(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(LINEAR_SCRIPT)
        self.vm = StoryVM(self.graph)

    def test_linear_execution_flow(self) -> None:
        events = []
        while not self.vm.is_ended:
            event = self.vm.step()
            if event is not None:
                events.append(event)

        # 1. SceneEnterEvent for intro
        assert isinstance(events[0], SceneEnterEvent)
        self.assertEqual(events[0].scene_id, "intro")

        # 2. NarrationEvent
        assert isinstance(events[1], NarrationEvent)
        self.assertIn("The sun rises", events[1].text)

        # 3. AppendEvent
        assert isinstance(events[2], AppendEvent)
        self.assertIn("The morning mist", events[2].text)

        # 4. FreshBoxEvent
        assert isinstance(events[3], FreshBoxEvent)
        self.assertIn("A rooster crows", events[3].text)

        # 5. DialogueEvent
        assert isinstance(events[4], DialogueEvent)
        self.assertEqual(events[4].speaker, "Hero")
        self.assertEqual(events[4].text, "Time to begin our adventure.")
        self.assertIsNone(events[4].emotion)

        # 6. SceneExitEvent (jump)
        assert isinstance(events[5], SceneExitEvent)
        self.assertEqual(events[5].transition_kind, "jump")
        self.assertEqual(events[5].target, "forest")

        # 7. SceneEnterEvent for forest
        assert isinstance(events[6], SceneEnterEvent)
        self.assertEqual(events[6].scene_id, "forest")

        # 8. Narration in forest
        assert isinstance(events[7], NarrationEvent)

        # 9. Dialogue with emotion
        assert isinstance(events[8], DialogueEvent)
        self.assertEqual(events[8].emotion, "determined")

        # 10. StoryEndEvent
        assert isinstance(events[9], StoryEndEvent)
        self.assertEqual(events[9].reason, "terminal")
        self.assertTrue(self.vm.is_ended)

    def test_visited_scenes_tracking(self) -> None:
        while not self.vm.is_ended:
            self.vm.step()

        self.assertEqual(self.vm.visited_scenes, {"intro", "forest"})

    def test_empty_graph_handling(self) -> None:
        empty_graph = eager_script.to_graph([])
        vm = StoryVM(empty_graph)
        self.assertIsNone(vm.current_scene_id)
        event = vm.step()
        assert isinstance(event, StoryEndEvent)
        self.assertEqual(event.reason, "no_entry")
        self.assertTrue(vm.is_ended)
