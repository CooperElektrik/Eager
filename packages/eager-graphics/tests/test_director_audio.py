"""Tests for the StageDirector audio-hook wiring (~ play / ~ stop / ~ volume).

The audio mixer itself lives in ``eager_core``; this test covers the graphics
layer's director integration with it.
"""

import unittest

from eager_core import AudioMixer, NullAudioBackend
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.events import HookEvent

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


if __name__ == "__main__":
    unittest.main()
