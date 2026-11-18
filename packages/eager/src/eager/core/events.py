"""Discrete narrative events emitted by the Eager story virtual machine."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias

__all__ = [
    "AppendEvent",
    "ChoiceOption",
    "ChoicePromptEvent",
    "DialogueEvent",
    "FreshBoxEvent",
    "HookEvent",
    "NarrationEvent",
    "SceneEnterEvent",
    "SceneExitEvent",
    "StoryEndEvent",
    "StoryEvent",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SceneEnterEvent:
    """Emitted when execution transitions into a scene node."""

    scene_id: str
    display_name: str
    line_number: int

    @property
    def type(self) -> str:
        """Event type identifier ('scene_enter')."""
        return "scene_enter"


@dataclass(frozen=True, slots=True)
class DialogueEvent:
    """Emitted for character dialogue beats."""

    speaker: str
    text: str
    voice: str | None
    emotion: str | None
    line_number: int
    character_id: str | None = None

    @property
    def type(self) -> str:
        """Event type identifier ('dialogue')."""
        return "dialogue"


@dataclass(frozen=True, slots=True)
class AppendEvent:
    """Emitted for box append continuation beats ('-')."""

    text: str
    line_number: int

    @property
    def type(self) -> str:
        """Event type identifier ('append')."""
        return "append"


@dataclass(frozen=True, slots=True)
class FreshBoxEvent:
    """Emitted for fresh box clear beats ('/')."""

    text: str
    line_number: int

    @property
    def type(self) -> str:
        """Event type identifier ('fresh_box')."""
        return "fresh_box"


@dataclass(frozen=True, slots=True)
class NarrationEvent:
    """Emitted for narrative prose beats."""

    text: str
    line_number: int

    @property
    def type(self) -> str:
        """Event type identifier ('narration')."""
        return "narration"


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    """An individual selectable branch option in a ChoicePromptEvent."""

    index: int
    text: str
    target: str | None = None
    line_number: int = 0
    condition: str | None = None
    enabled: bool = True

    def to_dict(self) -> dict[str, object]:
        """Serialize choice option to a dictionary."""
        data: dict[str, object] = {
            "index": self.index,
            "text": self.text,
            "target": self.target,
            "line_number": self.line_number,
            "enabled": self.enabled,
        }
        if self.condition is not None:
            data["condition"] = self.condition
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ChoiceOption:
        """Construct ChoiceOption from dictionary."""
        idx_val = data["index"]
        text_val = data["text"]
        target_val = data.get("target")
        line_val = data.get("line_number", 0)
        cond_val = data.get("condition")
        return cls(
            index=int(idx_val) if isinstance(idx_val, (int, str)) else 0,
            text=str(text_val),
            target=str(target_val) if target_val is not None else None,
            line_number=int(line_val) if isinstance(line_val, (int, str)) else 0,
            condition=str(cond_val) if cond_val is not None else None,
            enabled=bool(data.get("enabled", True)),
        )


@dataclass(frozen=True, slots=True)
class ChoicePromptEvent:
    """Emitted when story progression pauses for player branching selection."""

    options: tuple[ChoiceOption, ...]
    line_number: int

    @property
    def type(self) -> str:
        """Event type identifier ('choice_prompt')."""
        return "choice_prompt"


@dataclass(frozen=True, slots=True)
class HookEvent:
    """Emitted when an engine hook is triggered ('~ hook_name args')."""

    hook_name: str
    args: str
    line_number: int

    @property
    def type(self) -> str:
        """Event type identifier ('hook')."""
        return "hook"


@dataclass(frozen=True, slots=True)
class SceneExitEvent:
    """Emitted when leaving a scene node via transition, call, or return."""

    scene_id: str
    transition_kind: str  # "jump" | "call" | "choice" | "return" | "fallthrough"
    target: str | None
    line_number: int

    @property
    def type(self) -> str:
        """Event type identifier ('scene_exit')."""
        return "scene_exit"


@dataclass(frozen=True, slots=True)
class StoryEndEvent:
    """Emitted when the story execution completes or reaches a terminal scene."""

    scene_id: str | None
    reason: str  # "terminal" | "dead_end" | "completed" | "interrupted"

    @property
    def type(self) -> str:
        """Event type identifier ('story_end')."""
        return "story_end"


StoryEvent: TypeAlias = (
    SceneEnterEvent
    | DialogueEvent
    | AppendEvent
    | FreshBoxEvent
    | NarrationEvent
    | ChoicePromptEvent
    | HookEvent
    | SceneExitEvent
    | StoryEndEvent
)
