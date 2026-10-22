"""Unit tests for rename refactoring and code actions."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol.types import (
    CodeActionContext,
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.refactor import (
    compute_code_actions,
    compute_rename,
    prepare_rename,
)
from eager_script_lsp.workspace import WorkspaceIndex


def test_prepare_rename_valid():
    text = "## Start --- start\n> other\n"
    doc = ScriptDocument("file:///test.es", text)
    index = WorkspaceIndex(Path("."))

    # On label id
    r1 = prepare_rename(doc, index, Position(line=0, character=15))
    assert r1 is not None

    # On jump target
    r2 = prepare_rename(doc, index, Position(line=1, character=3))
    assert r2 is not None


def test_rename_scene_label_across_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f1 = root / "f1.es"
        f1.write_text("## Scene A --- old_label\nNarrator: Hi\n", encoding="utf-8")
        f2 = root / "f2.es"
        f2.write_text("## Scene B --- b\n> old_label\n? Go (old_label)\n", encoding="utf-8")

        index = WorkspaceIndex(root)
        index.initialize()
        doc1 = index.get_document(f1.as_uri())
        assert doc1 is not None

        edit = compute_rename(doc1, index, Position(line=0, character=16), "new_label")
        assert edit is not None
        assert edit.changes is not None

        # Both files should have edits replacing old_label with new_label
        assert f1.as_uri() in edit.changes
        assert f2.as_uri() in edit.changes
        assert any(e.new_text == "new_label" for e in edit.changes[f1.as_uri()])
        assert any(e.new_text == "new_label" for e in edit.changes[f2.as_uri()])


def test_code_action_create_missing_scene():
    text = "## Scene 1 --- s1\n> missing_scene\n"
    doc = ScriptDocument("file:///test.es", text)
    index = WorkspaceIndex(Path("."))

    diag = Diagnostic(
        range=Range(start=Position(line=1, character=2), end=Position(line=1, character=15)),
        message="Undefined target label 'missing_scene'",
        severity=DiagnosticSeverity.Error,
    )
    ctx = CodeActionContext(diagnostics=[diag])

    actions = compute_code_actions(doc, index, diag.range, ctx)
    create_actions = [a for a in actions if "missing_scene" in a.title]
    assert len(create_actions) == 1
    action = create_actions[0]
    assert action.edit is not None
    assert action.edit.changes is not None
    edits = action.edit.changes["file:///test.es"]
    assert any("## Missing Scene --- missing_scene" in e.new_text for e in edits)


def test_code_action_pin_beat_id():
    text = "## Scene 1 --- s1\nNarrator: Hello world\n"
    doc = ScriptDocument("file:///test.es", text)
    index = WorkspaceIndex(Path("."))

    range_ = Range(start=Position(line=1, character=5), end=Position(line=1, character=5))
    ctx = CodeActionContext(diagnostics=[])

    actions = compute_code_actions(doc, index, range_, ctx)
    pin_actions = [a for a in actions if "Pin explicit translation beat ID" in a.title]
    assert len(pin_actions) == 1
    edit = pin_actions[0].edit
    assert edit is not None and edit.changes is not None
    edits = edit.changes["file:///test.es"]
    assert any("{id=" in e.new_text for e in edits)


def test_rename_from_label_title():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f1 = root / "f1.es"
        f1.write_text("## Scene A --- s1\n> s1\n", encoding="utf-8")

        index = WorkspaceIndex(root)
        index.initialize()
        doc = index.get_document(f1.as_uri())
        assert doc is not None

        # Rename cursor positioned on 'Scene A' (col 5)
        edit = compute_rename(doc, index, Position(line=0, character=5), "s2")
        assert edit is not None and edit.changes is not None
        edits = edit.changes[f1.as_uri()]
        assert any(e.new_text == "s2" for e in edits)


def test_rename_character_occurrences():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        f1 = root / "f1.es"
        f1.write_text(
            '@character hoshiko "Hoshiko" color=#ff77aa\n## Scene 1 --- s1\nHoshiko: Hi\n~ show hoshiko smile\n',
            encoding="utf-8",
        )

        index = WorkspaceIndex(root)
        index.initialize()
        doc = index.get_document(f1.as_uri())
        assert doc is not None

        # Rename cursor on 'Hoshiko:' speaker
        edit = compute_rename(doc, index, Position(line=2, character=2), "kaori")
        assert edit is not None and edit.changes is not None
        edits = edit.changes[f1.as_uri()]

        # ID should be replaced with kaori
        assert any(e.new_text == "kaori" for e in edits)
        # Display name and speaker should be Kaori
        assert any(e.new_text == "Kaori" for e in edits)
