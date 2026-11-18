"""Unit tests for eager.core.dispatcher."""

from eager.core.dispatcher import EventDispatcher
from eager.core.events import DialogueEvent, HookEvent


def test_dispatcher_events() -> None:
    dispatcher = EventDispatcher()
    received: list[str] = []

    @dispatcher.on_event(DialogueEvent)
    def on_diag(evt: DialogueEvent) -> None:
        received.append(f"{evt.speaker}: {evt.text}")

    dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Hello world", voice=None, emotion=None, line_number=1))
    assert received == ["Alice: Hello world"]


def test_dispatcher_hooks() -> None:
    dispatcher = EventDispatcher()
    hook_calls: list[str] = []

    @dispatcher.on_hook("play_sfx")
    def on_sfx(args: str) -> None:
        hook_calls.append(args)

    dispatcher.dispatch(HookEvent(hook_name="play_sfx", args="bell.wav", line_number=1))
    assert hook_calls == ["bell.wav"]
