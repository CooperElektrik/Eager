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

    def test_audio_rollback_continuity_same_track(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)

        # Start playback in scene beat 1
        mixer.play("music", "bgm/peaceful.ogg", volume=0.8)
        state_beat1 = mixer.save_state()
        self.assertEqual(len([c for c in backend.calls if c[0] == "play"]), 1)

        # Progress to scene beat 2 (same track continues playing)
        _ = mixer.save_state()

        # Roll back from beat 2 to beat 1
        mixer.load_state(state_beat1)

        # Playback MUST NOT restart from frame 0 (no new backend.play calls)
        play_calls = [c for c in backend.calls if c[0] == "play"]
        self.assertEqual(len(play_calls), 1)
        self.assertTrue(mixer.channels["music"].is_playing)
        self.assertEqual(mixer.channels["music"].current_asset, "bgm/peaceful.ogg")

    def test_audio_rollback_across_track_change(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)

        # Scene 1: peaceful theme
        mixer.play("music", "bgm/peaceful.ogg", volume=0.8)
        state_scene1 = mixer.save_state()

        # Scene 2: battle starts
        mixer.play("music", "bgm/battle.ogg", volume=1.0)
        _ = mixer.save_state()
        self.assertEqual(len([c for c in backend.calls if c[0] == "play"]), 2)

        # Roll back to Scene 1
        mixer.load_state(state_scene1)

        # When rolling back across track change, peaceful theme must be restarted
        play_calls = [c for c in backend.calls if c[0] == "play"]
        self.assertEqual(len(play_calls), 3)
        self.assertEqual(play_calls[-1][2], "bgm/peaceful.ogg")
        self.assertEqual(mixer.channels["music"].current_asset, "bgm/peaceful.ogg")

    def test_audio_rollback_paused_state(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("music", "bgm/theme.ogg")
        mixer.pause("music")
        saved = mixer.save_state()

        mixer2 = AudioMixer(backend=backend)
        mixer2.load_state(saved)
        self.assertTrue(mixer2.channels["music"].is_paused)
        pause_calls = [c for c in backend.calls if c[0] == "pause" and c[1] == "music"]
        self.assertGreaterEqual(len(pause_calls), 1)

    def test_audio_polyphonic_sound_pool_overlap(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)

        first = mixer.play("sound", "thunder.ogg")
        second = mixer.play("sound", "click.ogg")
        self.assertEqual(first, "sound_0")
        self.assertEqual(second, "sound_1")
        # Both overlap instead of the second cutting off the first
        self.assertTrue(mixer.channels["sound_0"].is_playing)
        self.assertTrue(mixer.channels["sound_1"].is_playing)
        self.assertEqual(mixer.channels["sound_0"].current_asset, "thunder.ogg")
        self.assertTrue(mixer.is_playing("sound"))

        # Single-voice channels like music still cut off previous track
        mixer.play("music", "a.ogg")
        mixer.play("music", "b.ogg")
        self.assertEqual(mixer.channels["music"].current_asset, "b.ogg")

    def test_audio_polyphonic_stop_volume_fan_out(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound", "a.ogg", auto_channels=True)
        mixer.play("sound", "b.ogg", auto_channels=True)

        # Type volume set on the base applies to pooled slots
        mixer.set_channel_volume("sound", 0.5)
        pooled_vols = [
            c for c in backend.calls if c[0] == "set_volume" and c[1] in ("sound_0", "sound_1")
        ]
        self.assertTrue(len(pooled_vols) >= 2)

        # Track volume set on the base fans out too
        mixer.set_volume("sound", 0.3)
        self.assertAlmostEqual(mixer.channels["sound_0"].volume, 0.3)
        self.assertAlmostEqual(mixer.channels["sound_1"].volume, 0.3)

        # Stopping the base clears the whole pool
        mixer.stop("sound")
        self.assertFalse(mixer.is_playing("sound"))
        self.assertFalse(mixer.channels["sound_0"].is_playing)
        self.assertFalse(mixer.channels["sound_1"].is_playing)

        # Stopping one explicit slot leaves siblings playing
        mixer.play("sound", "c.ogg", auto_channels=True)
        mixer.play("sound", "d.ogg", auto_channels=True)
        mixer.stop("sound_0")
        self.assertFalse(mixer.is_playing("sound_0"))
        self.assertTrue(mixer.is_playing("sound_1"))

    def test_audio_polyphonic_slot_reuse_and_save_load(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound", "a.ogg", auto_channels=True)
        mixer.play("sound", "b.ogg", auto_channels=True)
        mixer.stop("sound_0")
        reused = mixer.play("sound", "c.ogg", auto_channels=True)
        self.assertEqual(reused, "sound_0")

        state = mixer.save_state()
        backend2 = NullAudioBackend()
        mixer2 = AudioMixer(backend=backend2)
        mixer2.load_state(state)
        self.assertTrue(mixer2.is_playing("sound"))
        self.assertTrue(mixer2.channels["sound_0"].is_playing)
        self.assertEqual(mixer2.channels["sound_0"].current_asset, "c.ogg")

    def test_audio_polyphonic_fade_reset_on_slot_reuse(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound_0", "a.ogg")
        mixer.stop("sound_0", fade_out=1.0)
        self.assertGreater(mixer.channels["sound_0"].fade_duration, 0.0)

        # A new SFX takes over the same slot before the fade completes.
        mixer.play("sound_0", "b.ogg")
        self.assertEqual(mixer.channels["sound_0"].fade_duration, 0.0)
        self.assertFalse(mixer.channels["sound_0"].stop_on_fade_complete)

        # The stale fade must not silence the new playback.
        mixer.update(1.5)
        self.assertTrue(mixer.channels["sound_0"].is_playing)
        self.assertEqual(mixer.channels["sound_0"].current_asset, "b.ogg")

    def test_audio_polyphonic_noncontiguous_indices_fill_gaps(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound_5", "sting.ogg")
        first = mixer.play("sound", "a.ogg", auto_channels=True, max_polyphony=4)
        second = mixer.play("sound", "b.ogg", auto_channels=True, max_polyphony=4)
        self.assertEqual(first, "sound_0")
        self.assertEqual(second, "sound_1")
        # The explicit high slot is untouched, not stolen.
        self.assertEqual(mixer.channels["sound_5"].current_asset, "sting.ogg")
        self.assertTrue(mixer.channels["sound_5"].is_playing)

    def test_audio_polyphonic_exhaustion_steals_oldest(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        got = [mixer.play("sound", f"{i}.ogg", auto_channels=True, max_polyphony=2) for i in range(3)]
        self.assertEqual(got, ["sound_0", "sound_1", "sound_0"])
        self.assertEqual(mixer.channels["sound_0"].current_asset, "2.ogg")
        self.assertEqual(mixer.channels["sound_1"].current_asset, "1.ogg")
        self.assertEqual(len(mixer._pool_members("sound")), 2)

    def test_audio_polyphonic_inherits_base_track_volume(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.set_volume("sound", 0.5)
        slot = mixer.play("sound", "click.ogg", auto_channels=True)
        self.assertAlmostEqual(mixer.channels[slot].volume, 0.5)
        last_play = [c for c in backend.calls if c[0] == "play"][-1]
        self.assertAlmostEqual(last_play[4], 0.5)  # master * type * inherited track

        # An explicit volume overrides the inheritance.
        slot2 = mixer.play("sound", "bang.ogg", auto_channels=True, volume=0.9)
        self.assertAlmostEqual(mixer.channels[slot2].volume, 0.9)

    def test_audio_polyphonic_pause_resume_fan_out(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound", "a.ogg", auto_channels=True)
        mixer.play("sound", "b.ogg", auto_channels=True)
        mixer.pause("sound")
        self.assertTrue(mixer.channels["sound_0"].is_paused)
        self.assertTrue(mixer.channels["sound_1"].is_paused)
        self.assertTrue(mixer.is_playing("sound"))  # paused still counts as active
        pauses = [c for c in backend.calls if c[0] == "pause"]
        self.assertEqual(len(pauses), 2)
        mixer.resume("sound")
        self.assertFalse(mixer.channels["sound_0"].is_paused)
        self.assertFalse(mixer.channels["sound_1"].is_paused)
        resumes = [c for c in backend.calls if c[0] == "resume"]
        self.assertEqual(len(resumes), 2)

    def test_audio_polyphonic_backend_completion_reuse(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound", "a.ogg", auto_channels=True)
        # The backend finishes naturally before mixer.update() runs.
        backend._playing_channels.discard("sound_0")
        self.assertFalse(mixer.is_playing("sound_0"))
        self.assertFalse(mixer.is_playing("sound"))
        reused = mixer.play("sound", "b.ogg", auto_channels=True)
        self.assertEqual(reused, "sound_0")

    def test_audio_polyphonic_checkpoint_prunes_idle_slots(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound", "a.ogg", auto_channels=True)
        mixer.play("sound", "b.ogg", auto_channels=True)
        active = mixer.save_state()
        self.assertIn("sound_0", active["channels"])

        mixer.stop("sound")
        mixer.update(0.0)
        idle_state = mixer.save_state()
        self.assertNotIn("sound_0", idle_state["channels"])
        self.assertNotIn("sound_1", idle_state["channels"])

        # Rolling back to a snapshot without pool slots drops local ghosts.
        mixer2 = AudioMixer(backend=NullAudioBackend())
        mixer2.play("sound", "x.ogg", auto_channels=True)
        self.assertIn("sound_0", mixer2.channels)
        mixer2.load_state(idle_state)
        self.assertNotIn("sound_0", mixer2.channels)

    def test_audio_polyphonic_unbounded_fills_gaps(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound_5", "sting.ogg")
        # Unbounded mode (max_polyphony<=0) fills gaps like bounded mode.
        first = mixer.play("sound", "a.ogg", auto_channels=True, max_polyphony=0)
        self.assertEqual(first, "sound_0")
        self.assertEqual(mixer.channels["sound_5"].current_asset, "sting.ogg")

    def test_audio_polyphonic_steal_spares_explicit_high_slots(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.play("sound_99", "rumble.ogg")
        mixer.play("sound", "a.ogg", auto_channels=True, max_polyphony=2)
        mixer.play("sound", "b.ogg", auto_channels=True, max_polyphony=2)
        # Pool exhausted: the oldest managed slot is stolen, never sound_99.
        victim = mixer.play("sound", "c.ogg", auto_channels=True, max_polyphony=2)
        self.assertEqual(victim, "sound_0")
        self.assertEqual(mixer.channels["sound_99"].current_asset, "rumble.ogg")
        self.assertTrue(mixer.channels["sound_99"].is_playing)

    def test_audio_polyphonic_unbounded_never_steals(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        for i in range(16):
            mixer.play("sound", f"{i}.ogg", auto_channels=True, max_polyphony=0)
        grown = mixer.play("sound", "extra.ogg", auto_channels=True, max_polyphony=0)
        self.assertEqual(grown, "sound_16")
        self.assertEqual(mixer.channels["sound_0"].current_asset, "0.ogg")

    def test_audio_polyphonic_explicit_slot_inherits_base_volume(self):
        backend = NullAudioBackend()
        mixer = AudioMixer(backend=backend)
        mixer.set_volume("sound", 0.5)
        mixer.play("sound_0", "click.ogg")
        self.assertAlmostEqual(mixer.channels["sound_0"].volume, 0.5)
        # An explicit volume still wins over the inheritance.
        mixer.play("sound_1", "bang.ogg", volume=0.9)
        self.assertAlmostEqual(mixer.channels["sound_1"].volume, 0.9)


if __name__ == "__main__":
    unittest.main()

