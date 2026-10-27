"""Tests for PygletAudioBackend and MiniaudioAudioBackend."""

from __future__ import annotations

import logging
import os
import tempfile
import wave
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


def _create_dummy_wav(path: str, duration_sec: float = 0.5, sample_rate: int = 44100) -> None:
    """Create a short dummy valid WAV file."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        num_frames = int(duration_sec * sample_rate)
        # Write zeros/silence
        wf.writeframes(b"\x00" * (num_frames * 4))


class TestHardwareAudioBackends:
    @pytest.fixture(autouse=True)
    def setup_teardown(self) -> Generator[None, None, None]:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.wav_path = os.path.join(self.tmp_dir.name, "test.wav")
        _create_dummy_wav(self.wav_path)
        yield
        self.tmp_dir.cleanup()

    def test_pyglet_audio_backend(self) -> None:
        pytest.importorskip("pyglet")
        from eager_graphics.renderers.pyglet import PygletAudioBackend

        backend = PygletAudioBackend()
        backend.play("music", self.wav_path, loop=True, volume=0.8, loop_start=0.1, loop_end=0.4)
        assert backend.is_playing("music")

        backend.set_volume("music", 0.5)
        backend.update(0.1)

        backend.pause("music")
        backend.resume("music")

        backend.stop("music")
        assert not backend.is_playing("music")

        backend.shutdown()

    def test_miniaudio_audio_backend(self) -> None:
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()
        backend.play("music", self.wav_path, loop=True, volume=0.8, loop_start=0.1, loop_end=0.4)
        if backend._active:
            assert backend.is_playing("music")

        backend.set_volume("music", 0.5)
        backend.update(0.1)

        backend.pause("music")
        assert not backend.is_playing("music")
        backend.resume("music")

        backend.stop("music")
        assert not backend.is_playing("music")

        backend.shutdown()

    def test_pyglet_audio_backend_error_handling(self, caplog: pytest.LogCaptureFixture) -> None:
        pytest.importorskip("pyglet")
        from eager_graphics.renderers.pyglet import PygletAudioBackend

        backend = PygletAudioBackend()
        missing_path = os.path.join(self.tmp_dir.name, "missing.wav")

        # Missing audio file should log warning and not crash
        with caplog.at_level(logging.WARNING, logger="eager_graphics.renderers.pyglet"):
            caplog.clear()
            backend.play("sfx", missing_path, loop=False)
            assert not backend.is_playing("sfx")
            assert any("missing.wav" in msg for msg in caplog.messages)

        # Corrupt audio file should log warning and not crash
        corrupt_path = os.path.join(self.tmp_dir.name, "corrupt.wav")
        with open(corrupt_path, "wb") as f:
            f.write(b"invalid wave data")

        with caplog.at_level(logging.WARNING, logger="eager_graphics.renderers.pyglet"):
            caplog.clear()
            backend.play("music", corrupt_path, loop=True)
            assert not backend.is_playing("music")
            assert any("corrupt.wav" in msg for msg in caplog.messages)

        backend.shutdown()

    def test_miniaudio_audio_backend_error_handling(self, caplog: pytest.LogCaptureFixture) -> None:
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()
        missing_path = os.path.join(self.tmp_dir.name, "missing.wav")

        # Missing file on streaming channel (music)
        with caplog.at_level(logging.WARNING, logger="eager_graphics.renderers.miniaudio"):
            caplog.clear()
            backend.play("music", missing_path, loop=True)
            assert not backend.is_playing("music")
            assert any("missing.wav" in msg for msg in caplog.messages)

        # Missing file on decoded channel (sfx)
        with caplog.at_level(logging.WARNING, logger="eager_graphics.renderers.miniaudio"):
            caplog.clear()
            backend.play("sfx", missing_path, loop=False)
            assert not backend.is_playing("sfx")
            assert any("missing.wav" in msg for msg in caplog.messages)

        # Corrupt file on decoded channel
        corrupt_path = os.path.join(self.tmp_dir.name, "corrupt.wav")
        with open(corrupt_path, "wb") as f:
            f.write(b"invalid wave data")

        with caplog.at_level(logging.WARNING, logger="eager_graphics.renderers.miniaudio"):
            caplog.clear()
            backend.play("sfx", corrupt_path, loop=False)
            assert not backend.is_playing("sfx")
            assert any("corrupt.wav" in msg for msg in caplog.messages)

        backend.shutdown()

    def test_miniaudio_device_uninitialized_fallback(self) -> None:
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()
        backend._active = False  # Simulate hardware device unavailability
        # Must return immediately without error
        backend.play("music", "test.wav", loop=True)
        assert not backend.is_playing("music")
        backend.shutdown()

    def test_miniaudio_streaming_vs_decoding(self) -> None:
        pytest.importorskip("miniaudio")
        from unittest.mock import patch

        import miniaudio

        try:
            miniaudio.PlaybackDevice()
        except miniaudio.MiniaudioError:
            pytest.skip("No audio device available to initialize miniaudio backend")

        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()

        with (
            patch.object(miniaudio, "stream_file", wraps=miniaudio.stream_file) as mock_stream,
            patch.object(miniaudio, "decode_file", wraps=miniaudio.decode_file) as mock_decode,
        ):
            # Long-running channel (music) must use stream_file
            backend.play("music", self.wav_path, loop=True)
            assert mock_stream.called
            assert not mock_decode.called

            mock_stream.reset_mock()
            mock_decode.reset_mock()

            # Short sound effect channel (sfx) must use decode_file
            backend.play("sfx", self.wav_path, loop=False)
            assert mock_decode.called
            assert not mock_stream.called

        backend.shutdown()

    def test_miniaudio_audio_backend_thread_safety(self) -> None:
        pytest.importorskip("miniaudio")
        import threading

        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()
        backend.play("music", self.wav_path, loop=True, volume=0.8)

        errors: list[Exception] = []

        def worker(thread_id: int) -> None:
            try:
                for i in range(40):
                    backend.set_volume("music", (i % 10) / 10.0)
                    backend.is_playing("music")
                    backend.pause("music")
                    backend.resume("music")
                    backend.update(0.01)
                    if i % 10 == 0:
                        backend.play(f"sfx_{thread_id}", self.wav_path, loop=False)
                    elif i % 10 == 5:
                        backend.stop(f"sfx_{thread_id}")
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        backend.shutdown()

    def test_miniaudio_stream_eof_non_loop(self) -> None:
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend, _ChannelTrack

        backend = MiniaudioAudioBackend()

        class DummyStream:
            def send(self, n: int) -> list[int]:
                return []

        track = _ChannelTrack(
            samples=None,
            sample_rate=44100,
            nchannels=2,
            volume=1.0,
            loop=False,
            stream=DummyStream(),
        )
        backend._tracks["music"] = track
        if backend._generator is not None:
            backend._generator.send(100)
            assert not track.is_playing
        backend.shutdown()

    def test_miniaudio_stream_stop_and_shutdown_clears_is_playing(self) -> None:
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend, _ChannelTrack

        backend = MiniaudioAudioBackend()

        class DummyStream:
            def send(self, n: int) -> list[int]:
                return [0] * 100

        track = _ChannelTrack(
            samples=None,
            sample_rate=44100,
            nchannels=2,
            volume=1.0,
            loop=False,
            stream=DummyStream(),
        )
        backend._tracks["music"] = track
        assert track.is_playing
        backend.stop("music")
        assert not track.is_playing

        track2 = _ChannelTrack(
            samples=None,
            sample_rate=44100,
            nchannels=2,
            volume=1.0,
            loop=False,
            stream=DummyStream(),
        )
        backend._tracks["sfx"] = track2
        assert track2.is_playing
        backend.shutdown()
        assert not track2.is_playing

    def test_miniaudio_stream_mid_playback_read_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """A stream raising an unhandled read error mid-playback must log WARNING and stop playing."""
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend, _ChannelTrack

        backend = MiniaudioAudioBackend()

        class FaultyStream:
            def __init__(self) -> None:
                self.calls = 0

            def send(self, n: int) -> list[int]:
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("Simulated mid-playback I/O fault")
                return [0] * (n * 2)

        track = _ChannelTrack(
            samples=None,
            sample_rate=44100,
            nchannels=2,
            volume=1.0,
            loop=False,
            path_str="faulty_stream.wav",
            stream=FaultyStream(),
        )
        backend._tracks["ambient"] = track
        assert track.is_playing

        generator: Any = backend._generator
        if generator is not None:
            # First send consumes initial valid chunk
            _ = generator.send(50)
            assert track.is_playing

            # Second send triggers FaultyStream error and logs WARNING
            with caplog.at_level(logging.WARNING, logger="eager_graphics.renderers.miniaudio"):
                caplog.clear()
                _ = generator.send(50)
                assert not track.is_playing
                assert any("faulty_stream.wav" in msg for msg in caplog.messages)

        backend.shutdown()

    def test_miniaudio_missing_library_fallback(self, caplog: pytest.LogCaptureFixture) -> None:
        """When miniaudio is not installed, MiniaudioAudioBackend must log warning and not crash."""
        import eager_graphics.renderers.miniaudio as ma_mod

        with (
            mock.patch.object(ma_mod, "MINIAUDIO_AVAILABLE", False),
            mock.patch.object(ma_mod, "miniaudio", None),
        ):
            ma_mod._WARNED_MISSING = False
            with caplog.at_level(logging.WARNING, logger="eager_graphics.renderers.miniaudio"):
                caplog.clear()
                backend = ma_mod.MiniaudioAudioBackend()
                assert not backend._active
                backend.play("music", self.wav_path, loop=True)
                assert not backend.is_playing("music")
                backend.stop("music")
                backend.shutdown()
                assert any("is not installed" in msg for msg in caplog.messages)
