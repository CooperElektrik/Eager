"""Tests for StageDirector event and hook dispatching."""

from typing import ClassVar

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector


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


class MockDialogueEvent:
    def __init__(self, speaker: str, emotion: str | None = None) -> None:
        self.type = "dialogue"
        self.speaker = speaker
        self.emotion = emotion


class MockSceneEnterEvent:
    def __init__(self, scene_id: str) -> None:
        self.type = "scene_enter"
        self.scene_id = scene_id


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
    try:
        from eager_core.events import DialogueEvent

        dlg = DialogueEvent(
            speaker="Alice",
            text="How dare you!",
            voice=None,
            emotion="furious",
            line_number=10,
        )
    except ImportError:
        dlg = MockDialogueEvent(speaker="Alice", emotion="furious")

    disp.emit_event(dlg)
    # The character expression should be automatically updated!
    assert comp.render_list()[0].asset_id == "alice/furious"


def test_director_scene_bg_auto_mapping() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    director.register_scene_bg("forest_clearing", "bg/forest", transition="cut")

    try:
        from eager_core.events import SceneEnterEvent

        enter_event = SceneEnterEvent(
            scene_id="forest_clearing",
            display_name="Forest Clearing",
            line_number=1,
        )
    except ImportError:
        enter_event = MockSceneEnterEvent(scene_id="forest_clearing")

    disp.emit_event(enter_event)
    items = comp.render_list()
    assert len(items) == 1
    assert items[0].asset_id == "bg/forest"


def test_director_ui_state_tracks_dialogue() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    try:
        from eager_core.events import DialogueEvent

        dlg = DialogueEvent(
            speaker="Alice",
            text="Hello there!",
            voice=None,
            emotion="happy",
            line_number=5,
        )
    except ImportError:
        class Dlg:
            type = "dialogue"
            speaker = "Alice"
            text = "Hello there!"
            emotion = "happy"

        dlg = Dlg()

    disp.emit_event(dlg)
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.text == "Hello there!"
    assert director.ui_state.emotion == "happy"
    assert director.ui_state.choices == []
    assert not director.ui_state.is_finished

    # Also test generic event fallback path directly
    class GenericDlg:
        type = "dialogue"
        speaker = "Bob"
        text = "Greetings!"
        emotion = "calm"

    director.handle_generic_event(GenericDlg())
    assert director.ui_state.speaker == "Bob"
    assert director.ui_state.text == "Greetings!"
    assert director.ui_state.emotion == "calm"


def test_director_ui_state_tracks_narration() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    # First put some dialogue
    director.ui_state.speaker = "Alice"
    director.ui_state.emotion = "happy"

    try:
        from eager_core.events import NarrationEvent

        narr = NarrationEvent(text="The sun began to set.", line_number=12)
    except ImportError:
        class Narr:
            type = "narration"
            text = "The sun began to set."

        narr = Narr()

    disp.emit_event(narr)
    assert director.ui_state.speaker is None
    assert director.ui_state.text == "The sun began to set."
    assert director.ui_state.emotion is None
    assert director.ui_state.choices == []

    # Also test generic event fallback path directly
    class GenericNarr:
        type = "narration"
        text = "Night fell."

    director.handle_generic_event(GenericNarr())
    assert director.ui_state.speaker is None
    assert director.ui_state.text == "Night fell."
    assert director.ui_state.emotion is None


def test_director_ui_state_tracks_choices() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    try:
        from eager_core.events import ChoiceOption as EagerChoiceOption
        from eager_core.events import ChoicePromptEvent

        choices_event = ChoicePromptEvent(
            options=(
                EagerChoiceOption(index=0, text="Go left", target="left_path", line_number=10),
                EagerChoiceOption(index=1, text="Go right", target="right_path", line_number=11),
            ),
            line_number=10,
        )
    except ImportError:
        class Opt:
            def __init__(self, index: int, text: str, target: str) -> None:
                self.index = index
                self.text = text
                self.target = target

        class Choices:
            type: ClassVar[str] = "choice_prompt"
            options: ClassVar[list] = [Opt(0, "Go left", "left_path"), Opt(1, "Go right", "right_path")]

        choices_event = Choices()

    disp.emit_event(choices_event)
    assert len(director.ui_state.choices) == 2
    assert director.ui_state.choices[0].index == 0
    assert director.ui_state.choices[0].text == "Go left"
    assert director.ui_state.choices[0].target == "left_path"
    assert director.ui_state.choices[1].index == 1
    assert director.ui_state.choices[1].text == "Go right"
    assert director.ui_state.choices[1].target == "right_path"

    # Also test generic event fallback path directly
    class GenericOpt:
        def __init__(self, index: int, text: str, target: str) -> None:
            self.index = index
            self.text = text
            self.target = target

    class GenericChoices:
        type: ClassVar[str] = "choice_prompt"
        options: ClassVar[list] = [GenericOpt(0, "Stay", "stay_path")]

    director.handle_generic_event(GenericChoices())
    assert len(director.ui_state.choices) == 1
    assert director.ui_state.choices[0].text == "Stay"


def test_director_ui_state_scene_exit_clears() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    director.ui_state.speaker = "Alice"
    director.ui_state.text = "Wait!"
    director.ui_state.emotion = "worried"
    from eager_graphics.ui_state import ChoiceOption

    director.ui_state.choices = [ChoiceOption(0, "Option A")]

    try:
        from eager_core.events import SceneExitEvent

        exit_evt = SceneExitEvent(
            scene_id="clearing",
            transition_kind="jump",
            target="cave",
            line_number=20,
        )
    except ImportError:
        class ExitEvt:
            type = "scene_exit"
            scene_id = "clearing"

        exit_evt = ExitEvt()

    disp.emit_event(exit_evt)
    assert director.ui_state.speaker is None
    assert director.ui_state.text == ""
    assert director.ui_state.emotion is None
    assert director.ui_state.choices == []

    # Also test generic event fallback
    director.ui_state.speaker = "Bob"
    director.ui_state.text = "Hello"
    class GenericExit:
        type = "scene_exit"

    director.handle_generic_event(GenericExit())
    assert director.ui_state.speaker is None
    assert director.ui_state.text == ""


def test_director_ui_state_story_end() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    assert not director.ui_state.is_finished

    try:
        from eager_core.events import StoryEndEvent

        end_evt = StoryEndEvent(scene_id="ending", reason="completed")
    except ImportError:
        class EndEvt:
            type = "story_end"

        end_evt = EndEvt()

    disp.emit_event(end_evt)
    assert director.ui_state.is_finished

    # Also test generic event fallback
    director.ui_state.is_finished = False
    class GenericEnd:
        type = "story_end"

    director.handle_generic_event(GenericEnd())
    assert director.ui_state.is_finished


def test_director_ui_state_append_and_fresh_box() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    from eager_core.events import AppendEvent, DialogueEvent, FreshBoxEvent

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

    # Generic event fallback path
    class GenericAppend:
        type = "append"
        text = "four"

    director.handle_generic_event(GenericAppend())
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.text == "three four"

    class GenericFresh:
        type = "fresh_box"
        text = "five"

    director.handle_generic_event(GenericFresh())
    assert director.ui_state.speaker == "Alice"
    assert director.ui_state.text == "five"


