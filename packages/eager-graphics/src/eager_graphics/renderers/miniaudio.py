"""Miniaudio-based audio playback backend for Eager-Graphics."""

from __future__ import annotations

import array
import sys
import threading
from pathlib import Path
from typing import Any

from eager_core.audio import BaseAudioBackend

try:
    import miniaudio

    MINIAUDIO_AVAILABLE = True
except ImportError:
    miniaudio = None  # type: ignore[assignment]
    MINIAUDIO_AVAILABLE = False


_WARNED_MISSING = False

STREAMING_CHANNELS = frozenset({"music", "ambient", "bgm", "bgs"})


def _check_miniaudio() -> bool:
    global _WARNED_MISSING
    if not MINIAUDIO_AVAILABLE or miniaudio is None:
        if not _WARNED_MISSING:
            sys.stderr.write(
                "Notice: 'miniaudio' is not installed; falling back to NullAudioBackend. "
                "Install with 'pip install eager-graphics[audio]'.\n"
            )
            _WARNED_MISSING = True
        return False
    return True


class _ChannelTrack:
    def __init__(
        self,
        samples: array.array | None,
        sample_rate: int,
        nchannels: int,
        volume: float = 1.0,
        loop: bool = False,
        loop_start_frame: int | None = None,
        loop_end_frame: int | None = None,
        path_str: str | None = None,
        stream: Any = None,
    ) -> None:
        self.samples = samples  # s16 samples interleaved for in-memory sfx
        self.sample_rate = sample_rate
        self.nchannels = nchannels
        self.volume = volume
        self.loop = loop
        self.loop_start_frame = loop_start_frame
        self.loop_end_frame = loop_end_frame
        self.path_str = path_str
        self.stream = stream
        self.buffer: array.array = array.array("h")
        self.frame_pos: int = 0
        self.total_frames: int = (
            len(samples) // nchannels if (samples is not None and nchannels > 0) else -1
        )
        self.is_playing: bool = True
        self.is_paused: bool = False


class MiniaudioAudioBackend(BaseAudioBackend):
    """Audio backend powered by miniaudio with soft-mixing and loop-point support.

    Decodes audio files (WAV, MP3, FLAC, Ogg Vorbis) to PCM frames and streams
    them into a miniaudio PlaybackDevice with per-channel volume, pausing, and
    intro/loop points. Uses a threading.Lock to synchronize access to active tracks
    between client calls and the miniaudio audio thread callback.
    """

    def __init__(self, sample_rate: int = 44100, nchannels: int = 2) -> None:
        self.sample_rate = sample_rate
        self.nchannels = nchannels
        self._tracks: dict[str, _ChannelTrack] = {}
        self._lock = threading.Lock()
        self._device: Any = None
        self._generator: Any = None
        self._active: bool = False

        if _check_miniaudio():
            self._start_device()

    def _start_device(self) -> None:
        if not MINIAUDIO_AVAILABLE or miniaudio is None:
            return

        def _pcm_generator():
            required_frames = yield b""
            bytes_per_sample = 2  # s16
            bytes_per_frame = self.nchannels * bytes_per_sample

            while True:
                req = required_frames
                with self._lock:
                    if not self._tracks:
                        out_bytes = bytes(req * bytes_per_frame)
                    else:
                        mixed = [0] * (req * self.nchannels)

                        for track in list(self._tracks.values()):
                            if not track.is_playing or track.is_paused:
                                continue

                            vol = track.volume
                            t_channels = track.nchannels

                            if track.samples is not None:
                                samples = track.samples
                                cur_f = track.frame_pos
                                total_f = track.total_frames
                                if total_f <= 0:
                                    continue
                                loop_end = (
                                    min(track.loop_end_frame, total_f)
                                    if track.loop_end_frame is not None
                                    else total_f
                                )
                                loop_start = (
                                    track.loop_start_frame
                                    if track.loop_start_frame is not None
                                    else 0
                                )

                                out_idx = 0
                                for _ in range(req):
                                    if cur_f >= loop_end:
                                        if track.loop:
                                            cur_f = loop_start
                                        else:
                                            track.is_playing = False
                                            break

                                    samp_idx = cur_f * t_channels
                                    if t_channels == 2:
                                        s_left = samples[samp_idx]
                                        s_right = samples[samp_idx + 1]
                                    else:
                                        s_left = samples[samp_idx]
                                        s_right = s_left

                                    mixed[out_idx] += int(s_left * vol)
                                    mixed[out_idx + 1] += int(s_right * vol)
                                    out_idx += 2
                                    cur_f += 1

                                track.frame_pos = cur_f

                            elif track.stream is not None:
                                needed_samples = req * t_channels
                                while len(track.buffer) < needed_samples:
                                    if track.loop_end_frame is not None and track.frame_pos >= track.loop_end_frame:
                                        if track.loop and track.path_str and miniaudio is not None:
                                            seek = track.loop_start_frame or 0
                                            track.frame_pos = seek
                                            try:
                                                track.stream = miniaudio.stream_file(
                                                    track.path_str,
                                                    output_format=miniaudio.SampleFormat.SIGNED16,
                                                    nchannels=track.nchannels,
                                                    sample_rate=track.sample_rate,
                                                    seek_frame=seek,
                                                )
                                            except Exception:  # noqa: BLE001
                                                track.is_playing = False
                                                break
                                        else:
                                            track.is_playing = False
                                            break
                                    try:
                                        frames_to_fetch = req
                                        if track.loop_end_frame is not None:
                                            frames_to_fetch = min(frames_to_fetch, track.loop_end_frame - track.frame_pos)
                                        self._lock.release()
                                        try:
                                            chunk = track.stream.send(max(1, frames_to_fetch))
                                        except StopIteration:
                                            chunk = []
                                        except Exception:  # noqa: BLE001
                                            chunk = []
                                            track.is_playing = False
                                        finally:
                                            self._lock.acquire()

                                        if not track.is_playing or track not in self._tracks.values():
                                            break

                                        if not chunk:
                                            if track.loop and track.path_str and miniaudio is not None:
                                                seek = track.loop_start_frame or 0
                                                track.frame_pos = seek
                                                try:
                                                    track.stream = miniaudio.stream_file(
                                                        track.path_str,
                                                        output_format=miniaudio.SampleFormat.SIGNED16,
                                                        nchannels=track.nchannels,
                                                        sample_rate=track.sample_rate,
                                                        seek_frame=seek,
                                                    )
                                                except Exception:  # noqa: BLE001
                                                    track.is_playing = False
                                                    break
                                            else:
                                                track.is_playing = False
                                                break
                                        else:
                                            track.buffer.extend(chunk)
                                            track.frame_pos += len(chunk) // t_channels
                                    except StopIteration:
                                        if track.loop and track.path_str and miniaudio is not None:
                                            seek = track.loop_start_frame or 0
                                            track.frame_pos = seek
                                            try:
                                                track.stream = miniaudio.stream_file(
                                                    track.path_str,
                                                    output_format=miniaudio.SampleFormat.SIGNED16,
                                                    nchannels=track.nchannels,
                                                    sample_rate=track.sample_rate,
                                                    seek_frame=seek,
                                                )
                                            except Exception:  # noqa: BLE001
                                                track.is_playing = False
                                                break
                                        else:
                                            track.is_playing = False
                                            break

                                samples_to_take = min(len(track.buffer), needed_samples)
                                out_idx = 0
                                for i in range(0, samples_to_take, t_channels):
                                    s_left = track.buffer[i]
                                    s_right = track.buffer[i + 1] if t_channels == 2 else s_left
                                    mixed[out_idx] += int(s_left * vol)
                                    mixed[out_idx + 1] += int(s_right * vol)
                                    out_idx += 2
                                del track.buffer[:samples_to_take]

                        # Clamp mixed samples to signed 16-bit
                        out_arr = array.array(
                            "h",
                            (max(-32768, min(32767, s)) for s in mixed),
                        )
                        out_bytes = out_arr.tobytes()

                required_frames = yield out_bytes

        try:
            self._generator = _pcm_generator()
            next(self._generator)
            self._device = miniaudio.PlaybackDevice(
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=self.nchannels,
                sample_rate=self.sample_rate,
            )
            self._device.start(self._generator)
            self._active = True
        except Exception:  # noqa: BLE001
            self._device = None
            self._active = False

    def play(
        self,
        channel: str,
        asset_path: str | Path,
        *,
        loop: bool = False,
        volume: float = 1.0,
        fade_in: float = 0.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        if not self._active or not MINIAUDIO_AVAILABLE or miniaudio is None:
            return

        path_str = str(asset_path)
        start_frame = int(loop_start * self.sample_rate) if loop_start is not None else None
        end_frame = int(loop_end * self.sample_rate) if loop_end is not None else None

        if channel.lower() in STREAMING_CHANNELS:
            try:
                stream = miniaudio.stream_file(
                    path_str,
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=self.nchannels,
                    sample_rate=self.sample_rate,
                    seek_frame=start_frame or 0,
                )
            except Exception:  # noqa: BLE001
                return

            track = _ChannelTrack(
                samples=None,
                sample_rate=self.sample_rate,
                nchannels=self.nchannels,
                volume=max(0.0, min(1.0, volume)),
                loop=loop,
                loop_start_frame=start_frame,
                loop_end_frame=end_frame,
                path_str=path_str,
                stream=stream,
            )
            if start_frame:
                track.frame_pos = start_frame
        else:
            try:
                decoded = miniaudio.decode_file(
                    path_str,
                    output_format=miniaudio.SampleFormat.SIGNED16,
                    nchannels=self.nchannels,
                    sample_rate=self.sample_rate,
                )
            except Exception:  # noqa: BLE001
                return

            track = _ChannelTrack(
                samples=decoded.samples,
                sample_rate=self.sample_rate,
                nchannels=self.nchannels,
                volume=max(0.0, min(1.0, volume)),
                loop=loop,
                loop_start_frame=start_frame,
                loop_end_frame=end_frame,
            )
        with self._lock:
            self._tracks[channel] = track

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        with self._lock:
            track = self._tracks.pop(channel, None)
            if track is not None:
                track.is_playing = False

    def set_volume(self, channel: str, volume: float) -> None:
        with self._lock:
            track = self._tracks.get(channel)
            if track is not None:
                track.volume = max(0.0, min(1.0, volume))

    def pause(self, channel: str) -> None:
        with self._lock:
            track = self._tracks.get(channel)
            if track is not None:
                track.is_paused = True

    def resume(self, channel: str) -> None:
        with self._lock:
            track = self._tracks.get(channel)
            if track is not None:
                track.is_paused = False

    def is_playing(self, channel: str) -> bool:
        with self._lock:
            track = self._tracks.get(channel)
            return bool(track is not None and track.is_playing and not track.is_paused)

    def update(self, dt: float) -> None:
        with self._lock:
            for ch, track in list(self._tracks.items()):
                if not track.is_playing:
                    del self._tracks[ch]

    def shutdown(self) -> None:
        with self._lock:
            for track in self._tracks.values():
                track.is_playing = False
            self._tracks.clear()
        if self._device is not None:
            try:
                self._device.stop()
                self._device.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._device = None
        self._active = False
