"""Tests for eager.core audio: AudioBackend, NullAudioBackend, and AudioMixer."""

from pathlib import Path
from typing import cast

import pytest

from eager.core.audio import AudioMixer, NullAudioBackend


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
    assert call[5] == 10.0  # loop_start
    assert call[6] == 90.0  # loop_end

    # Set master volume scales output
    mixer.set_master_volume(0.5)
    music_vol_calls = [c for c in backend.calls if c[0] == "set_volume" and c[1] == "music"]
    assert len(music_vol_calls) > 0
    assert cast(float, music_vol_calls[-1][2]) == pytest.approx(0.4)  # 0.5 master * 0.8 track

    # Stop channel
    mixer.stop("music")
    assert backend.calls[-1] == ("stop", "music")


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
    assert play_calls[0][5] == 12.5
    assert play_calls[0][6] == 95.0


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

def test_audio_fade_in_software_ramp() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("music", "bgm.ogg", volume=0.8, fade_in=2.0)

    # Initial volume starts at 0.0
    assert mixer.channels["music"].volume == 0.0
    assert mixer.channels["music"].fade_duration == 2.0
    assert mixer.channels["music"].fade_target_vol == 0.8

    # Advance 1.0 second (50% progress)
    mixer.update(1.0)
    assert mixer.channels["music"].volume == pytest.approx(0.4)

    # Advance another 1.0 second (100% complete)
    mixer.update(1.0)
    assert mixer.channels["music"].volume == pytest.approx(0.8)
    assert mixer.channels["music"].fade_duration == 0.0
    assert mixer.channels["music"].is_playing is True


def test_audio_pause_resume_all() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("music", "bgm.ogg")
    mixer.play("ambient", "wind.ogg")

    mixer.pause_all()
    assert mixer.channels["music"].is_paused is True
    assert mixer.channels["ambient"].is_paused is True

    mixer.resume_all()
    assert mixer.channels["music"].is_paused is False
    assert mixer.channels["ambient"].is_paused is False


def test_audio_update_preserves_paused_channel() -> None:
    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend)
    mixer.play("music", "bgm.ogg")
    assert mixer.channels["music"].is_playing is True

    mixer.pause("music")
    assert backend.is_playing("music") is False

    # Updating while paused must not wipe is_playing or current_asset
    mixer.update(0.016)
    assert mixer.channels["music"].is_playing is True
    assert mixer.channels["music"].is_paused is True
    assert mixer.channels["music"].current_asset == "bgm.ogg"

    mixer.resume("music")
    assert backend.is_playing("music") is True
    mixer.update(0.016)
    assert mixer.channels["music"].is_playing is True
    assert mixer.channels["music"].is_paused is False



def test_audio_mixer_save_state_settles_fades(tmp_path: Path) -> None:
    from eager.core.audio import AudioMixer, NullAudioBackend

    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend, asset_dir=tmp_path)
    mixer.play("music", "theme.ogg", fade_in=2.0, volume=0.8)
    mixer.play("ambient", "rain.ogg", fade_in=0.0, volume=0.6)
    mixer.stop("ambient", fade_out=1.0)

    state = mixer.save_state()
    music_state = state["channels"]["music"]
    ambient_state = state["channels"]["ambient"]
    assert music_state["volume"] == pytest.approx(0.8)
    assert music_state["fade_duration"] == 0.0
    assert ambient_state["is_playing"] is False
    assert ambient_state["current_asset"] is None


def test_audio_mixer_resolves_extensionless_and_channel_subdirs(tmp_path: Path) -> None:
    from eager.core.audio import AudioMixer, NullAudioBackend

    (tmp_path / "audio" / "music").mkdir(parents=True)
    (tmp_path / "audio" / "voice").mkdir(parents=True)
    theme = tmp_path / "audio" / "music" / "theme.ogg"
    line = tmp_path / "audio" / "voice" / "line01.wav"
    theme.write_bytes(b"OggS")
    line.write_bytes(b"RIFF")

    backend = NullAudioBackend()
    mixer = AudioMixer(backend=backend, asset_dir=tmp_path)
    mixer.play("music", "theme")
    mixer.play("voice", "line01")

    play_calls = [c for c in backend.calls if c[0] == "play"]
    assert play_calls[0][2] == str(theme.resolve())
    assert play_calls[1][2] == str(line.resolve())


def test_audio_mixer_blocks_traversal_without_asset_dir_and_cwd_fallback(tmp_path: Path) -> None:
    from eager.core.exceptions import AudioError

    backend = NullAudioBackend()
    mixer_no_dir = AudioMixer(backend=backend, asset_dir=None)
    with pytest.raises(AudioError, match="Path traversal detected"):
        mixer_no_dir._resolve_asset("../outside.ogg")
    with pytest.raises(AudioError, match="Path traversal detected"):
        mixer_no_dir._resolve_asset("/etc/passwd")

    mixer_with_dir = AudioMixer(backend=backend, asset_dir=tmp_path)
    resolved_missing = mixer_with_dir._resolve_asset("missing.ogg")
    assert isinstance(resolved_missing, Path)
    assert resolved_missing.is_relative_to(tmp_path.resolve())
