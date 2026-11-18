"""Execution state, snapshot serialization, and rollback management for Eager."""

from __future__ import annotations

import collections
import copy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from eager.core.audio import AudioMixerSaveState

__all__ = [
    "CallFrame",
    "Checkpoint",
    "CheckpointHistory",
    "StorySnapshot",
]


@dataclass(frozen=True, slots=True)
class CallFrame:
    """A return point frame on the narrative subroutine call stack."""

    scene_id: str
    beat_index: int
    kind: str = "call"  # "call" for '>>', "inline" for an optional inline choice block

    def to_dict(self) -> dict[str, object]:
        """Serialize call frame to a dictionary."""
        return {
            "scene_id": self.scene_id,
            "beat_index": self.beat_index,
            "kind": self.kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CallFrame:
        """Construct CallFrame from a serialized dictionary."""
        return cls(
            scene_id=data["scene_id"],
            beat_index=data["beat_index"],
            kind=data.get("kind", "call"),
        )


@dataclass(frozen=True, slots=True)
class StorySnapshot:
    """An immutable, serializable snapshot of the narrative execution state."""

    CURRENT_VERSION: ClassVar[int] = 1

    current_scene: str | None
    beat_index: int
    call_stack: tuple[CallFrame, ...]
    variables: dict[str, Any]
    visited_scenes: tuple[str, ...]
    pending_choice_beat: int | None = None
    next_transition_target: str | None = None
    just_entered_scene: bool = False
    is_ended: bool = False
    rng_state: list[Any] | None = None
    preamble_index: int = 0
    preamble_done: bool = False
    version: int = 1

    def to_dict(self) -> dict[str, object]:
        """Serialize snapshot to a JSON-compatible dictionary."""
        return {
            "version": self.version,
            "current_scene": self.current_scene,
            "beat_index": self.beat_index,
            "call_stack": [frame.to_dict() for frame in self.call_stack],
            "variables": copy.deepcopy(self.variables),
            "visited_scenes": list(self.visited_scenes),
            "pending_choice_beat": self.pending_choice_beat,
            "next_transition_target": self.next_transition_target,
            "just_entered_scene": self.just_entered_scene,
            "is_ended": self.is_ended,
            "rng_state": copy.deepcopy(self.rng_state) if self.rng_state is not None else None,
            "preamble_index": self.preamble_index,
            "preamble_done": self.preamble_done,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        target_version: int | None = None,
    ) -> StorySnapshot:
        """Restore a StorySnapshot from a dictionary."""
        version = int(data.get("version", 1))
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
            next_transition_target=data.get("next_transition_target"),
            just_entered_scene=data.get("just_entered_scene", False),
            is_ended=data.get("is_ended", False),
            rng_state=copy.deepcopy(data.get("rng_state")),
            preamble_index=data.get("preamble_index", 0),
            preamble_done=data.get("preamble_done", True),
        )


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Unified state snapshot captured at an interactive point in the story."""

    story: dict[str, Any]
    visual: dict[str, Any]
    audio: dict[str, Any] | AudioMixerSaveState
    backlog_len: int
    ui: dict[str, Any]
    backlog: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize checkpoint to a JSON-compatible dictionary."""
        d: dict[str, object] = {
            "story": copy.deepcopy(self.story),
            "visual": copy.deepcopy(self.visual),
            "audio": copy.deepcopy(dict(self.audio)),
            "backlog_len": self.backlog_len,
            "ui": copy.deepcopy(self.ui),
        }
        if self.backlog is not None:
            d["backlog"] = copy.deepcopy(self.backlog)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        """Restore a Checkpoint from a dictionary."""
        if not isinstance(data, dict):
            raise TypeError(f"Checkpoint data must be a dict, got {type(data).__name__}")
        story = data.get("story")
        visual = data.get("visual")
        audio = data.get("audio")
        ui = data.get("ui")
        backlog_raw = data.get("backlog_len", 0)
        backlog_len = int(0 if backlog_raw is None else backlog_raw)
        backlog_entries = data.get("backlog")
        return cls(
            story=story if isinstance(story, dict) else {},
            visual=visual if isinstance(visual, dict) else {},
            audio=audio if isinstance(audio, dict) else {},
            backlog_len=backlog_len,
            ui=ui if isinstance(ui, dict) else {},
            backlog=backlog_entries if isinstance(backlog_entries, list) else None,
        )


class CheckpointHistory:
    """Bounded history stack for interactive story checkpoints."""

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._history: collections.deque[Checkpoint] = collections.deque(maxlen=max_history)

    def push(self, checkpoint: Checkpoint) -> None:
        """Add a checkpoint to the history."""
        self._history.append(checkpoint)

    def pop(self) -> Checkpoint | None:
        """Remove and return the most recent checkpoint."""
        if not self._history:
            return None
        return self._history.pop()

    def clear(self) -> None:
        """Clear all stored checkpoints."""
        self._history.clear()

    @property
    def can_rollback(self) -> bool:
        """True if there is at least one previous checkpoint to restore."""
        return len(self._history) > 1

    @property
    def depth(self) -> int:
        """Number of checkpoints stored in history."""
        return len(self._history)

    def get_latest(self) -> Checkpoint | None:
        """Inspect the top checkpoint without popping."""
        return self._history[-1] if self._history else None
