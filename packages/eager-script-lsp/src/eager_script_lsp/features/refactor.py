"""Refactoring and Code Actions provider (multi-file rename and quick fixes)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from eager_runtime.i18n import compute_beat_id
from lsprotocol.types import (
    CodeAction,
    CodeActionContext,
    CodeActionKind,
    Position,
    Range,
    TextEdit,
    WorkspaceEdit,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex

__all__ = [
    "compute_code_actions",
    "compute_rename",
    "prepare_rename",
]


def prepare_rename(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    position: Position,
) -> Range | None:
    """Validate that the symbol under cursor can be safely renamed."""
    token = doc.get_token_at(position.line, position.character)
    if token is None:
        return None

    if token.kind in (
        "label_id", "label_title", "jump_target", "call_target", "choice_target", "label_ref",
        "speaker", "character_id", "character_name",
        "variable",
    ):
        return token.range
    return None


def compute_rename(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    position: Position,
    new_name: str,
) -> WorkspaceEdit | None:
    """Compute WorkspaceEdit for renaming labels, characters, or variables across files."""
    token = doc.get_token_at(position.line, position.character)
    if token is None:
        return None

    changes: dict[str, list[TextEdit]] = {}

    def add_edit(uri: str, range_: Range, new_text: str) -> None:
        changes.setdefault(uri, []).append(TextEdit(range=range_, new_text=new_text))

    # 1. Rename Scene Label
    if token.kind in ("label_id", "label_title", "jump_target", "call_target", "choice_target", "label_ref"):
        old_scene_id = token.metadata.get("scene_id", token.value) if token.metadata else token.value
        sym = workspace.get_scene(old_scene_id)
        if sym is None:
            return None

        # A: Update definition site
        def_doc = workspace.get_document(sym.uri)
        if def_doc:
            # Check if implicit slug or explicit
            label_token = def_doc.scene_spans.get(old_scene_id)
            if label_token and label_token.metadata.get("implicit"):
                # Was '## Title' -> replace with '## Title --- new_name'
                title_span = next(
                    (s for s in def_doc.spans if s.kind == "label_title" and s.start_line == label_token.start_line),
                    None,
                )
                if title_span:
                    header_line = def_doc.lines[title_span.start_line]
                    add_edit(
                        sym.uri,
                        Range(
                            start=Position(line=title_span.start_line, character=0),
                            end=Position(line=title_span.start_line, character=len(header_line)),
                        ),
                        f"## {title_span.value} --- {new_name}",
                    )
            elif label_token:
                add_edit(sym.uri, label_token.range, new_name)

        # B: Update all references across all files
        for doc_uri, d in workspace.documents.items():
            for occ in d.occurrences:
                if occ.kind == "label_ref" and occ.name == old_scene_id:
                    add_edit(doc_uri, occ.span.range, new_name)

        return WorkspaceEdit(changes=changes)

    # 2. Rename Character
    if token.kind in ("character_id", "character_name", "speaker"):
        char_sym_lookup = token.metadata.get("character") or token.value
        old_char_id = char_sym_lookup.lower()
        new_id = new_name.lower().replace(" ", "_")
        display_name = new_name if not new_name.islower() else new_name.title()

        for doc_uri, d in workspace.documents.items():
            for occ in d.occurrences:
                if occ.name.lower() == old_char_id:
                    if occ.kind == "character_def":
                        add_edit(doc_uri, occ.span.range, new_id)
                    elif occ.kind == "character_name":
                        add_edit(doc_uri, occ.span.range, display_name)
                    elif occ.kind == "character_ref":
                        if occ.span.kind == "speaker":
                            if occ.span.value.istitle() or not occ.span.value.islower():
                                add_edit(doc_uri, occ.span.range, display_name)
                            else:
                                add_edit(doc_uri, occ.span.range, new_id)
                        else:
                            add_edit(doc_uri, occ.span.range, new_id)
        return WorkspaceEdit(changes=changes)

    # 3. Rename Variable
    if token.kind == "variable":
        old_var = token.value
        var_sym = workspace.get_variable(old_var)
        if var_sym is not None:
            if var_sym.default_uri and var_sym.default_range:
                add_edit(var_sym.default_uri, var_sym.default_range, new_name)
            for doc_uri, r in var_sym.mutations:
                add_edit(doc_uri, r, new_name)
            for doc_uri, r in var_sym.reads:
                add_edit(doc_uri, r, new_name)
        return WorkspaceEdit(changes=changes)

    return None


def compute_code_actions(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    range_: Range,
    context: CodeActionContext,
) -> list[CodeAction]:
    """Provide quick fixes and refactoring actions for the current selection/diagnostics."""
    actions: list[CodeAction] = []

    # 1. Quick Fix for Undefined Scene Target
    for diag in context.diagnostics:
        m = re.search(r"Undefined target label ['\"]?([A-Za-z0-9_-]+)['\"]?", diag.message)
        if m:
            missing_label = m.group(1)
            display_title = missing_label.replace("_", " ").title()
            stub_content = f"\n\n## {display_title} --- {missing_label}\nNarrator: TODO\n"

            end_line = len(doc.lines)
            last_col = len(doc.lines[-1]) if doc.lines else 0
            insert_range = Range(
                start=Position(line=end_line, character=last_col),
                end=Position(line=end_line, character=last_col),
            )

            actions.append(
                CodeAction(
                    title=f"Create scene '## {display_title} --- {missing_label}'",
                    kind=CodeActionKind.QuickFix,
                    diagnostics=[diag],
                    edit=WorkspaceEdit(
                        changes={doc.uri: [TextEdit(range=insert_range, new_text=stub_content)]}
                    ),
                    is_preferred=True,
                )
            )

    # 2. Refactor Action: Pin explicit beat ID {id=...}
    token = doc.get_token_at(range_.start.line, range_.start.character)
    line_0 = range_.start.line
    if line_0 < len(doc.lines):
        line_text = doc.lines[line_0]
        item = doc.get_item_at_line(line_0)
        scene_id = doc.get_scene_at_line(line_0)
        if item is not None and scene_id is not None and "{id=" not in line_text:
            occ = doc.get_beat_occurrence(line_0)
            raw_beat_id = compute_beat_id(scene_id, item, occurrence=occ)
            # Shorten scene prefix if present
            short_id = raw_beat_id.split(".", 1)[-1] if "." in raw_beat_id else raw_beat_id
            tag_text = f" {{id={short_id}}}"

            line_end_pos = Position(line=line_0, character=len(line_text))
            actions.append(
                CodeAction(
                    title=f"Pin explicit translation beat ID '{{id={short_id}}}'",
                    kind=CodeActionKind.RefactorRewrite,
                    edit=WorkspaceEdit(
                        changes={
                            doc.uri: [
                                TextEdit(
                                    range=Range(start=line_end_pos, end=line_end_pos),
                                    new_text=tag_text,
                                )
                            ]
                        }
                    ),
                )
            )

    # 3. Quick Fix: Declare missing @default variable
    if token and token.kind == "variable":
        var_name = token.value
        if not var_name.startswith("persistent.") and (
            var_name not in workspace.variables or workspace.variables[var_name].default_val is None
        ):
            preamble_pos = Position(line=0, character=0)
            actions.append(
                CodeAction(
                    title=f"Declare '@default {var_name} = 0' in preamble",
                    kind=CodeActionKind.QuickFix,
                    edit=WorkspaceEdit(
                        changes={
                            doc.uri: [
                                TextEdit(
                                    range=Range(start=preamble_pos, end=preamble_pos),
                                    new_text=f"@default {var_name} = 0\n",
                                )
                            ]
                        }
                    ),
                )
            )

    return actions
