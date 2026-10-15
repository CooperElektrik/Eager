"""Tests for script logic, expressions, variables, conditional branching, and interpolation."""

import unittest

from eager_core.events import ChoicePromptEvent, DialogueEvent
from eager_script import parse, parse_graph, validate

from eager_runtime import PersistentData, StoryRuntimeError, StoryVM


class TestScriptLogic(unittest.TestCase):
    def test_variable_default_and_mutation(self):
        script = """
@default affinity = 0
@default player_name = "Alex"

## Start --- start
Narrator: Hello, [player_name]!
$ affinity += 10
$ player_name = "Alexander"
Narrator: Now named [player_name] with affinity [affinity].
"""
        graph = parse_graph(script)
        vm = StoryVM(graph)

        ev = vm.step()  # SceneEnter
        self.assertEqual(ev.type, "scene_enter")

        ev = vm.step()  # Narration
        self.assertEqual(ev.text, "Hello, Alex!")

        ev = vm.step()  # Narration after $ mutations
        self.assertEqual(ev.text, "Now named Alexander with affinity 10.")
        self.assertEqual(vm.get_variable("affinity"), 10)
        self.assertEqual(vm.get_variable("player_name"), "Alexander")

    def test_conditional_if_elif_else_branching(self):
        script = """
@default score = 15

## Scene --- scene
@if score > 20
Narrator: High score!
@elif score > 10
Narrator: Medium score!
@else
Narrator: Low score!
@end
Narrator: End of evaluation.
"""
        graph = parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # SceneEnter

        ev = vm.step()  # Should be Medium score!
        self.assertEqual(ev.text, "Medium score!")

        ev = vm.step()  # End of evaluation.
        self.assertEqual(ev.text, "End of evaluation.")

    def test_conditional_choices(self):
        script = """
@default has_key = False

## Door --- door
Guard: State your action.
? Unlock door (enter) if has_key
? Walk away (leave)

## Enter --- enter
Guard: Welcome.

## Leave --- leave
Guard: Farewell.
"""
        graph = parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # SceneEnter
        vm.step()  # Guard dialogue

        prompt: ChoicePromptEvent = vm.step()  # ChoicePromptEvent
        self.assertEqual(prompt.type, "choice_prompt")
        self.assertEqual(len(prompt.options), 2)
        # Option 0 should be disabled
        self.assertFalse(prompt.options[0].enabled)
        self.assertTrue(prompt.options[1].enabled)

        # Attempting to choose disabled option raises error
        with self.assertRaises(StoryRuntimeError):
            vm.choose(0)

        # Choosing enabled option succeeds
        vm.choose(1)
        self.assertEqual(vm.current_scene_id, "leave")

    def test_character_definition_and_interpolation(self):
        script = """
@character a "Alice" color=#ff0000

## Scene --- scene
a: Hello there!
"""
        graph = parse_graph(script)
        self.assertIn("a", graph.characters)
        self.assertEqual(graph.characters["a"]["name"], "Alice")

        vm = StoryVM(graph)
        vm.step()  # SceneEnter
        ev = vm.step()
        self.assertIsInstance(ev, DialogueEvent)
        self.assertEqual(ev.speaker, "Alice")
        self.assertEqual(ev.text, "Hello there!")

    def test_escaped_brackets_and_nested_expressions(self):
        script = """
@default x = 5

## Scene --- scene
Narrator: Escaped [[bracket]] and value [x].
"""
        graph = parse_graph(script)
        vm = StoryVM(graph)
        vm.step()
        ev = vm.step()
        self.assertEqual(ev.text, "Escaped [bracket] and value 5.")

    def test_validator_detects_unclosed_if_and_syntax_error(self):
        script = """
## Scene --- scene
@if 1 > 0
Alice: Hello
"""
        res = validate(parse(script))
        self.assertFalse(res.is_valid)
        self.assertTrue(any("Unclosed @if block" in e.message for e in res.errors))

        script_err = """
## Scene --- scene
@if (invalid syntax ==
Alice: Hello
@end
"""
        res_err = validate(parse(script_err))
        self.assertFalse(res_err.is_valid)
        self.assertTrue(any("Invalid expression" in e.message for e in res_err.errors))

    def test_private_attribute_blocking_in_interpolation(self):
        script = """
## Scene --- scene
Narrator: Secret is [persistent.__class__], [persistent._data], and [_private].
"""
        graph = parse_graph(script)
        vm = StoryVM(graph)
        vm.set_variable("persistent", PersistentData())
        vm.set_variable("_private", "secret_leak")
        vm.step()  # SceneEnter
        ev = vm.step()  # Narration
        # Verify [persistent.__class__], [persistent._data], and [_private] were NOT expanded/leaked
        self.assertEqual(ev.text, "Secret is [persistent.__class__], [persistent._data], and [_private].")


if __name__ == "__main__":
    unittest.main()

