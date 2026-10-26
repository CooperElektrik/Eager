"""File watcher for automatic script hot-reloading."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

__all__ = [
    "FileWatcher",
]


class FileWatcher:
    """Watches a file for changes using filesystem modification timestamps.

    Supports synchronous polling via :meth:`check_modified` or continuous
    monitoring. Zero-dependency implementation compatible with Python standard library.
    """

    def __init__(
        self,
        target_paths: str | Path | list[str | Path],
        *,
        interval: float = 0.25,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        if isinstance(target_paths, list):
            self.target_paths = [Path(p) for p in target_paths]
        else:
            self.target_paths = [Path(target_paths)]
        self.interval = interval
        self.on_change = on_change
        self._last_mtime: float | None = self._get_mtime()
        self._last_check_time: float = time.monotonic()

    def _get_mtime(self) -> float | None:
        mtimes: list[float] = []
        for p in self.target_paths:
            try:
                if p.is_dir():
                    for f in p.rglob("*.es"):
                        if not any(part.startswith((".", "venv", "__pycache__")) for part in f.parts):
                            mtimes.append(f.stat().st_mtime)
                elif p.exists():
                    mtimes.append(p.stat().st_mtime)
            except OSError:
                pass
        return max(mtimes) if mtimes else None

    def check_modified(self, force: bool = False) -> bool:
        """Check if target file has been modified since the last check.

        Throttled to :attr:`interval` unless `force` is True. Returns True
        and updates internal timestamp when modification is detected.
        """
        now = time.monotonic()
        if not force and (now - self._last_check_time < self.interval):
            return False

        self._last_check_time = now
        current_mtime = self._get_mtime()
        if current_mtime is None:
            return False

        if self._last_mtime is None:
            self._last_mtime = current_mtime
            return False

        if current_mtime > self._last_mtime:
            self._last_mtime = current_mtime
            if self.on_change is not None:
                self.on_change()
            return True

        return False

    def reset(self) -> None:
        """Reset the tracked modification time to the current file timestamp."""
        self._last_mtime = self._get_mtime()
        self._last_check_time = time.monotonic()
