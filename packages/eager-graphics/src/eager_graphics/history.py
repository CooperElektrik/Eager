"""Visual history stack management for stage compositor and director rollback."""

from __future__ import annotations

import collections
import copy
from typing import Any


class VisualHistoryManager:
    """Manages snapshots of visual and UI state for rollback and undo."""

    def __init__(self, max_history: int = 500) -> None:
        if max_history < 1:
            msg = "max_history must be at least 1"
            raise ValueError(msg)
        self.max_history = max_history
        self._history: collections.deque[dict[str, Any]] = collections.deque(maxlen=max_history)

    def push(self, snapshot: dict[str, Any]) -> None:
        """Push a visual state snapshot onto the history stack."""
        self._history.append(copy.deepcopy(snapshot))

    def pop(self) -> dict[str, Any] | None:
        """Pop and return the most recent visual state snapshot, or None if empty."""
        if not self._history:
            return None
        return self._history.pop()

    def clear(self) -> None:
        """Clear all snapshots in history."""
        self._history.clear()

    @property
    def can_rollback(self) -> bool:
        """Return True if there is at least one snapshot available to pop."""
        return len(self._history) > 0

    @property
    def depth(self) -> int:
        """Return current number of snapshots in history."""
        return len(self._history)

    def to_dict(self) -> dict[str, Any]:
        """Serialize history stack to a dictionary."""
        return {
            "max_history": self.max_history,
            "history": list(self._history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualHistoryManager:
        """Deserialize history stack from a dictionary."""
        max_history = int(data.get("max_history", 500))
        manager = cls(max_history=max_history)
        history_list = data.get("history", [])
        for item in history_list:
            manager.push(item)
        return manager
