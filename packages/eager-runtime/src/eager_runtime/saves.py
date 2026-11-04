"""Save file metadata, save slots, quicksaves, autosaves, and SaveManager."""

from __future__ import annotations

from eager_core.saves import (
    SaveData,
    SaveManager,
    SaveMetadata,
    SaveMigrationError,
)

__all__ = [
    "SaveData",
    "SaveManager",
    "SaveMetadata",
    "SaveMigrationError",
]
