"""Unit tests for code lenses and inlay hints."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol.types import Position, Range

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.lenses import (
    compute_code_lenses,
    compute_inlay_hints,
)
from eager_script_lsp.workspace import WorkspaceIndex


def test_code_lenses_and_inlay_hints():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Mountain Shrine
Narrator: Birds chirp.
> start

## Start --- start
Narrator: Here
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Code Lenses
        lenses = compute_code_lenses(doc, index)
        assert len(lenses) >= 2
        titles = [lens.command.title for lens in lenses if lens.command]
        assert any("incoming" in t for t in titles)
        assert any("Play from here" in t for t in titles)

        # Inlay Hints for implicit slug on '## Mountain Shrine'
        hints = compute_inlay_hints(
            doc,
            index,
            Range(start=Position(line=0, character=0), end=Position(line=5, character=0)),
        )
        assert len(hints) >= 1
        assert any("mountain_shrine" in h.label for h in hints)

        # Inlay Hints with range outside line 0 (lines 2-4) should not include line 0's hint
        hints_filtered = compute_inlay_hints(
            doc,
            index,
            Range(start=Position(line=2, character=0), end=Position(line=4, character=0)),
        )
        assert not any("mountain_shrine" in h.label for h in hints_filtered)

        # Inlay Hints for character display names
        text_char = """@character a "Alice"
## Start --- start
a: Hello world!
Alice: Already display name!
"""
        doc_char = ScriptDocument("file:///char.es", text_char)
        index.documents["file:///char.es"] = doc_char
        index._rebuild_index()

        hints_char = compute_inlay_hints(
            doc_char,
            index,
            Range(start=Position(line=0, character=0), end=Position(line=4, character=0)),
        )
        alice_hints = [h for h in hints_char if "Alice" in h.label]
        assert len(alice_hints) == 1
        assert alice_hints[0].position.line == 2
        assert alice_hints[0].position.character == 1
