"""Save file metadata, save slots, quicksaves, autosaves, and SaveManager."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager_runtime.session import Checkpoint
from eager_runtime.storage import atomic_write_json, safe_read_json


@dataclass(frozen=True, slots=True)
class SaveMetadata:
    """Metadata displayed on save/load slot buttons and inspect views."""

    slot_name: str
    timestamp: str  # ISO-8601 string
    scene_id: str | None
    scene_name: str | None
    dialogue_snippet: str | None
    playtime_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_name": self.slot_name,
            "timestamp": self.timestamp,
            "scene_id": self.scene_id,
            "scene_name": self.scene_name,
            "dialogue_snippet": self.dialogue_snippet,
            "playtime_seconds": self.playtime_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaveMetadata:
        return cls(
            slot_name=data.get("slot_name", ""),
            timestamp=data.get("timestamp", ""),
            scene_id=data.get("scene_id"),
            scene_name=data.get("scene_name"),
            dialogue_snippet=data.get("dialogue_snippet"),
            playtime_seconds=float(data.get("playtime_seconds", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class SaveData:
    """Complete save file container wrapping metadata and checkpoint."""

    metadata: SaveMetadata
    checkpoint: Checkpoint

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": self.metadata.to_dict(),
            "checkpoint": {
                "story": self.checkpoint.story,
                "visual": self.checkpoint.visual,
                "audio": self.checkpoint.audio,
                "backlog_len": self.checkpoint.backlog_len,
                "ui": self.checkpoint.ui,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaveData:
        from eager_runtime.session import Checkpoint

        meta = SaveMetadata.from_dict(data.get("metadata", {}))
        cp_data = data.get("checkpoint", {})
        cp = Checkpoint(
            story=cp_data.get("story", {}),
            visual=cp_data.get("visual", {}),
            audio=cp_data.get("audio", {}),
            backlog_len=int(cp_data.get("backlog_len", 0)),
            ui=cp_data.get("ui", {}),
        )
        return cls(metadata=meta, checkpoint=cp)


class SaveManager:
    """Manages reading, writing, listing, and organizing game save files."""

    def __init__(self, save_dir: Path, max_autosaves: int = 5, max_quicksaves: int = 5) -> None:
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.max_autosaves = max_autosaves
        self.max_quicksaves = max_quicksaves

    def _slot_path(self, slot_name: str) -> Path:
        """Get file path for given slot name."""
        # Sanitize slot name
        safe_name = "".join(c for c in slot_name if c.isalnum() or c in ("-", "_"))
        if not safe_name:
            safe_name = "slot"
        return self.save_dir / f"{safe_name}.json"

    def save_slot(self, slot_name: str, checkpoint: Checkpoint, metadata_extra: dict[str, Any] | None = None) -> SaveMetadata:
        """Save a checkpoint to a named slot."""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        
        # Extract scene_id, dialogue_snippet from checkpoint
        story_state = checkpoint.story
        ui_state = checkpoint.ui
        scene_id = story_state.get("current_scene")
        dialogue_snippet = ui_state.get("text")
        
        extra = metadata_extra or {}
        meta = SaveMetadata(
            slot_name=slot_name,
            timestamp=now,
            scene_id=scene_id,
            scene_name=extra.get("scene_name", scene_id),
            dialogue_snippet=dialogue_snippet[:100] if dialogue_snippet else None,
            playtime_seconds=float(extra.get("playtime_seconds", 0.0)),
        )

        save_obj = SaveData(metadata=meta, checkpoint=checkpoint)
        path = self._slot_path(slot_name)
        atomic_write_json(path, save_obj.to_dict())
        return meta

    def load_slot(self, slot_name: str) -> Checkpoint | None:
        """Load checkpoint from a named slot."""
        path = self._slot_path(slot_name)
        data = safe_read_json(path)
        if not data or "checkpoint" not in data:
            return None
        save_obj = SaveData.from_dict(data)
        return save_obj.checkpoint

    def get_slot_metadata(self, slot_name: str) -> SaveMetadata | None:
        """Inspect metadata for a slot without parsing full checkpoint."""
        path = self._slot_path(slot_name)
        data = safe_read_json(path)
        if not data or "metadata" not in data:
            return None
        return SaveMetadata.from_dict(data["metadata"])

    def delete_slot(self, slot_name: str) -> bool:
        """Delete save slot file."""
        path = self._slot_path(slot_name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_slots(self) -> list[SaveMetadata]:
        """List metadata for all existing save files, sorted newest to oldest."""
        slots: list[SaveMetadata] = []
        for p in self.save_dir.glob("*.json"):
            if p.name in ("persistent.json", "preferences.json"):
                continue
            meta = self.get_slot_metadata(p.stem)
            if meta is not None:
                slots.append(meta)
        slots.sort(key=lambda s: s.timestamp, reverse=True)
        return slots

    def _slot_sort_key(self, slot_name: str) -> tuple[str, int]:
        """Return (iso_timestamp, mtime_ns) for sorting slots by age."""
        path = self._slot_path(slot_name)
        if not path.exists():
            return ("", 0)
        meta = self.get_slot_metadata(slot_name)
        ts = meta.timestamp if meta and meta.timestamp else ""
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            mtime = 0
        return (ts, mtime)

    def _next_rotated_slot(self, prefix: str, max_count: int) -> str:
        """Find next available slot in circular buffer or the oldest to overwrite."""
        count = max(1, max_count)
        slots = [f"{prefix}_{i}" for i in range(1, count + 1)]

        # If any slot is missing, fill in slots in sequential order
        for slot in slots:
            if not self._slot_path(slot).exists():
                return slot

        # All slots exist: overwrite the oldest slot
        return min(slots, key=self._slot_sort_key)

    def _latest_rotated_slot(self, prefix: str, max_count: int) -> str | None:
        """Find the most recent slot in circular buffer, or legacy unindexed slot."""
        count = max(1, max_count)
        slots = [f"{prefix}_{i}" for i in range(1, count + 1)]
        existing = [s for s in slots if self._slot_path(s).exists()]
        if self._slot_path(prefix).exists():
            existing.append(prefix)
        if existing:
            return max(existing, key=self._slot_sort_key)
        return None

    def quicksave(self, checkpoint: Checkpoint, **extra: Any) -> SaveMetadata:
        """Save to circular quicksave slot."""
        slot = self._next_rotated_slot("quick", self.max_quicksaves)
        return self.save_slot(slot, checkpoint, extra)

    def quickload(self) -> Checkpoint | None:
        """Load from most recent quicksave slot."""
        slot = self._latest_rotated_slot("quick", self.max_quicksaves)
        if slot is None:
            return None
        return self.load_slot(slot)

    def autosave(self, checkpoint: Checkpoint, **extra: Any) -> SaveMetadata:
        """Save to circular autosave slot."""
        slot = self._next_rotated_slot("auto", self.max_autosaves)
        return self.save_slot(slot, checkpoint, extra)

    def autoload(self) -> Checkpoint | None:
        """Load from most recent autosave slot."""
        slot = self._latest_rotated_slot("auto", self.max_autosaves)
        if slot is None:
            return None
        return self.load_slot(slot)

