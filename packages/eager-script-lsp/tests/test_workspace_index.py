"""Unit tests for multi-file workspace indexing and graph topology."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from eager_script_lsp.workspace import WorkspaceIndex


def test_workspace_index_multi_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "assets" / "bg").mkdir(parents=True)
        (root / "assets" / "bg" / "classroom_day.png").write_bytes(b"PNG")
        (root / "assets" / "characters" / "hoshiko").mkdir(parents=True)
        (root / "assets" / "characters" / "hoshiko" / "smile.png").write_bytes(b"PNG")

        file1 = root / "ch1.es"
        file1.write_text("""# The opening chapter
## Chapter 1 --- ch1
@character hoshiko "Hoshiko" color=#ff77aa
@default score = 10
Narrator: Welcome!
~ bg classroom_day
~ show hoshiko smile
Hoshiko: Let's move to chapter 2!
$ score += 5
> ch2
""", encoding="utf-8")

        file2 = root / "ch2.es"
        file2.write_text("""## Chapter 2 --- ch2
Hoshiko: Here we are in chapter 2!
Narrator: Score is [score].
? Go back (ch1)
""", encoding="utf-8")

        index = WorkspaceIndex(root)
        index.initialize()

        assert "ch1" in index.labels
        assert "ch2" in index.labels
        assert index.labels["ch1"].docstring == "The opening chapter"
        assert "hoshiko" in index.characters
        assert index.characters["hoshiko"].attrs.get("color") == "#ff77aa"
        assert "score" in index.variables
        assert index.variables["score"].default_val == "10"
        assert len(index.variables["score"].mutations) >= 1

        # Check references & topology
        assert "ch2" in index.labels["ch1"].successors
        assert "ch1" in index.labels["ch2"].predecessors

        # Check asset indexing
        assert "classroom_day" in index.asset_index.backgrounds
        assert "smile" in index.asset_index.characters.get("hoshiko", set())


def test_workspace_index_entry_script_priority_and_sorting(tmp_path: Path):
    (tmp_path / "game.toml").write_text('[game]\nentry_script = "act1.es"\n', encoding="utf-8")
    (tmp_path / "act2.es").write_text("## Act2 --- act2\nNarrator: Act 2\n", encoding="utf-8")
    (tmp_path / "act1.es").write_text("## Act1 --- act1\nNarrator: Act 1\n", encoding="utf-8")
    (tmp_path / "act0.es").write_text("## Act0 --- act0\nNarrator: Act 0\n", encoding="utf-8")

    index = WorkspaceIndex(tmp_path)
    index.initialize()

    docs = list(index.documents.keys())
    # act1.es should be indexed first because entry_script is act1.es
    assert docs[0].endswith("act1.es")
    # act1 should be entry of merged graph
    assert index.merged_graph is not None
    assert index.merged_graph.entry == "act1"


def test_workspace_index_ignores_external_symlinks(tmp_path: Path):
    outside = tmp_path / "outside.es"
    outside.write_text("## Outside --- outside\nNarrator: Outside\n", encoding="utf-8")

    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir()
    (ws_dir / "main.es").write_text("## Main --- main\nNarrator: Main\n", encoding="utf-8")
    symlink = ws_dir / "external.es"
    try:
        symlink.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not supported")

    index = WorkspaceIndex(ws_dir)
    index.initialize()

    doc_paths = list(index.documents.keys())
    assert any(p.endswith("main.es") for p in doc_paths)
    assert not any("outside" in p or "external" in p for p in doc_paths)

