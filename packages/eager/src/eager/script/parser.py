"""Screenplay DSL parser for Eager-Script."""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Iterator
from dataclasses import replace

from eager.script.ast import (
    ParsedAppend,
    ParsedCall,
    ParsedCharacter,
    ParsedChoiceOption,
    ParsedChoiceSet,
    ParsedDefault,
    ParsedDialogue,
    ParsedElif,
    ParsedElse,
    ParsedEnd,
    ParsedError,
    ParsedFreshBox,
    ParsedHook,
    ParsedIf,
    ParsedInclude,
    ParsedItem,
    ParsedJump,
    ParsedLabel,
    ParsedNarration,
    ParsedReturn,
    ParsedSet,
    ParseError,
)
from eager.script.expr import ExprError, compile_expr
from eager.script.tokens import (
    _TOKEN_PATTERN,
    ParseResult,
    TokenSpan,
    emit_expression_spans,
    emit_hook_spans,
    emit_inline_text_spans,
    strip_inline_comment,
)

CHOICE_PATTERN = re.compile(r"^\?\s+(.+?)\s*\(([^()]+)\)(?:\s+if\s+(.+))?\s*$")
CHOICE_INLINE_PATTERN = re.compile(r"^\?\s+(.+?)(?:\s+if\s+(.+))?\s*$")
SPEAKER_PATTERN = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_\s\.\-\'\"]*?)(?:\s*\(([^)]+)\))?:(?:\s+(.*)|\s*)$"
)

SET_PATTERN = re.compile(r"^\$\s*([A-Za-z_][A-Za-z0-9_\.]*)\s*(\+=|-=|\*=|/=|%=|=)\s*(.+)$")
DEFAULT_PATTERN = re.compile(r"^@default\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
CHARACTER_PATTERN = re.compile(r"^@character\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:\"([^\"]*)\"|'([^']*)')?(.*)$")
IF_PATTERN = re.compile(r"^@if\s+(.+)$")
ELIF_PATTERN = re.compile(r"^@elif\s+(.+)$")
ELSE_PATTERN = re.compile(r"^@else\s*$")
END_PATTERN = re.compile(r"^@end\s*$")
INCLUDE_PATTERN = re.compile(r"^@include\s+(?:\"([^\"]+)\"|'([^']+)')\s*$")

_UNESCAPE_PATTERN = re.compile(r"\\([#:?\->\/~\\<@\$])")
_SLUG_NON_WORD = re.compile(r"[^\w\s-]")
_SLUG_DASH_SPACE = re.compile(r"[-\s]+")


def slugify(text: str) -> str:
    """Convert display name into a snake_case identifier."""
    slug = _SLUG_NON_WORD.sub("", text).strip().lower()
    return _SLUG_DASH_SPACE.sub("_", slug)


def _unescape(text: str) -> str:
    """Unescape DSL reserved characters escaped with backslash."""
    if "\\" not in text:
        return text
    return _UNESCAPE_PATTERN.sub(r"\1", text)


def _leading_indent(raw_line: str) -> int:
    """Return the number of leading space/tab characters on a raw source line."""
    stripped = raw_line.lstrip(" \t")
    if not stripped:
        return 0
    leading = raw_line[: len(raw_line) - len(stripped)]
    return len(leading.expandtabs(4))


def _adjust_span(item: ParsedItem, col_offset: int) -> ParsedItem:
    """Recursively adjust column offsets for an AST item."""
    if isinstance(item, ParsedChoiceSet):
        new_options = tuple(
            replace(
                opt,
                start_col=opt.start_col + col_offset,
                end_col=opt.end_col + col_offset,
                body=tuple(_adjust_span(b, col_offset) for b in opt.body),
            )
            for opt in item.options
        )
        return replace(
            item,
            start_col=item.start_col + col_offset,
            end_col=item.end_col + col_offset,
            options=new_options,
        )
    return replace(
        item,
        start_col=item.start_col + col_offset,
        end_col=item.end_col + col_offset,
    )


def _parse_label(line: str, line_number: int, start_col: int = 0, end_col: int = 0) -> ParsedLabel:
    """Parse a label definition ('## Name --- id' or '## Name')."""
    rest = line[2:].strip()
    if not rest:
        raise ParseError("Empty label definition", line_number, start_col, end_col)
    if "---" in rest:
        display, name = rest.split("---", 1)
        name = sys.intern(name.strip())
        display = display.strip()
        if not display:
            raise ParseError("Empty label display name", line_number, start_col, end_col)
        if not name:
            raise ParseError("Empty label identifier", line_number, start_col, end_col)
        return ParsedLabel(
            name=name,
            display_name=display,
            line_number=line_number,
            start_col=start_col,
            end_col=end_col,
        )

    slug = sys.intern(slugify(rest))
    if not slug:
        raise ParseError(
            f"Invalid label '{rest}' cannot be converted to a valid identifier",
            line_number,
            start_col,
            end_col,
        )
    return ParsedLabel(
        name=slug,
        display_name=rest,
        line_number=line_number,
        start_col=start_col,
        end_col=end_col,
    )


def _split_inline_choice(line: str) -> tuple[str, str | None, int, int, int, int] | None:
    """Split an inline choice line into (raw_text, cond, text_start, text_end, cond_start, cond_end)."""
    full = re.match(r"^\?\s+(.+?)\s*$", line)
    if not full:
        return None
    cond_match = re.match(r"^\?\s+(.+)\s+if\s+(.+?)\s*$", line)
    if cond_match:
        cond = cond_match.group(2).strip()
        try:
            compile_expr(cond)
            return (
                cond_match.group(1),
                cond,
                cond_match.start(1),
                cond_match.end(1),
                cond_match.start(2),
                cond_match.end(2),
            )
        except ExprError:
            pass
    return (full.group(1), None, full.start(1), full.end(1), 0, 0)


def _parse_choice(line: str, line_number: int, start_col: int = 0, end_col: int = 0) -> ParsedChoiceOption:
    """Parse a single choice line.

    Supports a named option (``? Text (target_label)`` / ``? Text (target_label) if cond``)
    as well as an anonymous inline option (``? Text`` / ``? Text if cond``) whose block is
    supplied by the indented lines immediately beneath it.
    """
    match = CHOICE_PATTERN.match(line)
    if match:
        text = _unescape(match.group(1).strip())
        raw_target: str | None = match.group(2).strip()
        condition = match.group(3).strip() if match.group(3) else None
    else:
        inline_parts = _split_inline_choice(line)
        if inline_parts is None:
            raise ParseError(
                "Invalid choice syntax. Expected '? Text (target_label)' or '? Text' with an indented block",
                line_number,
                start_col,
                end_col,
            )
        raw_opt_text, condition, _, _, _, _ = inline_parts
        text = _unescape(raw_opt_text.strip())
        raw_target = None

    if not text:
        raise ParseError("Empty choice text", line_number, start_col, end_col)

    target: str | None = None
    if raw_target is not None:
        if not raw_target:
            raise ParseError("Empty choice target", line_number, start_col, end_col)
        target = raw_target
    return ParsedChoiceOption(
        text=text,
        target=sys.intern(target) if target else None,
        line_number=line_number,
        condition=condition,
        start_col=start_col,
        end_col=end_col,
    )


def _parse_dialogue(
    speaker: str,
    raw_text: str,
    emotion: str | None,
    line_number: int,
    start_col: int = 0,
    end_col: int = 0,
) -> ParsedDialogue:
    """Extract optional voice tag and return ParsedDialogue."""
    voice: str | None = None
    text = raw_text.strip()
    if text.startswith("{voice:"):
        end_idx = text.find("}", 7)
        if end_idx != -1:
            v = text[7:end_idx].strip()
            if v:
                voice = v
                text = text[end_idx + 1:].strip()
    return ParsedDialogue(
        speaker=sys.intern(_unescape(speaker)),
        text=_unescape(text),
        voice=voice,
        line_number=line_number,
        emotion=sys.intern(emotion) if emotion else None,
        start_col=start_col,
        end_col=end_col,
    )


class ScreenplayParser:
    """Parses Eager-Script screenplay text into a sequence of parsed AST items.

    Supports the full DSL: hooks, subroutine calls, fresh-box/append
    beats, voice tags, and explicit label identifiers.
    """

    def __init__(self, *, recovery: bool = False, collect_tokens: bool = False) -> None:
        self.recovery = recovery
        self._collect_tokens = collect_tokens
        self.tokens: list[TokenSpan] = []
        self._narration_buffer: list[str] = []
        self._narration_line: int = 0
        self._narration_start_col: int = 0
        self._narration_end_col: int = 0
        self._choice_buffer: list[ParsedChoiceOption] = []
        self._choice_bodies: list[list[ParsedItem]] = []

    # ------------------------------------------------------------------
    # Flush helpers — each returns a list so both parse() and parse_iter()
    # can consume the result uniformly.
    # ------------------------------------------------------------------

    def _flush_narration(self) -> list[ParsedItem]:
        if self._narration_buffer:
            combined = (
                self._narration_buffer[0]
                if len(self._narration_buffer) == 1
                else " ".join(self._narration_buffer)
            )
            self._narration_buffer.clear()
            return [
                ParsedNarration(
                    text=_unescape(combined),
                    line_number=self._narration_line,
                    start_col=self._narration_start_col,
                    end_col=self._narration_end_col,
                )
            ]
        return []

    def _flush_choices(self) -> list[ParsedItem]:
        if self._choice_buffer:
            first_line = self._choice_buffer[0].line_number
            first_start = self._choice_buffer[0].start_col
            last_end = self._choice_buffer[-1].end_col
            options: list[ParsedChoiceOption] = []
            try:
                for opt, body in zip(self._choice_buffer, self._choice_bodies):
                    if opt.target is None and not body:
                        raise ParseError(
                            f"Invalid choice syntax: option '{opt.text}' needs a '(target)' or an indented block",
                            opt.line_number,
                            opt.start_col,
                            opt.end_col,
                        )
                    if opt.target is not None and body:
                        raise ParseError(
                            f"Choice option '{opt.text}' cannot combine a '(target)' with an indented block",
                            opt.line_number,
                            opt.start_col,
                            opt.end_col,
                        )
                    options.append(replace(opt, body=tuple(body)) if body else opt)
            finally:
                self._choice_buffer.clear()
                self._choice_bodies.clear()
            return [
                ParsedChoiceSet(
                    options=tuple(options),
                    line_number=first_line,
                    start_col=first_start,
                    end_col=last_end,
                )
            ]
        return []

    def _flush_all(self) -> list[ParsedItem]:
        items: list[ParsedItem] = []
        items.extend(self._flush_narration())
        items.extend(self._flush_choices())
        return items

    def _emit(self, span: TokenSpan) -> None:
        """Append a TokenSpan when token collection is enabled."""
        if self._collect_tokens:
            self.tokens.append(span)

    def _emit_label_tokens(self, clean: str, line_0: int, start_col: int) -> None:
        """Emit TokenSpans for a '##' label line."""
        self.tokens.append(
            TokenSpan("label_header", line_0, start_col, line_0, start_col + 2, "##")
        )
        rest = clean[2:].strip()
        if not rest:
            return
        if "---" in rest:
            disp, _sep, label_id = rest.partition("---")
            disp_clean = disp.strip()
            id_clean = label_id.strip()
            if not disp_clean or not id_clean:
                return
            disp_start = start_col + clean.find(disp_clean, 2)
            self.tokens.append(
                TokenSpan(
                    "label_title",
                    line_0,
                    disp_start,
                    line_0,
                    disp_start + len(disp_clean),
                    disp_clean,
                    {"scene_id": id_clean},
                )
            )
            sep_start = start_col + clean.find("---", disp_start - start_col + len(disp_clean))
            self.tokens.append(TokenSpan("label_sep", line_0, sep_start, line_0, sep_start + 3, "---"))
            id_start = start_col + clean.find(id_clean, sep_start - start_col + 3)
            self.tokens.append(
                TokenSpan(
                    "label_id",
                    line_0,
                    id_start,
                    line_0,
                    id_start + len(id_clean),
                    id_clean,
                    {"display_name": disp_clean, "implicit": False},
                )
            )
            return

        computed_slug = slugify(rest)
        if not computed_slug:
            return
        disp_start = start_col + clean.find(rest, 2)
        self.tokens.append(
            TokenSpan(
                "label_title",
                line_0,
                disp_start,
                line_0,
                disp_start + len(rest),
                rest,
                {"scene_id": computed_slug, "implicit": True},
            )
        )
        self.tokens.append(
            TokenSpan(
                "label_id",
                line_0,
                disp_start,
                line_0,
                disp_start + len(rest),
                computed_slug,
                {"display_name": rest, "implicit": True},
            )
        )

    def _build_choice(
        self, clean: str, idx: int, start_col: int = 0, end_col: int = 0
    ) -> ParsedChoiceOption:
        """Parse a ``?`` line into a :class:`ParsedChoiceOption`."""
        if self._collect_tokens:
            line_0 = idx - 1
            self.tokens.append(
                TokenSpan("choice_bullet", line_0, start_col, line_0, start_col + 1, "?")
            )
            m = CHOICE_PATTERN.match(clean)
            if m:
                raw_opt_text = m.group(1).strip()
                t_start = start_col + m.start(1)
                self.tokens.append(
                    TokenSpan("choice_text", line_0, t_start, line_0, start_col + m.end(1), raw_opt_text)
                )
                emit_inline_text_spans(self.tokens, line_0, raw_opt_text, t_start)
                raw_target = m.group(2).strip()
                self.tokens.append(
                    TokenSpan(
                        "choice_target",
                        line_0,
                        start_col + m.start(2),
                        line_0,
                        start_col + m.end(2),
                        raw_target,
                    )
                )
                if m.group(3):
                    cond = m.group(3).strip()
                    c_start = start_col + m.start(3)
                    self.tokens.append(
                        TokenSpan("choice_condition", line_0, c_start, line_0, start_col + m.end(3), cond)
                    )
                    emit_expression_spans(self.tokens, line_0, cond, c_start)
            else:
                inline_parts = _split_inline_choice(clean)
                if inline_parts and inline_parts[0].strip():
                    raw_opt_grp, cond_grp, m_t_start, m_t_end, m_c_start, m_c_end = inline_parts
                    raw_opt_text = raw_opt_grp.strip()
                    t_start = start_col + m_t_start
                    self.tokens.append(
                        TokenSpan(
                            "choice_text", line_0, t_start, line_0, start_col + m_t_end, raw_opt_text
                        )
                    )
                    emit_inline_text_spans(self.tokens, line_0, raw_opt_text, t_start)
                    if cond_grp:
                        c_start = start_col + m_c_start
                        self.tokens.append(
                            TokenSpan(
                                "choice_condition",
                                line_0,
                                c_start,
                                line_0,
                                start_col + m_c_end,
                                cond_grp,
                            )
                        )
                        emit_expression_spans(self.tokens, line_0, cond_grp, c_start)
        return _parse_choice(clean, idx, start_col=start_col, end_col=end_col)

    def _parse_prefixed(
        self, line: str, idx: int, start_col: int = 0, end_col: int = 0
    ) -> ParsedItem | None:
        """Dispatch a line whose first character is a control symbol.

        Returns the parsed item, or *None* when the prefix is not a recognised
        control sequence (e.g. a bare ``<``) so the caller can fall through to
        the dialogue / narration logic.
        """
        line_0 = idx - 1
        collect = self._collect_tokens

        if line.startswith("##"):
            if collect:
                self._emit_label_tokens(line, line_0, start_col)
            return _parse_label(line, idx, start_col=start_col, end_col=end_col)
        elif line.startswith(">>"):
            if collect:
                self.tokens.append(
                    TokenSpan("call_keyword", line_0, start_col, line_0, start_col + 2, ">>")
                )
            target = line[2:].strip()
            if not target:
                raise ParseError("Empty call target", idx, start_col, end_col)
            if collect:
                t_start = start_col + line.find(target, 2)
                self.tokens.append(
                    TokenSpan("call_target", line_0, t_start, line_0, t_start + len(target), target)
                )
            return ParsedCall(
                target=sys.intern(target),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("<<"):
            if collect:
                self.tokens.append(
                    TokenSpan("return_keyword", line_0, start_col, line_0, start_col + 2, "<<")
                )
            return ParsedReturn(line_number=idx, start_col=start_col, end_col=end_col)
        elif line.startswith(">"):
            if collect:
                self.tokens.append(
                    TokenSpan("jump_keyword", line_0, start_col, line_0, start_col + 1, ">")
                )
            target = line[1:].strip()
            if not target:
                raise ParseError("Empty jump target", idx, start_col, end_col)
            if collect:
                t_start = start_col + line.find(target, 1)
                self.tokens.append(
                    TokenSpan("jump_target", line_0, t_start, line_0, t_start + len(target), target)
                )
            return ParsedJump(
                target=sys.intern(target),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("~"):
            if collect:
                self.tokens.append(
                    TokenSpan("hook_marker", line_0, start_col, line_0, start_col + 1, "~")
                )
            hook = line[1:].strip()
            if not hook:
                raise ParseError("Empty hook name", idx, start_col, end_col)
            if collect:
                hook_offset = line.find(hook, 1)
                emit_hook_spans(self.tokens, line_0, line, hook_offset)
                # Shift hook spans emitted relative to `line` by `start_col`
                if start_col:
                    self._shift_recent_tokens_after(line_0, start_col)
            return ParsedHook(
                hook_name=hook,
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("-"):
            if collect:
                self.tokens.append(
                    TokenSpan("append_marker", line_0, start_col, line_0, start_col + 1, "-")
                )
                text_part = line[1:].strip()
                if text_part:
                    t_start = start_col + line.find(text_part, 1)
                    self.tokens.append(
                        TokenSpan(
                            "dialogue_text",
                            line_0,
                            t_start,
                            line_0,
                            t_start + len(text_part),
                            text_part,
                        )
                    )
                    emit_inline_text_spans(self.tokens, line_0, text_part, t_start)
            return ParsedAppend(
                text=_unescape(line[1:].strip()),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("/"):
            if collect:
                self.tokens.append(
                    TokenSpan("fresh_box_marker", line_0, start_col, line_0, start_col + 1, "/")
                )
                text_part = line[1:].strip()
                if text_part:
                    t_start = start_col + line.find(text_part, 1)
                    self.tokens.append(
                        TokenSpan(
                            "dialogue_text",
                            line_0,
                            t_start,
                            line_0,
                            t_start + len(text_part),
                            text_part,
                        )
                    )
                    emit_inline_text_spans(self.tokens, line_0, text_part, t_start)
            return ParsedFreshBox(
                text=_unescape(line[1:].strip()),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("$"):
            if collect:
                self.tokens.append(
                    TokenSpan("variable_set_marker", line_0, start_col, line_0, start_col + 1, "$")
                )
            match = SET_PATTERN.match(line)
            if not match:
                raise ParseError(
                    "Invalid variable syntax. Expected '$ target = expr' or '$ target += expr'",
                    idx,
                    start_col,
                    end_col,
                )
            target, op, expr_src = match.groups()
            target_clean = target.strip()
            op_clean = op.strip()
            expr_clean = expr_src.strip()
            if collect:
                self.tokens.append(
                    TokenSpan(
                        "variable",
                        line_0,
                        start_col + match.start(1),
                        line_0,
                        start_col + match.end(1),
                        target_clean,
                        {"role": "mutation"},
                    )
                )
                self.tokens.append(
                    TokenSpan(
                        "set_op",
                        line_0,
                        start_col + match.start(2),
                        line_0,
                        start_col + match.end(2),
                        op_clean,
                    )
                )
                e_start = start_col + match.start(3)
                self.tokens.append(
                    TokenSpan(
                        "expr",
                        line_0,
                        e_start,
                        line_0,
                        start_col + match.end(3),
                        expr_clean,
                    )
                )
                emit_expression_spans(self.tokens, line_0, expr_clean, e_start)
            return ParsedSet(
                target=target_clean,
                op=op_clean,
                expr_src=expr_clean,
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("@"):
            if line.startswith("@default"):
                match = DEFAULT_PATTERN.match(line)
                if not match:
                    raise ParseError(
                        "Invalid @default syntax. Expected '@default name = expr'",
                        idx,
                        start_col,
                        end_col,
                    )
                name, expr_src = match.groups()
                var_name = name.strip()
                expr_clean = expr_src.strip()
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + 8, "@default")
                    )
                    self.tokens.append(
                        TokenSpan(
                            "variable",
                            line_0,
                            start_col + match.start(1),
                            line_0,
                            start_col + match.end(1),
                            var_name,
                            {"role": "def", "default_value": expr_clean},
                        )
                    )
                    e_start = start_col + match.start(2)
                    self.tokens.append(
                        TokenSpan(
                            "expr",
                            line_0,
                            e_start,
                            line_0,
                            start_col + match.end(2),
                            expr_clean,
                        )
                    )
                    emit_expression_spans(self.tokens, line_0, expr_clean, e_start)
                return ParsedDefault(
                    name=var_name,
                    expr_src=expr_clean,
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@character"):
                match = CHARACTER_PATTERN.match(line)
                if not match:
                    raise ParseError(
                        "Invalid @character definition. Expected '@character id \"Name\" key=value ...'",
                        idx,
                        start_col,
                        end_col,
                    )
                char_id, name_d, name_s, rest = match.groups()
                char_id_clean = char_id.strip()
                display_name = (name_d or name_s or char_id).strip()
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + 10, "@character")
                    )
                    self.tokens.append(
                        TokenSpan(
                            "character_id",
                            line_0,
                            start_col + match.start(1),
                            line_0,
                            start_col + match.end(1),
                            char_id_clean,
                            {"name": name_d or name_s or "", "raw_attrs": rest or ""},
                        )
                    )
                    name_grp = 2 if name_d is not None else (3 if name_s is not None else None)
                    if name_grp is not None:
                        self.tokens.append(
                            TokenSpan(
                                "character_name",
                                line_0,
                                start_col + match.start(name_grp),
                                line_0,
                                start_col + match.end(name_grp),
                                match.group(name_grp).strip(),
                                {"character_id": char_id_clean.lower()},
                            )
                        )
                    if rest:
                        attrs_offset = start_col + match.start(4)
                        for tok_match in _TOKEN_PATTERN.finditer(rest):
                            tok_val = tok_match.group(1) or tok_match.group(2) or tok_match.group(3)
                            if "=" in tok_val:
                                k, _, v = tok_val.partition("=")
                                if v.startswith("#"):
                                    v_offset = attrs_offset + tok_match.start() + len(k) + 1
                                    self.tokens.append(
                                        TokenSpan(
                                            "color_literal",
                                            line_0,
                                            v_offset,
                                            line_0,
                                            v_offset + len(v),
                                            v,
                                        )
                                    )
                attrs: list[tuple[str, str]] = []
                if rest:
                    try:
                        tokens = shlex.split(rest)
                    except ValueError:
                        tokens = rest.split()
                    for token in tokens:
                        if "=" in token:
                            k, v = token.split("=", 1)
                            attrs.append((k.strip(), v.strip().strip("\"'")))
                return ParsedCharacter(
                    id=char_id_clean,
                    name=display_name,
                    attrs=tuple(attrs),
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@if"):
                match = IF_PATTERN.match(line)
                if not match or not match.group(1).strip():
                    raise ParseError("Empty @if expression", idx, start_col, end_col)
                expr_clean = match.group(1).strip()
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + 3, "@if")
                    )
                    e_start = start_col + match.start(1)
                    self.tokens.append(
                        TokenSpan("expr", line_0, e_start, line_0, start_col + match.end(1), expr_clean)
                    )
                    emit_expression_spans(self.tokens, line_0, expr_clean, e_start)
                return ParsedIf(
                    expr_src=expr_clean,
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@elif"):
                match = ELIF_PATTERN.match(line)
                if not match or not match.group(1).strip():
                    raise ParseError("Empty @elif expression", idx, start_col, end_col)
                expr_clean = match.group(1).strip()
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + 5, "@elif")
                    )
                    e_start = start_col + match.start(1)
                    self.tokens.append(
                        TokenSpan("expr", line_0, e_start, line_0, start_col + match.end(1), expr_clean)
                    )
                    emit_expression_spans(self.tokens, line_0, expr_clean, e_start)
                return ParsedElif(
                    expr_src=expr_clean,
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@else"):
                if not ELSE_PATTERN.match(line):
                    raise ParseError("Invalid @else syntax. Expected '@else'", idx, start_col, end_col)
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + 5, "@else")
                    )
                return ParsedElse(line_number=idx, start_col=start_col, end_col=end_col)
            elif line.startswith("@end"):
                if not END_PATTERN.match(line):
                    raise ParseError("Invalid @end syntax. Expected '@end'", idx, start_col, end_col)
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + 4, "@end")
                    )
                return ParsedEnd(line_number=idx, start_col=start_col, end_col=end_col)
            elif line.startswith("@include"):
                match = INCLUDE_PATTERN.match(line)
                if not match:
                    raise ParseError(
                        "Invalid @include syntax. Expected '@include \"filename.es\"'",
                        idx,
                        start_col,
                        end_col,
                    )
                path_grp = 1 if match.group(1) is not None else 2
                inc_path = match.group(path_grp)
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + 8, "@include")
                    )
                    self.tokens.append(
                        TokenSpan(
                            "include_path",
                            line_0,
                            start_col + match.start(path_grp),
                            line_0,
                            start_col + match.end(path_grp),
                            inc_path,
                        )
                    )
                return ParsedInclude(
                    path=inc_path.strip(),
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            else:
                if collect:
                    self.tokens.append(
                        TokenSpan("directive", line_0, start_col, line_0, start_col + len(line), line)
                    )
                raise ParseError(f"Unknown directive '{line.split()[0]}'", idx, start_col, end_col)
        return None  # e.g. bare '<' — not a control sequence

    # ------------------------------------------------------------------
    # Shared parse loop
    # ------------------------------------------------------------------

    def _iter_raw_lines(self, text: str) -> Iterator[tuple[int, str]]:
        """Yield ``(line_number, raw_line)`` pairs without splitting the whole text."""
        start = 0
        text_len = len(text)
        find = text.find
        idx = 0

        while start < text_len:
            idx += 1
            end = find("\n", start)
            if end == -1:
                raw_line = text[start:]
                start = text_len
            else:
                if end > start and text[end - 1] == "\r":
                    raw_line = text[start : end - 1]
                else:
                    raw_line = text[start:end]
                start = end + 1
            yield idx, raw_line

    def _shift_recent_tokens_after(self, line_0: int, col_offset: int) -> None:
        """Shift TokenSpans on line_0 emitted after the leading marker by col_offset."""
        for i in range(len(self.tokens) - 1, -1, -1):
            tok = self.tokens[i]
            if tok.start_line != line_0 or tok.kind == "hook_marker":
                break
            self.tokens[i] = replace(
                tok,
                start_col=tok.start_col + col_offset,
                end_col=tok.end_col + col_offset,
            )

    def _parse_inline_block(
        self, block: list[tuple[int, str]]
    ) -> tuple[tuple[ParsedItem, ...], list[ParsedError]]:
        """Parse an indented choice block into anonymous-scene body items.

        The block is dedented to its first line and re-parsed so nested control
        lines and inline blocks keep their relative structure. Source line
        numbers are preserved by offsetting the dedented text.
        """
        first_line = block[0][0]
        base_indent = 0
        for _, raw in block:
            if raw.strip():
                base_indent = _leading_indent(raw)
                break

        stripped: list[str] = []
        col_deltas: dict[int, int] = {}
        for line_num, raw in block:
            if not raw.strip():
                stripped.append("")
                col_deltas[line_num - 1] = 0
                continue
            indent_len = len(raw) - len(raw.lstrip(" \t"))
            expanded_prefix = raw[:indent_len].expandtabs(4)
            expanded_line = expanded_prefix + raw[indent_len:]
            if len(expanded_prefix) >= base_indent:
                stripped_line = expanded_line[base_indent:]
            else:
                stripped_line = raw.lstrip()
            stripped.append(stripped_line)
            nested_indent = len(stripped_line) - len(stripped_line.lstrip(" \t"))
            col_deltas[line_num - 1] = indent_len - nested_indent

        text = "\n" * (first_line - 1) + "\n".join(stripped)
        sub_parser = type(self)(recovery=self.recovery, collect_tokens=self._collect_tokens)
        nested = sub_parser.parse(text)

        if self._collect_tokens:
            for tok in sub_parser.tokens:
                delta = col_deltas.get(tok.start_line, base_indent)
                self.tokens.append(
                    replace(
                        tok,
                        start_col=tok.start_col + delta,
                        end_col=tok.end_col + delta,
                    )
                )

        valid_items: list[ParsedItem] = []
        inline_errors: list[ParsedError] = []
        for item in nested:
            if isinstance(item, ParsedError):
                inline_errors.append(
                    replace(
                        item,
                        start_col=item.start_col + base_indent,
                        end_col=item.end_col + base_indent,
                    )
                )
                continue
            if isinstance(item, (ParsedLabel, ParsedDefault, ParsedCharacter)):
                if self.recovery:
                    inline_errors.append(
                        ParsedError(
                            message="Scene labels and preamble directives are not allowed inside an inline choice block",
                            line_number=item.line_number,
                            start_col=item.start_col + base_indent,
                            end_col=item.end_col + base_indent,
                        )
                    )
                    continue
                raise ParseError(
                    "Scene labels and preamble directives are not allowed inside an inline choice block",
                    item.line_number,
                    item.start_col,
                    item.end_col,
                )
            valid_items.append(_adjust_span(item, base_indent))
        return tuple(valid_items), inline_errors

    def _parse(self, text: str) -> Iterator[ParsedItem]:
        """Shared line-by-line parse loop yielding AST items."""
        self.tokens.clear()
        self._narration_buffer.clear()
        self._narration_line = 0
        self._narration_start_col = 0
        self._narration_end_col = 0
        self._choice_buffer.clear()
        self._choice_bodies.clear()

        line_iter = self._iter_raw_lines(text)
        pending: tuple[int, str] | None = None

        while True:
            if pending is not None:
                idx, raw_line = pending
                pending = None
            else:
                nxt = next(line_iter, None)
                if nxt is None:
                    break
                idx, raw_line = nxt

            if not raw_line.strip():
                yield from self._flush_all()
                continue

            content_line, comment_col = strip_inline_comment(raw_line)
            if comment_col is not None and self._collect_tokens:
                line_0 = idx - 1
                self.tokens.append(
                    TokenSpan(
                        "comment",
                        line_0,
                        comment_col,
                        line_0,
                        len(raw_line),
                        raw_line[comment_col:],
                    )
                )

            clean = content_line.strip()
            if not clean:
                if not (comment_col is not None and self._choice_buffer):
                    yield from self._flush_all()
                continue

            start_col = len(content_line) - len(content_line.lstrip(" \t"))
            end_col = start_col + len(clean)
            c0 = clean[0]

            # ── Flush choices before processing non-choice lines ──────
            if c0 != "?" and self._choice_buffer:
                try:
                    yield from self._flush_choices()
                except ParseError as pe:
                    if self.recovery:
                        yield ParsedError(
                            message=str(pe),
                            line_number=pe.line_number,
                            line_text=clean,
                            start_col=getattr(pe, "start_col", start_col),
                            end_col=getattr(pe, "end_col", end_col),
                        )
                    else:
                        raise

            try:
                # ── Choice (?) ──────────────────────────────────────────
                if c0 == "?":
                    if self._narration_buffer:
                        yield from self._flush_narration()
                    choice_opt = self._build_choice(clean, idx, start_col=start_col, end_col=end_col)
                    choice_indent = _leading_indent(raw_line)

                    # Look ahead for an indented inline block attached to this option
                    block: list[tuple[int, str]] = []
                    leading_blanks: list[tuple[int, str]] = []
                    while True:
                        nxt = next(line_iter, None)
                        if nxt is None:
                            break
                        nidx, nraw = nxt
                        nclean = nraw.strip()
                        if not nclean:
                            if block:
                                block.append((nidx, nraw))
                            else:
                                leading_blanks.append((nidx, nraw))
                            continue
                        if _leading_indent(nraw) > choice_indent:
                            if leading_blanks:
                                block.extend(leading_blanks)
                                leading_blanks.clear()
                            block.append((nidx, nraw))
                        else:
                            pending = (nidx, nraw)
                            break

                    while block and not block[-1][1].strip():
                        block.pop()

                    if block:
                        if choice_opt.target is not None:
                            raise ParseError(
                                f"Choice option '{choice_opt.text}' cannot combine a '(target)' with an indented block",
                                choice_opt.line_number,
                                choice_opt.start_col,
                                choice_opt.end_col,
                            )
                        body_items, inline_errors = self._parse_inline_block(block)
                        self._choice_buffer.append(choice_opt)
                        self._choice_bodies.append(list(body_items))
                        if inline_errors:
                            yield from inline_errors
                    else:
                        if choice_opt.target is None:
                            raise ParseError(
                                f"Invalid choice syntax: option '{choice_opt.text}' needs a '(target)' or an indented block",
                                choice_opt.line_number,
                                choice_opt.start_col,
                                choice_opt.end_col,
                            )
                        self._choice_buffer.append(choice_opt)
                        self._choice_bodies.append([])
                        if leading_blanks:
                            yield from self._flush_choices()
                    continue

                # ── Prefixed control lines (## >> << > ~ - / $ @) ─────
                if c0 in "#><~-/$@":
                    item = self._parse_prefixed(clean, idx, start_col=start_col, end_col=end_col)
                    if item is not None:
                        if self._narration_buffer:
                            yield from self._flush_narration()
                        yield item
                        continue

                # ── Dialogue (Speaker: text) ───────────────────────────
                if ":" in clean:
                    match = SPEAKER_PATTERN.match(clean)
                    if match:
                        speaker, emotion, raw_text = match.groups()
                        if self._narration_buffer:
                            yield from self._flush_narration()
                        if self._collect_tokens:
                            line_0 = idx - 1
                            s_start = start_col + match.start(1)
                            s_end = start_col + match.end(1)
                            self.tokens.append(
                                TokenSpan("speaker", line_0, s_start, line_0, s_end, speaker)
                            )
                            after_speaker = s_end
                            if emotion:
                                e_start = start_col + match.start(2)
                                e_end = start_col + match.end(2)
                                self.tokens.append(
                                    TokenSpan(
                                        "emotion",
                                        line_0,
                                        e_start,
                                        line_0,
                                        e_end,
                                        emotion,
                                        {"character": speaker.lower()},
                                    )
                                )
                                after_speaker = e_end
                            colon_idx = content_line.find(":", after_speaker)
                            if colon_idx != -1:
                                self.tokens.append(
                                    TokenSpan("colon", line_0, colon_idx, line_0, colon_idx + 1, ":")
                                )
                                if raw_text:
                                    t_start = start_col + match.start(3)
                                    self.tokens.append(
                                        TokenSpan(
                                            "dialogue_text",
                                            line_0,
                                            t_start,
                                            line_0,
                                            t_start + len(raw_text),
                                            raw_text,
                                        )
                                    )
                                    emit_inline_text_spans(self.tokens, line_0, raw_text, t_start)
                        text_content = (raw_text or "").strip()
                        yield _parse_dialogue(
                            speaker.strip(),
                            text_content,
                            emotion,
                            idx,
                            start_col=start_col,
                            end_col=end_col,
                        )
                        continue

                # ── Narration ──────────────────────────────────────────
                if self._collect_tokens:
                    line_0 = idx - 1
                    self.tokens.append(
                        TokenSpan(
                            "dialogue_text",
                            line_0,
                            start_col,
                            line_0,
                            start_col + len(clean),
                            clean,
                        )
                    )
                    emit_inline_text_spans(self.tokens, line_0, clean, start_col)
                if not self._narration_buffer:
                    self._narration_line = idx
                    self._narration_start_col = start_col
                self._narration_end_col = end_col
                self._narration_buffer.append(clean)
            except ParseError as pe:
                if self.recovery:
                    yield ParsedError(
                        message=str(pe),
                        line_number=pe.line_number,
                        line_text=clean,
                        start_col=getattr(pe, "start_col", start_col),
                        end_col=getattr(pe, "end_col", end_col),
                    )
                    continue
                raise

        try:
            yield from self._flush_all()
        except ParseError as pe:
            if self.recovery:
                yield ParsedError(
                    message=str(pe),
                    line_number=pe.line_number,
                    start_col=getattr(pe, "start_col", 0),
                    end_col=getattr(pe, "end_col", 0),
                )
            else:
                raise

    def parse(self, text: str) -> list[ParsedItem]:
        """Parse screenplay text into a list of parsed items."""
        return list(self._parse(text))

    def parse_iter(self, text: str) -> Iterator[ParsedItem]:
        """Stream parsed AST items from screenplay text with O(1) memory."""
        return self._parse(text)


def parse(text: str, *, recovery: bool = False) -> list[ParsedItem]:
    """Parse screenplay text into AST items."""
    return ScreenplayParser(recovery=recovery).parse(text)


def parse_iter(text: str, *, recovery: bool = False) -> Iterator[ParsedItem]:
    """Stream screenplay text into AST items with O(1) memory."""
    return ScreenplayParser(recovery=recovery).parse_iter(text)


def parse_with_tokens(text: str, *, recovery: bool = False) -> ParseResult:
    """Parse screenplay text and return both AST items and lexical TokenSpans."""
    parser = ScreenplayParser(recovery=recovery, collect_tokens=True)
    items = parser.parse(text)
    return ParseResult(items=items, spans=list(parser.tokens))


__all__ = [
    "CHARACTER_PATTERN",
    "CHOICE_INLINE_PATTERN",
    "CHOICE_PATTERN",
    "DEFAULT_PATTERN",
    "ELIF_PATTERN",
    "ELSE_PATTERN",
    "END_PATTERN",
    "IF_PATTERN",
    "INCLUDE_PATTERN",
    "SET_PATTERN",
    "SPEAKER_PATTERN",
    "ParseResult",
    "ScreenplayParser",
    "TokenSpan",
    "parse",
    "parse_iter",
    "parse_with_tokens",
    "slugify",
]
