"""Fault-tolerant screenplay document scanner with exact token and symbol span tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import eager_script
from eager_runtime.i18n import get_beat_occurrence
from eager_script import (
    CHARACTER_PATTERN,
    CHOICE_INLINE_PATTERN,
    CHOICE_PATTERN,
    DEFAULT_PATTERN,
    ELIF_PATTERN,
    IF_PATTERN,
    SET_PATTERN,
    SPEAKER_PATTERN,
    ParsedItem,
    ParsedLabel,
    ParseError,
    SceneGraph,
    slugify,
    to_graph,
)
from lsprotocol.types import (
    DiagnosticSeverity,
    Position,
    Range,
)

_CALL_FUNC_PATTERN = re.compile(r"\b(visited|seen)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
_VAR_INTERPOLATION_PATTERN = re.compile(r"\[([A-Za-z_][A-Za-z0-9_\.]*)\]")
_TAG_PATTERN = re.compile(r"\{([^\}]+)\}")
_COLOR_TAG_PATTERN = re.compile(r"\{color=(#[0-9a-fA-F]{3,8})\}")
_BEAT_ID_TAG_PATTERN = re.compile(r"\{id=([a-zA-Z0-9_-]+)\}")
_TOKEN_PATTERN = re.compile(r'"([^"]*)"|\'([^\']*)\'|(\S+)')

__all__ = [
    "ScriptDocument",
    "SymbolOccurrence",
    "SyntaxIssue",
    "TokenSpan",
]


@dataclass(frozen=True, slots=True)
class TokenSpan:
    """A range within a document associated with a semantic token or syntax element."""

    kind: str
    start_line: int  # 0-based
    start_col: int   # 0-based
    end_line: int    # 0-based
    end_col: int     # 0-based
    value: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def range(self) -> Range:
        """Return LSP Range for this token span."""
        return Range(
            start=Position(line=self.start_line, character=self.start_col),
            end=Position(line=self.end_line, character=self.end_col),
        )

    def contains_position(self, line: int, col: int) -> bool:
        """Return True if (line, col) falls inside this span."""
        if line < self.start_line or line > self.end_line:
            return False
        if line == self.start_line and col < self.start_col:
            return False
        return not (line == self.end_line and col > self.end_col)


@dataclass(frozen=True, slots=True)
class SymbolOccurrence:
    """An indexed symbol definition or reference in the document."""

    kind: str  # "label_def" | "label_ref" | "character_def" | "character_ref" | "variable_def" | "variable_mutation" | "variable_read" | "asset_ref"
    name: str
    span: TokenSpan
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SyntaxIssue:
    """A lexical or syntactic issue detected during scanning."""

    message: str
    line: int        # 0-based
    start_col: int   # 0-based
    end_col: int     # 0-based
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
        # Return the most specific (smallest span)
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
        for item in self.ast_items:
            if getattr(item, "line_number", None) == target_line_1:
                return item
        return None

    def get_scene_at_line(self, line_0: int) -> str | None:
        """Return the scene identifier active at 0-based line_0."""
        target_line_1 = line_0 + 1
        current_scene: str | None = None
        for item in self.ast_items:
            if isinstance(item, ParsedLabel):
                if item.line_number <= target_line_1:
                    current_scene = item.name
                else:
                    break
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

        # Fallback to AST items if scene_graph is not built yet
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
        """Perform lexical token scanning and resilient AST extraction."""
        self.spans.clear()
        self.occurrences.clear()
        self.syntax_errors.clear()
        self.scene_spans.clear()

        # Step 1: Line-by-line lexical scan & token span extraction
        sanitized_lines = list(self.lines)
        for line_idx, raw_line in enumerate(self.lines):
            self._scan_line(line_idx, raw_line, sanitized_lines)

        # Step 2: Fault-tolerant AST parsing with line recovery
        self._recover_ast(sanitized_lines)

    def _scan_line(self, line_idx: int, raw_line: str, sanitized_lines: list[str]) -> None:
        line_len = len(raw_line)
        stripped = raw_line.strip()
        if not stripped:
            return

        indent = len(raw_line) - len(raw_line.lstrip(" \t"))

        # Standalone comment
        if stripped.startswith("#") and not stripped.startswith("##"):
            self.spans.append(
                TokenSpan(
                    kind="comment",
                    start_line=line_idx,
                    start_col=indent,
                    end_line=line_idx,
                    end_col=line_len,
                    value=stripped,
                )
            )
            return

        # Check inline comment (ignoring '#' inside string literals or escaped '\#')
        content_line = raw_line
        comment_span: TokenSpan | None = None
        inline_comment_idx = -1
        in_quote: str | None = None
        for idx in range(len(raw_line)):
            ch = raw_line[idx]
            if ch in ('"', "'") and (idx == 0 or raw_line[idx - 1] != "\\"):
                if in_quote == ch:
                    in_quote = None
                elif in_quote is None:
                    in_quote = ch
            elif (
                ch == "#"
                and in_quote is None
                and idx > 0
                and raw_line[idx - 1] in (" ", "\t")
                and (idx < 2 or raw_line[idx - 2] != "\\")
            ):
                inline_comment_idx = idx
                break

        if inline_comment_idx != -1:
            content_line = raw_line[:inline_comment_idx].rstrip()
            comment_text = raw_line[inline_comment_idx:]
            comment_span = TokenSpan(
                kind="comment",
                start_line=line_idx,
                start_col=inline_comment_idx,
                end_line=line_idx,
                end_col=line_len,
                value=comment_text,
            )
            self.spans.append(comment_span)

        content_stripped = content_line.strip()
        if not content_stripped:
            return

        # 1. Label: '## Title --- id' or '## Title'
        if content_stripped.startswith("##"):
            self._scan_label(line_idx, content_line, content_stripped, sanitized_lines)
            return

        # 2. Subroutine call '>>' or Return '<<' or Jump '>'
        if content_stripped.startswith(">>"):
            self._scan_call(line_idx, content_line, content_stripped, sanitized_lines)
            return
        if content_stripped.startswith("<<"):
            call_start = content_line.find("<<")
            self.spans.append(
                TokenSpan(
                    kind="return_keyword",
                    start_line=line_idx,
                    start_col=call_start,
                    end_line=line_idx,
                    end_col=call_start + 2,
                    value="<<",
                )
            )
            return
        if content_stripped.startswith(">"):
            self._scan_jump(line_idx, content_line, content_stripped, sanitized_lines)
            return

        # 3. Choice option '? '
        if content_stripped.startswith("?"):
            self._scan_choice(line_idx, content_line, content_stripped, sanitized_lines)
            return

        # 4. Engine hook '~ '
        if content_stripped.startswith("~"):
            self._scan_hook(line_idx, content_line, content_stripped, sanitized_lines)
            return

        # 5. Directives: @character, @default, @if, @elif, @else, @end
        if content_stripped.startswith("@"):
            self._scan_directive(line_idx, content_line, content_stripped, sanitized_lines)
            return

        # 6. Variable assignment '$ '
        if content_stripped.startswith("$"):
            self._scan_set(line_idx, content_line, content_stripped, sanitized_lines)
            return

        # 7. Append beat '- ' or Fresh box beat '/ '
        if content_stripped.startswith("- "):
            start_pos = content_line.find("-")
            self.spans.append(
                TokenSpan(
                    kind="append_marker",
                    start_line=line_idx,
                    start_col=start_pos,
                    end_line=line_idx,
                    end_col=start_pos + 1,
                    value="-",
                )
            )
            text_part = content_line[start_pos + 1:].strip()
            text_start = content_line.find(text_part, start_pos + 1)
            self._scan_dialogue_text(line_idx, text_part, text_start)
            return
        if content_stripped.startswith("/ "):
            start_pos = content_line.find("/")
            self.spans.append(
                TokenSpan(
                    kind="fresh_box_marker",
                    start_line=line_idx,
                    start_col=start_pos,
                    end_line=line_idx,
                    end_col=start_pos + 1,
                    value="/",
                )
            )
            text_part = content_line[start_pos + 1:].strip()
            text_start = content_line.find(text_part, start_pos + 1)
            self._scan_dialogue_text(line_idx, text_part, text_start)
            return

        # 8. Speaker dialogue or Narration
        speaker_match = SPEAKER_PATTERN.match(content_stripped)
        if speaker_match:
            line_indent = len(content_line) - len(content_line.lstrip())
            speaker_name = speaker_match.group(1)
            s_start = line_indent + speaker_match.start(1)
            s_end = line_indent + speaker_match.end(1)
            speaker_span = TokenSpan(
                kind="speaker",
                start_line=line_idx,
                start_col=s_start,
                end_line=line_idx,
                end_col=s_end,
                value=speaker_name,
            )
            self.spans.append(speaker_span)
            self.occurrences.append(
                SymbolOccurrence(
                    kind="character_ref",
                    name=speaker_name.lower(),
                    span=speaker_span,
                    metadata={"display_name": speaker_name},
                )
            )

            # Emotion
            if speaker_match.group(2):
                emotion_name = speaker_match.group(2)
                e_start = line_indent + speaker_match.start(2)
                e_end = line_indent + speaker_match.end(2)
                emotion_span = TokenSpan(
                    kind="emotion",
                    start_line=line_idx,
                    start_col=e_start,
                    end_line=line_idx,
                    end_col=e_end,
                    value=emotion_name,
                    metadata={"character": speaker_name.lower()},
                )
                self.spans.append(emotion_span)
                self.occurrences.append(
                    SymbolOccurrence(
                        kind="asset_ref",
                        name=f"{speaker_name.lower()}/{emotion_name.lower()}",
                        span=emotion_span,
                        metadata={
                            "asset_kind": "character",
                            "character": speaker_name.lower(),
                            "expression": emotion_name.lower(),
                        },
                    )
                )

            # Dialogue text after colon
            after_speaker_offset = s_end
            if speaker_match.group(2):
                after_speaker_offset = line_indent + speaker_match.end(2)
            colon_idx = content_line.find(":", after_speaker_offset)
            if colon_idx != -1:
                self.spans.append(
                    TokenSpan(
                        kind="colon",
                        start_line=line_idx,
                        start_col=colon_idx,
                        end_line=line_idx,
                        end_col=colon_idx + 1,
                        value=":",
                    )
                )
                if speaker_match.group(3):
                    text_part = speaker_match.group(3)
                    text_start = line_indent + speaker_match.start(3)
                    self._scan_dialogue_text(line_idx, text_part, text_start)
            return

        # Speakerless narration beat
        self._scan_dialogue_text(line_idx, content_stripped, content_line.find(content_stripped))

    def _scan_label(
        self, line_idx: int, content_line: str, content_stripped: str, sanitized_lines: list[str]
    ) -> None:
        start_pos = content_line.find("##")
        self.spans.append(
            TokenSpan(
                kind="label_header",
                start_line=line_idx,
                start_col=start_pos,
                end_line=line_idx,
                end_col=start_pos + 2,
                value="##",
            )
        )
        rest = content_stripped[2:].strip()
        if not rest:
            self.syntax_errors.append(
                SyntaxIssue(
                    message="Empty label definition",
                    line=line_idx,
                    start_col=start_pos,
                    end_col=len(content_line),
                )
            )
            sanitized_lines[line_idx] = "# <empty label>"
            return

        if "---" in rest:
            disp, _sep, label_id = rest.partition("---")
            disp_clean = disp.strip()
            id_clean = label_id.strip()

            if not disp_clean:
                self.syntax_errors.append(
                    SyntaxIssue(
                        message="Empty label display name",
                        line=line_idx,
                        start_col=start_pos,
                        end_col=len(content_line),
                    )
                )
                sanitized_lines[line_idx] = "# <empty display name>"
                return

            if not id_clean:
                self.syntax_errors.append(
                    SyntaxIssue(
                        message="Empty label identifier",
                        line=line_idx,
                        start_col=start_pos,
                        end_col=len(content_line),
                    )
                )
                sanitized_lines[line_idx] = "# <empty label id>"
                return

            disp_start = content_line.find(disp_clean, start_pos + 2)
            self.spans.append(
                TokenSpan(
                    kind="label_title",
                    start_line=line_idx,
                    start_col=disp_start,
                    end_line=line_idx,
                    end_col=disp_start + len(disp_clean),
                    value=disp_clean,
                    metadata={"scene_id": id_clean},
                )
            )
            sep_start = content_line.find("---", disp_start + len(disp_clean))
            self.spans.append(
                TokenSpan(
                    kind="label_sep",
                    start_line=line_idx,
                    start_col=sep_start,
                    end_line=line_idx,
                    end_col=sep_start + 3,
                    value="---",
                )
            )
            id_start = content_line.find(id_clean, sep_start + 3)
            id_span = TokenSpan(
                kind="label_id",
                start_line=line_idx,
                start_col=id_start,
                end_line=line_idx,
                end_col=id_start + len(id_clean),
                value=id_clean,
                metadata={"display_name": disp_clean, "implicit": False},
            )
            self.spans.append(id_span)
            self.scene_spans[id_clean] = id_span
            self.occurrences.append(
                SymbolOccurrence(
                    kind="label_def",
                    name=id_clean,
                    span=id_span,
                    metadata={"display_name": disp_clean},
                )
            )
        else:
            disp_clean = rest
            disp_start = content_line.find(disp_clean, start_pos + 2)
            computed_slug = slugify(disp_clean)
            if not computed_slug:
                self.syntax_errors.append(
                    SyntaxIssue(
                        message=f"Invalid label '{disp_clean}' cannot be converted to a valid identifier",
                        line=line_idx,
                        start_col=disp_start,
                        end_col=disp_start + len(disp_clean),
                    )
                )
                sanitized_lines[line_idx] = "# <invalid label>"
                return

            disp_span = TokenSpan(
                kind="label_title",
                start_line=line_idx,
                start_col=disp_start,
                end_line=line_idx,
                end_col=disp_start + len(disp_clean),
                value=disp_clean,
                metadata={"scene_id": computed_slug, "implicit": True},
            )
            self.spans.append(disp_span)
            id_span = TokenSpan(
                kind="label_id",
                start_line=line_idx,
                start_col=disp_start,
                end_line=line_idx,
                end_col=disp_start + len(disp_clean),
                value=computed_slug,
                metadata={"display_name": disp_clean, "implicit": True},
            )
            self.spans.append(id_span)
            self.scene_spans[computed_slug] = id_span
            self.occurrences.append(
                SymbolOccurrence(
                    kind="label_def",
                    name=computed_slug,
                    span=id_span,
                    metadata={"display_name": disp_clean, "implicit": True},
                )
            )

    def _scan_jump(
        self, line_idx: int, content_line: str, content_stripped: str, sanitized_lines: list[str]
    ) -> None:
        start_pos = content_line.find(">")
        self.spans.append(
            TokenSpan(
                kind="jump_keyword",
                start_line=line_idx,
                start_col=start_pos,
                end_line=line_idx,
                end_col=start_pos + 1,
                value=">",
            )
        )
        target = content_stripped[1:].strip()
        if not target:
            self.syntax_errors.append(
                SyntaxIssue(
                    message="Empty jump target",
                    line=line_idx,
                    start_col=start_pos,
                    end_col=len(content_line),
                )
            )
            sanitized_lines[line_idx] = "# <empty jump target>"
            return

        target_start = content_line.find(target, start_pos + 1)
        target_span = TokenSpan(
            kind="jump_target",
            start_line=line_idx,
            start_col=target_start,
            end_line=line_idx,
            end_col=target_start + len(target),
            value=target,
        )
        self.spans.append(target_span)
        self.occurrences.append(
            SymbolOccurrence(kind="label_ref", name=target, span=target_span)
        )

    def _scan_call(
        self, line_idx: int, content_line: str, content_stripped: str, sanitized_lines: list[str]
    ) -> None:
        start_pos = content_line.find(">>")
        self.spans.append(
            TokenSpan(
                kind="call_keyword",
                start_line=line_idx,
                start_col=start_pos,
                end_line=line_idx,
                end_col=start_pos + 2,
                value=">>",
            )
        )
        target = content_stripped[2:].strip()
        if not target:
            self.syntax_errors.append(
                SyntaxIssue(
                    message="Empty call target",
                    line=line_idx,
                    start_col=start_pos,
                    end_col=len(content_line),
                )
            )
            sanitized_lines[line_idx] = "# <empty call target>"
            return

        target_start = content_line.find(target, start_pos + 2)
        target_span = TokenSpan(
            kind="call_target",
            start_line=line_idx,
            start_col=target_start,
            end_line=line_idx,
            end_col=target_start + len(target),
            value=target,
        )
        self.spans.append(target_span)
        self.occurrences.append(
            SymbolOccurrence(kind="label_ref", name=target, span=target_span)
        )

    def _scan_choice(
        self, line_idx: int, content_line: str, content_stripped: str, sanitized_lines: list[str]
    ) -> None:
        bullet_start = content_line.find("?")
        self.spans.append(
            TokenSpan(
                kind="choice_bullet",
                start_line=line_idx,
                start_col=bullet_start,
                end_line=line_idx,
                end_col=bullet_start + 1,
                value="?",
            )
        )
        # Try full target choice pattern: ? Option (target) if cond
        indent = len(content_line) - len(content_line.lstrip(" \t"))
        m = CHOICE_PATTERN.match(content_stripped)
        if m:
            text = m.group(1).strip()
            target = m.group(2).strip()
            cond = m.group(3).strip() if m.group(3) else None

            # Option text
            t_start = indent + m.start(1)
            t_end = indent + m.end(1)
            self.spans.append(
                TokenSpan(
                    kind="choice_text",
                    start_line=line_idx,
                    start_col=t_start,
                    end_line=line_idx,
                    end_col=t_end,
                    value=text,
                )
            )
            self._scan_inline_text_spans(line_idx, text, t_start)
            # Target
            target_start = indent + m.start(2)
            target_end = indent + m.end(2)
            target_span = TokenSpan(
                kind="choice_target",
                start_line=line_idx,
                start_col=target_start,
                end_line=line_idx,
                end_col=target_end,
                value=target,
            )
            self.spans.append(target_span)
            self.occurrences.append(
                SymbolOccurrence(kind="label_ref", name=target, span=target_span)
            )
            # Condition
            if cond:
                c_start = indent + m.start(3)
                c_end = indent + m.end(3)
                self.spans.append(
                    TokenSpan(
                        kind="choice_condition",
                        start_line=line_idx,
                        start_col=c_start,
                        end_line=line_idx,
                        end_col=c_end,
                        value=cond,
                    )
                )
                self._scan_expression(line_idx, cond, c_start)
            return

        # Try inline choice pattern: ? Option if cond
        m_inline = CHOICE_INLINE_PATTERN.match(content_stripped)
        if m_inline:
            text = m_inline.group(1).strip()
            cond = m_inline.group(2).strip() if m_inline.group(2) else None
            if not text:
                self.syntax_errors.append(
                    SyntaxIssue(
                        message="Empty choice text",
                        line=line_idx,
                        start_col=bullet_start,
                        end_col=len(content_line),
                    )
                )
                sanitized_lines[line_idx] = "# <empty choice text>"
                return

            t_start = indent + m_inline.start(1)
            t_end = indent + m_inline.end(1)
            self.spans.append(
                TokenSpan(
                    kind="choice_text",
                    start_line=line_idx,
                    start_col=t_start,
                    end_line=line_idx,
                    end_col=t_end,
                    value=text,
                )
            )
            self._scan_inline_text_spans(line_idx, text, t_start)
            if cond:
                c_start = indent + m_inline.start(2)
                c_end = indent + m_inline.end(2)
                self.spans.append(
                    TokenSpan(
                        kind="choice_condition",
                        start_line=line_idx,
                        start_col=c_start,
                        end_line=line_idx,
                        end_col=c_end,
                        value=cond,
                    )
                )
                self._scan_expression(line_idx, cond, c_start)
            return

        # Syntax error on incomplete choice
        self.syntax_errors.append(
            SyntaxIssue(
                message="Invalid choice syntax. Expected '? Text (target)' or '? Text' with indented block",
                line=line_idx,
                start_col=bullet_start,
                end_col=len(content_line),
            )
        )
        sanitized_lines[line_idx] = "# <invalid choice>"

    def _scan_hook(
        self, line_idx: int, content_line: str, content_stripped: str, sanitized_lines: list[str]
    ) -> None:
        start_pos = content_line.find("~")
        self.spans.append(
            TokenSpan(
                kind="hook_marker",
                start_line=line_idx,
                start_col=start_pos,
                end_line=line_idx,
                end_col=start_pos + 1,
                value="~",
            )
        )
        hook_body = content_stripped[1:].strip()
        if not hook_body:
            self.syntax_errors.append(
                SyntaxIssue(
                    message="Empty hook name",
                    line=line_idx,
                    start_col=start_pos,
                    end_col=len(content_line),
                )
            )
            sanitized_lines[line_idx] = "# <empty hook>"
            return

        # Tokenize arguments with exact spans
        hook_start_offset = content_line.find(hook_body, start_pos + 1)
        raw_tokens: list[tuple[str, int, int]] = []
        for m in _TOKEN_PATTERN.finditer(content_line[hook_start_offset:]):
            val = m.group(1) or m.group(2) or m.group(3)
            raw_tokens.append((val, hook_start_offset + m.start(), hook_start_offset + m.end()))

        if not raw_tokens:
            return

        hook_name, h_start, h_end = raw_tokens[0]
        hook_span = TokenSpan(
            kind="hook_name",
            start_line=line_idx,
            start_col=h_start,
            end_line=line_idx,
            end_col=h_end,
            value=hook_name,
        )
        self.spans.append(hook_span)

        arg_tokens = raw_tokens[1:]
        # Analyze hook args semantically
        if hook_name in ("bg", "scene"):
            if arg_tokens:
                bg_name, b_start, b_end = arg_tokens[0]
                bg_span = TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=b_start,
                    end_line=line_idx,
                    end_col=b_end,
                    value=bg_name,
                    metadata={"asset_kind": "background"},
                )
                self.spans.append(bg_span)
                self.occurrences.append(
                    SymbolOccurrence(
                        kind="asset_ref",
                        name=bg_name,
                        span=bg_span,
                        metadata={"asset_kind": "background"},
                    )
                )
        elif hook_name in ("show", "hide", "move", "expr"):
            if arg_tokens:
                char_name, c_start, c_end = arg_tokens[0]
                char_span = TokenSpan(
                    kind="hook_arg",
                    start_line=line_idx,
                    start_col=c_start,
                    end_line=line_idx,
                    end_col=c_end,
                    value=char_name,
                    metadata={"character": char_name.lower()},
                )
                self.spans.append(char_span)
                self.occurrences.append(
                    SymbolOccurrence(
                        kind="character_ref",
                        name=char_name.lower(),
                        span=char_span,
                        metadata={"display_name": char_name},
                    )
                )

                # Optional expression sprite as 2nd positional argument
                if len(arg_tokens) > 1 and not arg_tokens[1][0].startswith(("at", "with", "to")) and "=" not in arg_tokens[1][0]:
                    expr_name, e_start, e_end = arg_tokens[1]
                    expr_span = TokenSpan(
                        kind="emotion",
                        start_line=line_idx,
                        start_col=e_start,
                        end_line=line_idx,
                        end_col=e_end,
                        value=expr_name,
                        metadata={"character": char_name.lower()},
                    )
                    self.spans.append(expr_span)
                    self.occurrences.append(
                        SymbolOccurrence(
                            kind="asset_ref",
                            name=f"{char_name.lower()}/{expr_name.lower()}",
                            span=expr_span,
                            metadata={
                                "asset_kind": "character",
                                "character": char_name.lower(),
                                "expression": expr_name.lower(),
                            },
                        )
                    )
        elif hook_name in ("play", "stop", "volume") or hook_name.startswith("play_"):
            if arg_tokens:
                first_tok, f_start, f_end = arg_tokens[0]
                # channel or track
                is_chan = first_tok in ("music", "sound", "voice", "ambient")
                if is_chan and len(arg_tokens) > 1 and "=" not in arg_tokens[1][0]:
                    track_name, t_start, t_end = arg_tokens[1]
                    track_span = TokenSpan(
                        kind="hook_arg",
                        start_line=line_idx,
                        start_col=t_start,
                        end_line=line_idx,
                        end_col=t_end,
                        value=track_name,
                        metadata={"asset_kind": "audio", "channel": first_tok},
                    )
                    self.spans.append(track_span)
                    self.occurrences.append(
                        SymbolOccurrence(
                            kind="asset_ref",
                            name=track_name,
                            span=track_span,
                            metadata={"asset_kind": "audio", "channel": first_tok},
                        )
                    )
                elif not is_chan and "=" not in first_tok:
                    chan = hook_name.replace("play_", "") if hook_name.startswith("play_") else "music"
                    track_span = TokenSpan(
                        kind="hook_arg",
                        start_line=line_idx,
                        start_col=f_start,
                        end_line=line_idx,
                        end_col=f_end,
                        value=first_tok,
                        metadata={"asset_kind": "audio", "channel": chan},
                    )
                    self.spans.append(track_span)
                    self.occurrences.append(
                        SymbolOccurrence(
                            kind="asset_ref",
                            name=first_tok,
                            span=track_span,
                            metadata={"asset_kind": "audio", "channel": chan},
                        )
                    )
        elif hook_name == "input" and arg_tokens:
            var_tok, v_start, v_end = arg_tokens[0]
            var_span = TokenSpan(
                kind="variable",
                start_line=line_idx,
                start_col=v_start,
                end_line=line_idx,
                end_col=v_end,
                value=var_tok,
            )
            self.spans.append(var_span)
            self.occurrences.append(
                SymbolOccurrence(
                    kind="variable_mutation",
                    name=var_tok,
                    span=var_span,
                )
            )

        # Remaining kwargs and keywords (at, with, to)
        for tok_val, t_start, t_end in arg_tokens:
            if tok_val in ("at", "with", "to"):
                self.spans.append(
                    TokenSpan(
                        kind="hook_keyword",
                        start_line=line_idx,
                        start_col=t_start,
                        end_line=line_idx,
                        end_col=t_end,
                        value=tok_val,
                    )
                )
            elif "=" in tok_val:
                k, _, v = tok_val.partition("=")
                k_end = t_start + len(k)
                v_start = k_end + 1
                self.spans.append(
                    TokenSpan(
                        kind="hook_kwarg_key",
                        start_line=line_idx,
                        start_col=t_start,
                        end_line=line_idx,
                        end_col=k_end,
                        value=k,
                    )
                )
                # Check color kwargs
                if v.startswith("#"):
                    self.spans.append(
                        TokenSpan(
                            kind="color_literal",
                            start_line=line_idx,
                            start_col=v_start,
                            end_line=line_idx,
                            end_col=t_end,
                            value=v,
                        )
                    )
                else:
                    self.spans.append(
                        TokenSpan(
                            kind="hook_kwarg_val",
                            start_line=line_idx,
                            start_col=v_start,
                            end_line=line_idx,
                            end_col=t_end,
                            value=v,
                        )
                    )

    def _scan_directive(
        self, line_idx: int, content_line: str, content_stripped: str, sanitized_lines: list[str]
    ) -> None:
        at_pos = content_line.find("@")
        if content_stripped.startswith("@character"):
            m = CHARACTER_PATTERN.match(content_stripped)
            if not m:
                self.syntax_errors.append(
                    SyntaxIssue(
                        message="Invalid @character definition. Expected '@character id \"Name\" key=val...'",
                        line=line_idx,
                        start_col=at_pos,
                        end_col=len(content_line),
                    )
                )
                sanitized_lines[line_idx] = "# <invalid @character>"
                return

            indent = len(content_line) - len(content_line.lstrip(" \t"))
            self.spans.append(
                TokenSpan(
                    kind="directive",
                    start_line=line_idx,
                    start_col=at_pos,
                    end_line=line_idx,
                    end_col=at_pos + len("@character"),
                    value="@character",
                )
            )
            char_id = m.group(1).strip()
            id_start = indent + m.start(1)
            id_end = indent + m.end(1)
            id_span = TokenSpan(
                kind="character_id",
                start_line=line_idx,
                start_col=id_start,
                end_line=line_idx,
                end_col=id_end,
                value=char_id,
            )
            self.spans.append(id_span)

            char_name = ""
            name_grp = 2 if m.group(2) is not None else (3 if m.group(3) is not None else None)
            if name_grp is not None:
                char_name = m.group(name_grp).strip()
                name_start = indent + m.start(name_grp)
                name_end = indent + m.end(name_grp)
                name_span = TokenSpan(
                    kind="character_name",
                    start_line=line_idx,
                    start_col=name_start,
                    end_line=line_idx,
                    end_col=name_end,
                    value=char_name,
                )
                self.spans.append(name_span)
                self.occurrences.append(
                    SymbolOccurrence(
                        kind="character_name",
                        name=char_id.lower(),
                        span=name_span,
                        metadata={"name": char_name},
                    )
                )

            # Attributes & colors
            attrs_str = m.group(4) or ""
            attrs_offset = indent + m.start(4)
            for tok_match in _TOKEN_PATTERN.finditer(attrs_str):
                tok_val = tok_match.group(1) or tok_match.group(2) or tok_match.group(3)
                if "=" in tok_val:
                    k, _, v = tok_val.partition("=")
                    if v.startswith("#"):
                        v_offset = attrs_offset + tok_match.start() + len(k) + 1
                        self.spans.append(
                            TokenSpan(
                                kind="color_literal",
                                start_line=line_idx,
                                start_col=v_offset,
                                end_line=line_idx,
                                end_col=v_offset + len(v),
                                value=v,
                            )
                        )

            self.occurrences.append(
                SymbolOccurrence(
                    kind="character_def",
                    name=char_id.lower(),
                    span=id_span,
                    metadata={"name": char_name, "raw_attrs": attrs_str},
                )
            )
            return

        if content_stripped.startswith("@default"):
            indent = len(content_line) - len(content_line.lstrip(" \t"))
            m = DEFAULT_PATTERN.match(content_stripped)
            if not m:
                self.syntax_errors.append(
                    SyntaxIssue(
                        message="Invalid @default syntax. Expected '@default name = expr'",
                        line=line_idx,
                        start_col=at_pos,
                        end_col=len(content_line),
                    )
                )
                sanitized_lines[line_idx] = "# <invalid @default>"
                return

            self.spans.append(
                TokenSpan(
                    kind="directive",
                    start_line=line_idx,
                    start_col=at_pos,
                    end_line=line_idx,
                    end_col=at_pos + len("@default"),
                    value="@default",
                )
            )
            var_name = m.group(1).strip()
            expr_val = m.group(2).strip()
            v_start = indent + m.start(1)
            v_end = indent + m.end(1)
            var_span = TokenSpan(
                kind="variable",
                start_line=line_idx,
                start_col=v_start,
                end_line=line_idx,
                end_col=v_end,
                value=var_name,
            )
            self.spans.append(var_span)
            self.occurrences.append(
                SymbolOccurrence(
                    kind="variable_def",
                    name=var_name,
                    span=var_span,
                    metadata={"default_value": expr_val},
                )
            )

            e_start = indent + m.start(2)
            e_end = indent + m.end(2)
            self.spans.append(
                TokenSpan(
                    kind="expr",
                    start_line=line_idx,
                    start_col=e_start,
                    end_line=line_idx,
                    end_col=e_end,
                    value=expr_val,
                )
            )
            self._scan_expression(line_idx, expr_val, e_start)
            return

        if content_stripped.startswith("@if"):
            indent = len(content_line) - len(content_line.lstrip(" \t"))
            m = IF_PATTERN.match(content_stripped)
            if not m or not m.group(1).strip():
                self.syntax_errors.append(
                    SyntaxIssue(
                        message="Empty @if expression",
                        line=line_idx,
                        start_col=at_pos,
                        end_col=len(content_line),
                    )
                )
                sanitized_lines[line_idx] = "# <empty @if>"
                return

            self.spans.append(
                TokenSpan(
                    kind="directive",
                    start_line=line_idx,
                    start_col=at_pos,
                    end_line=line_idx,
                    end_col=at_pos + len("@if"),
                    value="@if",
                )
            )
            expr_str = m.group(1).strip()
            e_start = indent + m.start(1)
            e_end = indent + m.end(1)
            self.spans.append(
                TokenSpan(
                    kind="expr",
                    start_line=line_idx,
                    start_col=e_start,
                    end_line=line_idx,
                    end_col=e_end,
                    value=expr_str,
                )
            )
            self._scan_expression(line_idx, expr_str, e_start)
            return

        if content_stripped.startswith("@elif"):
            indent = len(content_line) - len(content_line.lstrip(" \t"))
            m = ELIF_PATTERN.match(content_stripped)
            if not m or not m.group(1).strip():
                self.syntax_errors.append(
                    SyntaxIssue(
                        message="Empty @elif expression",
                        line=line_idx,
                        start_col=at_pos,
                        end_col=len(content_line),
                    )
                )
                sanitized_lines[line_idx] = "# <empty @elif>"
                return

            self.spans.append(
                TokenSpan(
                    kind="directive",
                    start_line=line_idx,
                    start_col=at_pos,
                    end_line=line_idx,
                    end_col=at_pos + len("@elif"),
                    value="@elif",
                )
            )
            expr_str = m.group(1).strip()
            e_start = indent + m.start(1)
            e_end = indent + m.end(1)
            self.spans.append(
                TokenSpan(
                    kind="expr",
                    start_line=line_idx,
                    start_col=e_start,
                    end_line=line_idx,
                    end_col=e_end,
                    value=expr_str,
                )
            )
            self._scan_expression(line_idx, expr_str, e_start)
            return

        if content_stripped in ("@else", "@end"):
            self.spans.append(
                TokenSpan(
                    kind="directive",
                    start_line=line_idx,
                    start_col=at_pos,
                    end_line=line_idx,
                    end_col=at_pos + len(content_stripped),
                    value=content_stripped,
                )
            )
            return

        # Unknown directive
        self.spans.append(
            TokenSpan(
                kind="directive",
                start_line=line_idx,
                start_col=at_pos,
                end_line=line_idx,
                end_col=at_pos + len(content_stripped),
                value=content_stripped,
            )
        )

    def _scan_set(
        self, line_idx: int, content_line: str, content_stripped: str, sanitized_lines: list[str]
    ) -> None:
        dollar_pos = content_line.find("$")
        self.spans.append(
            TokenSpan(
                kind="variable_set_marker",
                start_line=line_idx,
                start_col=dollar_pos,
                end_line=line_idx,
                end_col=dollar_pos + 1,
                value="$",
            )
        )
        m = SET_PATTERN.match(content_stripped)
        if not m:
            self.syntax_errors.append(
                SyntaxIssue(
                    message="Invalid variable syntax. Expected '$ var = expr'",
                    line=line_idx,
                    start_col=dollar_pos,
                    end_col=len(content_line),
                )
            )
            sanitized_lines[line_idx] = "# <invalid set>"
            return

        indent = len(content_line) - len(content_line.lstrip(" \t"))
        var_name = m.group(1).strip()
        op = m.group(2).strip()
        expr_str = m.group(3).strip()

        v_start = indent + m.start(1)
        v_end = indent + m.end(1)
        var_span = TokenSpan(
            kind="variable",
            start_line=line_idx,
            start_col=v_start,
            end_line=line_idx,
            end_col=v_end,
            value=var_name,
        )
        self.spans.append(var_span)
        self.occurrences.append(
            SymbolOccurrence(
                kind="variable_mutation",
                name=var_name,
                span=var_span,
            )
        )

        op_start = indent + m.start(2)
        op_end = indent + m.end(2)
        self.spans.append(
            TokenSpan(
                kind="set_op",
                start_line=line_idx,
                start_col=op_start,
                end_line=line_idx,
                end_col=op_end,
                value=op,
            )
        )

        e_start = indent + m.start(3)
        e_end = indent + m.end(3)
        self.spans.append(
            TokenSpan(
                kind="expr",
                start_line=line_idx,
                start_col=e_start,
                end_line=line_idx,
                end_col=e_end,
                value=expr_str,
            )
        )
        self._scan_expression(line_idx, expr_str, e_start)

    def _scan_dialogue_text(self, line_idx: int, text: str, text_start_col: int) -> None:
        """Scan inline tags, voice tags, and variable interpolations in dialogue or narration."""
        self.spans.append(
            TokenSpan(
                kind="dialogue_text",
                start_line=line_idx,
                start_col=text_start_col,
                end_line=line_idx,
                end_col=text_start_col + len(text),
                value=text,
            )
        )
        self._scan_inline_text_spans(line_idx, text, text_start_col)

    def _scan_inline_text_spans(self, line_idx: int, text: str, text_start_col: int) -> None:
        """Scan inline voice tags, beat IDs, color tags, text styling, and variable interpolations."""
        # 1. Voice tags: {voice:path}
        for m in re.finditer(r"\{voice:([^}]+)\}", text):
            v_start = text_start_col + m.start()
            v_end = text_start_col + m.end()
            path = m.group(1).strip()
            path_start = text_start_col + m.start(1)
            voice_span = TokenSpan(
                kind="voice_tag",
                start_line=line_idx,
                start_col=v_start,
                end_line=line_idx,
                end_col=v_end,
                value=m.group(0),
            )
            self.spans.append(voice_span)
            path_span = TokenSpan(
                kind="voice_path",
                start_line=line_idx,
                start_col=path_start,
                end_line=line_idx,
                end_col=path_start + len(path),
                value=path,
                metadata={"asset_kind": "voice"},
            )
            self.spans.append(path_span)
            self.occurrences.append(
                SymbolOccurrence(
                    kind="asset_ref",
                    name=path,
                    span=path_span,
                    metadata={"asset_kind": "voice"},
                )
            )

        # 2. Beat ID tags: {id=...}
        for m in _BEAT_ID_TAG_PATTERN.finditer(text):
            t_start = text_start_col + m.start()
            t_end = text_start_col + m.end()
            beat_id = m.group(1)
            self.spans.append(
                TokenSpan(
                    kind="beat_id_tag",
                    start_line=line_idx,
                    start_col=t_start,
                    end_line=line_idx,
                    end_col=t_end,
                    value=beat_id,
                )
            )

        # 3. Colors {color=#hex}
        for m in _COLOR_TAG_PATTERN.finditer(text):
            color_hex = m.group(1)
            c_start = text_start_col + m.start(1)
            self.spans.append(
                TokenSpan(
                    kind="color_literal",
                    start_line=line_idx,
                    start_col=c_start,
                    end_line=line_idx,
                    end_col=c_start + len(color_hex),
                    value=color_hex,
                )
            )

        # 4. Other inline tags: {b}, {/b}, {i}, {/i}, {size=...}, {w=...}, {p=...}
        for m in _TAG_PATTERN.finditer(text):
            full_tag = m.group(0)
            if full_tag.startswith(("{voice:", "{id=", "{color=")):
                continue
            t_start = text_start_col + m.start()
            t_end = text_start_col + m.end()
            self.spans.append(
                TokenSpan(
                    kind="text_tag",
                    start_line=line_idx,
                    start_col=t_start,
                    end_line=line_idx,
                    end_col=t_end,
                    value=full_tag,
                )
            )

        # 5. Variable interpolation: [var]
        for m in _VAR_INTERPOLATION_PATTERN.finditer(text):
            var_name = m.group(1)
            v_start = text_start_col + m.start(1)
            v_end = text_start_col + m.end(1)
            var_span = TokenSpan(
                kind="variable",
                start_line=line_idx,
                start_col=v_start,
                end_line=line_idx,
                end_col=v_end,
                value=var_name,
            )
            self.spans.append(var_span)
            self.occurrences.append(
                SymbolOccurrence(
                    kind="variable_read",
                    name=var_name,
                    span=var_span,
                )
            )

    def _scan_expression(self, line_idx: int, expr_str: str, expr_start_col: int) -> None:
        """Scan scene label refs and variable usages inside expressions."""
        # Check visited('label') or seen('label')
        for m in _CALL_FUNC_PATTERN.finditer(expr_str):
            target = m.group(2)
            t_start = expr_start_col + m.start(2)
            t_end = t_start + len(target)
            target_span = TokenSpan(
                kind="label_ref",
                start_line=line_idx,
                start_col=t_start,
                end_line=line_idx,
                end_col=t_end,
                value=target,
            )
            self.spans.append(target_span)
            self.occurrences.append(
                SymbolOccurrence(kind="label_ref", name=target, span=target_span)
            )

        # Mask out string literals with spaces of equal length to prevent matching inside strings
        clean_expr = re.sub(r"(\"[^\"]*\"|'[^']*')", lambda m: " " * len(m.group(0)), expr_str)

        # Extract identifier tokens that are variable references or builtin functions
        for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\b", clean_expr):
            ident = m.group(1)
            # Emit token span for built-in functions to support hover docs
            if ident in (
                "visited", "seen", "random", "chance", "min", "max",
                "abs", "len", "int", "str", "round"
            ):
                i_start = expr_start_col + m.start(1)
                i_end = expr_start_col + m.end(1)
                self.spans.append(
                    TokenSpan(
                        kind="builtin_func",
                        start_line=line_idx,
                        start_col=i_start,
                        end_line=line_idx,
                        end_col=i_end,
                        value=ident,
                    )
                )
                continue

            # Skip python/DSL built-in keywords
            if ident in (
                "True", "False", "None", "and", "or", "not", "is", "in", "persistent"
            ):
                continue
            i_start = expr_start_col + m.start(1)
            i_end = expr_start_col + m.end(1)
            var_span = TokenSpan(
                kind="variable",
                start_line=line_idx,
                start_col=i_start,
                end_line=line_idx,
                end_col=i_end,
                value=ident,
            )
            self.spans.append(var_span)
            self.occurrences.append(
                SymbolOccurrence(kind="variable_read", name=ident, span=var_span)
            )

    def _recover_ast(self, sanitized_lines: list[str]) -> None:
        """Attempt to parse AST items, performing error recovery if needed."""
        max_attempts = 30
        current_lines = list(sanitized_lines)

        for _ in range(max_attempts):
            text_to_parse = "\n".join(current_lines)
            try:
                self.ast_items = eager_script.parse(text_to_parse)
                break
            except ParseError as pe:
                err_line_1 = pe.line_number
                err_line_0 = max(0, err_line_1 - 1)
                # Check if we already noted this error
                already_recorded = any(
                    err.line == err_line_0 for err in self.syntax_errors
                )
                if not already_recorded:
                    raw_len = len(self.lines[err_line_0]) if err_line_0 < len(self.lines) else 0
                    self.syntax_errors.append(
                        SyntaxIssue(
                            message=str(pe).replace(f"Line {err_line_1}: ", ""),
                            line=err_line_0,
                            start_col=0,
                            end_col=raw_len,
                        )
                    )
                # Neutralize problematic line and retry
                if err_line_0 < len(current_lines):
                    line_raw = current_lines[err_line_0]
                    indent_prefix = line_raw[: len(line_raw) - len(line_raw.lstrip(" \t"))]
                    current_lines[err_line_0] = f"{indent_prefix}# <parse error recovery>"
                else:
                    break
            except Exception:  # noqa: BLE001
                break

        # Attempt to build SceneGraph from recovered items
        if self.ast_items:
            try:
                self.scene_graph = to_graph(self.ast_items)
            except Exception:  # noqa: BLE001
                self.scene_graph = None
