"""Execution state, snapshot serialization, and rollback management for Eager."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CallFrame:
    """A return point frame on the narrative subroutine call stack."""

    scene_id: str
    beat_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "beat_index": self.beat_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallFrame:
        return cls(
            scene_id=data["scene_id"],
            beat_index=data["beat_index"],
        )


@dataclass(frozen=True, slots=True)
class StorySnapshot:
    """An immutable, serializable snapshot of the narrative execution state."""

    current_scene: str | None
    beat_index: int
    call_stack: tuple[CallFrame, ...]
    variables: dict[str, Any]
    visited_scenes: tuple[str, ...]
    pending_choice_beat: int | None = None
    pending_input_beat: int | None = None
    next_transition_target: str | None = None
    just_entered_scene: bool = False
    is_ended: bool = False
    rng_state: list[Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to a JSON-compatible dictionary."""
        return {
            "current_scene": self.current_scene,
            "beat_index": self.beat_index,
            "call_stack": [frame.to_dict() for frame in self.call_stack],
            "variables": copy.deepcopy(self.variables),
            "visited_scenes": list(self.visited_scenes),
            "pending_choice_beat": self.pending_choice_beat,
            "pending_input_beat": self.pending_input_beat,
            "next_transition_target": self.next_transition_target,
            "just_entered_scene": self.just_entered_scene,
            "is_ended": self.is_ended,
            "rng_state": copy.deepcopy(self.rng_state) if self.rng_state is not None else None,
        }

    def to_json(self, indent: int | None = None) -> str:
        """Serialize snapshot to a JSON formatted string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StorySnapshot:
        """Restore a StorySnapshot from a dictionary."""
        call_stack = tuple(CallFrame.from_dict(f) for f in data.get("call_stack", []))
        variables = copy.deepcopy(data.get("variables", {}))
        visited_scenes = tuple(data.get("visited_scenes", []))
        return cls(
            current_scene=data.get("current_scene"),
            beat_index=data.get("beat_index", 0),
            call_stack=call_stack,
            variables=variables,
            visited_scenes=visited_scenes,
            pending_choice_beat=data.get("pending_choice_beat"),
            pending_input_beat=data.get("pending_input_beat"),
            next_transition_target=data.get("next_transition_target"),
            just_entered_scene=data.get("just_entered_scene", False),
            is_ended=data.get("is_ended", False),
            rng_state=copy.deepcopy(data.get("rng_state")),
        )

    @classmethod
    def from_json(cls, json_str: str) -> StorySnapshot:
        """Restore a StorySnapshot from a JSON formatted string."""
        return cls.from_dict(json.loads(json_str))


class HistoryManager:
    """Chronological trail of snapshots enabling time-travel and rollback."""

    def __init__(self, max_history: int = 500) -> None:
        self._history: list[StorySnapshot] = []
        self._max_history = max_history

    def push(self, snapshot: StorySnapshot) -> None:
        """Record a snapshot in history."""
        self._history.append(snapshot)
        if len(self._history) > self._max_history:
            self._history.pop(0)

    def pop(self) -> StorySnapshot | None:
        """Pop and return the previous snapshot if available."""
        if not self._history:
            return None
        return self._history.pop()

    def clear(self) -> None:
        """Clear all recorded history."""
        self._history.clear()

    @property
    def can_rollback(self) -> bool:
        """True if there is at least one recorded previous snapshot."""
        return len(self._history) > 0

    @property
    def depth(self) -> int:
        """Number of rollback points currently stored."""
        return len(self._history)
