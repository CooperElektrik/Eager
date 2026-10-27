"""Unit tests for EventDispatcher and script engine hook registration."""

import eager_script
from eager_core.events import (
    ChoicePromptEvent,
    DialogueEvent,
    HookEvent,
    InputPromptEvent,
    StoryEndEvent,
)

from eager_runtime import (
    EventDispatcher,
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


def test_hook_callback_execution() -> None:
    graph = eager_script.parse_graph(HOOK_SCRIPT)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()

    music_calls: list[str] = []
    fade_calls: list[str] = []
    lighting_calls: list[str] = []

    @dispatcher.on_hook("play_music")
    def on_music(args: str) -> None:
        music_calls.append(args)

    @dispatcher.on_hook("fade_in")
    def on_fade(args: str) -> None:
        fade_calls.append(args)

    @dispatcher.on_hook("trigger_lighting")
    def on_lighting(args: str) -> None:
        lighting_calls.append(args)

    # Run until choice prompt
    pause_event = dispatcher.run_until_pause(vm)
    assert isinstance(pause_event, ChoicePromptEvent)

    assert music_calls == ["bgm_theme.ogg"]
    assert fade_calls == ["duration=1.5"]
    assert lighting_calls == ["spot_center"]


def test_typed_event_callback_execution() -> None:
    graph = eager_script.parse_graph(HOOK_SCRIPT)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()

    dialogues: list[str] = []

    @dispatcher.on_event(DialogueEvent)
    def on_dialogue(event: DialogueEvent) -> None:
        dialogues.append(event.text)

    dispatcher.run_until_pause(vm)
    assert dialogues == ["The curtains rise."]


def test_wildcard_hook_listener() -> None:
    graph = eager_script.parse_graph(HOOK_SCRIPT)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()

    all_hooks: list[tuple[str, str]] = []

    @dispatcher.on_any_hook
    def on_any(event: HookEvent) -> None:
        all_hooks.append((event.hook_name, event.args))

    dispatcher.run_until_pause(vm)
    assert len(all_hooks) == 3
    assert all_hooks[0] == ("play_music", "bgm_theme.ogg")


def test_run_until_pause_stops_on_input_prompt() -> None:
    script = """## Start --- start
Alice: Welcome!
~ input hero_name "Enter your name:" default="Arthur"
Alice: Hello, [hero_name]!
"""
    graph = eager_script.parse_graph(script)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()

    pause_event = dispatcher.run_until_pause(vm)
    assert pause_event is not None
    assert isinstance(pause_event, InputPromptEvent)
    assert pause_event.var_name == "hero_name"
    assert pause_event.prompt == "Enter your name:"

    # Resume by submitting input and advancing
    vm.submit_input("Galahad")
    end_event = dispatcher.run_until_pause(vm)
    assert isinstance(end_event, StoryEndEvent)
    assert vm.get_variable("hero_name") == "Galahad"


def test_dispatcher_sequential_input_prompts() -> None:
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
    assert ev1.var_name == "first_name"
    vm.submit_input("John")

    ev2 = dispatcher.run_until_pause(vm)
    assert isinstance(ev2, InputPromptEvent)
    assert ev2.var_name == "last_name"
    vm.submit_input("Smith")

    ev3 = dispatcher.run_until_pause(vm)
    assert isinstance(ev3, StoryEndEvent)
    assert vm.get_variable("first_name") == "John"
    assert vm.get_variable("last_name") == "Smith"
