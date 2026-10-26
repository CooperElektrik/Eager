"""Adversarial stress tests for PygletAudioBackend and MiniaudioAudioBackend.

Milestone 3 Challenger suite verifying audio fallbacks, error resilience,
and graceful degradation under corrupted or missing audio assets.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Any
from unittest import mock

import pytest


def _create_test_wav(path: str, duration_sec: float = 0.2, sample_rate: int = 44100) -> None:
    """Create a minimal valid 16-bit stereo PCM WAV file."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        num_frames = int(duration_sec * sample_rate)
        wf.writeframes(b"\x00" * (num_frames * 4))


class TestAdversarialAudioResilience(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.valid_wav = os.path.join(self.tmp_dir.name, "valid.wav")
        _create_test_wav(self.valid_wav)

        self.missing_wav = os.path.join(self.tmp_dir.name, "non_existent.wav")

        self.zero_byte_wav = os.path.join(self.tmp_dir.name, "zero_byte.wav")
        with open(self.zero_byte_wav, "wb"):
            pass

        self.corrupt_header_wav = os.path.join(self.tmp_dir.name, "corrupt_header.wav")
        with open(self.corrupt_header_wav, "wb") as f:
            f.write(b"RIFF\x12\x34\x56\x78WAVEfmt \x01\x02\x03\x04")

        self.text_file = os.path.join(self.tmp_dir.name, "plain_text.txt")
        with open(self.text_file, "wb") as f:
            f.write(b"This is a plaintext script file, not an audio payload.")

        self.random_binary = os.path.join(self.tmp_dir.name, "random.bin")
        with open(self.random_binary, "wb") as f:
            f.write(os.urandom(2048))

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    # =========================================================================
    # 1. PygletAudioBackend Adversarial Tests
    # =========================================================================

    def test_pyglet_invalid_payloads_log_warning_and_do_not_crash(self) -> None:
        """PygletAudioBackend must log WARNING and set is_playing()=False on corrupt/missing files."""
        pytest.importorskip("pyglet")
        from eager_graphics.renderers.pyglet import PygletAudioBackend

        backend = PygletAudioBackend()

        adversarial_targets = [
            ("missing", self.missing_wav),
            ("zero_byte", self.zero_byte_wav),
            ("corrupt_header", self.corrupt_header_wav),
            ("text", self.text_file),
            ("random_binary", self.random_binary),
        ]

        for label, path in adversarial_targets:
            # Test streaming (music/ambient)
            with self.assertLogs("eager_graphics.renderers.pyglet", level="WARNING"):
                backend.play("music", path, loop=True)
                self.assertFalse(
                    backend.is_playing("music"),
                    f"Pyglet streaming should not be playing for {label}",
                )

            # Test static SFX (sfx/voice/ui)
            with self.assertLogs("eager_graphics.renderers.pyglet", level="WARNING"):
                backend.play("sfx", path, loop=False)
                self.assertFalse(
                    backend.is_playing("sfx"),
                    f"Pyglet sfx should not be playing for {label}",
                )

            backend.update(0.05)
            backend.stop("music")
            backend.stop("sfx")

        backend.shutdown()

    def test_pyglet_directory_and_empty_path(self) -> None:
        """PygletAudioBackend must handle directory and empty string paths safely."""
        pytest.importorskip("pyglet")
        from eager_graphics.renderers.pyglet import PygletAudioBackend

        backend = PygletAudioBackend()

        for invalid_path in [self.tmp_dir.name, "", Path(self.tmp_dir.name)]:
            with self.assertLogs("eager_graphics.renderers.pyglet", level="WARNING"):
                backend.play("music", invalid_path, loop=True)
                self.assertFalse(backend.is_playing("music"))

            with self.assertLogs("eager_graphics.renderers.pyglet", level="WARNING"):
                backend.play("sfx", invalid_path, loop=False)
                self.assertFalse(backend.is_playing("sfx"))

        backend.shutdown()

    def test_pyglet_corrupt_file_on_already_playing_channel(self) -> None:
        """Replacing an active channel with a corrupt file must stop playback and log WARNING."""
        pytest.importorskip("pyglet")
        from eager_graphics.renderers.pyglet import PygletAudioBackend

        backend = PygletAudioBackend()
        backend.play("music", self.valid_wav, loop=True)
        self.assertTrue(backend.is_playing("music"))

        with self.assertLogs("eager_graphics.renderers.pyglet", level="WARNING"):
            backend.play("music", self.corrupt_header_wav, loop=True)
            self.assertFalse(
                backend.is_playing("music"),
                "Active player should be stopped and channel should report is_playing() == False",
            )

        backend.update(0.05)
        backend.stop("music")
        backend.shutdown()

    # =========================================================================
    # 2. MiniaudioAudioBackend Adversarial Tests
    # =========================================================================

    def test_miniaudio_streaming_and_decoding_adversarial_payloads(self) -> None:
        """MiniaudioAudioBackend must log WARNING and safely reject corrupt/missing payloads."""
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()

        adversarial_targets = [
            ("missing", self.missing_wav),
            ("zero_byte", self.zero_byte_wav),
            ("corrupt_header", self.corrupt_header_wav),
            ("text", self.text_file),
            ("random_binary", self.random_binary),
        ]

        for label, path in adversarial_targets:
            # Streaming channel (music)
            with self.assertLogs("eager_graphics.renderers.miniaudio", level="WARNING"):
                backend.play("music", path, loop=True)
                self.assertFalse(
                    backend.is_playing("music"),
                    f"Miniaudio music should not be playing for {label}",
                )

            # Decoded channel (sfx)
            with self.assertLogs("eager_graphics.renderers.miniaudio", level="WARNING"):
                backend.play("sfx", path, loop=False)
                self.assertFalse(
                    backend.is_playing("sfx"),
                    f"Miniaudio sfx should not be playing for {label}",
                )

            backend.update(0.05)
            backend.stop("music")
            backend.stop("sfx")

        backend.shutdown()

    def test_miniaudio_directory_and_empty_path(self) -> None:
        """MiniaudioAudioBackend must safely handle directory and empty paths."""
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()

        for invalid_path in [self.tmp_dir.name, "", Path(self.tmp_dir.name)]:
            with self.assertLogs("eager_graphics.renderers.miniaudio", level="WARNING"):
                backend.play("music", invalid_path, loop=True)
                self.assertFalse(backend.is_playing("music"))

            with self.assertLogs("eager_graphics.renderers.miniaudio", level="WARNING"):
                backend.play("sfx", invalid_path, loop=False)
                self.assertFalse(backend.is_playing("sfx"))

        backend.shutdown()

    def test_miniaudio_device_init_failure_simulation(self) -> None:
        """Simulate hardware audio device init failure and verify warning log and graceful fallback."""
        pytest.importorskip("miniaudio")
        import miniaudio

        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        with (
            mock.patch.object(
                miniaudio,
                "PlaybackDevice",
                side_effect=RuntimeError("Hardware audio device unavailable"),
            ),
            self.assertLogs("eager_graphics.renderers.miniaudio", level="WARNING") as cm,
        ):
            backend = MiniaudioAudioBackend()
            self.assertFalse(backend._active)
            self.assertIsNone(backend._device)

            # Operations on inactive backend must return safely
            backend.play("music", self.valid_wav, loop=True)
            self.assertFalse(backend.is_playing("music"))
            backend.play("sfx", self.valid_wav, loop=False)
            self.assertFalse(backend.is_playing("sfx"))
            backend.pause("music")
            backend.resume("music")
            backend.set_volume("music", 0.5)
            backend.update(0.1)
            backend.stop("music")
            backend.shutdown()

        self.assertTrue(any("Hardware audio device unavailable" in msg for msg in cm.output))

    def test_miniaudio_stream_mid_playback_read_error(self) -> None:
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
        self.assertTrue(track.is_playing)

        generator: Any = backend._generator
        if generator is not None:
            # First send consumes initial valid chunk
            _ = generator.send(50)
            self.assertTrue(track.is_playing)

            # Second send triggers FaultyStream error and logs WARNING
            with self.assertLogs("eager_graphics.renderers.miniaudio", level="WARNING") as cm:
                _ = generator.send(50)
                self.assertFalse(track.is_playing)

            self.assertTrue(any("faulty_stream.wav" in msg for msg in cm.output))

        backend.shutdown()

    def test_miniaudio_missing_library_fallback(self) -> None:
        """When miniaudio is not installed, MiniaudioAudioBackend must log warning and not crash."""
        import eager_graphics.renderers.miniaudio as ma_mod

        with (
            mock.patch.object(ma_mod, "MINIAUDIO_AVAILABLE", False),
            mock.patch.object(ma_mod, "miniaudio", None),
        ):
            ma_mod._WARNED_MISSING = False
            with self.assertLogs("eager_graphics.renderers.miniaudio", level="WARNING") as cm:
                backend = ma_mod.MiniaudioAudioBackend()
                self.assertFalse(backend._active)
                backend.play("music", self.valid_wav, loop=True)
                self.assertFalse(backend.is_playing("music"))
                backend.stop("music")
                backend.shutdown()

            self.assertTrue(any("is not installed" in msg for msg in cm.output))


if __name__ == "__main__":
    unittest.main()
