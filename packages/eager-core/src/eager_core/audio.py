"""Audio backend protocols, audio mixer, and channel management for Eager."""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypedDict, cast

from eager_core.exceptions import AudioError

__all__ = [
    "AudioBackend",
    "AudioMixer",
    "AudioMixerSaveState",
    "BaseAudioBackend",
    "ChannelState",
    "NullAudioBackend",
]

logger = logging.getLogger(__name__)

_POOL_SUFFIX_RE = re.compile(r"^(.*)_(\d+)$")


class AudioMixerSaveState(TypedDict):
    """Serialized state representation of an AudioMixer for saves and checkpoints.

    Attributes:
        master_volume: Master volume scaling factor across all channels in [0.0, 1.0].
        channel_volumes: Mapping of channel names to category volume multipliers.
        channels: Dictionary of serialized channel state dictionaries.
        serial_counter: Counter for tracking playback serial allocations.
    """

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
        fade_in: float = 0.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        """Start playing an audio asset on the given channel.

        Args:
            channel: Target channel identifier (e.g. 'music', 'sound', 'voice').
            asset_path: Path or filename of the audio resource to play.
            loop: Whether the audio track should repeat seamlessly. Defaults to False.
            volume: Channel playback volume multiplier in the range [0.0, 1.0].
            fade_in: Duration of linear fade-in volume transition in seconds.
            loop_start: Optional loop start position in seconds.
            loop_end: Optional loop end position in seconds.
        """
        ...

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        """Stop audio playback on the specified channel.

        Args:
            channel: Identifier of the channel to halt.
            fade_out: Duration in seconds to fade out volume before stopping.
        """
        ...

    def set_volume(self, channel: str, volume: float) -> None:
        """Adjust the output volume for a specific audio channel.

        Args:
            channel: Target channel identifier.
            volume: Normalized volume level in the range [0.0, 1.0].
        """
        ...

    def pause(self, channel: str) -> None:
        """Pause playback on the given channel.

        Args:
            channel: Target channel identifier.
        """
        ...

    def resume(self, channel: str) -> None:
        """Resume playback on a paused channel.

        Args:
            channel: Target channel identifier.
        """
        ...

    def is_playing(self, channel: str) -> bool:
        """Check whether audio is currently actively playing on the channel.

        Args:
            channel: Target channel identifier.

        Returns:
            True if audio is actively playing on the channel.
        """
        ...

    def update(self, dt: float) -> None:
        """Tick per-frame backend processing, buffers, and active fades.

        Args:
            dt: Delta time elapsed since the previous update tick in seconds.
        """
        ...

    def shutdown(self) -> None:
        """Release audio devices, streams, and underlying backend resources."""
        ...


class BaseAudioBackend:
    """Base class providing default no-op implementations for optional lifecycle hooks."""

    def update(self, dt: float) -> None:
        """Periodic per-frame audio pump/update tick.

        Args:
            dt: Delta time elapsed since last frame in seconds.
        """
        _ = dt

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
    serial: int = 0

    # Fade automation
    fade_timer: float = 0.0
    fade_duration: float = 0.0
    fade_start_vol: float = 0.0
    fade_target_vol: float = 0.0
    stop_on_fade_complete: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize channel playback state to a dictionary.

        Returns:
            Dictionary containing state fields and active fade parameters.
        """
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
            "serial": self.serial,
            "fade_timer": self.fade_timer,
            "fade_duration": self.fade_duration,
            "fade_start_vol": self.fade_start_vol,
            "fade_target_vol": self.fade_target_vol,
            "stop_on_fade_complete": self.stop_on_fade_complete,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ChannelState:
        """Construct a ChannelState instance from serialized dictionary data.

        Args:
            data: Mapping containing channel state attributes.

        Returns:
            Deserialized ChannelState instance.
        """
        raw_queue = data.get("queue")
        queue_list = [str(x) for x in cast(list[object], raw_queue)] if isinstance(raw_queue, list) else []
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
            queue=queue_list,
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
        """Initialize the null backend with empty call records."""
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
        fade_in: float = 0.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        """Record a play call and mark the channel as playing.

        Args:
            channel: Target audio channel name.
            asset_path: Asset file path or identifier.
            loop: Whether playback repeats in a loop.
            volume: Initial volume level [0.0, 1.0].
            fade_in: Fade in duration in seconds.
            loop_start: Loop start time offset in seconds.
            loop_end: Loop end time offset in seconds.
        """
        self.calls.append(("play", channel, str(asset_path), loop, volume, fade_in, loop_start, loop_end))
        self._playing_channels.add(channel)

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        """Record a stop call and remove the channel from playing set.

        Args:
            channel: Audio channel name to stop.
            fade_out: Fade out duration in seconds.
        """
        self.calls.append(("stop", channel, fade_out))
        self._playing_channels.discard(channel)

    def set_volume(self, channel: str, volume: float) -> None:
        """Record a volume update for a channel.

        Args:
            channel: Target audio channel name.
            volume: New volume multiplier in [0.0, 1.0].
        """
        self.calls.append(("set_volume", channel, volume))

    def pause(self, channel: str) -> None:
        """Record a pause call for a channel.

        Args:
            channel: Audio channel name to pause.
        """
        self.calls.append(("pause", channel))

    def resume(self, channel: str) -> None:
        """Record a resume call for a channel.

        Args:
            channel: Audio channel name to resume.
        """
        self.calls.append(("resume", channel))

    def is_playing(self, channel: str) -> bool:
        """Check whether the channel is currently recorded as playing.

        Args:
            channel: Audio channel name.

        Returns:
            True if channel is currently playing in this backend.
        """
        return channel in self._playing_channels

    def update(self, dt: float) -> None:
        """Record an update tick.

        Args:
            dt: Delta time elapsed in seconds.
        """
        self.calls.append(("update", dt))

    def shutdown(self) -> None:
        """Record a shutdown call and set shutdown_called flag."""
        self.shutdown_called = True
        self.calls.append(("shutdown",))


class AudioMixer:
    """Manages audio playback across music, sound, voice, and ambient channels."""

    STANDARD_CHANNELS: tuple[str, ...] = ("music", "sound", "voice", "ambient")

    #: Default cap on concurrent auto-allocated pool channels per base
    #: (e.g. ``sound_0`` … ``sound_15``). When every slot is busy the oldest
    #: entry is stolen. Set to ``None`` (or pass ``max_polyphony<=0``) for
    #: unbounded growth.
    DEFAULT_MAX_POLYPHONY: int = 16

    def __init__(
        self,
        backend: AudioBackend | None = None,
        asset_dir: Path | str | None = None,
    ) -> None:
        """Initialize AudioMixer with an audio backend and optional asset directory.

        Args:
            backend: Concrete AudioBackend implementation. Defaults to NullAudioBackend if None.
            asset_dir: Base directory path for resolving relative audio asset paths.
        """
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
        type_vol = self._type_volume(channel)
        return max(0.0, min(1.0, self.master_volume * type_vol * chan_vol))

    @staticmethod
    def _split_pool_name(channel: str) -> tuple[str, int | None]:
        """Split ``sound_3`` into ``("sound", 3)``; plain names yield ``(name, None)``."""
        m = _POOL_SUFFIX_RE.match(channel)
        if m and m.group(1):
            try:
                return m.group(1), int(m.group(2))
            except ValueError:
                pass
        return channel, None

    def _type_volume(self, channel: str) -> float:
        """Return the type/category volume for *channel*.

        Pool members (``sound_0``) inherit their base channel's type volume
        (``sound``) unless they have an explicit entry.
        """
        if channel in self.channel_volumes:
            return self.channel_volumes[channel]
        base, suffix = self._split_pool_name(channel)
        while suffix is not None:
            if base in self.channel_volumes:
                return self.channel_volumes[base]
            base, suffix = self._split_pool_name(base)
        return 1.0

    def _pool_members(self, base: str) -> list[str]:
        """Return allocated pool channel names for *base* (e.g. ``sound_0``)."""
        prefix = f"{base}_"
        members: list[str] = []
        for name in self.channels:
            if name.startswith(prefix) and name[len(prefix):].isdigit():
                members.append(name)
        return sorted(members, key=lambda n: int(n[len(prefix):]))

    def _is_pool_member(self, channel: str) -> bool:
        base, suffix = self._split_pool_name(channel)
        return suffix is not None and channel != base

    def _allocate_pool_channel(self, base: str, max_polyphony: int | None = None) -> str:
        """Find a free ``<base>_N`` slot or allocate a new one.

        Reuses the lowest-index idle slot first so the pool stays compact.
        A slot counts as busy while the mixer marks it playing *and* the
        backend still reports it playing (so naturally-finished sounds are
        reusable even before the next :meth:`update`). Gaps are filled
        before appending: with ``sound_5`` already taken, the next
        allocation is ``sound_0``. Once every index in ``0..cap-1`` exists
        and is busy, the oldest (lowest serial) entry is stolen instead of
        growing forever. A *cap* of ``None`` (or ``<=0``) means unbounded
        growth.
        """
        if base not in self.channels:
            self.channels[base] = ChannelState(name=base)
            if base not in self.channel_volumes:
                self.channel_volumes[base] = 1.0
        if max_polyphony is not None and max_polyphony <= 0:
            cap: int | None = None
        else:
            cap = max_polyphony if max_polyphony is not None else self.DEFAULT_MAX_POLYPHONY
        prefix = f"{base}_"
        indices: dict[int, str] = {}
        for name in self.channels:
            if name.startswith(prefix) and name[len(prefix):].isdigit():
                indices[int(name[len(prefix):])] = name
        for idx in sorted(indices):
            name = indices[idx]
            chan = self.channels[name]
            if not chan.is_playing:
                chan.queue.clear()
                return name
            try:
                backend_busy = self.backend.is_playing(name)
            except Exception:  # noqa: BLE001
                backend_busy = True
            if not backend_busy:
                chan.queue.clear()
                return name
        # Fill the lowest gap first (unified for bounded and unbounded
        # modes): with ``sound_5`` taken, the next allocation is ``sound_0``.
        candidate = 0
        while cap is None or candidate < cap:
            if candidate not in indices:
                return f"{base}_{candidate}"
            candidate += 1
        # Every slot 0..cap-1 exists and is busy: steal the oldest managed
        # slot. Explicit out-of-range slots (e.g. a dedicated ``sound_99``)
        # are never stolen.
        assert cap is not None  # unbounded mode always returns inside the loop
        managed = [indices[i] for i in range(cap) if i in indices]
        busy = sorted(
            ((self.channels[name].serial, name) for name in managed),
            key=lambda t: t[0],
        )
        if busy:
            victim = busy[0][1]
            logger.debug("Stealing oldest pool slot %r (base %r) due to polyphony cap %s", victim, base, cap)
            self.channels[victim].queue.clear()
            return victim
        return f"{base}_0"

    def _slot_audible(self, channel: str) -> bool:
        """Return True if an exact channel entry is currently audible.

        Unlike the raw ``ChannelState.is_playing`` flag this also consults
        the backend, so naturally-finished sounds read as stopped even
        before the next :meth:`update` tick. Paused channels count as
        active since they will resume.
        """
        chan = self.channels.get(channel)
        if chan is None or not chan.is_playing:
            return False
        if chan.is_paused:
            return True
        try:
            return bool(self.backend.is_playing(channel))
        except Exception:  # noqa: BLE001
            return True

    def is_playing(self, channel: str) -> bool:
        """Return True if *channel* is audibly active.

        For a base channel (e.g. ``sound``) this covers the base entry plus
        every allocated pool member (``sound_0``, ``sound_1``, …). Pool
        member names are checked exactly.
        """
        if self._is_pool_member(channel):
            return self._slot_audible(channel)
        targets = [channel, *self._pool_members(channel)]
        return any(self._slot_audible(name) for name in targets)

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
        auto_channels: bool | None = None,
        max_polyphony: int | None = None,
    ) -> str:
        """Play an audio asset on the specified channel.

        When *auto_channels* is True (or None on the ``sound`` channel),
        playback is dynamically allocated onto a pool slot named
        ``<channel>_N`` (``sound_0``, ``sound_1``, …) so overlapping sounds
        layer rather than cutting each other off. Explicit pool names
        (``sound_0``) always play directly on that slot.

        When *volume* is omitted (``None``), a pool slot — whether
        auto-allocated or explicitly addressed (``sound_0``) — inherits the
        base channel's current track volume (so ``~ volume sound 0.5``
        applies to later SFX); every other channel defaults to ``1.0``.
        """
        inherit_base: str | None = None
        use_auto = auto_channels if auto_channels is not None else (channel == "sound")
        if use_auto and not self._is_pool_member(channel):
            inherit_base = channel
            channel = self._allocate_pool_channel(channel, max_polyphony)
            logger.debug("Auto-allocated pool channel %r for base %r", channel, inherit_base)

        if channel not in self.channels:
            self.channels[channel] = ChannelState(name=channel)
            # Pool members (sound_0) inherit the base type volume via
            # _type_volume fallback, so only brand-new base/custom channel
            # names get an explicit entry.
            if not self._is_pool_member(channel):
                _ = self.channel_volumes.setdefault(channel, 1.0)

        chan = self.channels[channel]
        if loop is not None:
            is_loop = loop
        else:
            base, _suffix = self._split_pool_name(channel)
            is_loop = channel in ("music", "ambient") or base in ("music", "ambient")
        if volume is None:
            base_name = inherit_base
            if base_name is None and self._is_pool_member(channel):
                base_name = self._split_pool_name(channel)[0]
            base_chan = self.channels.get(base_name) if base_name is not None else None
            volume = base_chan.volume if base_chan is not None else 1.0
        self._serial_counter += 1
        chan.serial = self._serial_counter
        chan.current_asset = asset_path
        chan.loop = is_loop
        chan.volume = max(0.0, min(1.0, volume))
        chan.loop_start = loop_start
        chan.loop_end = loop_end
        chan.is_playing = True
        chan.is_paused = False
        # A fresh playback cancels any pending fade-out automation; without
        # this a reused/stolen slot would be silenced mid-playback when the
        # stale fade completes in update().
        chan.fade_timer = 0.0
        chan.fade_duration = 0.0
        chan.fade_start_vol = 0.0
        chan.fade_target_vol = 0.0
        chan.stop_on_fade_complete = False

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
        return channel

    def _stop_one(self, channel: str, *, fade_out: float = 0.0) -> None:
        """Stop a single exact channel entry."""
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

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        """Stop playback on a channel.

        Stopping a base channel (``sound``) fans out to every allocated
        pool member (``sound_0``, ``sound_1``, …). Explicit pool names stop
        exactly that slot.
        """
        if self._is_pool_member(channel):
            self._stop_one(channel, fade_out=fade_out)
            return
        targets = [channel, *self._pool_members(channel)]
        for name in targets:
            self._stop_one(name, fade_out=fade_out)

    def stop_all(self, *, fade_out: float = 0.0) -> None:
        """Stop playback across all audio channels."""
        for name in list(self.channels):
            self._stop_one(name, fade_out=fade_out)

    def pause(self, channel: str) -> None:
        """Pause playback on a channel (base names fan out to pool members)."""
        if self._is_pool_member(channel):
            targets = [channel]
        else:
            targets = [channel, *self._pool_members(channel)]
        for name in targets:
            chan = self.channels.get(name)
            if chan and chan.is_playing:
                chan.is_paused = True
                self.backend.pause(name)

    def resume(self, channel: str) -> None:
        """Resume playback on a paused channel (base names fan out)."""
        if self._is_pool_member(channel):
            targets = [channel]
        else:
            targets = [channel, *self._pool_members(channel)]
        for name in targets:
            chan = self.channels.get(name)
            if chan and chan.is_paused:
                chan.is_paused = False
                self.backend.resume(name)

    def set_volume(self, channel: str, volume: float) -> None:
        """Set track volume for a channel (base names fan out to pool members)."""
        clamped = max(0.0, min(1.0, volume))
        if self._is_pool_member(channel):
            targets = [channel]
        else:
            targets = [channel, *self._pool_members(channel)]
        for name in targets:
            chan = self.channels.get(name)
            if chan is not None:
                chan.volume = clamped
                self.backend.set_volume(name, self._effective_volume(name))

    def set_master_volume(self, volume: float) -> None:
        """Set master volume scaling all channels."""
        self.master_volume = max(0.0, min(1.0, volume))
        for name in self.channels:
            self.backend.set_volume(name, self._effective_volume(name))

    def set_channel_volume(self, channel: str, volume: float) -> None:
        """Set type volume for a category of channel.

        Setting a base channel (``sound``) also pushes the recomputed
        effective volume to every allocated pool member so SFX preferences
        apply to overlapping sounds.
        """
        self.channel_volumes[channel] = max(0.0, min(1.0, volume))
        if self._is_pool_member(channel):
            targets = [channel]
        else:
            targets = [channel, *self._pool_members(channel)]
        for name in targets:
            self.backend.set_volume(name, self._effective_volume(name))

    def queue(self, channel: str, asset_path: str) -> None:
        """Queue an audio asset to play after current playback completes."""
        if channel not in self.channels:
            self.channels[channel] = ChannelState(name=channel)
            if not self._is_pool_member(channel):
                _ = self.channel_volumes.setdefault(channel, 1.0)
        chan = self.channels[channel]
        if not chan.is_playing:
            _ = self.play(channel, asset_path)
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
                _ = self.play(chan.name, next_asset)

        self.backend.update(dt)

    def shutdown(self) -> None:
        """Shut down the audio backend and release audio resources."""
        logger.debug("Shutting down audio backend %r", type(self.backend).__name__)
        self.backend.shutdown()

    def save_state(self) -> AudioMixerSaveState:
        """Save mixer state for checkpoints and saves.

        Idle pool members (``sound_0`` with nothing playing, nothing queued
        and no fade running) are pruned so checkpoints do not accumulate
        ghost channels over a long session.
        """
        result: AudioMixerSaveState = {
            "master_volume": self.master_volume,
            "channel_volumes": dict(self.channel_volumes),
            "channels": {
                name: chan.to_dict()
                for name, chan in self.channels.items()
                if not (
                    self._is_pool_member(name)
                    and not chan.is_playing
                    and not chan.queue
                    and chan.fade_duration == 0.0
                    and not chan.stop_on_fade_complete
                )
            },
            "serial_counter": self._serial_counter,
        }
        logger.debug("Saved mixer state: %d channels, master_volume=%.2f", len(result["channels"]), self.master_volume)
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
                logger.warning("load_state: skipping non-mapping channel entry %r", name)
                continue
            data: dict[str, object] = {
                str(k): v for k, v in cast(Mapping[object, object], data_obj).items()
            }
            chan = ChannelState.from_dict(data)
            existing = self.channels.get(name)

            # Check if this exact playback serial/track is already playing
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
                # Same music track/serial continues smoothly across rollback without restarting from frame 0
                if abs(existing.volume - chan.volume) > 1e-4:
                    self.backend.set_volume(name, self._effective_volume(name))
                if chan.is_paused and not existing.is_paused:
                    self.backend.pause(name)
                elif not chan.is_paused and existing.is_paused:
                    self.backend.resume(name)
            elif chan.is_playing and chan.current_asset:
                logger.debug("Restoring playback on channel %r (asset=%r)", name, chan.current_asset)
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
                self._stop_one(name)

        for name in list(self.channels):
            if name not in raw_channels_dict:
                if self._is_pool_member(name):
                    # Drop ghost pool slots allocated after this snapshot so
                    # rollback/checkpoints do not accumulate them forever.
                    with contextlib.suppress(Exception):
                        self.backend.stop(name)
                    del self.channels[name]
                else:
                    self._stop_one(name)
