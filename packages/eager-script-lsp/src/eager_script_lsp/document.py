"""Fault-tolerant screenplay document scanner backed by eager.script's parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eager.core.i18n import get_beat_occurrence
from eager.script import (
    ParsedChoiceSet,
    ParsedItem,
    ParsedLabel,
    SceneGraph,
    parse_with_tokens,
    to_graph,
)
from eager.script.tokens import TokenSpan as CoreTokenSpan
from lsprotocol.types import (
    DiagnosticSeverity,
    Position,
    Range,
)

__all__ = [
    "ScriptDocument",
    "SymbolOccurrence",
    "SyntaxIssue",
    "TokenSpan",
]

_MAX_SYNTAX_ERRORS = 30
_LABEL_REF_KINDS = frozenset({"jump_target", "call_target", "choice_target", "label_ref"})


@dataclass(frozen=True, slots=True)
class TokenSpan(CoreTokenSpan):
    """A range within a document associated with a semantic token or syntax element."""

    @property
    def range(self) -> Range:
        """Return LSP Range for this token span."""
        return Range(
            start=Position(line=self.start_line, character=self.start_col),
            end=Position(line=self.end_line, character=self.end_col),
        )


@dataclass(frozen=True, slots=True)
class SymbolOccurrence:
    """An indexed symbol definition or reference in the document."""

    kind: str  # "label_def" | "label_ref" | "character_def" | "character_ref" | "variable_def" | "variable_mutation" | "variable_read" | "asset_ref"
    name: str
    span: TokenSpan
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SyntaxIssue:
    """A lexical or syntactic issue detected during parsing."""

    message: str
    line: int  # 0-based
    start_col: int  # 0-based
    end_col: int  # 0-based
    severity: DiagnosticSeverity = DiagnosticSeverity.Error


class ScriptDocument:
    """Represents an open Eager-Script document with fault-tolerant AST and token spans."""

    def __init__(self, uri: str, text: str) -> None:
        self.uri = uri
        self.text = text
        self.lines: list[str] = text.splitlines(keepends=False) or [""]
        self.spans: list[TokenSpan] = []
        self.occurrences: list[SymbolOccurrence] = []
        self.syntax_errors: list[SyntaxIssue] = []
        self.ast_items: list[ParsedItem] = []
        self.scene_graph: SceneGraph | None = None
        self.scene_spans: dict[str, TokenSpan] = {}
        self.parse()

    def get_token_at(self, line: int, col: int) -> TokenSpan | None:
        """Find the innermost/most specific TokenSpan covering (line, col)."""
        matches: list[TokenSpan] = []
        for span in self.spans:
            if span.contains_position(line, col):
                matches.append(span)
        if not matches:
            return None
        matches.sort(key=lambda s: (s.end_line - s.start_line, s.end_col - s.start_col))
        return matches[0]

    def get_tokens_in_range(self, range_: Range) -> list[TokenSpan]:
        """Return all TokenSpans intersecting the given Range."""
        res: list[TokenSpan] = []
        r_start = (range_.start.line, range_.start.character)
        r_end = (range_.end.line, range_.end.character)

        for s in self.spans:
            s_start = (s.start_line, s.start_col)
            s_end = (s.end_line, s.end_col)
            if s_end < r_start or s_start > r_end:
                continue
            res.append(s)
        return res

    def get_item_at_line(self, line_0: int) -> ParsedItem | None:
        """Return the AST item on 0-based line_0, if any."""
        target_line_1 = line_0 + 1

        def search_items(items: Any) -> ParsedItem | None:
            for item in items:
                if getattr(item, "line_number", None) == target_line_1:
                    return item
                if isinstance(item, ParsedChoiceSet):
                    for opt in item.options:
                        if opt.body:
                            found = search_items(opt.body)
                            if found is not None:
                                return found
            return None

        return search_items(self.ast_items)

    def get_item_at_position(self, line_0: int, col_0: int) -> ParsedItem | None:
        """Return the AST item covering 0-based line_0 and col_0, if any."""
        target_line_1 = line_0 + 1

        def search_items(items: Any) -> ParsedItem | None:
            for item in items:
                if getattr(item, "line_number", None) == target_line_1:
                    start = getattr(item, "start_col", 0)
                    end = getattr(item, "end_col", 0)
                    if start <= col_0 <= end or end == 0:
                        return item
                if isinstance(item, ParsedChoiceSet):
                    for opt in item.options:
                        if opt.body:
                            found = search_items(opt.body)
                            if found is not None:
                                return found
            return None

        return search_items(self.ast_items)

    def get_scene_at_line(self, line_0: int) -> str | None:
        """Return the scene identifier active at 0-based line_0."""
        target_line_1 = line_0 + 1
        current_scene: str | None = None
        scene_items: list[Any] = []
        collecting = False

        for item in self.ast_items:
            if isinstance(item, ParsedLabel):
                if item.line_number <= target_line_1:
                    current_scene = item.name
                    scene_items = []
                    collecting = True
                else:
                    break
            elif collecting:
                scene_items.append(item)

        if current_scene:

            def find_anon_scene(items: Any, parent_scene: str) -> str | None:
                for it in items:
                    if isinstance(it, ParsedChoiceSet):
                        for opt in it.options:
                            if opt.body:
                                anon_id = f"{parent_scene}__anon_{opt.line_number}"
                                for sub_item in opt.body:
                                    if getattr(sub_item, "line_number", None) == target_line_1:
                                        return anon_id
                                nested = find_anon_scene(opt.body, anon_id)
                                if nested is not None:
                                    return nested
                return None

            anon = find_anon_scene(scene_items, current_scene)
            if anon is not None:
                return anon

        return current_scene

    def get_beat_occurrence(self, line_0: int) -> int:
        """Compute the 1-based occurrence count of the beat at 0-based line_0."""
        scene_id = self.get_scene_at_line(line_0)
        item = self.get_item_at_line(line_0)
        if not scene_id or not item:
            return 1

        if self.scene_graph and scene_id in self.scene_graph.nodes:
            node = self.scene_graph.nodes[scene_id]
            for idx, b in enumerate(node.body):
                if getattr(b, "line_number", None) == item.line_number:
                    return get_beat_occurrence(node.body, idx)

        scene_items: list[Any] = []
        in_scene = False
        for ast_item in self.ast_items:
            if isinstance(ast_item, ParsedLabel):
                if in_scene:
                    break
                if ast_item.name == scene_id:
                    in_scene = True
            elif in_scene:
                scene_items.append(ast_item)

        for idx, b in enumerate(scene_items):
            if getattr(b, "line_number", None) == item.line_number:
                return get_beat_occurrence(scene_items, idx)
        return 1

    def parse(self) -> None:
        """Parse the document with eager.script and index token spans and symbols."""
        self.spans.clear()
        self.occurrences.clear()
        self.syntax_errors.clear()
        self.scene_spans.clear()

        try:
            result = parse_with_tokens(self.text, recovery=True)
        except Exception:  # noqa: BLE001
            self.ast_items = []
            self.scene_graph = None
            return

        for raw_span in result.spans:
            span = TokenSpan(
                kind=raw_span.kind,
                start_line=raw_span.start_line,
                start_col=raw_span.start_col,
                end_line=raw_span.end_line,
                end_col=raw_span.end_col,
                value=raw_span.value,
                metadata=raw_span.metadata,
            )
            self.spans.append(span)
            self._index_token(span)

        valid_items: list[ParsedItem] = []
        seen_error_lines: set[int] = set()
        for it in result.items:
            if getattr(it, "type", "") == "error":
                if len(self.syntax_errors) >= _MAX_SYNTAX_ERRORS:
                    continue
                err_line_1 = getattr(it, "line_number", 1)
                err_line_0 = max(0, err_line_1 - 1)
                if err_line_0 in seen_error_lines:
                    continue
                seen_error_lines.add(err_line_0)
                raw_len = len(self.lines[err_line_0]) if err_line_0 < len(self.lines) else 0
                msg = getattr(it, "message", "Syntax error")
                s_col = getattr(it, "start_col", 0)
                e_col = getattr(it, "end_col", 0) or raw_len
                self.syntax_errors.append(
                    SyntaxIssue(
                        message=str(msg).replace(f"Line {err_line_1}: ", ""),
                        line=err_line_0,
                        start_col=s_col,
                        end_col=e_col,
                    )
                )
            else:
                valid_items.append(it)

        self.ast_items = valid_items
        if self.ast_items:
            try:
                self.scene_graph = to_graph(self.ast_items)
            except Exception:  # noqa: BLE001
                self.scene_graph = None
        else:
            self.scene_graph = None

    def _index_token(self, span: TokenSpan) -> None:
        """Index semantic SymbolOccurrences and scene_spans from a TokenSpan."""
        kind = span.kind
        if kind == "label_id":
            self.scene_spans[span.value] = span
            meta: dict[str, Any] = {"display_name": span.metadata.get("display_name", "")}
            if span.metadata.get("implicit"):
                meta["implicit"] = True
            self.occurrences.append(
                SymbolOccurrence(kind="label_def", name=span.value, span=span, metadata=meta)
            )
        elif kind in _LABEL_REF_KINDS:
            self.occurrences.append(SymbolOccurrence(kind="label_ref", name=span.value, span=span))
        elif kind == "speaker":
            self.occurrences.append(
                SymbolOccurrence(
                    kind="character_ref",
                    name=span.value.lower(),
                    span=span,
                    metadata={"display_name": span.value},
                )
            )
        elif kind == "emotion":
            char = span.metadata.get("character", "")
            self.occurrences.append(
                SymbolOccurrence(
                    kind="asset_ref",
                    name=f"{char}/{span.value.lower()}",
                    span=span,
                    metadata={
                        "asset_kind": "character",
                        "character": char,
                        "expression": span.value.lower(),
                    },
                )
            )
        elif kind == "character_id":
            self.occurrences.append(
                SymbolOccurrence(
                    kind="character_def",
                    name=span.value.lower(),
                    span=span,
                    metadata={
                        "name": span.metadata.get("name", ""),
                        "raw_attrs": span.metadata.get("raw_attrs", ""),
                    },
                )
            )
        elif kind == "character_name":
            self.occurrences.append(
                SymbolOccurrence(
                    kind="character_name",
                    name=span.metadata.get("character_id", ""),
                    span=span,
                    metadata={"name": span.value},
                )
            )
        elif kind == "include_path":
            self.occurrences.append(
                SymbolOccurrence(kind="include_path", name=span.value, span=span)
            )
        elif kind == "voice_path":
            self.occurrences.append(
                SymbolOccurrence(
                    kind="asset_ref",
                    name=span.value,
                    span=span,
                    metadata={"asset_kind": "voice"},
                )
            )
        elif kind == "hook_arg":
            if "asset_kind" in span.metadata:
                self.occurrences.append(
                    SymbolOccurrence(
                        kind="asset_ref",
                        name=span.value,
                        span=span,
                        metadata=dict(span.metadata),
                    )
                )
            elif "character" in span.metadata:
                self.occurrences.append(
                    SymbolOccurrence(
                        kind="character_ref",
                        name=span.metadata["character"],
                        span=span,
                        metadata={"display_name": span.value},
                    )
                )
        elif kind == "variable":
            role = span.metadata.get("role", "read")
            if role == "def":
                self.occurrences.append(
                    SymbolOccurrence(
                        kind="variable_def",
                        name=span.value,
                        span=span,
                        metadata={"default_value": span.metadata.get("default_value", "")},
                    )
                )
            elif role == "mutation":
                self.occurrences.append(
                    SymbolOccurrence(kind="variable_mutation", name=span.value, span=span)
                )
            else:
                self.occurrences.append(
                    SymbolOccurrence(kind="variable_read", name=span.value, span=span)
                )
