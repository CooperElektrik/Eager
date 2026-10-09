"""Tests for eager_core audio: AudioBackend, NullAudioBackend, and AudioMixer."""

import unittest

from eager_core.audio import AudioMixer, NullAudioBackend


class TestAudioMixer(unittest.TestCase):
    def test_audio_mixer_channels_and_volumes(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)

        # Initial playback
        mixer.play("music", "bgm/theme.ogg", loop=True, volume=0.8)
        self.assertEqual(len(backend.calls), 1)
        call = backend.calls[0]
        self.assertEqual(call[0], "play")
        self.assertEqual(call[1], "music")
        self.assertEqual(call[2], "bgm/theme.ogg")
        self.assertTrue(call[3])
        self.assertAlmostEqual(call[4], 0.8)

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

        # Update another 0.5s (finished)
        mixer.update(0.5)
        self.assertFalse(mixer.channels["music"].is_playing)

    def test_audio_save_and_load_state(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("ambient", "wind.ogg", volume=0.7)

        state = mixer.save_state()
        self.assertIn("channels", state)
        self.assertTrue(state["channels"]["ambient"]["is_playing"])

        backend2 = NullAudioBackend()
        mixer2 = AudioMixer(backend=backend2)
        mixer2.load_state(state)
        self.assertTrue(mixer2.channels["ambient"].is_playing)
        self.assertEqual(backend2.calls[-1][0], "play")


if __name__ == "__main__":
    unittest.main()
