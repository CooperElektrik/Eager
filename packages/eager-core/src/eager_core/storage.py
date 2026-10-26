"""Filesystem storage helpers for Eager saves, persistent data, and preferences."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import cast

from eager_core.exceptions import StorageError

__all__ = [
    "atomic_write_json",
    "get_default_save_dir",
    "safe_read_json",
]

logger = logging.getLogger(__name__)


def get_default_save_dir(game_name: str = "default") -> Path:
    """Return platform-standard save data directory."""
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        base = Path(xdg_data)
    else:
        base = Path.home() / ".local" / "share"
    save_dir = base / "eager" / game_name
    save_dir.mkdir(parents=True, exist_ok=True)
    return save_dir


def atomic_write_json(file_path: Path, data: object) -> None:
    """Write JSON data atomically using a temporary file in the same directory."""
    temp_path: Path | None = None
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            text = json.dumps(data, indent=2)
        except (TypeError, ValueError) as err:
            raise StorageError(f"Failed to serialize data to JSON for {file_path}: {err}") from err
        _ = temp_path.write_text(text, encoding="utf-8")
        _ = temp_path.replace(file_path)
        logger.debug("Atomically wrote JSON to %s", file_path)
    except OSError as err:
        if not isinstance(err, StorageError):
            raise StorageError(f"I/O error writing JSON to {file_path}: {err}") from err
        raise
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def safe_read_json(file_path: Path, default: object = None, *, backup_corrupt: bool = False) -> object:
    """Read JSON file safely, returning default if missing or corrupted."""
    if not file_path.exists():
        logger.debug("JSON file not found: %s (returning default)", file_path)
        return default
    try:
        text = file_path.read_text(encoding="utf-8")
        return cast(object, json.loads(text))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        logger.warning("Failed to read JSON file %s (returning default)", file_path, exc_info=True)
        if backup_corrupt:
            try:
                import shutil
                bak_path = file_path.with_name(file_path.name + ".corrupt.bak")
                _ = shutil.copy2(file_path, bak_path)
            except OSError:
                pass
        return default
