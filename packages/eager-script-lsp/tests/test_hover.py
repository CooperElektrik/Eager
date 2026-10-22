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
