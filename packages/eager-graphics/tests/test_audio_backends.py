"""Tests for PygletAudioBackend, RaylibAudioBackend, and MiniaudioAudioBackend."""

import os
import tempfile
import unittest
import wave

import pytest


def _create_dummy_wav(path: str, duration_sec: float = 0.5, sample_rate: int = 44100) -> None:
    """Create a short dummy valid WAV file."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        num_frames = int(duration_sec * sample_rate)
        # Write zeros/silence
        wf.writeframes(b"\x00" * (num_frames * 4))


class TestHardwareAudioBackends(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.wav_path = os.path.join(self.tmp_dir.name, "test.wav")
        _create_dummy_wav(self.wav_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_pyglet_audio_backend(self) -> None:
        pytest.importorskip("pyglet")
        from eager_graphics.renderers.pyglet import PygletAudioBackend

        backend = PygletAudioBackend()
        backend.play("music", self.wav_path, loop=True, volume=0.8, loop_start=0.1, loop_end=0.4)
        self.assertTrue(backend.is_playing("music"))

        backend.set_volume("music", 0.5)
        backend.update(0.1)

        backend.pause("music")
        backend.resume("music")

        backend.stop("music")
        self.assertFalse(backend.is_playing("music"))

        backend.shutdown()

    def test_raylib_audio_backend(self) -> None:
        pytest.importorskip("pyray")
        from eager_graphics.renderers.raylib import RaylibAudioBackend

        backend = RaylibAudioBackend()
        backend.play("music", self.wav_path, loop=True, volume=0.8, loop_start=0.1, loop_end=0.4)

        backend.set_volume("music", 0.5)
        backend.update(0.1)

        backend.pause("music")
        self.assertFalse(backend.is_playing("music"))
        backend.resume("music")

        backend.stop("music")
        self.assertFalse(backend.is_playing("music"))

        backend.shutdown()

    def test_miniaudio_audio_backend(self) -> None:
        pytest.importorskip("miniaudio")
        from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

        backend = MiniaudioAudioBackend()
        backend.play("music", self.wav_path, loop=True, volume=0.8, loop_start=0.1, loop_end=0.4)
        if backend._active:
            self.assertTrue(backend.is_playing("music"))

        backend.set_volume("music", 0.5)
        backend.update(0.1)

        backend.pause("music")
        self.assertFalse(backend.is_playing("music"))
        backend.resume("music")

        backend.stop("music")
        self.assertFalse(backend.is_playing("music"))

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

        self.assertEqual(len(errors), 0)
        backend.shutdown()


if __name__ == "__main__":
    unittest.main()

