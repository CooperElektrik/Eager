"""Tests for StageDirector event and hook dispatching."""

from collections.abc import Callable
from typing import Any, TypeVar

import pytest

from eager.backends.renderers.null import NullRenderer
from eager.core.audio import AudioMixer, NullAudioBackend
from eager.core.dispatcher import EventDispatcher
from eager.core.events import (
    AppendEvent,
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    HookEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)
from eager.core.types import Color
from eager.stage.compositor import StageCompositor
from eager.stage.director import StageDirector

_E = TypeVar("_E")


class MockEventDispatcher:
    """Mock dispatcher matching Eager's EventDispatcher interface."""

    def __init__(self) -> None:
        self.hooks: dict[str, list[Callable[[str], object]]] = {}
        self.events: dict[type, list[Callable[[Any], object]]] = {}
        self.any_listeners: list[Callable[[object], object]] = []

    def on_hook(self, name: str) -> Callable[[Callable[[str], object]], Callable[[str], object]]:
        def decorator(fn: Callable[[str], object]) -> Callable[[str], object]:
            self.hooks.setdefault(name, []).append(fn)
            return fn

        return decorator

    def on_event(self, event_cls: type[_E]) -> Callable[[Callable[[_E], object]], Callable[[_E], object]]:
        def decorator(fn: Callable[[_E], object]) -> Callable[[_E], object]:
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


def test_director_dialogue_emotion_with_display_name_and_character_id_mapping() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    disp = MockEventDispatcher()
    director.bind(disp)

    # Register character h as Hoshiko
    director.register_character("h", name="Hoshiko")

    # Show character on stage using character ID 'h'
    comp.show_character("h", "neutral", position="center", transition="cut")
    assert comp.render_list()[0].asset_id == "h/neutral"

    # DialogueEvent emitted with display name 'Hoshiko' and emotion 'happy'
    dlg = DialogueEvent(
        speaker="Hoshiko",
        text="Hello!",
        voice=None,
        emotion="happy",
        line_number=5,
    )
    disp.emit_event(dlg)
    assert comp.render_list()[0].asset_id == "h/happy"

    # Test handle_expr with display name
    director.handle_expr("Hoshiko sad")
    assert comp.render_list()[0].asset_id == "h/sad"

    # Test handle_move with display name
    director.handle_move("Hoshiko to left")

    # Test handle_hide with display name
    director.handle_hide("Hoshiko with cut")
    assert len(comp.render_list()) == 0



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
            ChoiceOption(index=0, text="Go left", target="left_path", line_number=10),
            ChoiceOption(index=1, text="Go right", target="right_path", line_number=11),
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


# ---------------------------------------------------------------------- #
# Scene, Image, Side Image Director Hooks
# ---------------------------------------------------------------------- #


def test_scene_and_image_hooks():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    # Put a character sprite on the stage
    compositor.show_character("alice", "happy", position="center", transition="cut")
    char_layer0 = compositor.stage.get_layer("characters")
    assert char_layer0 is not None
    assert "alice" in char_layer0.elements

    # ~ scene clears characters and sets background
    director.handle_scene("forest with cut")
    char_layer = compositor.stage.get_layer("characters")
    assert char_layer is not None
    assert len(char_layer.elements) == 0
    bg_layer = compositor.stage.get_layer("background")
    assert bg_layer is not None
    assert "bg_main" in bg_layer.elements
    assert bg_layer.elements["bg_main"].asset_id == "bg/forest"

    # ~ image displays arbitrary foreground element
    director.handle_image("item_sword props/sword at center z=50")
    fg_layer = compositor.stage.get_layer("foreground")
    assert fg_layer is not None
    assert "item_sword" in fg_layer.elements
    assert fg_layer.elements["item_sword"].asset_id == "props/sword"


def test_side_image_resolution():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    director.register_character("alice", asset_prefix="char/alice", side_image="side/alice")
    director.register_character("bob", asset_prefix="char/bob")

    # Alice has explicit side_image
    side_alice = director.resolve_side_image("alice", "happy")
    assert side_alice == "side/alice"

    # Bob falls back to asset_prefix + emotion
    side_bob = director.resolve_side_image("bob", "smile")
    assert side_bob == "char/bob_smile"

    # Unknown speaker has no side image
    assert director.resolve_side_image("unknown", None) is None


# ---------------------------------------------------------------------- #
# Audio Hooks & Voice Integration
# ---------------------------------------------------------------------- #


class TestDirectorAudioHooks:
    def test_stage_director_audio_hooks(self) -> None:
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # Trigger ~ play music title.ogg
        dispatcher.dispatch(HookEvent(hook_name="play", args="music title.ogg fade=1.0 volume=0.9", line_number=10))
        assert mixer.channels["music"].is_playing
        assert backend.calls[-1][0] == "play"
        assert backend.calls[-1][1] == "music"

        # Trigger ~ volume music 0.5
        dispatcher.dispatch(HookEvent(hook_name="volume", args="music 0.5", line_number=11))
        assert mixer.channels["music"].volume == pytest.approx(0.5)

        # Trigger ~ stop music fade=0.5
        dispatcher.dispatch(HookEvent(hook_name="stop", args="music fade=0.5", line_number=12))
        assert mixer.channels["music"].fade_duration == 0.5

    def test_stage_director_audio_loop_points(self) -> None:
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        dispatcher.dispatch(
            HookEvent(
                hook_name="play",
                args="music theme.ogg loop=True loop_start=12.5 loop_end=95.0",
                line_number=10,
            )
        )
        assert backend.calls[-1][0] == "play"
        assert backend.calls[-1][1] == "music"
        assert backend.calls[-1][3] is True  # loop
        assert backend.calls[-1][5] == 12.5  # loop_start
        assert backend.calls[-1][6] == 95.0  # loop_end

    def test_stage_director_voice_playback_and_auto_stop(self) -> None:
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # Dialogue with voice clip
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Hello!", voice="alice_01.ogg", emotion=None, line_number=1))
        assert mixer.channels["voice"].is_playing
        assert backend.calls[-1][0] == "play"
        assert backend.calls[-1][1] == "voice"
        assert backend.calls[-1][2] == "alice_01.ogg"

        # Dialogue without voice clip stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Second line without voice.", voice=None, emotion=None, line_number=2))
        assert not mixer.channels["voice"].is_playing
        assert backend.calls[-1][0] == "stop"
        assert backend.calls[-1][1] == "voice"

        # Narration also stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Third line.", voice="alice_02.ogg", emotion=None, line_number=3))
        assert mixer.channels["voice"].is_playing
        dispatcher.dispatch(NarrationEvent(text="A quiet pause.", line_number=4))
        assert not mixer.channels["voice"].is_playing

        # SceneExitEvent stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Fourth line.", voice="alice_03.ogg", emotion=None, line_number=5))
        assert mixer.channels["voice"].is_playing
        dispatcher.dispatch(SceneExitEvent(scene_id="intro", transition_kind="jump", target=None, line_number=6))
        assert not mixer.channels["voice"].is_playing

        # StoryEndEvent stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Fifth line.", voice="alice_04.ogg", emotion=None, line_number=7))
        assert mixer.channels["voice"].is_playing
        dispatcher.dispatch(StoryEndEvent(scene_id="intro", reason="completed"))
        assert not mixer.channels["voice"].is_playing

    def test_stage_director_skip_mode_suppression(self) -> None:
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        is_skipping = False
        director = StageDirector(compositor, audio=mixer, skip_mode_cb=lambda: is_skipping)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # When skip is not active, sound and voice play
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound click.ogg", line_number=1))
        assert backend.calls[-1][1] == "sound"

        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Voice line", voice="alice_v.ogg", emotion=None, line_number=2))
        assert backend.calls[-1][1] == "voice"

        # When skip is active, sound/voice hook and dialogue voice are dropped
        is_skipping = True
        backend.calls.clear()

        dispatcher.dispatch(HookEvent(hook_name="play", args="sound click2.ogg", line_number=3))
        dispatcher.dispatch(HookEvent(hook_name="play", args="voice clip2.ogg", line_number=4))
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Voice line 2", voice="alice_v2.ogg", emotion=None, line_number=5))

        # Only the auto-stop call on voice from dialogue occurs, no play calls for sound/voice
        play_calls = [c for c in backend.calls if c[0] == "play"]
        assert play_calls == []

        # But music/ambient still play during skip mode!
        dispatcher.dispatch(HookEvent(hook_name="play", args="music bgm.ogg", line_number=6))
        assert backend.calls[-1][0] == "play"
        assert backend.calls[-1][1] == "music"

    def test_ui_choice_menu_zero_and_many_options(self) -> None:
        from eager.ui.components import ChoiceMenu

        # 1. Zero options (empty choice box)
        menu_empty = ChoiceMenu(1280, 720)
        menu_empty.set_options([])
        backend = NullRenderer()
        menu_empty.draw(backend)
        assert len(backend.ui_calls) == 0

        # 2. Large choice list (15 choices)
        many_choices = [
            ChoiceOption(index=i, text=f"Option {i}", target=f"target_{i}", enabled=True)
            for i in range(15)
        ]
        menu_many = ChoiceMenu(1280, 720)
        menu_many.set_options(many_choices)
        menu_many.draw(backend)
        assert len(backend.ui_calls) > 0
        # Boundary click tests
        assert menu_many.hit_test(-100, -100) is None
        assert menu_many.hit_test(2000, 2000) is None

    def test_stage_director_audio_generic_hooks(self) -> None:
        """Verify ~ play, ~ stop, ~ pause, ~ resume hooks route correctly."""
        backend = NullAudioBackend()
        audio = AudioMixer(backend=backend)
        comp = StageCompositor(1920, 1080)
        director = StageDirector(comp, audio=audio)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        dispatcher.dispatch(HookEvent(hook_name="play", args="music theme.ogg fade=1.0 loop=True", line_number=1))
        assert audio.channels["music"].is_playing
        assert backend.calls[-1][0] == "play"
        assert backend.calls[-1][1] == "music"

        dispatcher.dispatch(HookEvent(hook_name="play", args="sound hit.ogg volume=0.7", line_number=2))
        assert "sound" in audio.channels
        assert backend.calls[-1][0] == "play"
        assert backend.calls[-1][1] == "sound"

        dispatcher.dispatch(HookEvent(hook_name="play", args="voice voice_line.ogg", line_number=3))
        assert audio.channels["voice"].is_playing
        assert backend.calls[-1][0] == "play"
        assert backend.calls[-1][1] == "voice"

        dispatcher.dispatch(HookEvent(hook_name="pause", args="music", line_number=4))
        assert audio.channels["music"].is_paused is True

        dispatcher.dispatch(HookEvent(hook_name="resume", args="music", line_number=5))
        assert audio.channels["music"].is_paused is False

        dispatcher.dispatch(HookEvent(hook_name="stop", args="music fade=0.5", line_number=6))
        assert audio.channels["music"].fade_duration == 0.5

    def test_director_hide_image_and_hide_element(self) -> None:
        """Verify ~ image, ~ hide_image, and ~ hide_element hooks."""
        from eager.core.dispatcher import EventDispatcher
        from eager.core.events import HookEvent

        comp = StageCompositor()
        director = StageDirector(comp)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        dispatcher.dispatch(HookEvent(hook_name="image", args="logo ui/logo at center z=50", line_number=1))
        fg = comp.stage.get_layer("foreground")
        assert fg is not None
        assert fg.get_element("logo") is not None

        dispatcher.dispatch(HookEvent(hook_name="hide_image", args="logo", line_number=2))
        assert fg.get_element("logo") is None

        # Arbitrary layer
        dispatcher.dispatch(HookEvent(hook_name="image", args="icon ui/icon layer=custom_layer", line_number=3))
        custom_layer = comp.stage.get_layer("custom_layer")
        assert custom_layer is not None
        assert custom_layer.get_element("icon") is not None

        dispatcher.dispatch(HookEvent(hook_name="hide_element", args="custom_layer icon", line_number=4))
        assert custom_layer.get_element("icon") is None

    def test_director_scene_bg(self) -> None:
        """Verify ~ scene_bg hook."""
        from eager.core.dispatcher import EventDispatcher
        from eager.core.events import HookEvent, SceneEnterEvent

        comp = StageCompositor()
        director = StageDirector(comp)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        dispatcher.dispatch(HookEvent(hook_name="scene_bg", args="intro bg/forest with dissolve duration=1.0", line_number=1))
        assert "intro" in director.scene_backgrounds
        assert director.scene_backgrounds["intro"] == ("bg/forest", "dissolve", 1.0)

        dispatcher.dispatch(SceneEnterEvent(scene_id="intro", display_name="Intro", line_number=1))
        comp.step(1.0)
        bg_layer = comp.stage.get_layer("background")
        assert bg_layer is not None
        bg_elem = bg_layer.get_element("bg_main")
        assert bg_elem is not None
        assert bg_elem.asset_id == "bg/forest"





