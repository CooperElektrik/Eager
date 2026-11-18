"""Pyglet-based audio playback backend for Eager-Graphics."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import pyglet
    import pyglet.media
except ImportError as err:
    msg = "Pyglet is not installed. Install with 'pip install eager-graphics[hardware]' or 'pip install pyglet'."
    raise ImportError(msg) from err

__all__ = [
    "PygletAudioBackend",
]


class PygletAudioBackend:
    """Pyglet-based audio backend implementing AudioBackend protocol.

    Uses a `pyglet.media.Player` per channel for playback, volume, and looping.
    Supports whole-file looping and seamless loop points (loop_start/loop_end).
    Caches StaticSource for short SFX sounds to avoid repeated disk reads and decodes.
    """

    def __init__(self) -> None:
        self._players: dict[str, pyglet.media.Player] = {}
        self._loop_points: dict[str, tuple[float | None, float | None]] = {}
        self._static_sources: dict[str, pyglet.media.Source] = {}

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
        """Start playback of an audio asset using Pyglet media player.

        Args:
            channel: Target audio channel name.
            asset_path: File path or resource identifier of the audio track.
            loop: Whether the audio track repeats when finished. Defaults to False.
            volume: Normalized volume level in the range [0.0, 1.0]. Defaults to 1.0.
            fade_in: Fade in duration in seconds. Defaults to 0.0.
            loop_start: Optional loop start timestamp in seconds.
            loop_end: Optional loop end timestamp in seconds.
        """
        path_str = str(asset_path)
        if channel in self._players:
            old_player = self._players[channel]
            try:
                old_player.pause()
                old_player.delete()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to release previous player on channel %r: %s", channel, exc
                )

        is_sfx = not loop or channel in ("sfx", "voice", "ui", "sound")
        source: pyglet.media.Source | None = None

        if is_sfx:
            source = self._static_sources.get(path_str)
            if source is None:
                try:
                    loaded = pyglet.media.load(path_str, streaming=False)
                    static_src = (
                        pyglet.media.StaticSource(loaded)
                        if not isinstance(loaded, pyglet.media.StaticSource)
                        else loaded
                    )
                    self._static_sources[path_str] = static_src
                    source = static_src
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to load static audio source for channel %r from %r: %s",
                        channel,
                        path_str,
                        exc,
                    )

        if source is None:
            try:
                source = pyglet.media.load(path_str, streaming=True)
            except Exception as exc_stream:  # noqa: BLE001
                try:
                    source = pyglet.media.load(path_str, streaming=False)
                except Exception as exc_static:  # noqa: BLE001
                    logger.warning(
                        "Failed to load or decode audio for channel %r from %r "
                        "(streaming failed: %s; non-streaming failed: %s)",
                        channel,
                        path_str,
                        exc_stream,
                        exc_static,
                    )
                    return

        try:
            player = pyglet.media.Player()
            player.queue(source)
            player.volume = max(0.0, min(1.0, volume))
            self._loop_points[channel] = (loop_start, loop_end)

            if loop:
                if loop_start is None and loop_end is None:
                    player.loop = True
                else:
                    player.loop = False

                    @player.event
                    def on_player_eos() -> None:
                        seek_pos = loop_start if loop_start is not None else 0.0
                        try:
                            player.seek(seek_pos)
                            player.play()
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Failed to seek/loop audio on EOS for channel %r: %s",
                                channel,
                                exc,
                            )
            else:
                player.loop = False

            self._players[channel] = player
            player.play()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to play audio on channel %r from %r: %s",
                channel,
                path_str,
                exc,
            )
            self._players.pop(channel, None)
            self._loop_points.pop(channel, None)

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        """Halt playback and delete the player for a channel.

        Args:
            channel: Target audio channel name.
            fade_out: Duration in seconds to fade out before stopping.
        """
        player = self._players.get(channel)
        if player is not None:
            try:
                player.pause()
                player.delete()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error stopping player on channel %r: %s", channel, exc
                )
            del self._players[channel]
            self._loop_points.pop(channel, None)

    def set_volume(self, channel: str, volume: float) -> None:
        """Adjust channel playback volume.

        Args:
            channel: Target audio channel name.
            volume: Normalized volume level in the range [0.0, 1.0].
        """
        player = self._players.get(channel)
        if player is not None:
            player.volume = max(0.0, min(1.0, volume))

    def pause(self, channel: str) -> None:
        """Pause playback on the channel.

        Args:
            channel: Target audio channel name.
        """
        player = self._players.get(channel)
        if player is not None:
            player.pause()

    def resume(self, channel: str) -> None:
        """Resume playback on the channel.

        Args:
            channel: Target audio channel name.
        """
        player = self._players.get(channel)
        if player is not None:
            player.play()

    def is_playing(self, channel: str) -> bool:
        """Check whether audio is actively playing on the channel.

        Args:
            channel: Target audio channel name.

        Returns:
            True if player exists and is currently playing.
        """
        player = self._players.get(channel)
        return bool(player is not None and player.playing)

    def update(self, dt: float) -> None:
        """Process custom loop point wrapping.

        Args:
            dt: Delta time elapsed in seconds.
        """
        for ch, player in list(self._players.items()):
            if not player.playing:
                continue
            loop_start, loop_end = self._loop_points.get(ch, (None, None))
            if loop_end is not None and player.time >= loop_end:
                seek_pos = loop_start if loop_start is not None else 0.0
                try:
                    player.seek(seek_pos)
                    player.play()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to seek/loop audio at loop_end on channel %r: %s",
                        ch,
                        exc,
                    )

    def shutdown(self) -> None:
        """Stop all channel players and release media sources."""
        for ch, player in list(self._players.items()):
            try:
                player.pause()
                player.delete()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error stopping player during shutdown on channel %r: %s", ch, exc
                )
        self._players.clear()
        self._loop_points.clear()
        self._static_sources.clear()
