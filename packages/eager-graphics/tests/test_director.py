"""Tests for StageDirector event and hook dispatching."""

import unittest

from eager_core import AudioMixer, NullAudioBackend
from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    HookEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)
from eager_core.events import (
    ChoiceOption as EagerChoiceOption,
)
from eager_core.types import Color
from eager_runtime.dispatcher import EventDispatcher

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector
from eager_graphics.renderers.null import NullRenderer
from eager_graphics.ui_components import UIOverlay
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


# ---------------------------------------------------------------------- #
# Scene, Image, Side Image & NVL Director Hooks
# ---------------------------------------------------------------------- #


def test_scene_and_image_hooks():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    # Put a character sprite on the stage
    compositor.show_character("alice", "happy", position="center", transition="cut")
    assert "alice" in compositor.stage.get_layer("characters").elements

    # ~ scene clears characters and sets background
    director.handle_scene("forest with cut")
    char_layer = compositor.stage.get_layer("characters")
    assert len(char_layer.elements) == 0
    bg_layer = compositor.stage.get_layer("background")
    assert "bg_main" in bg_layer.elements
    assert bg_layer.elements["bg_main"].asset_id == "bg/forest"

    # ~ image displays arbitrary foreground element
    director.handle_image("item_sword props/sword at center z=50")
    fg_layer = compositor.stage.get_layer("foreground")
    assert "item_sword" in fg_layer.elements
    assert fg_layer.elements["item_sword"].asset_id == "props/sword"


def test_side_image_resolution():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    director.register_character("alice", asset_prefix="char/alice", side_image="side/alice")
    director.register_character("bob", asset_prefix="char/bob")

    # Alice has explicit side_image
    side_alice = director._resolve_side_image("alice", "happy")
    assert side_alice == "side/alice"

    # Bob falls back to asset_prefix + emotion
    side_bob = director._resolve_side_image("bob", "smile")
    assert side_bob == "char/bob_smile"

    # Unknown speaker has no side image
    assert director._resolve_side_image("unknown", None) is None


def test_nvl_mode_and_overlay():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    # Toggle NVL mode on
    director.handle_nvl("on")
    assert director.ui_state.nvl_mode is True

    # Simulate dialogue events
    class DummyEvent:
        def __init__(self, speaker, text, emotion=None):
            self.speaker = speaker
            self.text = text
            self.emotion = emotion

    director.handle_dialogue_event(DummyEvent("Alice", "First NVL line."))
    director.handle_dialogue_event(DummyEvent("Bob", "Second NVL line."))
    director.handle_narration_event(DummyEvent(None, "And narrator spoke."))

    assert len(director.ui_state.nvl_entries) == 3
    assert director.ui_state.nvl_entries[0].speaker == "Alice"
    assert director.ui_state.nvl_entries[1].text == "Second NVL line."

    # Append
    director.handle_append_event(DummyEvent(None, "More narrator text."))
    assert "More narrator text." in director.ui_state.nvl_entries[2].text

    # Draw through NullRenderer to verify UIOverlay renders NVL without error
    renderer = NullRenderer()
    overlay = UIOverlay(1280, 720)
    overlay.draw(renderer, director.ui_state)

    # Verify rect was drawn for NVL window
    rects = [c for c in renderer.ui_calls if c["kind"] == "rect"]
    assert len(rects) > 0

    # Clear NVL
    director.handle_nvl_clear("")
    assert len(director.ui_state.nvl_entries) == 0

    # Toggle NVL off
    director.handle_nvl("off")
    assert director.ui_state.nvl_mode is False


# ---------------------------------------------------------------------- #
# Audio Hooks & Voice Integration
# ---------------------------------------------------------------------- #


class TestDirectorAudioHooks(unittest.TestCase):
    def test_stage_director_audio_hooks(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # Trigger ~ play music title.ogg
        dispatcher.dispatch(HookEvent(hook_name="play", args="music title.ogg fade=1.0 volume=0.9", line_number=10))
        self.assertTrue(mixer.channels["music"].is_playing)
        self.assertEqual(backend.calls[-1][0], "play")
        self.assertEqual(backend.calls[-1][1], "music")

        # Trigger ~ volume music 0.5
        dispatcher.dispatch(HookEvent(hook_name="volume", args="music 0.5", line_number=11))
        self.assertAlmostEqual(mixer.channels["music"].volume, 0.5)

        # Trigger ~ stop music fade=0.5
        dispatcher.dispatch(HookEvent(hook_name="stop", args="music fade=0.5", line_number=12))
        self.assertEqual(mixer.channels["music"].fade_duration, 0.5)

    def test_stage_director_audio_loop_points(self):
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
        self.assertEqual(backend.calls[-1][0], "play")
        self.assertEqual(backend.calls[-1][1], "music")
        self.assertTrue(backend.calls[-1][3])  # loop
        self.assertEqual(backend.calls[-1][6], 12.5)  # loop_start
        self.assertEqual(backend.calls[-1][7], 95.0)  # loop_end

    def test_stage_director_voice_playback_and_auto_stop(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # Dialogue with voice clip
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Hello!", voice="alice_01.ogg", emotion=None, line_number=1))
        self.assertTrue(mixer.channels["voice"].is_playing)
        self.assertEqual(backend.calls[-1][0], "play")
        self.assertEqual(backend.calls[-1][1], "voice")
        self.assertEqual(backend.calls[-1][2], "alice_01.ogg")

        # Dialogue without voice clip stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Second line without voice.", voice=None, emotion=None, line_number=2))
        self.assertFalse(mixer.channels["voice"].is_playing)
        self.assertEqual(backend.calls[-1][0], "stop")
        self.assertEqual(backend.calls[-1][1], "voice")

        # Narration also stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Third line.", voice="alice_02.ogg", emotion=None, line_number=3))
        self.assertTrue(mixer.channels["voice"].is_playing)
        dispatcher.dispatch(NarrationEvent(text="A quiet pause.", line_number=4))
        self.assertFalse(mixer.channels["voice"].is_playing)

        # SceneExitEvent stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Fourth line.", voice="alice_03.ogg", emotion=None, line_number=5))
        self.assertTrue(mixer.channels["voice"].is_playing)
        dispatcher.dispatch(SceneExitEvent(scene_id="intro", transition_kind="jump", target=None, line_number=6))
        self.assertFalse(mixer.channels["voice"].is_playing)

        # StoryEndEvent stops voice channel
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Fifth line.", voice="alice_04.ogg", emotion=None, line_number=7))
        self.assertTrue(mixer.channels["voice"].is_playing)
        dispatcher.dispatch(StoryEndEvent(scene_id="intro", reason="completed"))
        self.assertFalse(mixer.channels["voice"].is_playing)

    def test_stage_director_skip_mode_suppression(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        is_skipping = False
        director = StageDirector(compositor, audio=mixer, skip_mode_cb=lambda: is_skipping)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # When skip is not active, sound and voice play
        # (sound effects are polyphonic by default -> sound_0 pool slot)
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound click.ogg", line_number=1))
        self.assertEqual(backend.calls[-1][1], "sound_0")

        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Voice line", voice="alice_v.ogg", emotion=None, line_number=2))
        self.assertEqual(backend.calls[-1][1], "voice")

        # When skip is active, sound/voice hook and dialogue voice are dropped
        is_skipping = True
        backend.calls.clear()

        dispatcher.dispatch(HookEvent(hook_name="play", args="sound click2.ogg", line_number=3))
        dispatcher.dispatch(HookEvent(hook_name="play", args="voice clip2.ogg", line_number=4))
        dispatcher.dispatch(DialogueEvent(speaker="Alice", text="Voice line 2", voice="alice_v2.ogg", emotion=None, line_number=5))

        # Only the auto-stop call on voice from dialogue occurs, no play calls for sound/voice
        play_calls = [c for c in backend.calls if c[0] == "play"]
        self.assertEqual(play_calls, [])

        # But music/ambient still play during skip mode!
        dispatcher.dispatch(HookEvent(hook_name="play", args="music bgm.ogg", line_number=6))
        self.assertEqual(backend.calls[-1][0], "play")
        self.assertEqual(backend.calls[-1][1], "music")

    def test_stage_director_sound_polyphony_by_default(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # Overlapping SFX layer instead of cutting off
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound thunder.ogg", line_number=1))
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound click.ogg", line_number=2))
        plays = [c for c in backend.calls if c[0] == "play"]
        self.assertEqual([p[1] for p in plays], ["sound_0", "sound_1"])
        self.assertTrue(mixer.channels["sound_0"].is_playing)
        self.assertTrue(mixer.channels["sound_1"].is_playing)
        self.assertEqual(mixer.channels["sound_0"].current_asset, "thunder.ogg")
        self.assertEqual(mixer.channels["sound_1"].current_asset, "click.ogg")

        # ~ stop sound fans out to the whole pool
        dispatcher.dispatch(HookEvent(hook_name="stop", args="sound", line_number=3))
        self.assertFalse(mixer.is_playing("sound"))

    def test_stage_director_sound_polyphony_opt_out_and_opt_in(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # Legacy single-voice cutoff
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound a.ogg auto_channels=false", line_number=1))
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound b.ogg auto_channels=false", line_number=2))
        plays = [c for c in backend.calls if c[0] == "play"]
        self.assertTrue(all(p[1] == "sound" for p in plays))
        self.assertEqual(mixer.channels["sound"].current_asset, "b.ogg")

        # Other channels stay single by default but can opt in
        backend.calls.clear()
        dispatcher.dispatch(HookEvent(hook_name="play", args="music sting.ogg auto_channels=true", line_number=3))
        self.assertEqual(backend.calls[-1][1], "music_0")

    def test_stage_director_sound_volume_inheritance(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        # Track volume configured before playback carries into pool slots.
        dispatcher.dispatch(HookEvent(hook_name="volume", args="sound 0.5", line_number=1))
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound click.ogg", line_number=2))
        self.assertAlmostEqual(mixer.channels["sound_0"].volume, 0.5)

        # An explicit hook volume overrides the inherited one.
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound bang.ogg volume=0.9", line_number=3))
        self.assertAlmostEqual(mixer.channels["sound_1"].volume, 0.9)

    def test_stage_director_explicit_slot_inherits_base_volume(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        dispatcher.dispatch(HookEvent(hook_name="volume", args="sound 0.5", line_number=1))
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound_0 click.ogg", line_number=2))
        self.assertAlmostEqual(mixer.channels["sound_0"].volume, 0.5)

    def test_stage_director_max_polyphony_zero_is_unbounded(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        compositor = StageCompositor()
        director = StageDirector(compositor, audio=mixer)
        dispatcher = EventDispatcher()
        director.bind(dispatcher)

        for i in range(16):
            dispatcher.dispatch(
                HookEvent(hook_name="play", args=f"sound s{i}.ogg auto_channels=true", line_number=i)
            )
        dispatcher.dispatch(
            HookEvent(hook_name="play", args="sound extra.ogg auto_channels=true max_polyphony=0", line_number=100)
        )
        # Unbounded: grows to sound_16 instead of stealing sound_0.
        self.assertEqual(backend.calls[-1][1], "sound_16")
        self.assertEqual(mixer.channels["sound_0"].current_asset, "s0.ogg")




