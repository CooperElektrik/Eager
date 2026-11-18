"""Audio backend protocols, audio mixer, and channel management for Eager."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypedDict, cast

from eager.core.exceptions import AudioError

__all__ = [
    "AudioBackend",
    "AudioMixer",
    "AudioMixerSaveState",
    "BaseAudioBackend",
    "ChannelState",
    "NullAudioBackend",
]

logger = logging.getLogger(__name__)


class AudioMixerSaveState(TypedDict):
    """Serialized state representation of an AudioMixer for saves and checkpoints."""

    master_volume: float
    channel_volumes: dict[str, float]
    channels: dict[str, dict[str, object]]
    serial_counter: int


class AudioBackend(Protocol):
    """Low-level sound/music playback provider."""

    def play(
        self,
        channel: str,
        asset_path: str | Path,
        *,
        loop: bool = False,
        volume: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        """Start playing an audio asset on the given channel."""
        ...

    def stop(self, channel: str) -> None:
        """Stop audio playback on the specified channel."""
        ...

    def set_volume(self, channel: str, volume: float) -> None:
        """Adjust the output volume for a specific audio channel."""
        ...

    def pause(self, channel: str) -> None:
        """Pause playback on the given channel."""
        ...

    def resume(self, channel: str) -> None:
        """Resume playback on a paused channel."""
        ...

    def is_playing(self, channel: str) -> bool:
        """Check whether audio is currently actively playing on the channel."""
        ...

    def update(self, dt: float) -> None:
        """Pump audio backend buffers and process periodic tasks."""
        ...

    def shutdown(self) -> None:
        """Cleanly close the audio device and release all audio resources."""
        ...


class BaseAudioBackend:
    """Shared base providing default no-op lifecycle hooks for AudioBackend implementations."""

    def update(self, dt: float) -> None:
        """Pump audio buffers or periodic tasks (no-op by default)."""

    def shutdown(self) -> None:
        """Cleanly close the audio backend and release resources (no-op by default)."""


@dataclass
class ChannelState:
    """State tracking for a single audio mixer channel."""

    name: str
    current_asset: str | None = None
    volume: float = 1.0
    loop: bool = False
    is_playing: bool = False
    is_paused: bool = False
    loop_start: float | None = None
    loop_end: float | None = None
    serial: int = 0

    # Fade automation
    fade_timer: float = 0.0
    fade_duration: float = 0.0
    fade_start_vol: float = 0.0
    fade_target_vol: float = 0.0
    stop_on_fade_complete: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize channel playback state to a dictionary."""
        return {
            "name": self.name,
            "current_asset": self.current_asset,
            "volume": self.volume,
            "loop": self.loop,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "loop_start": self.loop_start,
            "loop_end": self.loop_end,
            "serial": self.serial,
            "fade_timer": self.fade_timer,
            "fade_duration": self.fade_duration,
            "fade_start_vol": self.fade_start_vol,
            "fade_target_vol": self.fade_target_vol,
            "stop_on_fade_complete": self.stop_on_fade_complete,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ChannelState:
        """Construct a ChannelState instance from serialized dictionary data."""
        name_val = data["name"]
        vol_val = data.get("volume", 1.0)
        serial_val = data.get("serial", 0)
        ft_val = data.get("fade_timer", 0.0)
        fd_val = data.get("fade_duration", 0.0)
        fsv_val = data.get("fade_start_vol", 0.0)
        ftv_val = data.get("fade_target_vol", 0.0)
        ls_val = data.get("loop_start")
        le_val = data.get("loop_end")
        return cls(
            name=str(name_val),
            current_asset=str(data["current_asset"]) if data.get("current_asset") is not None else None,
            volume=float(vol_val) if isinstance(vol_val, (int, float, str)) else 1.0,
            loop=bool(data.get("loop", False)),
            is_playing=bool(data.get("is_playing", False)),
            is_paused=bool(data.get("is_paused", False)),
            loop_start=float(ls_val) if ls_val is not None and isinstance(ls_val, (int, float, str)) else None,
            loop_end=float(le_val) if le_val is not None and isinstance(le_val, (int, float, str)) else None,
            serial=int(serial_val) if isinstance(serial_val, (int, str)) else 0,
            fade_timer=float(ft_val) if isinstance(ft_val, (int, float, str)) else 0.0,
            fade_duration=float(fd_val) if isinstance(fd_val, (int, float, str)) else 0.0,
            fade_start_vol=float(fsv_val) if isinstance(fsv_val, (int, float, str)) else 0.0,
            fade_target_vol=float(ftv_val) if isinstance(ftv_val, (int, float, str)) else 0.0,
            stop_on_fade_complete=bool(data.get("stop_on_fade_complete", False)),
        )


class NullAudioBackend:
    """Headless no-op audio backend recording calls for test inspection."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self._playing_channels: set[str] = set()
        self.shutdown_called: bool = False

    def play(
        self,
        channel: str,
        asset_path: str | Path,
        *,
        loop: bool = False,
        volume: float = 1.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        """Record a play call and mark the channel as playing."""
        self.calls.append(("play", channel, str(asset_path), loop, volume, loop_start, loop_end))
        self._playing_channels.add(channel)

    def stop(self, channel: str) -> None:
        """Record a stop call and remove the channel from playing set."""
        self.calls.append(("stop", channel))
        self._playing_channels.discard(channel)

    def set_volume(self, channel: str, volume: float) -> None:
        """Record a volume update for a channel."""
        self.calls.append(("set_volume", channel, volume))

    def pause(self, channel: str) -> None:
        """Record a pause call for a channel."""
        self.calls.append(("pause", channel))

    def resume(self, channel: str) -> None:
        """Record a resume call for a channel."""
        self.calls.append(("resume", channel))

    def is_playing(self, channel: str) -> bool:
        """Check whether the channel is currently recorded as playing."""
        return channel in self._playing_channels

    def update(self, dt: float) -> None:
        """Record an update tick."""
        self.calls.append(("update", dt))

    def shutdown(self) -> None:
        """Record a shutdown call and set shutdown_called flag."""
        self.shutdown_called = True
        self.calls.append(("shutdown",))


class AudioMixer:
    """Manages audio playback across music, sound, voice, and ambient channels."""

    STANDARD_CHANNELS: tuple[str, ...] = ("music", "sound", "voice", "ambient")

    def __init__(
        self,
        backend: AudioBackend | None = None,
        asset_dir: Path | str | None = None,
    ) -> None:
        self.backend: AudioBackend = backend if backend is not None else NullAudioBackend()
        self.asset_dir: Path | None = Path(asset_dir) if asset_dir is not None else None
        if backend is None:
            logger.debug("AudioMixer initialized with NullAudioBackend (headless mode)")

        self.channels: dict[str, ChannelState] = {
            name: ChannelState(name=name, loop=(name in ("music", "ambient")))
            for name in self.STANDARD_CHANNELS
        }

        self.master_volume: float = 1.0
        self.channel_volumes: dict[str, float] = {name: 1.0 for name in self.STANDARD_CHANNELS}
        self._serial_counter: int = 0

    def _resolve_asset(self, asset_path: str) -> Path | str:
        """Resolve audio file relative to asset_dir if configured."""
        if self.asset_dir is not None:
            resolved_base = self.asset_dir.resolve()
            cand = (self.asset_dir / asset_path).resolve()
            if not cand.is_relative_to(resolved_base):
                raise AudioError(f"Path traversal detected in audio asset path: {asset_path}")
            if cand.exists():
                return cand
            audio_cand = (self.asset_dir / "audio" / asset_path).resolve()
            if not audio_cand.is_relative_to(resolved_base):
                raise AudioError(f"Path traversal detected in audio asset path: {asset_path}")
            if audio_cand.exists():
                return audio_cand
        return asset_path

    def _effective_volume(self, channel: str) -> float:
        """Compute final output volume = master * channel_type * track_vol."""
        chan = self.channels.get(channel)
        chan_vol = chan.volume if chan else 1.0
        type_vol = self.channel_volumes.get(channel, 1.0)
        return max(0.0, min(1.0, self.master_volume * type_vol * chan_vol))

    def is_playing(self, channel: str) -> bool:
        """Return True if *channel* is audibly active."""
        chan = self.channels.get(channel)
        if chan is None:
            return False
        if chan.is_playing:
            return True
        return chan.fade_duration > 0.0 and chan.fade_target_vol > 0.0

    def play(
        self,
        channel: str,
        asset_path: str,
        *,
        loop: bool | None = None,
        fade_in: float = 0.0,
        volume: float | None = None,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> str:
        """Play an audio asset on the specified channel."""
        if channel not in self.channels:
            self.channels[channel] = ChannelState(name=channel)
            _ = self.channel_volumes.setdefault(channel, 1.0)

        chan = self.channels[channel]
        is_loop = loop if loop is not None else (channel in ("music", "ambient"))
        if volume is None:
            volume = 1.0

        self._serial_counter += 1
        chan.serial = self._serial_counter
        chan.current_asset = asset_path
        chan.loop = is_loop
        target_vol = max(0.0, min(1.0, volume))
        chan.volume = 0.0 if fade_in > 0.0 else target_vol
        chan.loop_start = loop_start
        chan.loop_end = loop_end
        chan.is_playing = True
        chan.is_paused = False
        chan.fade_timer = 0.0
        if fade_in > 0.0:
            chan.fade_duration = fade_in
            chan.fade_start_vol = 0.0
            chan.fade_target_vol = target_vol
        else:
            chan.fade_duration = 0.0
            chan.fade_start_vol = 0.0
            chan.fade_target_vol = 0.0
        chan.stop_on_fade_complete = False

        resolved = self._resolve_asset(asset_path)
        initial_vol = self._effective_volume(channel)
        self.backend.play(
            channel,
            resolved,
            loop=is_loop,
            volume=initial_vol,
            loop_start=loop_start,
            loop_end=loop_end,
        )
        return channel

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

    def pause_all(self) -> None:
        """Pause playback across all active audio channels."""
        for name in list(self.channels):
            self.pause(name)

    def resume_all(self) -> None:
        """Resume playback across all paused audio channels."""
        for name in list(self.channels):
            self.resume(name)

    def set_volume(self, channel: str, volume: float) -> None:
        """Set track volume for a channel."""
        clamped = max(0.0, min(1.0, volume))
        chan = self.channels.get(channel)
        if chan is not None:
            chan.volume = clamped
            self.backend.set_volume(channel, self._effective_volume(channel))

    def set_master_volume(self, volume: float) -> None:
        """Set master volume scaling all channels."""
        self.master_volume = max(0.0, min(1.0, volume))
        for name in self.channels:
            self.backend.set_volume(name, self._effective_volume(name))

    def set_channel_volume(self, channel: str, volume: float) -> None:
        """Set type volume for a channel."""
        self.channel_volumes[channel] = max(0.0, min(1.0, volume))
        self.backend.set_volume(channel, self._effective_volume(channel))

    def update(self, dt: float) -> None:
        """Process fade automations and pump audio backend."""
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

            if chan.is_playing and not self.backend.is_playing(chan.name):
                chan.is_playing = False
                chan.current_asset = None

        self.backend.update(dt)

    def shutdown(self) -> None:
        """Shut down the audio backend and release audio resources."""
        logger.debug("Shutting down audio backend %r", type(self.backend).__name__)
        self.backend.shutdown()

    def save_state(self) -> AudioMixerSaveState:
        """Save mixer state for checkpoints and saves."""
        result: AudioMixerSaveState = {
            "master_volume": self.master_volume,
            "channel_volumes": dict(self.channel_volumes),
            "channels": {name: chan.to_dict() for name, chan in self.channels.items()},
            "serial_counter": self._serial_counter,
        }
        return result

    def load_state(self, state: Mapping[str, object]) -> None:
        """Restore mixer state from checkpoint."""
        if not state:
            return
        master_vol = state.get("master_volume", 1.0)
        if isinstance(master_vol, (int, float, str)):
            self.master_volume = float(master_vol)

        raw_channel_volumes = state.get("channel_volumes")
        if isinstance(raw_channel_volumes, Mapping):
            self.channel_volumes = {
                str(k): float(v)
                for k, v in cast(Mapping[object, object], raw_channel_volumes).items()
                if isinstance(v, (int, float, str))
            }

        serial_counter = state.get("serial_counter", 0)
        if isinstance(serial_counter, (int, str)):
            self._serial_counter = max(self._serial_counter, int(serial_counter))

        raw_channels = state.get("channels")
        raw_channels_dict: dict[str, object] = (
            {str(k): v for k, v in cast(Mapping[object, object], raw_channels).items()}
            if isinstance(raw_channels, Mapping)
            else {}
        )
        for name, data_obj in raw_channels_dict.items():
            if not isinstance(data_obj, Mapping):
                continue
            data: dict[str, object] = {
                str(k): v for k, v in cast(Mapping[object, object], data_obj).items()
            }
            chan = ChannelState.from_dict(data)
            existing = self.channels.get(name)

            is_same_track = (
                existing is not None
                and existing.is_playing
                and chan.is_playing
                and chan.current_asset is not None
                and existing.current_asset == chan.current_asset
                and existing.serial == chan.serial
                and chan.serial > 0
                and self.backend.is_playing(name)
            )

            was_paused = bool(data.get("is_paused", False))
            self.channels[name] = chan
            if is_same_track and existing is not None:
                if abs(existing.volume - chan.volume) > 1e-4:
                    self.backend.set_volume(name, self._effective_volume(name))
                if chan.is_paused and not existing.is_paused:
                    self.backend.pause(name)
                elif not chan.is_paused and existing.is_paused:
                    self.backend.resume(name)
            elif chan.is_playing and chan.current_asset:
                _ = self.play(
                    name,
                    chan.current_asset,
                    loop=chan.loop,
                    volume=chan.volume,
                    loop_start=chan.loop_start,
                    loop_end=chan.loop_end,
                )
                serial_obj = data.get("serial", 0)
                restored_serial = int(serial_obj) if isinstance(serial_obj, (int, str)) else 0
                if restored_serial > 0:
                    chan.serial = restored_serial
                if was_paused:
                    self.pause(name)
            else:
                self.stop(name)

        for name in list(self.channels):
            if name not in raw_channels_dict:
                self.stop(name)
