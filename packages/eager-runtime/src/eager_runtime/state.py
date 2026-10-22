"""Execution state, snapshot serialization, and rollback management for Eager."""

from __future__ import annotations

import collections
import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from eager_core.audio import AudioMixerSaveState


@dataclass(frozen=True, slots=True)
class CallFrame:
    """A return point frame on the narrative subroutine call stack."""

    scene_id: str
    beat_index: int
    kind: str = "call"  # "call" for '>>', "inline" for an optional inline choice block

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "beat_index": self.beat_index,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallFrame:
        return cls(
            scene_id=data["scene_id"],
            beat_index=data["beat_index"],
            kind=data.get("kind", "call"),
        )


@dataclass(frozen=True, slots=True)
class StorySnapshot:
    """An immutable, serializable snapshot of the narrative execution state."""

    CURRENT_VERSION: ClassVar[int] = 1
    _migrations: ClassVar[dict[int, Callable[[dict[str, Any]], dict[str, Any]]]] = {}

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
    version: int = 1

    @classmethod
    def register_migration(
        cls,
        from_version: int,
        migration_fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register a schema migration function for a specific StorySnapshot version."""
        cls._migrations[from_version] = migration_fn

    @classmethod
    def clear_migrations(cls) -> None:
        """Clear all registered StorySnapshot migrations."""
        cls._migrations.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialize snapshot to a JSON-compatible dictionary."""
        return {
            "version": self.version,
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
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        target_version: int | None = None,
    ) -> StorySnapshot:
        """Restore a StorySnapshot from a dictionary, applying migrations if necessary."""
        data = copy.deepcopy(data)
        target = cls.CURRENT_VERSION if target_version is None else target_version
        version = int(data.get("version", 1))
        while (version < target or version in cls._migrations) and version in cls._migrations:
            data = cls._migrations[version](data)
            version = int(data.get("version", version + 1))

        call_stack = tuple(CallFrame.from_dict(f) for f in data.get("call_stack", []))
        variables = copy.deepcopy(data.get("variables", {}))
        visited_scenes = tuple(data.get("visited_scenes", []))
        return cls(
            version=version,
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


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Unified state snapshot captured at an interactive point in the story."""

    story: dict[str, Any]
    visual: dict[str, Any]
    audio: dict[str, Any] | AudioMixerSaveState
    backlog_len: int
    ui: dict[str, Any]
    active_input_prompt: dict[str, Any] | None = None


class CheckpointHistory:
    """Bounded history stack for interactive story checkpoints with redo support."""

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._history: collections.deque[Checkpoint] = collections.deque(maxlen=max_history)
        self._redo_stack: list[Checkpoint] = []

    def push(self, checkpoint: Checkpoint) -> None:
        """Add a checkpoint to the history and clear redo stack."""
        self._history.append(checkpoint)
        self._redo_stack.clear()

    def pop(self) -> Checkpoint | None:
        """Remove and return the most recent checkpoint, preserving it on redo stack."""
        if not self._history:
            return None
        cp = self._history.pop()
        self._redo_stack.append(cp)
        return cp

    def roll_forward(self) -> Checkpoint | None:
        """Pop a checkpoint from redo stack and push it back to history."""
        if not self._redo_stack:
            return None
        cp = self._redo_stack.pop()
        self._history.append(cp)
        return cp

    def clear(self) -> None:
        """Clear all stored checkpoints and redo stack."""
        self._history.clear()
        self._redo_stack.clear()

    def clear_redo(self) -> None:
        """Clear only the redo stack."""
        self._redo_stack.clear()

    @property
    def can_rollback(self) -> bool:
        """True if there is at least one previous checkpoint to restore."""
        return len(self._history) > 1

    @property
    def can_roll_forward(self) -> bool:
        """True if there is at least one popped checkpoint that can be restored forward."""
        return len(self._redo_stack) > 0

    @property
    def depth(self) -> int:
        """Number of checkpoints stored in history."""
        return len(self._history)

    def get_latest(self) -> Checkpoint | None:
        """Inspect the top checkpoint without popping."""
        return self._history[-1] if self._history else None
