"""Tests for ProjectConfig."""

from __future__ import annotations

from pathlib import Path

from eager.script.project import ProjectConfig


def test_project_config_defaults(tmp_path: Path) -> None:
    non_existent = tmp_path / "game.toml"
    cfg = ProjectConfig.load(non_existent)
    assert cfg.title == "Untitled Project"
    assert cfg.virtual_width == 1920
    assert cfg.virtual_height == 1080


def test_project_config_load(tmp_path: Path) -> None:
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        """
[game]
title = "My Epic VN"
version = "1.2.3"
author = "Dev"
entry_script = "act1.es"

[window]
width = 1280
height = 720
""",
        encoding="utf-8",
    )
    cfg = ProjectConfig.load(toml_path)
    assert cfg.title == "My Epic VN"
    assert cfg.version == "1.2.3"
    assert cfg.author == "Dev"
    assert cfg.entry_script == "act1.es"
    assert cfg.virtual_width == 1280
    assert cfg.virtual_height == 720
