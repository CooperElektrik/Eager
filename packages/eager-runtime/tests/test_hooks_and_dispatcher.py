"""Unit tests for EventDispatcher and script engine hook registration."""

import unittest

import eager_script

from eager_runtime import (
    ChoicePromptEvent,
    DialogueEvent,
    EventDispatcher,
    HookEvent,
    InputPromptEvent,
    StoryEndEvent,
    StoryVM,
)

HOOK_SCRIPT = """
## Stage --- stage
~ play_music bgm_theme.ogg
~ fade_in duration=1.5
Alice: The curtains rise.
~ trigger_lighting spot_center
? Bow gracefully (bow)
? Wave to audience (wave)

## Bow --- bow
~ play_sfx applause.ogg
Alice: Thank you all!

## Wave --- wave
Alice: Hello everyone!
"""


class TestHooksAndDispatcher(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(HOOK_SCRIPT)
        self.vm = StoryVM(self.graph)
        self.dispatcher = EventDispatcher()

    def test_hook_callback_execution(self) -> None:
        music_calls = []
        fade_calls = []
        lighting_calls = []

        @self.dispatcher.on_hook("play_music")
        def on_music(args: str):
            music_calls.append(args)

        @self.dispatcher.on_hook("fade_in")
        def on_fade(args: str):
            fade_calls.append(args)

        @self.dispatcher.on_hook("trigger_lighting")
        def on_lighting(args: str):
            lighting_calls.append(args)

        # Run until choice prompt
        pause_event = self.dispatcher.run_until_pause(self.vm)
        self.assertIsInstance(pause_event, ChoicePromptEvent)

        self.assertEqual(music_calls, ["bgm_theme.ogg"])
        self.assertEqual(fade_calls, ["duration=1.5"])
        self.assertEqual(lighting_calls, ["spot_center"])

    def test_typed_event_callback_execution(self) -> None:
        dialogues = []

        @self.dispatcher.on_event(DialogueEvent)
        def on_dialogue(event: DialogueEvent):
            dialogues.append(event.text)

        self.dispatcher.run_until_pause(self.vm)
        self.assertEqual(dialogues, ["The curtains rise."])

    def test_wildcard_hook_listener(self) -> None:
        all_hooks = []

        @self.dispatcher.on_any_hook
        def on_any(event: HookEvent):
            all_hooks.append((event.hook_name, event.args))

        self.dispatcher.run_until_pause(self.vm)
        self.assertEqual(len(all_hooks), 3)
        self.assertEqual(all_hooks[0], ("play_music", "bgm_theme.ogg"))

    def test_run_until_pause_stops_on_input_prompt(self) -> None:
        script = """## Start --- start
Alice: Welcome!
~ input hero_name "Enter your name:" default="Arthur"
Alice: Hello, [hero_name]!
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        dispatcher = EventDispatcher()

        pause_event = dispatcher.run_until_pause(vm)
        self.assertIsNotNone(pause_event)
        self.assertIsInstance(pause_event, InputPromptEvent)
        assert isinstance(pause_event, InputPromptEvent)
        self.assertEqual(pause_event.var_name, "hero_name")
        self.assertEqual(pause_event.prompt, "Enter your name:")

        # Resume by submitting input and advancing
        vm.submit_input("Galahad")
        end_event = dispatcher.run_until_pause(vm)
        self.assertIsInstance(end_event, StoryEndEvent)
        self.assertEqual(vm.get_variable("hero_name"), "Galahad")

    def test_dispatcher_sequential_input_prompts(self) -> None:
        """Verify run_until_pause cleanly pauses across multiple consecutive input prompts."""
        script = """
## Start --- start
~ input first_name "First name:" "Jane"
~ input last_name "Last name:" "Doe"
Alice: Full identity: [first_name] [last_name].
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        dispatcher = EventDispatcher()

        ev1 = dispatcher.run_until_pause(vm)
        assert isinstance(ev1, InputPromptEvent)
        self.assertEqual(ev1.var_name, "first_name")
        vm.submit_input("John")

        ev2 = dispatcher.run_until_pause(vm)
        assert isinstance(ev2, InputPromptEvent)
        self.assertEqual(ev2.var_name, "last_name")
        vm.submit_input("Smith")

        ev3 = dispatcher.run_until_pause(vm)
        assert isinstance(ev3, StoryEndEvent)
        self.assertEqual(vm.get_variable("first_name"), "John")
        self.assertEqual(vm.get_variable("last_name"), "Smith")

