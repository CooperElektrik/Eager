"""Code lenses (topology edges & Warp and Play) and inlay hints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager_runtime.i18n import compute_beat_id
from lsprotocol.types import (
    CodeLens,
    Command,
    InlayHint,
    InlayHintKind,
    Position,
    Range,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex


def compute_code_lenses(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
) -> list[CodeLens]:
    """Provide Code Lenses for scenes (edge topology and 'Play from here')."""
    lenses: list[CodeLens] = []

    for span in doc.spans:
        if span.kind == "label_title":
            line_0 = span.start_line
            scene_id = doc.get_scene_at_line(line_0)
            if not scene_id:
                continue

            sym = workspace.get_scene(scene_id)
            in_count = len(sym.predecessors) if sym else 0
            out_count = len(sym.successors) if sym else 0

            target_range = Range(
                start=Position(line=line_0, character=0),
                end=Position(line=line_0, character=0),
            )

            # Lens 1: Topology
            lenses.append(
                CodeLens(
                    range=target_range,
                    command=Command(
                        title=f"{in_count} incoming · {out_count} outgoing",
                        command="eager.showReferences",
                        arguments=[doc.uri, scene_id],
                    ),
                )
            )

            # Lens 2: Warp & Play
            lenses.append(
                CodeLens(
                    range=target_range,
                    command=Command(
                        title="▶ Play from here",
                        command="eager.warpAndPlay",
                        arguments=[doc.uri, scene_id],
                    ),
                )
            )

    return lenses


def compute_inlay_hints(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    range_: Range,
) -> list[InlayHint]:
    """Provide Inlay Hints for auto-generated label slugs and translation coverage."""
    hints: list[InlayHint] = []
    start_line = range_.start.line
    end_line = range_.end.line

    # 1. Implicit slug hint on labels without '---'
    for scene_id, label_span in doc.scene_spans.items():
        if label_span.metadata.get("implicit") and start_line <= label_span.start_line <= end_line:
            pos = Position(line=label_span.end_line, character=label_span.end_col)
            hints.append(
                InlayHint(
                    position=pos,
                    label=f" : --- {scene_id}",
                    kind=InlayHintKind.Type,
                    padding_left=True,
                    tooltip=f"Auto-generated scene ID: {scene_id}",
                )
            )

    # 2. Locale status hints on dialogue lines
    if workspace.translation_catalogs:
        for span in doc.spans:
            if span.kind == "speaker" and start_line <= span.start_line <= end_line:
                line_0 = span.start_line
                item = doc.get_item_at_line(line_0)
                scene_id = doc.get_scene_at_line(line_0)
                if item and scene_id:
                    beat_id = compute_beat_id(scene_id, item, occurrence=1)
                    pos = Position(line=line_0, character=len(doc.lines[line_0]))

                    # Check each active locale
                    for loc_code, cat in workspace.translation_catalogs.items():
                        is_translated = beat_id in cat.strings and bool(cat.strings[beat_id].strip())
                        status_str = f"[{'✓' if is_translated else '✗'} {loc_code}]"
                        hints.append(
                            InlayHint(
                                position=pos,
                                label=f" {status_str}",
                                kind=InlayHintKind.Parameter,
                                padding_left=True,
                                tooltip=f"Translation status ({loc_code}): {'Translated' if is_translated else 'Missing'}",
                            )
                        )

    return hints
