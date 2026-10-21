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
from eager_core.types import Color

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


def test_director_auto_highlight_speaker_and_dimming() -> None:
    from eager_core.types import WHITE, Color, Vec2

    comp = StageCompositor(1920, 1080)
    director = StageDirector(
        comp,
        auto_highlight_speaker=True,
        dim_color=Color(0.65, 0.65, 0.70, 1.0),
        highlight_duration=0.2,
        pop_scale=1.05,
    )
    disp = MockEventDispatcher()
    director.bind(disp)
    director.register_character("alice")
    director.register_character("bob")

    # Put alice and bob on stage
    comp.show_character("alice", position="left", duration=0.0)
    comp.show_character("bob", position="right", duration=0.0)

    char_layer = comp.stage.get_layer("characters")
    assert char_layer is not None
    alice_elem = char_layer.get_element("alice")
    bob_elem = char_layer.get_element("bob")
    assert alice_elem is not None and bob_elem is not None
    assert alice_elem.state.tint == WHITE
    assert bob_elem.state.tint == WHITE

    # Alice speaks: Alice should be WHITE (and pop_scale), Bob should dim
    disp.emit_event(DialogueEvent(speaker="alice", text="Hi Bob!", voice=None, emotion=None, line_number=1))
    # Run timeline to finish tweens
    comp.update(0.25)
    assert alice_elem.state.tint == WHITE
    assert alice_elem.state.scale == Vec2(1.05, 1.05)
    assert bob_elem.state.tint == Color(0.65, 0.65, 0.70, 1.0)
    assert bob_elem.state.scale == Vec2(1.0, 1.0)

    # Bob speaks: Bob should tween to WHITE and pop_scale, Alice dims to dim_color and restores scale
    disp.emit_event(DialogueEvent(speaker="bob", text="Hi Alice!", voice=None, emotion=None, line_number=2))
    comp.update(0.25)
    assert bob_elem.state.tint == WHITE
    assert bob_elem.state.scale == Vec2(1.05, 1.05)
    assert alice_elem.state.tint == Color(0.65, 0.65, 0.70, 1.0)
    assert alice_elem.state.scale == Vec2(1.0, 1.0)

    # NarrationEvent fires: All sprites restore to WHITE and scale 1.0
    disp.emit_event(NarrationEvent(text="A quiet wind blows.", line_number=3))
    comp.update(0.25)
    assert alice_elem.state.tint == WHITE
    assert alice_elem.state.scale == Vec2(1.0, 1.0)
    assert bob_elem.state.tint == WHITE


def test_director_character_color_and_name_resolution() -> None:
    comp = StageCompositor()
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    director.register_character("alice", name="Alice", color="#ff77aa", side_image="side/alice.png")

    # Dialogue with display name "Alice" should match character_id "alice"
    disp.emit_event(DialogueEvent(speaker="Alice", text="Hello!", voice=None, emotion=None, line_number=1))
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.side_image == "side/alice.png"
    assert director.ui_state.speaker_color == Color.from_hex("#ff77aa")


def test_director_auto_highlight_speaker_hop() -> None:
    from eager_core.types import WHITE, Vec2

    comp = StageCompositor(1920, 1080)
    director = StageDirector(
        comp,
        auto_highlight_speaker=True,
        highlight_duration=0.1,
        pop_hop=15.0,
    )
    disp = MockEventDispatcher()
    director.bind(disp)

    comp.show_character("alice", position="center", duration=0.0)
    char_layer = comp.stage.get_layer("characters")
    assert char_layer is not None
    alice_elem = char_layer.get_element("alice")
    assert alice_elem is not None
    initial_y = alice_elem.position.y

    # Alice speaks: hops up by 15px
    disp.emit_event(DialogueEvent(speaker="alice", text="Hop!", voice=None, emotion=None, line_number=1))
    comp.update(0.15)
    assert alice_elem.position == Vec2(alice_elem.position.x, initial_y - 15.0)

    # NarrationEvent: returns to original initial_y
    disp.emit_event(NarrationEvent(text="Landing.", line_number=2))
    comp.update(0.15)
    assert alice_elem.position == Vec2(alice_elem.position.x, initial_y)
    assert alice_elem.state.tint == WHITE



