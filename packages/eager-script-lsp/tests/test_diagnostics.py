"""Unit tests for LSP diagnostics engine."""

from __future__ import annotations

import tempfile
from pathlib import Path

from lsprotocol.types import DiagnosticSeverity, DiagnosticTag

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.workspace import WorkspaceIndex


def test_diagnostics_broken_links_and_syntax():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Start --- start
Narrator: Hello
> non_existent_scene
Narrator: Dead code after jump
"""
        doc = ScriptDocument("file:///test.es", text)
        index.documents["file:///test.es"] = doc
        index._rebuild_index()

        diags = compute_diagnostics(doc, index)

        # Should have error for non_existent_scene
        errors = [d for d in diags if d.severity == DiagnosticSeverity.Error]
        assert any("non_existent_scene" in e.message for e in errors)

        # Should have warning with tag Unnecessary for dead code
        warnings = [d for d in diags if d.severity == DiagnosticSeverity.Warning]
        dead_code_warn = [w for w in warnings if w.tags and DiagnosticTag.Unnecessary in w.tags]
        assert len(dead_code_warn) > 0


def test_diagnostics_cross_file_valid_target():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        doc1 = ScriptDocument("file:///f1.es", "## Scene 1 --- s1\n> s2\n")
        doc2 = ScriptDocument("file:///f2.es", "## Scene 2 --- s2\nNarrator: Done\n")

        index.documents["file:///f1.es"] = doc1
        index.documents["file:///f2.es"] = doc2
        index._rebuild_index()

        diags1 = compute_diagnostics(doc1, index)
        # Should not flag s2 as undefined because it exists in f2.es
        errors = [d for d in diags1 if d.severity == DiagnosticSeverity.Error]
        assert not any("s2" in e.message for e in errors)


def test_diagnostics_asset_linter():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "assets").mkdir()
        index = WorkspaceIndex(root)

        text = """## Scene 1 --- s1
~ bg non_existent_bg
Narrator: Hi
"""
        doc = ScriptDocument("file:///test_assets.es", text)
        index.documents["file:///test_assets.es"] = doc
        index._rebuild_index()

        diags = compute_diagnostics(doc, index)
        asset_diags = [d for d in diags if d.source == "eager-assets"]
        assert len(asset_diags) > 0
        assert "non_existent_bg" in asset_diags[0].message


def test_diagnostics_duplicate_beat_id():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        index = WorkspaceIndex(root)

        text = """## Scene 1 --- s1
Narrator: Beat one {id=same_id}
Narrator: Beat two {id=same_id}
"""
        doc = ScriptDocument("file:///test_i18n.es", text)
        index.documents["file:///test_i18n.es"] = doc
        index._rebuild_index()

        diags = compute_diagnostics(doc, index)
        i18n_diags = [d for d in diags if d.source == "eager-i18n"]
        assert len(i18n_diags) > 0
        assert "same_id" in i18n_diags[0].message
