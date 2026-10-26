"""Save file metadata, save slots, quicksaves, autosaves, and SaveManager."""

from __future__ import annotations

import copy
import datetime
import inspect
import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from eager_core.storage import atomic_write_json, safe_read_json

from eager_runtime.runtime import StoryRuntimeError

if TYPE_CHECKING:
    from eager_runtime.state import Checkpoint

__all__ = [
    "MigrationHook",
    "SaveData",
    "SaveManager",
    "SaveMetadata",
    "SaveMigrationError",
]

logger = logging.getLogger(__name__)


class SaveMigrationError(StoryRuntimeError):
    """Raised when save data cannot be migrated to the target schema version."""


MigrationHook = (
    Callable[[dict[str, Any], int, int], dict[str, Any]]
    | Callable[[dict[str, Any], int], dict[str, Any]]
    | Callable[[dict[str, Any]], dict[str, Any]]
)


def _backup_corrupt_slot(path: Path) -> None:
    """Safely copy a corrupted save file to <path>.corrupt.bak."""
    try:
        if path.is_file():
            bak_path = path.with_name(path.name + ".corrupt.bak")
            shutil.copy2(path, bak_path)
    except OSError:
        pass


def _invoke_migration_hook(
    hook: MigrationHook,
    data: dict[str, Any],
    source_version: int,
    target_version: int,
) -> dict[str, Any]:
    """Invoke migration hook supporting 1, 2, or 3 arguments."""
    try:
        sig = inspect.signature(hook)
        params = [
            p
            for p in sig.parameters.values()
            if p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        param_count = len(params)
    except (ValueError, TypeError):
        param_count = 3

    if param_count == 1:
        res = hook(data)  # type: ignore[call-arg]
    elif param_count == 2:
        res = hook(data, source_version)  # type: ignore[call-arg]
    else:
        res = hook(data, source_version, target_version)  # type: ignore[call-arg]

    if not isinstance(res, dict):
        msg = f"Migration hook must return a dict, got {type(res).__name__}"
        raise SaveMigrationError(msg)
    return res


@dataclass(frozen=True, slots=True)
class SaveMetadata:
    """Metadata displayed on save/load slot buttons and inspect views."""

    CURRENT_VERSION: ClassVar[int] = 2

    slot_name: str
    timestamp: str  # ISO-8601 string
    scene_id: str | None
    scene_name: str | None
    dialogue_snippet: str | None
    playtime_seconds: float = 0.0
    thumbnail_path: str | None = None
    version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "slot_name": self.slot_name,
            "timestamp": self.timestamp,
            "scene_id": self.scene_id,
            "scene_name": self.scene_name,
            "dialogue_snippet": self.dialogue_snippet,
            "playtime_seconds": self.playtime_seconds,
            "thumbnail_path": self.thumbnail_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaveMetadata:
        if not isinstance(data, dict):
            raise TypeError(f"SaveMetadata data must be a dict, got {type(data).__name__}")

        playtime_raw = data.get("playtime_seconds", 0.0)
        playtime_seconds = float(0.0 if playtime_raw is None else playtime_raw)

        version_raw = data.get("version", 1)
        version = int(1 if version_raw is None else version_raw)

        slot_name = data.get("slot_name", "")
        if not isinstance(slot_name, str):
            slot_name = str(slot_name) if slot_name is not None else ""

        timestamp = data.get("timestamp", "")
        if not isinstance(timestamp, str):
            timestamp = str(timestamp) if timestamp is not None else ""

        scene_id = data.get("scene_id")
        scene_name = data.get("scene_name")
        dialogue_snippet = data.get("dialogue_snippet")
        thumbnail_path = data.get("thumbnail_path")

        return cls(
            slot_name=slot_name,
            timestamp=timestamp,
            scene_id=scene_id if isinstance(scene_id, str) or scene_id is None else str(scene_id),
            scene_name=scene_name if isinstance(scene_name, str) or scene_name is None else str(scene_name),
            dialogue_snippet=dialogue_snippet if isinstance(dialogue_snippet, str) or dialogue_snippet is None else str(dialogue_snippet),
            playtime_seconds=playtime_seconds,
            thumbnail_path=thumbnail_path if isinstance(thumbnail_path, str) or thumbnail_path is None else str(thumbnail_path),
            version=version,
        )

    @property
    def playtime_formatted(self) -> str:
        """Format playtime in seconds to HH:MM:SS (or MM:SS if under an hour)."""
        total = int(self.playtime_seconds)
        hours = total // 3600
        mins = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"


@dataclass(frozen=True, slots=True)
class SaveData:
    """Complete save file container wrapping metadata and checkpoint."""

    CURRENT_VERSION: ClassVar[int] = 1

    metadata: SaveMetadata
    checkpoint: Checkpoint
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "metadata": self.metadata.to_dict(),
            "checkpoint": {
                "story": self.checkpoint.story,
                "visual": self.checkpoint.visual,
                "audio": self.checkpoint.audio,
                "backlog_len": self.checkpoint.backlog_len,
                "ui": self.checkpoint.ui,
                "active_input_prompt": self.checkpoint.active_input_prompt,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SaveData:
        from eager_runtime.state import Checkpoint

        if not isinstance(data, dict):
            raise TypeError(f"SaveData data must be a dict, got {type(data).__name__}")

        version_raw = data.get("version", 1)
        version = int(1 if version_raw is None else version_raw)

        meta_raw = data.get("metadata", {})
        if not isinstance(meta_raw, dict):
            raise TypeError(f"SaveData 'metadata' must be a dict, got {type(meta_raw).__name__}")
        meta = SaveMetadata.from_dict(meta_raw)

        cp_raw = data.get("checkpoint")
        if not isinstance(cp_raw, dict):
            raise TypeError(f"SaveData 'checkpoint' must be a dict, got {type(cp_raw).__name__}")

        backlog_raw = cp_raw.get("backlog_len", 0)
        backlog_len = int(0 if backlog_raw is None else backlog_raw)

        story = cp_raw.get("story")
        visual = cp_raw.get("visual")
        audio = cp_raw.get("audio")
        ui = cp_raw.get("ui")

        cp = Checkpoint(
            story=story if isinstance(story, dict) else {},
            visual=visual if isinstance(visual, dict) else {},
            audio=audio if isinstance(audio, dict) else {},
            backlog_len=backlog_len,
            ui=ui if isinstance(ui, dict) else {},
            active_input_prompt=cp_raw.get("active_input_prompt")
            if isinstance(cp_raw.get("active_input_prompt"), dict)
            else None,
        )
        return cls(metadata=meta, checkpoint=cp, version=version)


def _migrate_save_data_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate save data from schema v1 to v2.

    Adds ``thumbnail_path`` (``None``) to metadata and bumps both the top-level
    and metadata version fields to 2.
    """
    data = copy.deepcopy(data)
    data["version"] = 2
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        metadata.setdefault("thumbnail_path", None)
        metadata["version"] = 2
    return data


class SaveManager:
    """Manages reading, writing, listing, and organizing game save files."""

    _class_migrations: ClassVar[dict[int, Callable[[dict[str, Any]], dict[str, Any]]]] = {
        1: _migrate_save_data_v1_to_v2,
    }

    def __init__(
        self,
        save_dir: Path,
        max_autosaves: int = 5,
        max_quicksaves: int = 5,
        *,
        target_version: int = SaveData.CURRENT_VERSION,
        migration_hook: MigrationHook | None = None,
    ) -> None:
        self.save_dir = save_dir
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.max_autosaves = max_autosaves
        self.max_quicksaves = max_quicksaves
        self.target_version = target_version
        self.migration_hook = migration_hook
        self._migrations: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = dict(
            self._class_migrations
        )

    @classmethod
    def register_schema_migration(
        cls,
        from_version: int,
        migration_fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register a global schema migration function for a specific version."""
        cls._class_migrations[from_version] = migration_fn

    @classmethod
    def clear_schema_migrations(cls) -> None:
        """Clear all globally registered schema migrations."""
        cls._class_migrations.clear()

    def register_migration(
        self,
        from_version: int,
        migration_fn: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> None:
        """Register a schema migration function on this manager instance."""
        self._migrations[from_version] = migration_fn

    def clear_migrations(self) -> None:
        """Clear migrations registered on this manager instance."""
        self._migrations.clear()

    def upgrade_save_data(
        self,
        data: dict[str, Any],
        *,
        target_version: int | None = None,
        migration_hook: MigrationHook | None = None,
    ) -> dict[str, Any]:
        """Upgrade save data dictionary to target schema version using registered migrations or hook."""
        target = self.target_version if target_version is None else target_version
        hook = migration_hook if migration_hook is not None else self.migration_hook

        data = copy.deepcopy(data)
        current_v = int(data.get("version", 0))

        if current_v > target:
            msg = f"Save file version {current_v} is newer than target version {target}."
            raise SaveMigrationError(msg)

        if current_v == target:
            return data

        while current_v < target:
            if current_v in self._migrations:
                data = self._migrations[current_v](data)
                next_v = int(data.get("version", current_v + 1))
                if next_v <= current_v:
                    data["version"] = current_v + 1
                    next_v = current_v + 1
                current_v = next_v
            elif hook is not None:
                data = _invoke_migration_hook(hook, data, current_v, target)
                data.setdefault("version", target)
                current_v = int(data["version"])
                break
            elif current_v == 0:
                # Built-in migration from legacy unversioned (v0) to v1
                data["version"] = 1
                if "checkpoint" in data and isinstance(data["checkpoint"], dict):
                    cp = data["checkpoint"]
                    if "story" in cp and isinstance(cp["story"], dict):
                        cp["story"].setdefault("version", 1)
                current_v = 1
            else:
                msg = f"No migration registered to upgrade save data from version {current_v} to {target}."
                raise SaveMigrationError(msg)

        return data

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
            thumbnail_path=extra.get("thumbnail_path"),
            version=self.target_version,
        )

        save_obj = SaveData(metadata=meta, checkpoint=checkpoint, version=self.target_version)
        path = self._slot_path(slot_name)
        atomic_write_json(path, save_obj.to_dict())
        return meta

    def load_slot(
        self,
        slot_name: str,
        *,
        target_version: int | None = None,
        migration_hook: MigrationHook | None = None,
    ) -> Checkpoint | None:
        """Load checkpoint from a named slot, migrating schema if necessary."""
        path = self._slot_path(slot_name)
        if not path.is_file():
            return None

        data = safe_read_json(path, backup_corrupt=True)
        if not isinstance(data, dict) or "checkpoint" not in data or not isinstance(data["checkpoint"], dict):
            _backup_corrupt_slot(path)
            return None

        try:
            migrated_data = self.upgrade_save_data(
                data,
                target_version=target_version,
                migration_hook=migration_hook,
            )
            save_obj = SaveData.from_dict(migrated_data)
            return save_obj.checkpoint
        except (TypeError, ValueError, AttributeError, KeyError) as err:
            logger.warning("Corrupted save slot %s (%s); backing up and returning None", path, err)
            _backup_corrupt_slot(path)
            return None

    def get_slot_metadata(self, slot_name: str) -> SaveMetadata | None:
        """Inspect metadata for a slot without parsing full checkpoint."""
        path = self._slot_path(slot_name)
        data = safe_read_json(path)
        if not isinstance(data, dict) or "metadata" not in data:
            return None
        meta_data = data["metadata"]
        if not isinstance(meta_data, dict):
            return None
        try:
            return SaveMetadata.from_dict(meta_data)
        except (TypeError, ValueError, AttributeError, KeyError):
            return None

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

    def quicksave(
        self,
        checkpoint: Checkpoint,
        *,
        prefix: str = "quick",
        max_slots: int | None = None,
        **extra: Any,
    ) -> SaveMetadata:
        """Save to circular quicksave slot (or custom prefix)."""
        limit = self.max_quicksaves if max_slots is None else max_slots
        slot = self._next_rotated_slot(prefix, limit)
        return self.save_slot(slot, checkpoint, extra)

    def quickload(
        self,
        *,
        prefix: str = "quick",
        max_slots: int | None = None,
        target_version: int | None = None,
        migration_hook: MigrationHook | None = None,
    ) -> Checkpoint | None:
        """Load from most recent quicksave slot (or custom prefix)."""
        limit = self.max_quicksaves if max_slots is None else max_slots
        slot = self._latest_rotated_slot(prefix, limit)
        if slot is None:
            return None
        return self.load_slot(
            slot,
            target_version=target_version,
            migration_hook=migration_hook,
        )

    def autosave(self, checkpoint: Checkpoint, **extra: Any) -> SaveMetadata:
        """Save to circular autosave slot."""
        return self.quicksave(checkpoint, prefix="auto", max_slots=self.max_autosaves, **extra)

    def autoload(
        self,
        *,
        target_version: int | None = None,
        migration_hook: MigrationHook | None = None,
    ) -> Checkpoint | None:
        """Load from most recent autosave slot."""
        return self.quickload(
            prefix="auto",
            max_slots=self.max_autosaves,
            target_version=target_version,
            migration_hook=migration_hook,
        )

