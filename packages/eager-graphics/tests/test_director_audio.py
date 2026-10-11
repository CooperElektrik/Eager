"""Tests for the StageDirector audio-hook wiring (~ play / ~ stop / ~ volume).

The audio mixer itself lives in ``eager_core``; this test covers the graphics
layer's director integration with it.
"""

import unittest

from eager_core import AudioMixer, NullAudioBackend
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.events import (
    DialogueEvent,
    HookEvent,
    NarrationEvent,
    SceneExitEvent,
    StoryEndEvent,
)

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector


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
        dispatcher.dispatch(HookEvent(hook_name="play", args="sound click.ogg", line_number=1))
        self.assertEqual(backend.calls[-1][1], "sound")

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


if __name__ == "__main__":
    unittest.main()
