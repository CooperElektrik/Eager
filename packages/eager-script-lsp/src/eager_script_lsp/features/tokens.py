"""Semantic tokens, document colors, folding ranges, and document links."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager_core.types import Color as EagerColor
from lsprotocol.types import (
    Color,
    ColorInformation,
    ColorPresentation,
    DocumentLink,
    FoldingRange,
    FoldingRangeKind,
    Range,
    SemanticTokens,
    SemanticTokensLegend,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex

__all__ = [
    "KIND_TO_TOKEN_TYPE",
    "LEGEND",
    "SEMANTIC_TOKEN_MODIFIERS",
    "SEMANTIC_TOKEN_TYPES",
    "compute_color_presentation",
    "compute_document_colors",
    "compute_document_links",
    "compute_folding_ranges",
    "compute_semantic_tokens",
]

SEMANTIC_TOKEN_TYPES = [
    "namespace",   # 0: scene labels
    "class",       # 1: characters / speakers
    "enumMember",  # 2: emotion / expressions
    "function",    # 3: hooks & built-in expr functions
    "variable",    # 4: variables
    "keyword",     # 5: keywords & directives
    "string",      # 6: asset paths & string literals
    "macro",       # 7: text tags & voice tags
    "comment",     # 8: comments
]

SEMANTIC_TOKEN_MODIFIERS = [
    "declaration",
    "definition",
    "readonly",
    "defaultLibrary",
]

LEGEND = SemanticTokensLegend(
    token_types=SEMANTIC_TOKEN_TYPES,
    token_modifiers=SEMANTIC_TOKEN_MODIFIERS,
)

KIND_TO_TOKEN_TYPE: dict[str, int] = {
    "label_header": 5,      # keyword
    "label_title": 0,       # namespace
    "label_sep": 5,         # keyword
    "label_id": 0,          # namespace
    "jump_keyword": 5,      # keyword
    "jump_target": 0,       # namespace
    "call_keyword": 5,      # keyword
    "call_target": 0,       # namespace
    "return_keyword": 5,    # keyword
    "choice_bullet": 5,     # keyword
    "choice_target": 0,     # namespace
    "speaker": 1,           # class
    "character_id": 1,      # class
    "character_name": 1,    # class
    "emotion": 2,           # enumMember
    "hook_marker": 5,       # keyword
    "hook_name": 3,         # function
    "builtin_func": 3,      # function
    "hook_keyword": 5,      # keyword
    "hook_arg": 6,          # string
    "directive": 5,         # keyword
    "variable": 4,          # variable
    "set_op": 5,            # keyword
    "text_tag": 7,          # macro
    "voice_tag": 7,         # macro
    "voice_path": 6,        # string
    "beat_id_tag": 7,       # macro
    "color_literal": 6,     # string
    "comment": 8,           # comment
}


def compute_semantic_tokens(doc: ScriptDocument) -> SemanticTokens:
    """Compute delta-encoded semantic tokens for syntax highlighting."""
    sorted_spans = sorted(doc.spans, key=lambda s: (s.start_line, s.start_col))

    data: list[int] = []
    prev_line = 0
    prev_col = 0
    prev_end_col = 0

    for span in sorted_spans:
        token_type_idx = KIND_TO_TOKEN_TYPE.get(span.kind)
        if token_type_idx is None:
            continue

        line_0 = span.start_line
        col_0 = span.start_col
        length = span.end_col - span.start_col
        if length <= 0 or span.end_line != span.start_line:
            # Single-line tokens only in standard LSP
            continue

        if line_0 == prev_line and col_0 < prev_end_col:
            # Skip overlapping inner or duplicate span to satisfy LSP strict non-overlapping rule
            continue

        delta_line = line_0 - prev_line
        delta_col = col_0 if delta_line > 0 else (col_0 - prev_col)

        data.extend([delta_line, delta_col, length, token_type_idx, 0])

        prev_line = line_0
        prev_col = col_0
        prev_end_col = col_0 + length

    return SemanticTokens(data=data)


def compute_document_colors(doc: ScriptDocument) -> list[ColorInformation]:
    """Extract hexadecimal color codes for IDE color pickers."""
    colors: list[ColorInformation] = []

    for span in doc.spans:
        if span.kind == "color_literal":
            hex_str = span.value
            try:
                c = EagerColor.from_hex(hex_str)
                colors.append(
                    ColorInformation(
                        range=span.range,
                        color=Color(red=c.r, green=c.g, blue=c.b, alpha=c.a),
                    )
                )
            except (ValueError, TypeError, KeyError):
                pass

    return colors


def compute_color_presentation(
    color: Color,
    range_: Range,
) -> list[ColorPresentation]:
    """Format an updated color back into screenplay hex format."""
    r_byte = round(color.red * 255)
    g_byte = round(color.green * 255)
    b_byte = round(color.blue * 255)
    hex_str = f"#{r_byte:02x}{g_byte:02x}{b_byte:02x}"
    return [ColorPresentation(label=hex_str)]


def compute_folding_ranges(doc: ScriptDocument) -> list[FoldingRange]:
    """Compute folding regions for scenes, @if blocks, and choice blocks."""
    ranges: list[FoldingRange] = []

    # 1. Scene fold ranges
    scene_starts: list[int] = []
    for span in doc.spans:
        if span.kind == "label_header":
            scene_starts.append(span.start_line)

    for i in range(len(scene_starts)):
        start = scene_starts[i]
        end = scene_starts[i + 1] - 1 if (i + 1) < len(scene_starts) else (len(doc.lines) - 1)
        if end > start:
            ranges.append(
                FoldingRange(
                    start_line=start,
                    end_line=end,
                    kind=FoldingRangeKind.Region,
                )
            )

    # 2. @if ... @end fold ranges
    if_stack: list[int] = []
    for line_idx, line in enumerate(doc.lines):
        stripped = line.strip()
        if stripped.startswith("@if"):
            if_stack.append(line_idx)
        elif stripped.startswith("@end") and if_stack:
            start_l = if_stack.pop()
            if line_idx > start_l:
                    ranges.append(
                        FoldingRange(
                            start_line=start_l,
                            end_line=line_idx,
                            kind=FoldingRangeKind.Region,
                        )
                    )

    # 3. Choice menu folding
    in_choice = False
    choice_start = 0
    for line_idx, line in enumerate(doc.lines):
        stripped = line.strip()
        if stripped.startswith("?") or (in_choice and line.startswith(("    ", "\t"))):
            if not in_choice:
                in_choice = True
                choice_start = line_idx
        else:
            if in_choice:
                in_choice = False
                if line_idx - 1 > choice_start:
                    ranges.append(
                        FoldingRange(
                            start_line=choice_start,
                            end_line=line_idx - 1,
                            kind=FoldingRangeKind.Region,
                        )
                    )
    if in_choice and len(doc.lines) - 1 > choice_start:
        ranges.append(
            FoldingRange(
                start_line=choice_start,
                end_line=len(doc.lines) - 1,
                kind=FoldingRangeKind.Region,
            )
        )

    return ranges


def compute_document_links(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
) -> list[DocumentLink]:
    """Provide clickable links to referenced media files on disk."""
    links: list[DocumentLink] = []

    for span in doc.spans:
        if span.kind in ("hook_arg", "emotion", "voice_path"):
            asset_kind = span.metadata.get("asset_kind")
            disk_path = None
            if asset_kind == "background":
                disk_path = workspace.asset_index.file_paths.get(f"bg:{span.value}")
            elif asset_kind == "voice":
                disk_path = workspace.asset_index.file_paths.get(f"voice:{span.value}")
            elif asset_kind == "character" or span.kind == "emotion":
                char_id = span.metadata.get("character", "")
                expr = span.value.lower()
                disk_path = workspace.asset_index.file_paths.get(f"char:{char_id}/{expr}")
            elif asset_kind == "audio":
                disk_path = workspace.asset_index.file_paths.get(f"audio:{span.value}")

            if disk_path is not None and disk_path.is_file():
                links.append(
                    DocumentLink(
                        range=span.range,
                        target=disk_path.as_uri(),
                        tooltip=f"Open {disk_path.name}",
                    )
                )

    return links
