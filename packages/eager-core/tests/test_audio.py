"""Tests for eager_core audio: AudioBackend, NullAudioBackend, and AudioMixer."""

import unittest

from eager_core.audio import AudioMixer, NullAudioBackend


class TestAudioMixer(unittest.TestCase):
    def test_audio_mixer_channels_and_volumes(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)

        # Initial playback
        mixer.play("music", "bgm/theme.ogg", loop=True, volume=0.8, loop_start=10.0, loop_end=90.0)
        self.assertEqual(len(backend.calls), 1)
        call = backend.calls[0]
        self.assertEqual(call[0], "play")
        self.assertEqual(call[1], "music")
        self.assertEqual(call[2], "bgm/theme.ogg")
        self.assertTrue(call[3])
        self.assertAlmostEqual(call[4], 0.8)
        self.assertEqual(call[5], 0.0)  # fade_in
        self.assertEqual(call[6], 10.0)  # loop_start
        self.assertEqual(call[7], 90.0)  # loop_end

        # Set master volume scales output
        mixer.set_master_volume(0.5)
        music_vol_calls = [c for c in backend.calls if c[0] == "set_volume" and c[1] == "music"]
        self.assertTrue(len(music_vol_calls) > 0)
        self.assertAlmostEqual(music_vol_calls[-1][2], 0.4)  # 0.5 master * 0.8 track

        # Stop channel
        mixer.stop("music")
        self.assertEqual(backend.calls[-1], ("stop", "music", 0.0))

    def test_audio_fade_update(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)

        mixer.play("music", "bgm/theme.ogg", volume=1.0)
        mixer.stop("music", fade_out=1.0)

        # Update 0.5s (halfway)
        mixer.update(0.5)
        self.assertTrue(mixer.channels["music"].is_playing)
        self.assertAlmostEqual(mixer.channels["music"].volume, 0.5, places=1)
        self.assertIn(("update", 0.5), backend.calls)

        # Update another 0.5s (finished)
        mixer.update(0.5)
        self.assertFalse(mixer.channels["music"].is_playing)

    def test_audio_save_and_load_state_with_loop_points(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("music", "theme.ogg", volume=0.7, loop=True, loop_start=12.5, loop_end=95.0)

        state = mixer.save_state()
        self.assertIn("channels", state)
        self.assertTrue(state["channels"]["music"]["is_playing"])
        self.assertEqual(state["channels"]["music"]["loop_start"], 12.5)
        self.assertEqual(state["channels"]["music"]["loop_end"], 95.0)

        backend2 = NullAudioBackend()
        mixer2 = AudioMixer(backend=backend2)
        mixer2.load_state(state)
        self.assertTrue(mixer2.channels["music"].is_playing)
        self.assertEqual(mixer2.channels["music"].loop_start, 12.5)
        self.assertEqual(mixer2.channels["music"].loop_end, 95.0)
        play_calls = [c for c in backend2.calls if c[0] == "play" and c[1] == "music"]
        self.assertEqual(len(play_calls), 1)
        self.assertEqual(play_calls[0][1], "music")
        self.assertEqual(play_calls[0][2], "theme.ogg")
        self.assertTrue(play_calls[0][3])
        self.assertAlmostEqual(play_calls[0][4], 0.7)
        self.assertEqual(play_calls[0][6], 12.5)
        self.assertEqual(play_calls[0][7], 95.0)

    def test_audio_mixer_shutdown(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        self.assertFalse(backend.shutdown_called)
        mixer.shutdown()
        self.assertTrue(backend.shutdown_called)
        self.assertIn(("shutdown",), backend.calls)


if __name__ == "__main__":
    unittest.main()
