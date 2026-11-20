"""User preferences (audio volumes, text speed, auto-forward time, window settings)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from eager.core.storage import atomic_write_json, safe_read_json

__all__ = [
    "Preferences",
]


@dataclass
class Preferences:
    """User configurable visual novel engine preferences."""

    text_speed: float = 50.0  # characters per second (0 = instant)
    auto_forward_time: float = 3.0  # seconds to wait before advancing in auto mode
    master_volume: float = 1.0  # 0.0 - 1.0
    music_volume: float = 0.8
    sfx_volume: float = 1.0
    voice_volume: float = 1.0
    ambient_volume: float = 0.8
    skip_unseen: bool = False
    autosave_enabled: bool = True
    fullscreen: bool = False

    @classmethod
    def load(cls, file_path: Path) -> Preferences:
        """Load preferences from disk, filling in missing or invalid fields with defaults."""
        data = safe_read_json(file_path, default={})
        if not isinstance(data, dict):
            return cls()
        defaults = cls()
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            val = data[f.name]
            default_val = getattr(defaults, f.name)
            if isinstance(default_val, bool):
                if isinstance(val, bool):
                    kwargs[f.name] = val
            elif (
                isinstance(default_val, float)
                and isinstance(val, (int, float))
                and not isinstance(val, bool)
                and math.isfinite(float(val))
            ):
                kwargs[f.name] = float(val)
        return cls(**kwargs)

    def save(self, file_path: Path) -> None:
        """Save preferences atomically to disk."""
        atomic_write_json(file_path, asdict(self))
