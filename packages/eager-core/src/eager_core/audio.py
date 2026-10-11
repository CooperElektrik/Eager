"""Audio backend protocols, audio mixer, and channel management for Eager."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class AudioBackend(Protocol):
    """Low-level sound/music playback provider."""

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
        ...

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        ...

    def set_volume(self, channel: str, volume: float) -> None:
        ...

    def pause(self, channel: str) -> None:
        ...

    def resume(self, channel: str) -> None:
        ...

    def is_playing(self, channel: str) -> bool:
        ...

    def update(self, dt: float) -> None:
        ...

    def shutdown(self) -> None:
        ...


class BaseAudioBackend:
    """Base class providing default no-op implementations for optional lifecycle hooks."""

    def update(self, dt: float) -> None:
        """Periodic per-frame audio pump/update tick."""

    def shutdown(self) -> None:
        """Free low-level audio resources and devices."""


@dataclass
class ChannelState:
    """State tracking for a single audio mixer channel."""

    name: str
    current_asset: str | None = None
    volume: float = 1.0
    loop: bool = False
    is_playing: bool = False
    is_paused: bool = False
    queue: list[str] = dataclasses.field(default_factory=list)
    loop_start: float | None = None
    loop_end: float | None = None

    # Fade automation
    fade_timer: float = 0.0
    fade_duration: float = 0.0
    fade_start_vol: float = 0.0
    fade_target_vol: float = 0.0
    stop_on_fade_complete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "current_asset": self.current_asset,
            "volume": self.volume,
            "loop": self.loop,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "queue": list(self.queue),
            "loop_start": self.loop_start,
            "loop_end": self.loop_end,
            "fade_timer": self.fade_timer,
            "fade_duration": self.fade_duration,
            "fade_start_vol": self.fade_start_vol,
            "fade_target_vol": self.fade_target_vol,
            "stop_on_fade_complete": self.stop_on_fade_complete,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChannelState:
        return cls(
            name=data["name"],
            current_asset=data.get("current_asset"),
            volume=float(data.get("volume", 1.0)),
            loop=bool(data.get("loop", False)),
            is_playing=bool(data.get("is_playing", False)),
            is_paused=bool(data.get("is_paused", False)),
            queue=list(data.get("queue", [])),
            loop_start=data.get("loop_start"),
            loop_end=data.get("loop_end"),
            fade_timer=float(data.get("fade_timer", 0.0)),
            fade_duration=float(data.get("fade_duration", 0.0)),
            fade_start_vol=float(data.get("fade_start_vol", 0.0)),
            fade_target_vol=float(data.get("fade_target_vol", 0.0)),
            stop_on_fade_complete=bool(data.get("stop_on_fade_complete", False)),
        )


class NullAudioBackend(BaseAudioBackend):
    """Headless no-op audio backend recording calls for test inspection."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self._playing_channels: set[str] = set()
        self.shutdown_called: bool = False

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
        self.calls.append(("play", channel, str(asset_path), loop, volume, fade_in, loop_start, loop_end))
        self._playing_channels.add(channel)

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        self.calls.append(("stop", channel, fade_out))
        self._playing_channels.discard(channel)

    def set_volume(self, channel: str, volume: float) -> None:
        self.calls.append(("set_volume", channel, volume))

    def pause(self, channel: str) -> None:
        self.calls.append(("pause", channel))

    def resume(self, channel: str) -> None:
        self.calls.append(("resume", channel))

    def is_playing(self, channel: str) -> bool:
        return channel in self._playing_channels

    def update(self, dt: float) -> None:
        self.calls.append(("update", dt))

    def shutdown(self) -> None:
        self.shutdown_called = True
        self.calls.append(("shutdown",))


class AudioMixer:
    """Manages audio playback across music, sound, voice, and ambient channels."""

    STANDARD_CHANNELS = ("music", "sound", "voice", "ambient")

    def __init__(
        self,
        backend: AudioBackend | None = None,
        asset_dir: Path | str | None = None,
    ) -> None:
        self.backend: AudioBackend = backend if backend is not None else NullAudioBackend()
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None

        self.channels: dict[str, ChannelState] = {
            name: ChannelState(name=name, loop=(name in ("music", "ambient")))
            for name in self.STANDARD_CHANNELS
        }

        self.master_volume: float = 1.0
        self.channel_volumes: dict[str, float] = {name: 1.0 for name in self.STANDARD_CHANNELS}

    def _resolve_asset(self, asset_path: str) -> Path | str:
        """Resolve audio file relative to asset_dir if configured."""
        if self.asset_dir is not None:
            cand = self.asset_dir / asset_path
            if cand.exists():
                return cand
            audio_cand = self.asset_dir / "audio" / asset_path
            if audio_cand.exists():
                return audio_cand
        return asset_path

    def _effective_volume(self, channel: str) -> float:
        """Compute final output volume = master * channel_type * track_vol."""
        chan = self.channels.get(channel)
        chan_vol = chan.volume if chan else 1.0
        type_vol = self.channel_volumes.get(channel, 1.0)
        return max(0.0, min(1.0, self.master_volume * type_vol * chan_vol))

    def play(
        self,
        channel: str,
        asset_path: str,
        *,
        loop: bool | None = None,
        fade_in: float = 0.0,
        volume: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        """Play an audio asset on the specified channel."""
        if channel not in self.channels:
            self.channels[channel] = ChannelState(name=channel)
            self.channel_volumes[channel] = 1.0

        chan = self.channels[channel]
        is_loop = loop if loop is not None else (channel in ("music", "ambient"))
        chan.current_asset = asset_path
        chan.loop = is_loop
        chan.volume = volume
        chan.loop_start = loop_start
        chan.loop_end = loop_end
        chan.is_playing = True
        chan.is_paused = False

        resolved = self._resolve_asset(asset_path)
        final_vol = self._effective_volume(channel)
        self.backend.play(
            channel,
            resolved,
            loop=is_loop,
            volume=final_vol,
            fade_in=fade_in,
            loop_start=loop_start,
            loop_end=loop_end,
        )

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        """Stop playback on a channel."""
        chan = self.channels.get(channel)
        if chan is None:
            return

        if fade_out > 0.0:
            chan.fade_duration = fade_out
            chan.fade_timer = 0.0
            chan.fade_start_vol = chan.volume
            chan.fade_target_vol = 0.0
            chan.stop_on_fade_complete = True
        else:
            chan.is_playing = False
            chan.current_asset = None
            self.backend.stop(channel)

    def stop_all(self, *, fade_out: float = 0.0) -> None:
        """Stop playback across all audio channels."""
        for name in list(self.channels):
            self.stop(name, fade_out=fade_out)

    def pause(self, channel: str) -> None:
        """Pause playback on a channel."""
        chan = self.channels.get(channel)
        if chan and chan.is_playing:
            chan.is_paused = True
            self.backend.pause(channel)

    def resume(self, channel: str) -> None:
        """Resume playback on a paused channel."""
        chan = self.channels.get(channel)
        if chan and chan.is_paused:
            chan.is_paused = False
            self.backend.resume(channel)

    def set_volume(self, channel: str, volume: float) -> None:
        """Set track volume for a channel."""
        chan = self.channels.get(channel)
        if chan is not None:
            chan.volume = max(0.0, min(1.0, volume))
            self.backend.set_volume(channel, self._effective_volume(channel))

    def set_master_volume(self, volume: float) -> None:
        """Set master volume scaling all channels."""
        self.master_volume = max(0.0, min(1.0, volume))
        for name in self.channels:
            self.backend.set_volume(name, self._effective_volume(name))

    def set_channel_volume(self, channel: str, volume: float) -> None:
        """Set type volume for a category of channel."""
        self.channel_volumes[channel] = max(0.0, min(1.0, volume))
        self.backend.set_volume(channel, self._effective_volume(channel))

    def queue(self, channel: str, asset_path: str) -> None:
        """Queue an audio asset to play after current playback completes."""
        if channel not in self.channels:
            self.channels[channel] = ChannelState(name=channel)
            self.channel_volumes[channel] = 1.0
        chan = self.channels[channel]
        if not chan.is_playing:
            self.play(channel, asset_path)
        else:
            chan.queue.append(asset_path)

    def update(self, dt: float) -> None:
        """Process fade automations and channel queues, and pump audio backend."""
        for chan in self.channels.values():
            if chan.fade_duration > 0.0:
                chan.fade_timer += dt
                progress = min(1.0, chan.fade_timer / chan.fade_duration)
                new_vol = chan.fade_start_vol + (chan.fade_target_vol - chan.fade_start_vol) * progress
                chan.volume = new_vol
                self.backend.set_volume(chan.name, self._effective_volume(chan.name))

                if progress >= 1.0:
                    chan.fade_duration = 0.0
                    if chan.stop_on_fade_complete:
                        chan.stop_on_fade_complete = False
                        chan.is_playing = False
                        chan.current_asset = None
                        self.backend.stop(chan.name)

            # Check if backend finished playing
            if chan.is_playing and not self.backend.is_playing(chan.name):
                chan.is_playing = False
                chan.current_asset = None

            # Advance channel queue if idle and tracks are queued
            if not chan.is_playing and chan.queue:
                next_asset = chan.queue.pop(0)
                self.play(chan.name, next_asset)

        if hasattr(self.backend, "update"):
            self.backend.update(dt)

    def shutdown(self) -> None:
        """Shut down the audio backend and release audio resources."""
        if hasattr(self.backend, "shutdown"):
            self.backend.shutdown()

    def save_state(self) -> dict[str, Any]:
        """Save mixer state for checkpoints and saves."""
        return {
            "master_volume": self.master_volume,
            "channel_volumes": dict(self.channel_volumes),
            "channels": {name: chan.to_dict() for name, chan in self.channels.items()},
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore mixer state from checkpoint."""
        if not state:
            return
        self.master_volume = float(state.get("master_volume", 1.0))
        self.channel_volumes = {k: float(v) for k, v in state.get("channel_volumes", {}).items()}

        raw_channels = state.get("channels", {})
        for name, data in raw_channels.items():
            chan = ChannelState.from_dict(data)
            self.channels[name] = chan
            if chan.is_playing and chan.current_asset:
                self.play(
                    name,
                    chan.current_asset,
                    loop=chan.loop,
                    volume=chan.volume,
                    loop_start=chan.loop_start,
                    loop_end=chan.loop_end,
                )
            else:
                self.stop(name)
