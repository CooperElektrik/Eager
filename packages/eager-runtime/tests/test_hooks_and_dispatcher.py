"""Unit tests for EventDispatcher and script engine hook registration."""

import unittest

import eager_script

from eager_runtime import (
    ChoicePromptEvent,
    DialogueEvent,
    EventDispatcher,
    HookEvent,
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
