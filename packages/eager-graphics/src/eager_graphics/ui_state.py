"""UI state sidecar data structures tracking dialogue, choices, and story state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eager_core.events import ChoiceOption
from eager_core.types import Color


@dataclass
class NVLEntry:
    """An individual line or paragraph in NVL mode."""

    speaker: str | None
    text: str
    emotion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "emotion": self.emotion,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NVLEntry:
        return cls(
            speaker=data.get("speaker"),
            text=str(data.get("text", "")),
            emotion=data.get("emotion"),
        )


@dataclass
class UIState:
    """Current state of narrative UI elements (dialogue box, choices, completion status)."""

    speaker: str | None = None
    text: str = ""
    emotion: str | None = None
    choices: list[ChoiceOption] = field(default_factory=list)
    is_finished: bool = False
    side_image: str | None = None
    nvl_mode: bool = False
    nvl_entries: list[NVLEntry] = field(default_factory=list)
    visible_chars: int | None = None
    speaker_color: Color | None = None

    def clear_dialogue(self) -> None:
        """Clear active dialogue and speaker information."""
        self.speaker = None
        self.text = ""
        self.emotion = None
        self.side_image = None
        self.visible_chars = None
        self.speaker_color = None

    def clear_nvl(self) -> None:
        """Clear NVL mode accumulated text lines."""
        self.nvl_entries.clear()

    def clear_choices(self) -> None:
        """Clear active choice options."""
        self.choices.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialize UIState to a dictionary."""
        return {
            "speaker": self.speaker,
            "text": self.text,
            "emotion": self.emotion,
            "choices": [choice.to_dict() for choice in self.choices],
            "is_finished": self.is_finished,
            "side_image": self.side_image,
            "nvl_mode": self.nvl_mode,
            "nvl_entries": [e.to_dict() for e in self.nvl_entries],
            "visible_chars": self.visible_chars,
            "speaker_color": self.speaker_color.to_hex() if self.speaker_color is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UIState:
        """Deserialize UIState from a dictionary."""
        choices_raw = data.get("choices", [])
        choices = [
            ChoiceOption.from_dict(c) if isinstance(c, dict) else c
            for c in choices_raw
        ]
        nvl_raw = data.get("nvl_entries", [])
        nvl_entries = [
            NVLEntry.from_dict(e) if isinstance(e, dict) else e
            for e in nvl_raw
        ]
        speaker_color_raw = data.get("speaker_color")
        speaker_color = (
            Color.from_hex(speaker_color_raw)
            if isinstance(speaker_color_raw, str)
            else (speaker_color_raw if isinstance(speaker_color_raw, Color) else None)
        )
        return cls(
            speaker=data.get("speaker"),
            text=data.get("text", ""),
            emotion=data.get("emotion"),
            choices=choices,
            is_finished=bool(data.get("is_finished", False)),
            side_image=data.get("side_image"),
            nvl_mode=bool(data.get("nvl_mode", False)),
            nvl_entries=nvl_entries,
            visible_chars=data.get("visible_chars"),
            speaker_color=speaker_color,
        )

