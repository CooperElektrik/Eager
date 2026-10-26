"""Unit tests for context-aware completions."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol import types
from lsprotocol.types import Position

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.completion import compute_completions
from eager_script_lsp.server import create_server
from eager_script_lsp.workspace import WorkspaceIndex


def test_completion_labels():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Scene One --- s1
Narrator: Hello
> 
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Cursor after '> ' on line 2
        comp_list = compute_completions(doc, index, Position(line=2, character=2))
        labels = [item.label for item in comp_list.items]
        assert "s1" in labels


def test_completion_character_emotions_from_assets():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "assets" / "characters" / "hoshiko").mkdir(parents=True)
        (root / "assets" / "characters" / "hoshiko" / "smile.png").write_bytes(b"PNG")
        (root / "assets" / "characters" / "hoshiko" / "surprised.png").write_bytes(b"PNG")

        index = WorkspaceIndex(root)
        index.initialize()

        text = """## Start --- start
Hoshiko (
"""
        doc = ScriptDocument("file:///test.es", text)
        comp_list = compute_completions(doc, index, Position(line=1, character=9))
        labels = [item.label for item in comp_list.items]
        assert "smile" in labels
        assert "surprised" in labels


def test_completion_hooks_and_backgrounds():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "assets" / "bg").mkdir(parents=True)
        (root / "assets" / "bg" / "classroom_day.png").write_bytes(b"PNG")

        index = WorkspaceIndex(root)
        index.initialize()

        text = "## Start --- start\n~ bg "
        doc = ScriptDocument("file:///test.es", text)
        comp_list = compute_completions(doc, index, Position(line=1, character=5))
        labels = [item.label for item in comp_list.items]
        assert "classroom_day" in labels


def test_completion_tilde_trigger():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)
        index.initialize()

        # Cursor directly after '~'
        text = "## Start --- start\n~"
        doc = ScriptDocument("file:///test.es", text)
        comp_list = compute_completions(doc, index, Position(line=1, character=1))
        labels = [item.label for item in comp_list.items]
        assert "bg" in labels
        assert "show" in labels
        assert "play" in labels

        bg_item = next(i for i in comp_list.items if i.label == "bg")
        assert bg_item.text_edit is not None
        assert bg_item.text_edit.new_text == "~ bg "
        assert bg_item.filter_text is not None
        assert "~bg" in bg_item.filter_text

        # Cursor after '~b'
        text_b = "## Start --- start\n~b"
        doc_b = ScriptDocument("file:///test.es", text_b)
        comp_list_b = compute_completions(doc_b, index, Position(line=1, character=2))
        labels_b = [item.label for item in comp_list_b.items]
        assert "bg" in labels_b
        assert "bg_clear" in labels_b


def test_completion_jump_and_directive_triggers():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = "## Scene One --- s1\n> \n@\n"
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Cursor directly after '>'
        comp_jump = compute_completions(doc, index, Position(line=1, character=1))
        assert "s1" in [i.label for i in comp_jump.items]

        # Cursor directly after '@'
        comp_dir = compute_completions(doc, index, Position(line=2, character=1))
        dir_labels = [i.label for i in comp_dir.items]
        assert "@character" in dir_labels
        assert "@if" in dir_labels


def test_completion_tilde_with_space():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)
        index.initialize()

        # Cursor after '~ '
        text_space = "## Start --- start\nNarrator: Hello\n~ "
        doc_space = ScriptDocument("file:///test.es", text_space)
        comp_list = compute_completions(doc_space, index, Position(line=2, character=2))
        labels = [item.label for item in comp_list.items]
        assert "bg" in labels
        assert "show" in labels
        item_bg = next(i for i in comp_list.items if i.label == "bg")
        assert item_bg.text_edit is not None
        assert item_bg.text_edit.new_text == "bg "

        # Cursor after '~ b'
        text_b = "## Start --- start\nNarrator: Hello\n~ b"
        doc_b = ScriptDocument("file:///test.es", text_b)
        comp_list_b = compute_completions(doc_b, index, Position(line=2, character=3))
        labels_b = [item.label for item in comp_list_b.items]
        assert "bg" in labels_b
        item_b = next(i for i in comp_list_b.items if i.label == "bg")
        assert isinstance(item_b.text_edit, types.TextEdit)
        assert item_b.text_edit.new_text == "bg "
        assert item_b.text_edit.range.start.character == 2
        assert item_b.text_edit.range.end.character == 3


def test_server_incremental_edit_and_completion():
    s = create_server()
    gen = s.protocol.lsp_initialize(types.InitializeParams(capabilities=types.ClientCapabilities(), root_uri="file:///tmp"))
    try:
        func, args, kwargs = next(gen)
        gen.send(func(*args, **(kwargs or {})))
    except StopIteration:
        pass
    s.protocol.lsp_initialized(types.InitializedParams())

    uri = "file:///tmp/scene.es"
    open_gen = s.protocol.lsp_text_document__did_open(types.DidOpenTextDocumentParams(
        text_document=types.TextDocumentItem(
            uri=uri,
            language_id="eager-script",
            version=1,
            text="## Start --- start\nNarrator: Hello\n"
        )
    ))
    try:
        for x in open_gen:
            func, a, kw = x
            func(*a, **(kw or {}))
    except TypeError:
        pass

    change_gen = s.protocol.lsp_text_document__did_change(types.DidChangeTextDocumentParams(
        text_document=types.VersionedTextDocumentIdentifier(uri=uri, version=2),
        content_changes=[
            types.TextDocumentContentChangePartial(
                range=types.Range(
                    start=types.Position(line=2, character=0),
                    end=types.Position(line=2, character=0)
                ),
                text="~"
            )
        ]
    ))
    try:
        for x in change_gen:
            func, a, kw = x
            func(*a, **(kw or {}))
    except TypeError:
        pass

    # Ensure document in workspace_index has kept its 3 lines intact
    doc = s.workspace_index.get_document(uri)
    assert doc is not None
    assert len(doc.lines) == 3

    comp_handler = s.protocol.fm.features[types.TEXT_DOCUMENT_COMPLETION]
    comp_res = comp_handler(types.CompletionParams(
        text_document=types.TextDocumentIdentifier(uri=uri),
        position=types.Position(line=2, character=1)
    ))
    assert len(comp_res.items) == 18
    bg_item = next(i for i in comp_res.items if i.label == "bg")
    assert bg_item.text_edit is not None
    assert bg_item.text_edit.new_text == "~ bg "
    assert bg_item.filter_text == "~bg"


def test_completion_variable_interpolation_and_tags():
    """Verify variable interpolation and inline text tag completions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """@default score = 50
## Scene 1 --- s1
Narrator: Player has [
Narrator: Text with {
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Variable interpolation '[' at line 2 col 22
        comp_var = compute_completions(doc, index, Position(line=2, character=22))
        labels_var = [i.label for i in comp_var.items]
        assert "score" in labels_var

        # Inline tag '{' at line 3 col 21
        comp_tag = compute_completions(doc, index, Position(line=3, character=21))
        labels_tag = [i.label for i in comp_tag.items]
        assert "{b}...{/b}" in labels_tag
        assert "{color=#...}" in labels_tag


def test_completion_expressions_in_set_and_if():
    """Verify variable and builtin function completions inside '$ var = <cursor>' and '@if <cursor>'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """@default score = 10
## S1 --- s1
$ score = 
@if 
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Inside '$ score = ' (line 2 col 10)
        comp_set = compute_completions(doc, index, Position(line=2, character=10))
        labels_set = [i.label for i in comp_set.items]
        assert "score" in labels_set
        assert "visited(label)" in labels_set
        assert "chance(p)" in labels_set

        # Inside '@if ' (line 3 col 4)
        comp_if = compute_completions(doc, index, Position(line=3, character=4))
        labels_if = [i.label for i in comp_if.items]
        assert "score" in labels_if
        assert "visited(label)" in labels_if
        # Ensure directive snippets (@if, @character, etc.) are NOT offered
        assert "@character" not in labels_if
        assert "@if" not in labels_if


def test_completion_partial_jump_filtering():
    """Verify partial typing after jump operator filters scene labels and replaces correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Scene Alpha --- alpha
## Scene Beta --- beta
> al
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Cursor after '> al' on line 2 col 4
        comp = compute_completions(doc, index, Position(line=2, character=4))
        labels = [i.label for i in comp.items]
        assert "alpha" in labels
        assert "beta" not in labels

        alpha_item = next(i for i in comp.items if i.label == "alpha")
        assert isinstance(alpha_item.text_edit, types.TextEdit)
        assert alpha_item.text_edit.new_text == "alpha"
        assert alpha_item.text_edit.range.start.character == 2
        assert alpha_item.text_edit.range.end.character == 4


def test_completion_visited_and_seen_functions():
    """Verify typing inside visited('...') or seen('...') suggests scene labels."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Intro --- intro
## Ending --- ending
@if visited('in
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Cursor after "visited('in" (line 2 col 14)
        comp = compute_completions(doc, index, Position(line=2, character=14))
        labels = [i.label for i in comp.items]
        assert "intro" in labels
        assert "ending" not in labels


def test_completion_choice_inline_target():
    """Verify typing inside '? Option (<cursor>)' suggests scene labels."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Scene 1 --- s1
## Scene 2 --- s2
? Go to next (s
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        # Cursor after "? Go to next (s" (line 2 col 15)
        comp = compute_completions(doc, index, Position(line=2, character=15))
        labels = [i.label for i in comp.items]
        assert "s1" in labels
        assert "s2" in labels


