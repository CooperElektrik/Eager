"""Discrete narrative events emitted by the Eager story virtual machine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class SceneEnterEvent:
    """Emitted when execution transitions into a scene node."""

    scene_id: str
    display_name: str
    line_number: int

    @property
    def type(self) -> str:
        return "scene_enter"

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "scene_id": self.scene_id,
            "display_name": self.display_name,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class DialogueEvent:
    """Emitted for character dialogue beats."""

    speaker: str
    text: str
    voice: str | None
    emotion: str | None
    line_number: int
    beat_id: str | None = None

    @property
    def type(self) -> str:
        return "dialogue"

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": self.type,
            "speaker": self.speaker,
            "text": self.text,
            "voice": self.voice,
            "emotion": self.emotion,
            "line_number": self.line_number,
        }
        if self.beat_id is not None:
            data["beat_id"] = self.beat_id
        return data


@dataclass(frozen=True, slots=True)
class AppendEvent:
    """Emitted for box append continuation beats ('-')."""

    text: str
    line_number: int
    beat_id: str | None = None

    @property
    def type(self) -> str:
        return "append"

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
        }
        if self.beat_id is not None:
            data["beat_id"] = self.beat_id
        return data


@dataclass(frozen=True, slots=True)
class FreshBoxEvent:
    """Emitted for fresh box clear beats ('/')."""

    text: str
    line_number: int
    beat_id: str | None = None

    @property
    def type(self) -> str:
        return "fresh_box"

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
        }
        if self.beat_id is not None:
            data["beat_id"] = self.beat_id
        return data


@dataclass(frozen=True, slots=True)
class NarrationEvent:
    """Emitted for narrative prose beats."""

    text: str
    line_number: int
    beat_id: str | None = None

    @property
    def type(self) -> str:
        return "narration"

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
        }
        if self.beat_id is not None:
            data["beat_id"] = self.beat_id
        return data


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    """An individual selectable branch option in a ChoicePromptEvent."""

    index: int
    text: str
    target: str | None = None
    line_number: int = 0
    condition: str | None = None
    enabled: bool = True
    beat_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "index": self.index,
            "text": self.text,
            "target": self.target,
            "line_number": self.line_number,
            "enabled": self.enabled,
        }
        if self.condition is not None:
            data["condition"] = self.condition
        if self.beat_id is not None:
            data["beat_id"] = self.beat_id
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ChoiceOption:
        idx_val = data["index"]
        text_val = data["text"]
        target_val = data.get("target")
        line_val = data.get("line_number", 0)
        cond_val = data.get("condition")
        beat_val = data.get("beat_id")
        return cls(
            index=int(idx_val) if isinstance(idx_val, (int, str)) else 0,
            text=str(text_val),
            target=str(target_val) if target_val is not None else None,
            line_number=int(line_val) if isinstance(line_val, (int, str)) else 0,
            condition=str(cond_val) if cond_val is not None else None,
            enabled=bool(data.get("enabled", True)),
            beat_id=str(beat_val) if beat_val is not None else None,
        )


@dataclass(frozen=True, slots=True)
class ChoicePromptEvent:
    """Emitted when story progression pauses for player branching selection."""

    options: tuple[ChoiceOption, ...]
    line_number: int
    beat_id: str | None = None

    @property
    def type(self) -> str:
        return "choice_prompt"

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": self.type,
            "options": [opt.to_dict() for opt in self.options],
            "line_number": self.line_number,
        }
        if self.beat_id is not None:
            data["beat_id"] = self.beat_id
        return data


@dataclass(frozen=True, slots=True)
class HookEvent:
    """Emitted when an engine hook is triggered ('~ hook_name args')."""

    hook_name: str
    args: str
    line_number: int

    @property
    def type(self) -> str:
        return "hook"

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "hook_name": self.hook_name,
            "args": self.args,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class SceneExitEvent:
    """Emitted when leaving a scene node via transition, call, or return."""

    scene_id: str
    transition_kind: str  # "jump" | "call" | "choice" | "return" | "fallthrough"
    target: str | None
    line_number: int

    @property
    def type(self) -> str:
        return "scene_exit"

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "scene_id": self.scene_id,
            "transition_kind": self.transition_kind,
            "target": self.target,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class StoryEndEvent:
    """Emitted when the story execution completes or reaches a terminal scene."""

    scene_id: str | None
    reason: str  # "terminal" | "dead_end" | "completed" | "interrupted"

    @property
    def type(self) -> str:
        return "story_end"

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "scene_id": self.scene_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class InputPromptEvent:
    """Emitted when story prompts the player for textual input ('~ input var prompt')."""

    var_name: str
    prompt: str
    default: str = ""
    line_number: int = 0
    beat_id: str | None = None

    @property
    def type(self) -> str:
        return "input_prompt"

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "type": self.type,
            "var_name": self.var_name,
            "prompt": self.prompt,
            "default": self.default,
            "line_number": self.line_number,
        }
        if self.beat_id is not None:
            data["beat_id"] = self.beat_id
        return data


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
    | InputPromptEvent
)
