"""Lightweight frame timing and FPS measurement utilities."""

from __future__ import annotations

import time

__all__ = ["FrameClock"]


class FrameClock:
    """Track frame timestamps and compute FPS (frames-per-second).

    Parameters
    ----------
    rolling_window : int, optional
        Number of recent frames used for the rolling-average FPS, by default 60.

    Attributes
    ----------
    rolling_window : int
        The rolling-average window size.
    """

    def __init__(self, rolling_window: int = 60) -> None:
        if rolling_window < 2:
            msg = "rolling_window must be >= 2"
            raise ValueError(msg)
        self.rolling_window: int = rolling_window
        self._timestamps: list[float] = []
        self._frame_count: int = 0
        self._start_time: float | None = None
        self._last_time: float | None = None
        self._last_dt: float = 0.0

    # ------------------------------------------------------------------ #
    # Core
    # ------------------------------------------------------------------ #

    def tick(self, now: float | None = None) -> float:
        """Record a frame boundary and return the delta since the last.

        Parameters
        ----------
        now : float, optional
            Explicit timestamp (for deterministic testing). When ``None``
            (the default) :func:`time.perf_counter` is used.

        Returns
        -------
        float
            Seconds elapsed since the previous tick, or ``0.0`` on the first tick.
        """
        if now is None:
            now = time.perf_counter()

        if self._last_time is None:
            self._start_time = now
            self._last_time = now
            self._last_dt = 0.0
            self._frame_count = 1
            self._timestamps = [now]
            return 0.0

        dt = now - self._last_time
        self._last_dt = max(0.0, dt)
        self._last_time = now
        self._frame_count += 1
        self._timestamps.append(now)
        self._trim()
        return self._last_dt

    def _trim(self) -> None:
        """Keep only the last ``rolling_window + 1`` timestamps."""
        keep = self.rolling_window + 1
        if len(self._timestamps) > keep:
            del self._timestamps[: len(self._timestamps) - keep]

    def reset(self) -> None:
        """Clear all recorded timestamps and counters."""
        self._timestamps.clear()
        self._frame_count = 0
        self._start_time = None
        self._last_time = None
        self._last_dt = 0.0

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def frame_count(self) -> int:
        """Total number of frames recorded since the last :meth:`reset`."""
        return self._frame_count

    @property
    def dt(self) -> float:
        """Delta time (seconds) of the most recent frame."""
        return self._last_dt

    @property
    def fps(self) -> float:
        """Instantaneous FPS based on the last frame interval."""
        if self._last_dt <= 0.0:
            return 0.0
        return 1.0 / self._last_dt

    @property
    def fps_avg(self) -> float:
        """Rolling-average FPS over the last ``rolling_window`` frames."""
        if len(self._timestamps) < 2:
            return 0.0
        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed <= 0.0:
            return 0.0
        n_intervals = len(self._timestamps) - 1
        return n_intervals / elapsed

    @property
    def fps_overall(self) -> float:
        """Overall FPS since the clock started or was last reset."""
        if self._start_time is None or self._last_time is None:
            return 0.0
        elapsed = self._last_time - self._start_time
        if elapsed <= 0.0:
            return 0.0
        return self._frame_count / elapsed

    @property
    def elapsed(self) -> float:
        """Total wall-clock time (seconds) since the clock started/reset."""
        if self._start_time is None or self._last_time is None:
            return 0.0
        return self._last_time - self._start_time
