"""Tests for PygletAudioBackend and MiniaudioAudioBackend."""

from __future__ import annotations

import os
import tempfile
import wave
from typing import TYPE_CHECKING

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
    tmp_dir: tempfile.TemporaryDirectory[str]  # pyright: ignore[reportUninitializedInstanceVariable]
    wav_path: str  # pyright: ignore[reportUninitializedInstanceVariable]

    @pytest.fixture(autouse=True)
    def setup_teardown(self) -> Generator[None, None, None]:
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.wav_path = os.path.join(self.tmp_dir.name, "test.wav")
        _create_dummy_wav(self.wav_path)
        yield
        self.tmp_dir.cleanup()

    def test_pyglet_audio_backend(self) -> None:
        pytest.importorskip("pyglet")
        from eager.backends.audio.pyglet import PygletAudioBackend

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

