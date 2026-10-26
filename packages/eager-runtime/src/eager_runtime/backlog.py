"""Dialogue backlog / history log tracking speaker, text, and voice audio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "Backlog",
    "BacklogEntry",
]


@dataclass(frozen=True, slots=True)
class BacklogEntry:
    """An individual entry recorded in the dialogue backlog."""

    speaker: str | None
    text: str
    voice: str | None = None
    emotion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "voice": self.voice,
            "emotion": self.emotion,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BacklogEntry:
        return cls(
            speaker=data.get("speaker"),
            text=data.get("text", ""),
            voice=data.get("voice"),
            emotion=data.get("emotion"),
        )


class Backlog:
    """Bounded chronological collection of dialogue and narration lines."""

    def __init__(self, max_entries: int = 200) -> None:
        self.max_entries = max_entries
        self.entries: list[BacklogEntry] = []

    def add(
        self,
        speaker: str | None,
        text: str,
        voice: str | None = None,
        emotion: str | None = None,
    ) -> None:
        """Add a line to the backlog."""
        clean_text = text.strip()
        if not clean_text:
            return
        entry = BacklogEntry(speaker=speaker, text=clean_text, voice=voice, emotion=emotion)
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries.pop(0)

    def append_to_last(self, text: str) -> None:
        """Append continuation text to the most recent backlog entry."""
        if not self.entries:
            self.add(None, text)
            return
        last = self.entries[-1]
        combined = f"{last.text} {text.strip()}".strip()
        self.entries[-1] = BacklogEntry(
            speaker=last.speaker,
            text=combined,
            voice=last.voice,
            emotion=last.emotion,
        )

    def clear(self) -> None:
        """Clear all backlog entries."""
        self.entries.clear()

    def __len__(self) -> int:
        return len(self.entries)

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.entries]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]], max_entries: int = 200) -> Backlog:
        b = cls(max_entries=max_entries)
        b.entries = [BacklogEntry.from_dict(d) for d in data]
        return b
