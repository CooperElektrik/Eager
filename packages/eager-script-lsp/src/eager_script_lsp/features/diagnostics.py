"""Diagnostics engine providing real-time syntax, AST, asset, and i18n diagnostics."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import eager.script
from eager.core.assets import check_assets
from lsprotocol.types import (
    Diagnostic,
    DiagnosticSeverity,
    DiagnosticTag,
    Position,
    Range,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex

__all__ = [
    "compute_diagnostics",
]


def compute_diagnostics(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    *,
    check_disk_assets: bool = True,
) -> list[Diagnostic]:
    """Compute all diagnostics for the given document within the workspace."""
    diagnostics: list[Diagnostic] = []

    # 1. Syntax errors from resilient document scanner
    for issue in doc.syntax_errors:
        line_idx = issue.line
        start_col = max(0, issue.start_col)
        end_col = max(start_col + 1, issue.end_col)
        if line_idx < len(doc.lines) and end_col > len(doc.lines[line_idx]):
            end_col = len(doc.lines[line_idx])

        diag = Diagnostic(
            range=Range(
                start=Position(line=line_idx, character=start_col),
                end=Position(line=line_idx, character=end_col),
            ),
            message=issue.message,
            severity=issue.severity,
            source="eager-syntax",
        )
        diagnostics.append(diag)

    # 2. Structural & AST validation
    if doc.ast_items:
        val_result = eager.script.validate(doc.ast_items)

        for err in val_result.errors:
            # Check if this error is an undefined target that actually exists in another workspace file
            target_match = re.search(r"Undefined target label ['\"]?([A-Za-z0-9_-]+)['\"]?", err.message)
            if target_match:
                tgt = target_match.group(1)
                if tgt in workspace.labels:
                    # Target exists across files in the workspace
                    continue

            line_0 = max(0, err.line_number - 1)
            token_range = _find_best_range(doc, line_0, target_match.group(1) if target_match else None)

            diagnostics.append(
                Diagnostic(
                    range=token_range,
                    message=err.message,
                    severity=DiagnosticSeverity.Error,
                    source="eager-validator",
                )
            )

        for warn in val_result.warnings:
            # 1. Suppress subroutine warning if workspace contains returns
            if "Subroutine call" in warn.message:
                workspace_has_return = any(
                    any(s.kind == "return_keyword" for s in d.spans)
                    for d in workspace.documents.values()
                )
                if workspace_has_return:
                    continue

            # 2. Suppress orphan label warning if targeted elsewhere in workspace
            m_orphan = re.search(
                r"Label ['\"]?([A-Za-z0-9_-]+)['\"]? is defined but never targeted",
                warn.message,
            )
            if m_orphan:
                lbl = m_orphan.group(1)
                if lbl in workspace.references and len(workspace.references[lbl]) > 0:
                    continue

            # 3. Suppress unreachable from entry warning if predecessor exists in workspace
            m_unreach = re.search(
                r"Label ['\"]?([A-Za-z0-9_-]+)['\"]? is unreachable from the script entry",
                warn.message,
            )
            if m_unreach:
                lbl = m_unreach.group(1)
                sym = workspace.get_scene(lbl)
                if sym and len(sym.predecessors) > 0:
                    continue

            line_0 = max(0, warn.line_number - 1)
            token_range = _find_best_range(doc, line_0)
            is_unreachable = "unreachable" in warn.message.lower() or "dead code" in warn.message.lower()
            tags = [DiagnosticTag.Unnecessary] if is_unreachable else None

            diagnostics.append(
                Diagnostic(
                    range=token_range,
                    message=warn.message,
                    severity=DiagnosticSeverity.Warning,
                    source="eager-validator",
                    tags=tags,
                )
            )

    # Cross-file duplicate scene label detection
    from eager_script_lsp.workspace import normalize_uri

    norm_doc_uri = normalize_uri(doc.uri)
    for occ in doc.occurrences:
        if occ.kind == "label_def":
            scene_id = occ.name
            # Check other documents for the same scene_id
            for other_uri, other_doc in workspace.documents.items():
                if normalize_uri(other_uri) == norm_doc_uri:
                    continue
                if scene_id in other_doc.scene_spans:
                    diagnostics.append(
                        Diagnostic(
                            range=occ.span.range,
                            message=f"Duplicate scene label '{scene_id}' already defined in '{other_uri}'",
                            severity=DiagnosticSeverity.Error,
                            source="eager-validator",
                        )
                    )
                    break

    # 3. Asset consistency linter (disk checks deferred on incremental keystrokes)
    if check_disk_assets and workspace.asset_dir.is_dir() and (doc.scene_graph or doc.ast_items):
        target_items = doc.scene_graph if doc.scene_graph else doc.ast_items
        extra_chars = {
            cid: {"name": sym.name, "attrs": dict(sym.attrs)}
            for cid, sym in workspace.characters.items()
            if sym.is_defined
        }
        report = check_assets(target_items, workspace.asset_dir, extra_characters=extra_chars)
        for issue in report.missing:
            ref = issue.reference
            line_0 = max(0, ref.line_number - 1)
            # Find matching asset span
            token_range = _find_best_range(doc, line_0, ref.identifier)
            cands = ", ".join(issue.expected_paths[:3])
            msg = f"Missing {ref.kind} asset '{ref.identifier}' (expected e.g. {cands})"

            diagnostics.append(
                Diagnostic(
                    range=token_range,
                    message=msg,
                    severity=DiagnosticSeverity.Warning,
                    source="eager-assets",
                )
            )

    return diagnostics


def _find_best_range(doc: ScriptDocument, line_0: int, target_text: str | None = None) -> Range:
    """Find the most accurate range on line_0 for an error or warning."""
    if line_0 >= len(doc.lines):
        return Range(start=Position(line=line_0, character=0), end=Position(line=line_0, character=0))

    line_text = doc.lines[line_0]

    if target_text:
        # Check tokens on this line for exact match
        for s in doc.spans:
            if s.start_line == line_0 and (s.value == target_text or target_text in s.value):
                return s.range

        # Fallback substring search
        idx = line_text.find(target_text)
        if idx != -1:
            return Range(
                start=Position(line=line_0, character=idx),
                end=Position(line=line_0, character=idx + len(target_text)),
            )

    # General line range
    stripped = line_text.strip()
    if not stripped:
        return Range(
            start=Position(line=line_0, character=0),
            end=Position(line=line_0, character=len(line_text)),
        )

    start_col = line_text.find(stripped)
    return Range(
        start=Position(line=line_0, character=start_col),
        end=Position(line=line_0, character=start_col + len(stripped)),
    )
