"""User preferences (audio volumes, text speed, auto-forward time, window settings)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from eager_core.storage import atomic_write_json, safe_read_json


@dataclass
class Preferences:
    """User configurable visual novel engine preferences."""

    text_speed: float = 50.0  # characters per second (0 = instant)
    auto_forward_time: float = 3.0  # seconds to wait before advancing in auto mode
    master_volume: float = 1.0  # 0.0 - 1.0
    music_volume: float = 0.8
    sfx_volume: float = 1.0
    voice_volume: float = 1.0
    skip_unseen: bool = False
    fullscreen: bool = False
    resolution_scale: float = 1.0
    language: str = "default"

    @classmethod
    def load(cls, file_path: Path) -> Preferences:
        """Load preferences from disk, filling in missing defaults."""
        data = safe_read_json(file_path, default={})
        if not isinstance(data, dict):
            return cls()
        # Filter keys matching fields
        kwargs = {k: v for k, v in data.items() if hasattr(cls, k)}
        return cls(**kwargs)

    def save(self, file_path: Path) -> None:
        """Save preferences atomically to disk."""
        atomic_write_json(file_path, asdict(self))
