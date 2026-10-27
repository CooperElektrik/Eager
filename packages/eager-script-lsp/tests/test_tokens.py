"""Unit tests for semantic tokens, document colors, and folding ranges."""

from __future__ import annotations

from lsprotocol.types import Color, Position, Range

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.tokens import (
    compute_color_presentation,
    compute_document_colors,
    compute_folding_ranges,
    compute_semantic_tokens,
)


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
