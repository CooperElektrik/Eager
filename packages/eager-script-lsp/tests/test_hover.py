"""Unit tests for rich hover information."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol.types import MarkupContent, Position

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.hover import compute_hover
from eager_script_lsp.workspace import WorkspaceIndex


def test_hover_scene():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """# This is the introductory scene
## Prologue --- prologue
Narrator: Welcome to the world.
Narrator: Let's begin.
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        hover = compute_hover(doc, index, Position(line=1, character=18))
        assert hover is not None
        assert isinstance(hover.contents, MarkupContent)
        assert "Prologue" in hover.contents.value
        assert "This is the introductory scene" in hover.contents.value
        assert "Welcome to the world" in hover.contents.value

        # Hover directly on display title 'Prologue' (col 5) instead of id 'prologue' (col 18)
        hover_title = compute_hover(doc, index, Position(line=1, character=5))
        assert hover_title is not None
        assert isinstance(hover_title.contents, MarkupContent)
        assert "Prologue" in hover_title.contents.value
        assert "prologue" in hover_title.contents.value


def test_hover_character():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """@character hoshiko "Hoshiko" color=#ff77aa
## Scene 1 --- s1
Hoshiko: Hi there!
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        hover = compute_hover(doc, index, Position(line=2, character=2))
        assert hover is not None
        assert isinstance(hover.contents, MarkupContent)
        assert "Hoshiko" in hover.contents.value
        assert "#ff77aa" in hover.contents.value


def test_hover_outside_document_bounds():
    """Verify hover outside document bounds returns None safely."""
    doc = ScriptDocument("file:///test.es", "## Scene 1 --- s1\nNarrator: Hello\n")
    index = WorkspaceIndex(Path("."))
    assert compute_hover(doc, index, Position(line=9999, character=0)) is None
    assert compute_hover(doc, index, Position(line=0, character=9999)) is None


def test_hover_whitespace_and_punctuation():
    """Verify hovering on colons, separators, and spaces returns None."""
    doc = ScriptDocument("file:///test.es", "## Scene 1 --- s1\nNarrator: Hello\n")
    index = WorkspaceIndex(Path("."))
    # Colon at col 8
    assert compute_hover(doc, index, Position(line=1, character=8)) is None
    # Separator '---' at col 12
    assert compute_hover(doc, index, Position(line=0, character=12)) is None


def test_hover_engine_hooks_and_variables():
    """Verify hover displays rich markdown docs for engine hooks and variable statistics."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """@character hoshiko "Hoshiko" color=#ff77aa
@default score = 100
## Scene 1 --- s1
~ bg school_day
~ shake intensity=1.5
~ show hoshiko smile
$ score += 10
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Hover on '~ bg' (line 3, col 3)
        h_bg = compute_hover(doc, index, Position(line=3, character=3))
        assert h_bg is not None
        assert isinstance(h_bg.contents, MarkupContent)
        assert "Engine Hook: `~ bg`" in h_bg.contents.value

        # Hover on '~ shake' (line 4, col 3)
        h_shake = compute_hover(doc, index, Position(line=4, character=3))
        assert h_shake is not None
        assert isinstance(h_shake.contents, MarkupContent)
        assert "Camera shake effect" in h_shake.contents.value

        # Hover on character in hook '~ show hoshiko' (line 5, col 8)
        h_char = compute_hover(doc, index, Position(line=5, character=8))
        assert h_char is not None
        assert isinstance(h_char.contents, MarkupContent)
        assert "Character: `Hoshiko`" in h_char.contents.value

        # Hover on '$ score' (line 6, col 3)
        h_var = compute_hover(doc, index, Position(line=6, character=3))
        assert h_var is not None
        assert isinstance(h_var.contents, MarkupContent)
        assert "Variable: `$score`" in h_var.contents.value
        assert "**Initial default:** `100`" in h_var.contents.value


def test_hover_builtin_functions():
    """Verify hover displays markdown documentation for built-in expression functions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Scene 1 --- s1
@if visited("s1") and chance(0.5)
Narrator: Hello
@end
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Hover on 'visited' (line 1, col 6)
        h_vis = compute_hover(doc, index, Position(line=1, character=6))
        assert h_vis is not None
        assert isinstance(h_vis.contents, MarkupContent)
        assert "visited" in h_vis.contents.value

        # Hover on 'chance' (line 1, col 24)
        h_chance = compute_hover(doc, index, Position(line=1, character=24))
        assert h_chance is not None
        assert isinstance(h_chance.contents, MarkupContent)
        assert "chance" in h_chance.contents.value


def test_hover_disk_asset_resolution():
    """Verify asset hover shows disk path and file size when asset exists on disk."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "assets" / "bg").mkdir(parents=True)
        (root / "assets" / "bg" / "courtyard.png").write_bytes(b"PNG_DATA_SAMPLE")

        index = WorkspaceIndex(root)
        index.initialize()

        doc = ScriptDocument("file:///test.es", "## S1 --- s1\n~ bg courtyard\n~ bg missing_bg\n")
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Hover on existing bg
        h_exist = compute_hover(doc, index, Position(line=1, character=6))
        assert h_exist is not None
        assert isinstance(h_exist.contents, MarkupContent)
        assert "Asset: `courtyard`" in h_exist.contents.value
        assert "courtyard.png" in h_exist.contents.value

        # Hover on missing bg returns None
        h_missing = compute_hover(doc, index, Position(line=2, character=6))
        assert h_missing is None
