"""Project configuration parser for game.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

__all__ = [
    "ProjectConfig",
]


@dataclass
class ProjectConfig:
    """Settings defined in game.toml."""

    title: str = "Untitled Project"
    version: str = "0.1.0"
    author: str = "Anonymous"
    entry_script: str = "main.es"
    virtual_width: int = 1920
    virtual_height: int = 1080
    scene_backgrounds: dict[str, tuple[str, str, float]] = field(default_factory=dict)
    scale_mode: str = "letterbox"

    @classmethod
    def load(cls, toml_path: Path) -> ProjectConfig:
        """Load and parse game.toml configuration file."""
        if not toml_path.exists():
            return cls()
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        game_data = data.get("game", {})
        window_data = data.get("window", {})
        pres_section = data.get("presentation", {}) or data.get("stage", {})

        scene_bgs: dict[str, tuple[str, str, float]] = {}
        scenes_sec = data.get("scenes", {})
        if isinstance(scenes_sec, dict):
            for sc_id, s_data in scenes_sec.items():
                if isinstance(s_data, dict) and "background" in s_data:
                    bg_asset = str(s_data["background"])
                    trans = str(s_data.get("transition", "crossfade"))
                    dur = float(s_data.get("duration", 0.5))
                    scene_bgs[str(sc_id)] = (bg_asset, trans, dur)
                elif isinstance(s_data, str):
                    scene_bgs[str(sc_id)] = (s_data, "crossfade", 0.5)

        return cls(
            title=game_data.get("title", "Untitled Project"),
            version=game_data.get("version", "0.1.0"),
            author=game_data.get("author", "Anonymous"),
            entry_script=game_data.get("entry_script", "main.es"),
            virtual_width=int(window_data.get("width", 1920)),
            virtual_height=int(window_data.get("height", 1080)),
            scene_backgrounds=scene_bgs,
            scale_mode=str(window_data.get("scale_mode") or pres_section.get("scale_mode", "letterbox")),
        )
