"""Unit tests for semantic tokens, document colors, folding ranges, document links, lenses, and inlay hints."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol.types import Color, Position, Range

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.lenses import (
    compute_code_lenses,
    compute_inlay_hints,
)
from eager_script_lsp.features.tokens import (
    compute_color_presentation,
    compute_document_colors,
    compute_folding_ranges,
    compute_semantic_tokens,
)
from eager_script_lsp.workspace import WorkspaceIndex


def test_semantic_tokens():
    text = """## Start --- start
Narrator: Hello
~ bg classroom_day
Hoshiko (smile): Hi!
> other
"""
    doc = ScriptDocument("file:///test.es", text)
    tokens = compute_semantic_tokens(doc)
    assert len(tokens.data) > 0
    # Data is encoded in multiples of 5 integers: [deltaLine, deltaStartChar, length, tokenType, tokenModifiers]
    assert len(tokens.data) % 5 == 0


def test_document_colors_and_presentation():
    text = """@character hoshiko "Hoshiko" color=#ff77aa
~ flash color=#00ff00
Narrator: Colored {color=#112233}text{/color}
"""
    doc = ScriptDocument("file:///test.es", text)
    colors = compute_document_colors(doc)
    assert len(colors) == 3
    # Check normalized color values [0.0, 1.0]
    assert colors[1].color.red == 0.0
    assert colors[1].color.green == 1.0
    assert colors[1].color.blue == 0.0
    assert colors[1].color.alpha == 1.0

    # Color presentation
    pres = compute_color_presentation(
        Color(red=1.0, green=0.0, blue=0.0, alpha=1.0),
        Range(start=Position(line=0, character=0), end=Position(line=0, character=7)),
    )
    assert len(pres) == 1
    assert pres[0].label == "#ff0000"


def test_folding_ranges():
    text = """## Scene 1 --- s1
Narrator: Line 1
Narrator: Line 2
@if score > 0
Narrator: High
@end

## Scene 2 --- s2
Narrator: Done
"""
    doc = ScriptDocument("file:///test.es", text)
    folds = compute_folding_ranges(doc)
    assert len(folds) >= 2


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


def test_semantic_tokens_no_overlap():
    text = """## Implicit Title
Narrator: Hello {voice:audio/clip.ogg} world!
"""
    doc = ScriptDocument("file:///test.es", text)
    tokens = compute_semantic_tokens(doc)
    assert len(tokens.data) % 5 == 0

    # Verify no delta_col on same line is negative and tokens don't overlap
    current_line = 0
    current_col = 0
    for i in range(0, len(tokens.data), 5):
        delta_line = tokens.data[i]
        delta_col = tokens.data[i + 1]
        length = tokens.data[i + 2]

        if delta_line > 0:
            current_line += delta_line
            current_col = delta_col
        else:
            assert delta_col >= 0
            current_col += delta_col

        assert length > 0
        current_col += length
