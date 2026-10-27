"""Tests for eager_core audio: AudioBackend, NullAudioBackend, and AudioMixer."""

from typing import cast

import pytest

from eager_core.audio import AudioMixer, NullAudioBackend


def test_audio_mixer_channels_and_volumes() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)

    # Initial playback
    mixer.play("music", "bgm/theme.ogg", loop=True, volume=0.8, loop_start=10.0, loop_end=90.0)
    assert len(backend.calls) == 1
    call = backend.calls[0]
    assert call[0] == "play"
    assert call[1] == "music"
    assert call[2] == "bgm/theme.ogg"
    assert call[3] is True
    assert cast(float, call[4]) == pytest.approx(0.8)
    assert call[5] == 0.0  # fade_in
    assert call[6] == 10.0  # loop_start
    assert call[7] == 90.0  # loop_end

    # Set master volume scales output
    mixer.set_master_volume(0.5)
    music_vol_calls = [c for c in backend.calls if c[0] == "set_volume" and c[1] == "music"]
    assert len(music_vol_calls) > 0
    assert cast(float, music_vol_calls[-1][2]) == pytest.approx(0.4)  # 0.5 master * 0.8 track

    # Stop channel
    mixer.stop("music")
    assert backend.calls[-1] == ("stop", "music", 0.0)


def test_audio_fade_update() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)

    mixer.play("music", "bgm/theme.ogg", volume=1.0)
    mixer.stop("music", fade_out=1.0)

    # Update 0.5s (halfway)
    mixer.update(0.5)
    assert mixer.channels["music"].is_playing
    assert mixer.channels["music"].volume == pytest.approx(0.5, abs=0.1)
    assert ("update", 0.5) in backend.calls

    # Update another 0.5s (finished)
    mixer.update(0.5)
    assert not mixer.channels["music"].is_playing


def test_audio_save_and_load_state_with_loop_points() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("music", "theme.ogg", volume=0.7, loop=True, loop_start=12.5, loop_end=95.0)

    state = mixer.save_state()
    assert "channels" in state
    assert state["channels"]["music"]["is_playing"]
    assert state["channels"]["music"]["loop_start"] == 12.5
    assert state["channels"]["music"]["loop_end"] == 95.0

    backend2 = NullAudioBackend()
    mixer2 = AudioMixer(backend=backend2)
    mixer2.load_state(state)
    assert mixer2.channels["music"].is_playing
    assert mixer2.channels["music"].loop_start == 12.5
    assert mixer2.channels["music"].loop_end == 95.0
    play_calls = [c for c in backend2.calls if c[0] == "play" and c[1] == "music"]
    assert len(play_calls) == 1
    assert play_calls[0][1] == "music"
    assert play_calls[0][2] == "theme.ogg"
    assert play_calls[0][3] is True
    assert cast(float, play_calls[0][4]) == pytest.approx(0.7)
    assert play_calls[0][6] == 12.5
    assert play_calls[0][7] == 95.0


def test_audio_mixer_shutdown() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    assert not backend.shutdown_called
    mixer.shutdown()
    assert backend.shutdown_called
    assert ("shutdown",) in backend.calls


def test_audio_rollback_continuity_same_track() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)

    # Start playback in scene beat 1
    mixer.play("music", "bgm/peaceful.ogg", volume=0.8)
    state_beat1 = mixer.save_state()
    assert len([c for c in backend.calls if c[0] == "play"]) == 1

    # Progress to scene beat 2 (same track continues playing)
    _ = mixer.save_state()

    # Roll back from beat 2 to beat 1
    mixer.load_state(state_beat1)

    # Playback MUST NOT restart from frame 0 (no new backend.play calls)
    play_calls = [c for c in backend.calls if c[0] == "play"]
    assert len(play_calls) == 1
    assert mixer.channels["music"].is_playing
    assert mixer.channels["music"].current_asset == "bgm/peaceful.ogg"


def test_audio_rollback_across_track_change() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)

    # Scene 1: peaceful theme
    mixer.play("music", "bgm/peaceful.ogg", volume=0.8)
    state_scene1 = mixer.save_state()

    # Scene 2: battle starts
    mixer.play("music", "bgm/battle.ogg", volume=1.0)
    _ = mixer.save_state()
    assert len([c for c in backend.calls if c[0] == "play"]) == 2

    # Roll back to Scene 1
    mixer.load_state(state_scene1)

    # When rolling back across track change, peaceful theme must be restarted
    play_calls = [c for c in backend.calls if c[0] == "play"]
    assert len(play_calls) == 3
    assert play_calls[-1][2] == "bgm/peaceful.ogg"
    assert mixer.channels["music"].current_asset == "bgm/peaceful.ogg"


def test_audio_rollback_paused_state() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("music", "bgm/theme.ogg")
    mixer.pause("music")
    saved = mixer.save_state()

    mixer2 = AudioMixer(backend=backend)
    mixer2.load_state(saved)
    assert mixer2.channels["music"].is_paused
    pause_calls = [c for c in backend.calls if c[0] == "pause" and c[1] == "music"]
    assert len(pause_calls) >= 1


def test_audio_polyphonic_sound_pool_overlap() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)

    first = mixer.play("sound", "thunder.ogg")
    second = mixer.play("sound", "click.ogg")
    assert first == "sound_0"
    assert second == "sound_1"
    # Both overlap instead of the second cutting off the first
    assert mixer.channels["sound_0"].is_playing
    assert mixer.channels["sound_1"].is_playing
    assert mixer.channels["sound_0"].current_asset == "thunder.ogg"
    assert mixer.is_playing("sound")

    # Single-voice channels like music still cut off previous track
    mixer.play("music", "a.ogg")
    mixer.play("music", "b.ogg")
    assert mixer.channels["music"].current_asset == "b.ogg"


def test_audio_polyphonic_stop_volume_fan_out() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound", "a.ogg", auto_channels=True)
    mixer.play("sound", "b.ogg", auto_channels=True)

    # Type volume set on the base applies to pooled slots
    mixer.set_channel_volume("sound", 0.5)
    pooled_vols = [
        c for c in backend.calls if c[0] == "set_volume" and c[1] in ("sound_0", "sound_1")
    ]
    assert len(pooled_vols) >= 2

    # Track volume set on the base fans out too
    mixer.set_volume("sound", 0.3)
    assert mixer.channels["sound_0"].volume == pytest.approx(0.3)
    assert mixer.channels["sound_1"].volume == pytest.approx(0.3)

    # Stopping the base clears the whole pool
    mixer.stop("sound")
    assert not mixer.is_playing("sound")
    assert not mixer.channels["sound_0"].is_playing
    assert not mixer.channels["sound_1"].is_playing

    # Stopping one explicit slot leaves siblings playing
    mixer.play("sound", "c.ogg", auto_channels=True)
    mixer.play("sound", "d.ogg", auto_channels=True)
    mixer.stop("sound_0")
    assert not mixer.is_playing("sound_0")
    assert mixer.is_playing("sound_1")


def test_audio_polyphonic_slot_reuse_and_save_load() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound", "a.ogg", auto_channels=True)
    mixer.play("sound", "b.ogg", auto_channels=True)
    mixer.stop("sound_0")
    reused = mixer.play("sound", "c.ogg", auto_channels=True)
    assert reused == "sound_0"

    state = mixer.save_state()
    backend2 = NullAudioBackend()
    mixer2 = AudioMixer(backend=backend2)
    mixer2.load_state(state)
    assert mixer2.is_playing("sound")
    assert mixer2.channels["sound_0"].is_playing
    assert mixer2.channels["sound_0"].current_asset == "c.ogg"


def test_audio_polyphonic_fade_reset_on_slot_reuse() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound_0", "a.ogg")
    mixer.stop("sound_0", fade_out=1.0)
    assert mixer.channels["sound_0"].fade_duration > 0.0

    # A new SFX takes over the same slot before the fade completes.
    mixer.play("sound_0", "b.ogg")
    assert mixer.channels["sound_0"].fade_duration == 0.0
    assert not mixer.channels["sound_0"].stop_on_fade_complete

    # The stale fade must not silence the new playback.
    mixer.update(1.5)
    assert mixer.channels["sound_0"].is_playing
    assert mixer.channels["sound_0"].current_asset == "b.ogg"


def test_audio_polyphonic_noncontiguous_indices_fill_gaps() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound_5", "sting.ogg")
    first = mixer.play("sound", "a.ogg", auto_channels=True, max_polyphony=4)
    second = mixer.play("sound", "b.ogg", auto_channels=True, max_polyphony=4)
    assert first == "sound_0"
    assert second == "sound_1"
    # The explicit high slot is untouched, not stolen.
    assert mixer.channels["sound_5"].current_asset == "sting.ogg"
    assert mixer.channels["sound_5"].is_playing


def test_audio_polyphonic_exhaustion_steals_oldest() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    got = [mixer.play("sound", f"{i}.ogg", auto_channels=True, max_polyphony=2) for i in range(3)]
    assert got == ["sound_0", "sound_1", "sound_0"]
    assert mixer.channels["sound_0"].current_asset == "2.ogg"
    assert mixer.channels["sound_1"].current_asset == "1.ogg"
    assert len(mixer._pool_members("sound")) == 2


def test_audio_polyphonic_inherits_base_track_volume() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.set_volume("sound", 0.5)
    slot = mixer.play("sound", "click.ogg", auto_channels=True)
    assert mixer.channels[slot].volume == pytest.approx(0.5)
    last_play = [c for c in backend.calls if c[0] == "play"][-1]
    assert cast(float, last_play[4]) == pytest.approx(0.5)  # master * type * inherited track

    # An explicit volume overrides the inheritance.
    slot2 = mixer.play("sound", "bang.ogg", auto_channels=True, volume=0.9)
    assert mixer.channels[slot2].volume == pytest.approx(0.9)


def test_audio_polyphonic_pause_resume_fan_out() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound", "a.ogg", auto_channels=True)
    mixer.play("sound", "b.ogg", auto_channels=True)
    mixer.pause("sound")
    assert mixer.channels["sound_0"].is_paused
    assert mixer.channels["sound_1"].is_paused
    assert mixer.is_playing("sound")  # paused still counts as active
    pauses = [c for c in backend.calls if c[0] == "pause"]
    assert len(pauses) == 2
    mixer.resume("sound")
    assert not mixer.channels["sound_0"].is_paused
    assert not mixer.channels["sound_1"].is_paused
    resumes = [c for c in backend.calls if c[0] == "resume"]
    assert len(resumes) == 2


def test_audio_polyphonic_backend_completion_reuse() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound", "a.ogg", auto_channels=True)
    # The backend finishes naturally before mixer.update() runs.
    backend._playing_channels.discard("sound_0")
    assert not mixer.is_playing("sound_0")
    assert not mixer.is_playing("sound")
    reused = mixer.play("sound", "b.ogg", auto_channels=True)
    assert reused == "sound_0"


def test_audio_polyphonic_checkpoint_prunes_idle_slots() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound", "a.ogg", auto_channels=True)
    mixer.play("sound", "b.ogg", auto_channels=True)
    active = mixer.save_state()
    assert "sound_0" in active["channels"]

    mixer.stop("sound")
    mixer.update(0.0)
    idle_state = mixer.save_state()
    assert "sound_0" not in idle_state["channels"]
    assert "sound_1" not in idle_state["channels"]

    # Rolling back to a snapshot without pool slots drops local ghosts.
    mixer2 = AudioMixer(backend=NullAudioBackend())
    mixer2.play("sound", "x.ogg", auto_channels=True)
    assert "sound_0" in mixer2.channels
    mixer2.load_state(idle_state)
    assert "sound_0" not in mixer2.channels


def test_audio_polyphonic_unbounded_fills_gaps() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound_5", "sting.ogg")
    # Unbounded mode (max_polyphony<=0) fills gaps like bounded mode.
    first = mixer.play("sound", "a.ogg", auto_channels=True, max_polyphony=0)
    assert first == "sound_0"
    assert mixer.channels["sound_5"].current_asset == "sting.ogg"


def test_audio_polyphonic_steal_spares_explicit_high_slots() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("sound_99", "rumble.ogg")
    mixer.play("sound", "a.ogg", auto_channels=True, max_polyphony=2)
    mixer.play("sound", "b.ogg", auto_channels=True, max_polyphony=2)
    # Pool exhausted: the oldest managed slot is stolen, never sound_99.
    victim = mixer.play("sound", "c.ogg", auto_channels=True, max_polyphony=2)
    assert victim == "sound_0"
    assert mixer.channels["sound_99"].current_asset == "rumble.ogg"
    assert mixer.channels["sound_99"].is_playing


def test_audio_polyphonic_unbounded_never_steals() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    for i in range(16):
        mixer.play("sound", f"{i}.ogg", auto_channels=True, max_polyphony=0)
    grown = mixer.play("sound", "extra.ogg", auto_channels=True, max_polyphony=0)
    assert grown == "sound_16"
    assert mixer.channels["sound_0"].current_asset == "0.ogg"


def test_audio_polyphonic_explicit_slot_inherits_base_volume() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.set_volume("sound", 0.5)
    mixer.play("sound_0", "click.ogg")
    assert mixer.channels["sound_0"].volume == pytest.approx(0.5)
    # An explicit volume still wins over the inheritance.
    mixer.play("sound_1", "bang.ogg", volume=0.9)
    assert mixer.channels["sound_1"].volume == pytest.approx(0.9)
