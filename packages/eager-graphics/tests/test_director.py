"""Tests for StageDirector event and hook dispatching."""

from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)
from eager_core.events import (
    ChoiceOption as EagerChoiceOption,
)

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector
from eager_graphics.ui_state import ChoiceOption


class MockEventDispatcher:
    """Mock dispatcher matching Eager's EventDispatcher interface."""

    def __init__(self) -> None:
        self.hooks: dict[str, list] = {}
        self.events: dict[type, list] = {}
        self.any_listeners: list = []

    def on_hook(self, name: str):
        def decorator(fn):
            self.hooks.setdefault(name, []).append(fn)
            return fn

        return decorator

    def on_event(self, event_cls: type):
        def decorator(fn):
            self.events.setdefault(event_cls, []).append(fn)
            return fn

        return decorator

    def on_any_event(self, fn):
        self.any_listeners.append(fn)
        return fn

    def emit_hook(self, name: str, args: str) -> None:
        for fn in self.hooks.get(name, []):
            fn(args)

    def emit_event(self, event: object) -> None:
        for fn in self.events.get(type(event), []):
            fn(event)
        for fn in self.any_listeners:
            fn(event)


def test_director_hook_dispatch() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    # Test ~ bg
    disp.emit_hook("bg", "castle_gate with cut")
    items = comp.render_list()
    assert len(items) == 1
    assert items[0].asset_id == "bg/castle_gate"

    # Test ~ show
    disp.emit_hook("show", "alice happy at left with cut")
    items = comp.render_list()
    assert len(items) == 2
    alice = next(it for it in items if it.layer == "characters")
    assert alice.asset_id == "alice/happy"
    assert alice.x == 480.0

    # Test ~ move
    disp.emit_hook("move", "alice to right duration=0.0")
    alice_moved = next(it for it in comp.render_list() if it.layer == "characters")
    assert alice_moved.x == 1440.0

    # Test ~ expr
    disp.emit_hook("expr", "alice stern")
    alice_expr = next(it for it in comp.render_list() if it.layer == "characters")
    assert alice_expr.asset_id == "alice/stern"

    # Test ~ hide
    disp.emit_hook("hide", "alice with cut")
    chars = [it for it in comp.render_list() if it.layer == "characters"]
    assert len(chars) == 0


def test_director_dialogue_emotion_auto_sync() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    # Mount Alice with default expression
    comp.show_character("alice", "normal", position="center", transition="cut")
    assert comp.render_list()[0].asset_id == "alice/normal"

    # Trigger dialogue with emotion tag
    dlg = DialogueEvent(
        speaker="Alice",
        text="How dare you!",
        voice=None,
        emotion="furious",
        line_number=10,
    )

    disp.emit_event(dlg)
    # The character expression should be automatically updated!
    assert comp.render_list()[0].asset_id == "alice/furious"


def test_director_scene_bg_auto_mapping() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    director.register_scene_bg("forest_clearing", "bg/forest", transition="cut")

    enter_event = SceneEnterEvent(
        scene_id="forest_clearing",
        display_name="Forest Clearing",
        line_number=1,
    )

    disp.emit_event(enter_event)
    items = comp.render_list()
    assert len(items) == 1
    assert items[0].asset_id == "bg/forest"


def test_director_ui_state_tracks_dialogue() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    dlg = DialogueEvent(
        speaker="Alice",
        text="Hello there!",
        voice=None,
        emotion="happy",
        line_number=5,
    )

    disp.emit_event(dlg)
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.text == "Hello there!"
    assert director.ui_state.emotion == "happy"
    assert director.ui_state.choices == []
    assert not director.ui_state.is_finished


def test_director_ui_state_tracks_narration() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    # First put some dialogue
    director.ui_state.speaker = "Alice"
    director.ui_state.emotion = "happy"

    narr = NarrationEvent(text="The sun began to set.", line_number=12)

    disp.emit_event(narr)
    assert director.ui_state.speaker is None
    assert director.ui_state.text == "The sun began to set."
    assert director.ui_state.emotion is None
    assert director.ui_state.choices == []


def test_director_ui_state_tracks_choices() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    choices_event = ChoicePromptEvent(
        options=(
            EagerChoiceOption(index=0, text="Go left", target="left_path", line_number=10),
            EagerChoiceOption(index=1, text="Go right", target="right_path", line_number=11),
        ),
        line_number=10,
    )

    disp.emit_event(choices_event)
    assert len(director.ui_state.choices) == 2
    assert director.ui_state.choices[0].index == 0
    assert director.ui_state.choices[0].text == "Go left"
    assert director.ui_state.choices[0].target == "left_path"
    assert director.ui_state.choices[1].index == 1
    assert director.ui_state.choices[1].text == "Go right"
    assert director.ui_state.choices[1].target == "right_path"


def test_director_ui_state_scene_exit_clears() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    director.ui_state.speaker = "Alice"
    director.ui_state.text = "Wait!"
    director.ui_state.emotion = "worried"
    director.ui_state.choices = [ChoiceOption(0, "Option A")]

    exit_evt = SceneExitEvent(
        scene_id="clearing",
        transition_kind="jump",
        target="cave",
        line_number=20,
    )

    disp.emit_event(exit_evt)
    assert director.ui_state.speaker is None
    assert director.ui_state.text == ""
    assert director.ui_state.emotion is None
    assert director.ui_state.choices == []


def test_director_ui_state_story_end() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    assert not director.ui_state.is_finished

    end_evt = StoryEndEvent(scene_id="ending", reason="completed")

    disp.emit_event(end_evt)
    assert director.ui_state.is_finished


def test_director_ui_state_append_and_fresh_box() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    # Dialogue
    disp.emit_event(DialogueEvent(speaker="Alice", text="One", voice=None, emotion=None, line_number=1))
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.text == "One"

    # Append
    disp.emit_event(AppendEvent(text="two", line_number=2))
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.text == "One two"

    # Fresh box
    disp.emit_event(FreshBoxEvent(text="three", line_number=3))
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.text == "three"


