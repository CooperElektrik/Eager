"""Persistent data manager across playthroughs (unlocks, seen scenes, ending flags)."""

from __future__ import annotations

import collections.abc
from pathlib import Path
from typing import Any

from eager_core.storage import atomic_write_json, safe_read_json

__all__ = [
    "PersistentData",
]


class PersistentData(collections.abc.MutableMapping[str, Any]):
    """Persistent game state that survives playthroughs and saves."""

    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path
        self._data: dict[str, Any] = {}
        if self._file_path is not None and self._file_path.exists():
            self.load()

    def load(self) -> None:
        """Load persistent data from disk."""
        if self._file_path is None:
            return
        loaded = safe_read_json(self._file_path, default=None, backup_corrupt=True)
        if isinstance(loaded, dict):
            self._data = loaded
        else:
            if self._file_path.exists():
                try:
                    import shutil

                    bak_path = self._file_path.with_name(self._file_path.name + ".corrupt.bak")
                    if not bak_path.exists():
                        shutil.copy2(self._file_path, bak_path)
                except OSError:
                    pass
            self._data = {}

    def save(self) -> None:
        """Save persistent data to disk atomically."""
        if self._file_path is None:
            return
        atomic_write_json(self._file_path, self._data)

    def __getitem__(self, key: str) -> Any:
        """Retrieve a stored persistent value by key."""
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """Store a persistent value by key."""
        self._data[key] = value

    def __delitem__(self, key: str) -> None:
        """Remove a persistent variable by key."""
        del self._data[key]

    def __iter__(self) -> collections.abc.Iterator[str]:
        """Iterate over all persistent variable keys."""
        return iter(self._data)

    def __len__(self) -> int:
        """Return the number of stored persistent variables."""
        return len(self._data)

    def __getattr__(self, name: str) -> Any:
        """Access a persistent variable as an attribute."""
        if name.startswith("_"):
            raise AttributeError(name)
        return self._data.get(name)

    def __setattr__(self, name: str, value: Any) -> None:
        """Set a persistent variable as an attribute."""
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def to_dict(self) -> dict[str, Any]:
        """Return shallow copy as standard dictionary."""
        return dict(self._data)

    def unlock_gallery(self, image_id: str) -> None:
        """Unlock a CG gallery image."""
        gallery = set(self._data.get("gallery", []))
        gallery.add(image_id)
        self._data["gallery"] = sorted(gallery)
        self.save()

    def is_gallery_unlocked(self, image_id: str) -> bool:
        """Return True if the CG gallery image is unlocked."""
        return image_id in self._data.get("gallery", [])

    def unlock_achievement(self, ach_id: str) -> None:
        """Unlock an achievement."""
        ach = set(self._data.get("achievements", []))
        ach.add(ach_id)
        self._data["achievements"] = sorted(ach)
        self.save()

    def has_achievement(self, ach_id: str) -> bool:
        """Return True if the achievement is unlocked."""
        return ach_id in self._data.get("achievements", [])

