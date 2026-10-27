"""Tests for ProjectConfig and multi-file scene graph merging validation."""

from __future__ import annotations

import logging
from pathlib import Path

import eager_script
import pytest

from eager_runtime.project import (
    ProjectConfig,
    load_project_graph,
    mask_script_includes,
    merge_graphs,
    resolve_project_scripts,
)


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


def test_merge_graphs_empty() -> None:
    merged = merge_graphs([])
    assert merged.entry is None
    assert len(merged.nodes) == 0


def test_merge_graphs_valid_connected() -> None:
    g1 = eager_script.parse_graph(
        """
## Act 1 --- act1
Narrator: Beginning.
> act2
"""
    )
    g2 = eager_script.parse_graph(
        """
## Act 2 --- act2
Narrator: Continuation.
"""
    )
    merged = merge_graphs([g1, g2], strict=True)
    assert merged.entry == "act1"
    assert "act1" in merged.nodes
    assert "act2" in merged.nodes
    assert len(merged.edges) == 1
    assert merged.edges[0].source == "act1"
    assert merged.edges[0].target == "act2"


def test_merge_graphs_duplicate_label_error() -> None:
    g1 = eager_script.parse_graph(
        """
## Intro --- scene_a
Narrator: In file 1.
"""
    )
    g2 = eager_script.parse_graph(
        """
## Intro Copy --- scene_a
Narrator: In file 2 with same label!
"""
    )
    with pytest.raises(ValueError, match="Duplicate scene label 'scene_a' across merged graphs"):
        merge_graphs([g1, g2])


def test_merge_graphs_broken_link_error() -> None:
    g1 = eager_script.parse_graph(
        """
## Scene 1 --- s1
Narrator: Going to unknown scene.
> nowhere
"""
    )
    g2 = eager_script.parse_graph(
        """
## Scene 2 --- s2
Narrator: Alone.
"""
    )
    with pytest.raises(ValueError, match="Invalid transition target 'nowhere' from scene 's1'"):
        merge_graphs([g1, g2])


def test_merge_graphs_reachability(caplog: pytest.LogCaptureFixture) -> None:
    g1 = eager_script.parse_graph(
        """
## Main --- main
Narrator: Story entry.
"""
    )
    g2 = eager_script.parse_graph(
        """
## Orphan --- orphan
Narrator: Never reached.
"""
    )
    # Non-strict mode logs a warning
    with caplog.at_level(logging.WARNING):
        merged = merge_graphs([g1, g2], strict=False)
        assert merged.entry == "main"
        assert "orphan" in merged.nodes
        assert any("Unreachable scenes detected from entry 'main': orphan" in r.message for r in caplog.records)

    # Strict mode raises ValueError
    with pytest.raises(ValueError, match="Unreachable scenes detected from entry 'main': orphan"):
        merge_graphs([g1, g2], strict=True)


def test_merge_graphs_missing_entry_error() -> None:
    g1 = eager_script.SceneGraph(
        entry="ghost_entry",
        nodes={},
        edges=(),
        preamble=(),
    )
    with pytest.raises(ValueError, match="Entry scene 'ghost_entry' does not exist in merged graphs"):
        merge_graphs([g1])


def test_merge_graphs_cyclic_references() -> None:
    g1 = eager_script.parse_graph("## Scene A --- a\n> b")
    g2 = eager_script.parse_graph("## Scene B --- b\n> c")
    g3 = eager_script.parse_graph("## Scene C --- c\n> a")

    merged = merge_graphs([g1, g2, g3], strict=True)
    assert merged.entry == "a"
    assert set(merged.nodes.keys()) == {"a", "b", "c"}
    assert len(merged.edges) == 3


def test_project_config_theme_and_overrides(tmp_path: Path) -> None:
    toml_path = tmp_path / "game.toml"
    toml_path.write_text(
        """
[game]
title = "Themed VN"
theme = "dark"

[theme]
accent_color = "#ffaa00"
bg_color = "#112233"
font_size = 18
""",
        encoding="utf-8",
    )
    cfg = ProjectConfig.load(toml_path)
    assert cfg.title == "Themed VN"
    assert cfg.theme == "dark"
    assert "accent_color" in cfg.theme_overrides
    assert cfg.theme_overrides["accent_color"].r == pytest.approx(1.0)
    assert cfg.theme_overrides["accent_color"].g == pytest.approx(170 / 255, abs=0.01)
    assert cfg.theme_overrides["accent_color"].b == pytest.approx(0.0)
    assert cfg.theme_overrides["font_size"] == 18


def test_mask_script_includes() -> None:
    text = '@include "chapter1.es"\n## Intro --- intro\n  @include "extra.es"\nNarrator: Hello'
    masked = mask_script_includes(text)
    lines = masked.splitlines()
    assert lines[0] == '# @include "chapter1.es"'
    assert lines[1] == "## Intro --- intro"
    assert lines[2] == '  # @include "extra.es"'
    assert lines[3] == "Narrator: Hello"


def test_load_project_graph_with_includes(tmp_path: Path) -> None:
    sub = tmp_path / "chapter1.es"
    sub.write_text(
        """
## Chapter 1 --- ch1
Narrator: This is chapter one.
""",
        encoding="utf-8",
    )

    main = tmp_path / "main.es"
    main.write_text(
        """
@include "chapter1.es"
## Prologue --- prologue
Narrator: Beginning.
> ch1
""",
        encoding="utf-8",
    )

    graph = load_project_graph(main, strict=True)
    assert graph.entry == "prologue"
    assert "prologue" in graph.nodes
    assert "ch1" in graph.nodes
    assert len(graph.edges) == 1
    assert graph.edges[0].source == "prologue"
    assert graph.edges[0].target == "ch1"


def test_resolve_project_scripts_include_traversal(tmp_path: Path) -> None:
    outside = tmp_path / "outside.es"
    outside.write_text("## Secret --- secret\nNarrator: secret.\n", encoding="utf-8")

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    main = proj_dir / "main.es"
    main.write_text('@include "../outside.es"\n## Main --- main\nNarrator: Hello.\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolve_project_scripts(main)


def test_resolve_project_scripts_deterministic_and_entry_script(tmp_path: Path) -> None:
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "game.toml").write_text('[game]\nentry_script = "ch1.es"\n', encoding="utf-8")
    (proj_dir / "ch2.es").write_text("## SceneB --- scene_b\nNarrator: B.\n", encoding="utf-8")
    (proj_dir / "ch1.es").write_text("## SceneA --- scene_a\nNarrator: A.\n", encoding="utf-8")
    (proj_dir / "ch3.es").write_text("## SceneC --- scene_c\nNarrator: C.\n", encoding="utf-8")

    scripts = resolve_project_scripts(proj_dir)
    # ch1.es must be first (configured entry_script), followed by ch2.es and ch3.es sorted
    assert [s.name for s in scripts] == ["ch1.es", "ch2.es", "ch3.es"]


def test_resolve_project_scripts_symlink_traversal(tmp_path: Path) -> None:
    outside = tmp_path / "outside.es"
    outside.write_text("## Secret --- secret\nNarrator: secret.\n", encoding="utf-8")

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    symlink = proj_dir / "symlink.es"
    try:
        symlink.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not supported in environment")

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolve_project_scripts(proj_dir)




