"""Unit tests for navigation features (definition, references, symbols, call hierarchy)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol.types import Position

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.navigation import (
    compute_definition,
    compute_document_symbols,
    compute_incoming_calls,
    compute_outgoing_calls,
    compute_references,
    prepare_call_hierarchy,
)
from eager_script_lsp.workspace import WorkspaceIndex


def test_go_to_definition_and_references():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        f1 = root / "f1.es"
        f1.write_text("## Scene One --- s1\n> s2\n", encoding="utf-8")
        f2 = root / "f2.es"
        f2.write_text("## Scene Two --- s2\nNarrator: Arrived\n? Back (s1)\n", encoding="utf-8")

        index.initialize()
        doc1 = index.get_document(f1.as_uri())
        assert doc1 is not None

        # Definition of s2 from '> s2' in f1.es
        loc = compute_definition(doc1, index, Position(line=1, character=3))
        assert loc is not None
        assert not isinstance(loc, list)
        assert loc.uri == f2.as_uri()

        # References to s1 from f2.es
        doc2 = index.get_document(f2.as_uri())
        assert doc2 is not None
        refs = compute_references(doc2, index, Position(line=2, character=9))
        uris = [r.uri for r in refs]
        assert f1.as_uri() in uris
        assert f2.as_uri() in uris


def test_document_symbols():
    text = """@character hoshiko "Hoshiko"
@default score = 0
## Scene One --- s1
$ score += 1
? Opt A
    Narrator: In A
>> s2
"""
    doc = ScriptDocument("file:///test.es", text)
    symbols = compute_document_symbols(doc)
    assert len(symbols) > 0
    names = [s.name for s in symbols]
    assert "Preamble" in names or "Scene One" in names


def test_call_hierarchy():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f1 = root / "story.es"
        f1.write_text("""## Start --- start
> middle

## Middle --- middle
> finish

## Finish --- finish
Narrator: Done
""", encoding="utf-8")

        index = WorkspaceIndex(root)
        index.initialize()
        doc = index.get_document(f1.as_uri())
        assert doc is not None

        # Middle scene
        items = prepare_call_hierarchy(doc, index, Position(line=3, character=5))
        assert items is not None and len(items) == 1
        item = items[0]

        incoming = compute_incoming_calls(index, item)
        assert any("Start" in inc.from_.name for inc in incoming)

        outgoing = compute_outgoing_calls(index, item)
        assert any("Finish" in out.to.name for out in outgoing)
