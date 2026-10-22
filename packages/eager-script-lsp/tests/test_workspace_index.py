"""Unit tests for multi-file workspace indexing and graph topology."""

from __future__ import annotations

import tempfile
from pathlib import Path

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
