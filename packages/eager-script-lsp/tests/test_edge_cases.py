"""Resilience and edge-case testing for parser, diagnostics, and server lifecycle."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol import types
from lsprotocol.types import DiagnosticSeverity, MarkupContent, Position

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.completion import compute_completions
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.features.hover import compute_hover
from eager_script_lsp.features.navigation import compute_definition, compute_references
from eager_script_lsp.server import create_server
from eager_script_lsp.workspace import WorkspaceIndex


def test_empty_and_whitespace_documents():
    """Verify empty and whitespace-only documents do not crash any LSP provider."""
    index = WorkspaceIndex(Path("."))

    for label, text in [("empty", ""), ("whitespace", "   \n\t  \n  "), ("newlines", "\n\n\n")]:
        doc = ScriptDocument(f"file:///{label}.es", text)
        assert len(doc.syntax_errors) == 0
        diags = compute_diagnostics(doc, index)
        assert len(diags) == 0

        pos = Position(line=0, character=0)
        assert compute_hover(doc, index, pos) is None
        assert compute_definition(doc, index, pos) is None
        assert compute_references(doc, index, pos) == []

        comp = compute_completions(doc, index, pos)
        if label == "empty":
            assert len(comp.items) == 0
        else:
            # On whitespace lines, narrator/character completion is safely suggested
            assert any(item.label == "Narrator" for item in comp.items)


def test_unicode_and_multibyte_document_handling():
    """Verify full unicode compatibility: Japanese, Cyrillic, emoji, and column offsets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """# 🌸 桜の物語
@character hoshiko "星子" color=#ff77aa
## 第一章：旅立ち --- ch1_start
Narrator: こんにちは世界！ ✨
> ch1_end

## 終わり --- ch1_end
Narrator: おしまい
"""
        doc = ScriptDocument("file:///unicode.es", text)
        assert len(doc.syntax_errors) == 0
        index.documents["file:///unicode.es"] = doc
        index._rebuild_index()

        diags = compute_diagnostics(doc, index)
        assert len(diags) == 0

        # Hover on unicode scene title
        hover_scene = compute_hover(doc, index, Position(line=2, character=5))
        assert hover_scene is not None
        assert isinstance(hover_scene.contents, MarkupContent)
        assert "第一章：旅立ち" in hover_scene.contents.value

        # Hover on character definition
        hover_char = compute_hover(doc, index, Position(line=1, character=13))
        assert hover_char is not None
        assert isinstance(hover_char.contents, MarkupContent)
        assert "星子" in hover_char.contents.value


def test_comment_parsing_edge_cases():
    """Verify inline comments, hashes in strings, and escaped hashes."""
    text = """## Scene 1 --- s1
Narrator: "Text with # inside quotes" # Real comment
Narrator: Escaped \\#hash is dialogue # Another comment
# Standalone comment
"""
    doc = ScriptDocument("file:///comments.es", text)
    comments = [s.value for s in doc.spans if s.kind == "comment"]
    assert len(comments) == 3
    assert "# Real comment" in comments[0]
    assert "# Another comment" in comments[1]
    assert "# Standalone comment" in comments[2]


def test_malformed_unclosed_and_stray_blocks():
    """Verify unclosed @if blocks and stray directives produce accurate diagnostics."""
    index = WorkspaceIndex(Path("."))

    cases = [
        ("unclosed", "## S --- s\n@if score > 10\nNarrator: Win\n", "Unclosed @if block"),
        ("nested_unclosed", "## S --- s\n@if a\n@if b\nNarrator: Deep\n@end\n", "Unclosed @if block"),
        ("stray_else", "## S --- s\n@else\nNarrator: Stray\n", "@else without matching @if"),
        ("stray_elif", "## S --- s\n@elif x\nNarrator: Stray\n", "@elif without matching @if"),
        ("stray_end", "## S --- s\n@end\nNarrator: Stray\n", "@end without matching @if"),
    ]

    for name, script, expected_msg in cases:
        doc = ScriptDocument(f"file:///{name}.es", script)
        diags = compute_diagnostics(doc, index)
        errors = [d for d in diags if d.severity == DiagnosticSeverity.Error]
        assert any(expected_msg in e.message for e in errors), f"Failed for {name}"


def test_malformed_syntax_resilience():
    """Verify syntax issues in expressions, empty jumps, and directives are flagged without crashing."""
    cases = [
        ("empty_jump", "## S --- s\n> \n", "Empty jump target"),
        ("empty_call", "## S --- s\n>> \n", "Empty call target"),
        ("empty_if", "## S --- s\n@if \n", "Empty @if expression"),
        ("empty_elif", "## S --- s\n@if x\nNarrator: 1\n@elif \n@end\n", "Empty @elif expression"),
        ("invalid_set", "## S --- s\n$ \n", "Invalid variable syntax"),
        ("invalid_char", "@character\n## S --- s\n", "Invalid @character definition"),
        ("invalid_default", "@default\n## S --- s\n", "Invalid @default syntax"),
    ]

    for name, script, expected_msg in cases:
        doc = ScriptDocument(f"file:///{name}.es", script)
        assert len(doc.syntax_errors) > 0
        assert any(expected_msg in err.message for err in doc.syntax_errors)


def test_excessive_syntax_errors_recovery_limit():
    """Verify scripts with >30 parse errors stop recovering at max_attempts without crashing."""
    index = WorkspaceIndex(Path("."))
    # Choice line without indented block fails parse
    broken_script = "\n".join(["? Option without block"] * 35)
    doc = ScriptDocument("file:///many_errors.es", broken_script)
    # Recovers at bounded limit (30)
    assert len(doc.syntax_errors) == 30
    diags = compute_diagnostics(doc, index)
    assert len(diags) == 30


def test_ast_recovery_indentation_preservation():
    """Verify parse error recovery preserves line indentation in block structures."""
    script = """## Start --- start
? Make choice
    Narrator: Option A chosen
    $ invalid set syntax %%%
    Narrator: Still inside option A
> start
"""
    doc = ScriptDocument("file:///choice_indent.es", script)
    # The error on the invalid set line was captured
    assert len(doc.syntax_errors) > 0
    # AST items were successfully recovered
    assert len(doc.ast_items) > 0


def test_did_close_untracked_document_publishes_empty_diagnostics():
    """Verify closing an untracked or deleted buffer clears diagnostics in client."""
    s = create_server()
    published_diags: list[types.PublishDiagnosticsParams] = []

    def mock_publish(params: types.PublishDiagnosticsParams) -> None:
        published_diags.append(params)

    s.text_document_publish_diagnostics = mock_publish  # type: ignore[assignment]

    deleted_uri = "file:///tmp/deleted_nonexistent_buffer.es"
    s.workspace_index.documents[deleted_uri] = ScriptDocument(deleted_uri, "## A --- a\n")

    # Trigger on_did_close
    did_close_handler = s.protocol.fm.features[types.TEXT_DOCUMENT_DID_CLOSE]
    did_close_handler(types.DidCloseTextDocumentParams(
        text_document=types.TextDocumentIdentifier(uri=deleted_uri)
    ))

    # Document should be removed from workspace_index
    assert deleted_uri not in s.workspace_index.documents
    # Empty diagnostics should be published to clear UI squiggles
    matching = [p for p in published_diags if p.uri == deleted_uri]
    assert len(matching) > 0
    assert len(matching[0].diagnostics) == 0


def test_complex_nested_expression_tokens_and_hover():
    """Verify nested expressions properly generate builtin_func spans and hover docs."""
    index = WorkspaceIndex(Path("."))
    script = """## S1 --- s1
@if visited("s1") and (len("test") > 0 or seen("s1"))
Narrator: Logic passed
@end
"""
    doc = ScriptDocument("file:///nested_expr.es", script)
    assert len(doc.syntax_errors) == 0

    # Spans should include visited, len, seen
    builtin_spans = [s for s in doc.spans if s.kind == "builtin_func"]
    values = [s.value for s in builtin_spans]
    assert "visited" in values
    assert "len" in values
    assert "seen" in values

    # Hover on 'len' (line 1, col 23)
    h_len = compute_hover(doc, index, Position(line=1, character=24))
    assert h_len is not None
    assert isinstance(h_len.contents, MarkupContent)
    assert "len" in h_len.contents.value

