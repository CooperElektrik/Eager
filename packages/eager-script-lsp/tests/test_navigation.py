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


def test_definition_characters_variables_and_assets():
    """Verify Go to Definition for characters, variables, and media assets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "assets" / "bg").mkdir(parents=True)
        (root / "assets" / "bg" / "park.png").write_bytes(b"PNG")

        f1 = root / "script.es"
        f1.write_text("""@character kaori "Kaori"
@default health = 100
## Scene 1 --- s1
Kaori: Hello
$ health -= 10
~ bg park
~ bg missing_park
UnknownSpeaker: Who am I?
$ uninitialized_var = 5
""", encoding="utf-8")

        index = WorkspaceIndex(root)
        index.initialize()
        doc = index.get_document(f1.as_uri())
        assert doc is not None

        # Character speaker -> @character line
        loc_char = compute_definition(doc, index, Position(line=3, character=2))
        assert loc_char is not None and not isinstance(loc_char, list)
        assert loc_char.range.start.line == 0

        # Variable mutation -> @default line
        loc_var = compute_definition(doc, index, Position(line=4, character=3))
        assert loc_var is not None and not isinstance(loc_var, list)
        assert loc_var.range.start.line == 1

        # Existing asset -> file URI on disk
        loc_asset = compute_definition(doc, index, Position(line=5, character=6))
        assert loc_asset is not None and not isinstance(loc_asset, list)
        assert loc_asset.uri.endswith("park.png")

        # Missing asset -> None
        assert compute_definition(doc, index, Position(line=6, character=6)) is None

        # Speaker with no @character -> None
        assert compute_definition(doc, index, Position(line=7, character=2)) is None

        # Variable with no @default -> falls back to first mutation location (line 8)
        loc_uninit = compute_definition(doc, index, Position(line=8, character=3))
        assert loc_uninit is not None and not isinstance(loc_uninit, list)
        assert loc_uninit.range.start.line == 8


def test_references_character_and_variable_occurrences():
    """Verify Find References locates all character and variable occurrences across workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "f1.es").write_text("""@character hoshiko "Hoshiko"
@default affinity = 10
## Scene 1 --- s1
Hoshiko: Hi
~ show hoshiko smile
$ affinity += 5
""", encoding="utf-8")

        index = WorkspaceIndex(root)
        index.initialize()
        doc = index.get_document((root / "f1.es").as_uri())
        assert doc is not None

        # Character references (decl, speaker, hook)
        refs_char = compute_references(doc, index, Position(line=3, character=2))
        assert len(refs_char) >= 3

        # Variable references (default, mutation)
        refs_var = compute_references(doc, index, Position(line=5, character=3))
        assert len(refs_var) >= 2


def test_document_symbols_empty_document():
    """Verify document symbols returns empty list on empty documents without error."""
    doc = ScriptDocument("file:///empty.es", "")
    symbols = compute_document_symbols(doc)
    assert symbols == []


def test_navigation_out_of_bounds_queries():
    """Verify definition and reference queries return None/empty when position is out of bounds."""
    index = WorkspaceIndex(Path("."))
    doc = ScriptDocument("file:///test.es", "## Scene 1 --- s1\nNarrator: Hello\n")

    oob = Position(line=9999, character=9999)
    assert compute_definition(doc, index, oob) is None
    assert compute_references(doc, index, oob) == []


def test_include_directive_definition_and_links():
    import tempfile

    from lsprotocol.types import Location

    from eager_script_lsp.features.tokens import compute_document_links

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f_inc = root / "included.es"
        f_inc.write_text("## Included --- inc\nNarrator: In included\n", encoding="utf-8")
        f_main = root / "main.es"
        f_main.write_text('@include "included.es"\n## Start --- start\n> inc\n', encoding="utf-8")

        index = WorkspaceIndex(root)
        index.initialize()
        doc = index.get_document(f_main.as_uri())
        assert doc is not None

        # Position on "included.es" (line 0, col 12)
        loc = compute_definition(doc, index, Position(line=0, character=12))
        assert loc is not None
        assert isinstance(loc, Location)
        assert loc.uri == f_inc.as_uri()

        # Document links
        links = compute_document_links(doc, index)
        assert any(link.target == f_inc.as_uri() for link in links)


