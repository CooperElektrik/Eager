"""Screenplay DSL parser for Eager-Script."""

from __future__ import annotations

import re
import shlex
import sys
from collections.abc import Iterator
from dataclasses import replace

from eager_script.ast import (
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

_INLINE_COMMENT_PATTERN = re.compile(r"(?<!\\)\s+#(\s.*)?$")
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
        inline_match = CHOICE_INLINE_PATTERN.match(line)
        if not inline_match:
            raise ParseError(
                "Invalid choice syntax. Expected '? Text (target_label)' or '? Text' with an indented block",
                line_number,
                start_col,
                end_col,
            )
        text = _unescape(inline_match.group(1).strip())
        raw_target = None
        condition = inline_match.group(2).strip() if inline_match.group(2) else None

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

    def __init__(self, *, recovery: bool = False) -> None:
        self.recovery = recovery
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

    def _build_choice(
        self, clean: str, idx: int, start_col: int = 0, end_col: int = 0
    ) -> ParsedChoiceOption:
        """Parse a ``?`` line into a :class:`ParsedChoiceOption`."""
        return _parse_choice(clean, idx, start_col=start_col, end_col=end_col)

    def _parse_prefixed(
        self, line: str, idx: int, start_col: int = 0, end_col: int = 0
    ) -> ParsedItem | None:
        """Dispatch a line whose first character is a control symbol.

        Returns the parsed item, or *None* when the prefix is not a recognised
        control sequence (e.g. a bare ``<``) so the caller can fall through to
        the dialogue / narration logic.
        """
        if line.startswith("##"):
            return _parse_label(line, idx, start_col=start_col, end_col=end_col)
        elif line.startswith(">>"):
            target = line[2:].strip()
            if not target:
                raise ParseError("Empty call target", idx, start_col, end_col)
            return ParsedCall(
                target=sys.intern(target),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("<<"):
            return ParsedReturn(line_number=idx, start_col=start_col, end_col=end_col)
        elif line.startswith(">"):
            target = line[1:].strip()
            if not target:
                raise ParseError("Empty jump target", idx, start_col, end_col)
            return ParsedJump(
                target=sys.intern(target),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("~"):
            hook = line[1:].strip()
            if not hook:
                raise ParseError("Empty hook name", idx, start_col, end_col)
            return ParsedHook(
                hook_name=hook,
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("-"):
            return ParsedAppend(
                text=_unescape(line[1:].strip()),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("/"):
            return ParsedFreshBox(
                text=_unescape(line[1:].strip()),
                line_number=idx,
                start_col=start_col,
                end_col=end_col,
            )
        elif line.startswith("$"):
            match = SET_PATTERN.match(line)
            if not match:
                raise ParseError(
                    "Invalid set statement syntax. Expected '$ target = expr' or '$ target += expr'",
                    idx,
                    start_col,
                    end_col,
                )
            target, op, expr_src = match.groups()
            return ParsedSet(
                target=target.strip(),
                op=op.strip(),
                expr_src=expr_src.strip(),
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
                return ParsedDefault(
                    name=name.strip(),
                    expr_src=expr_src.strip(),
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@character"):
                match = CHARACTER_PATTERN.match(line)
                if not match:
                    raise ParseError(
                        "Invalid @character syntax. Expected '@character id \"Name\" key=value ...'",
                        idx,
                        start_col,
                        end_col,
                    )
                char_id, name_d, name_s, rest = match.groups()
                display_name = name_d or name_s or char_id
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
                    id=char_id.strip(),
                    name=display_name.strip(),
                    attrs=tuple(attrs),
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@if"):
                match = IF_PATTERN.match(line)
                if not match:
                    raise ParseError("Invalid @if syntax. Expected '@if expr'", idx, start_col, end_col)
                return ParsedIf(
                    expr_src=match.group(1).strip(),
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@elif"):
                match = ELIF_PATTERN.match(line)
                if not match:
                    raise ParseError("Invalid @elif syntax. Expected '@elif expr'", idx, start_col, end_col)
                return ParsedElif(
                    expr_src=match.group(1).strip(),
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            elif line.startswith("@else"):
                if not ELSE_PATTERN.match(line):
                    raise ParseError("Invalid @else syntax. Expected '@else'", idx, start_col, end_col)
                return ParsedElse(line_number=idx, start_col=start_col, end_col=end_col)
            elif line.startswith("@end"):
                if not END_PATTERN.match(line):
                    raise ParseError("Invalid @end syntax. Expected '@end'", idx, start_col, end_col)
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
                path = match.group(1) or match.group(2)
                return ParsedInclude(
                    path=path.strip(),
                    line_number=idx,
                    start_col=start_col,
                    end_col=end_col,
                )
            else:
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

    def _parse_inline_block(self, block: list[tuple[int, str]]) -> tuple[ParsedItem, ...]:
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
        for _, raw in block:
            if not raw.strip():
                stripped.append("")
                continue
            indent_len = len(raw) - len(raw.lstrip(" \t"))
            expanded_prefix = raw[:indent_len].expandtabs(4)
            expanded_line = expanded_prefix + raw[indent_len:]
            if len(expanded_prefix) >= base_indent:
                stripped.append(expanded_line[base_indent:])
            else:
                stripped.append(raw.lstrip())

        text = "\n" * (first_line - 1) + "\n".join(stripped)
        nested = type(self)().parse(text)
        for item in nested:
            if isinstance(item, (ParsedLabel, ParsedDefault, ParsedCharacter)):
                raise ParseError(
                    "Scene labels and preamble directives are not allowed inside an inline choice block",
                    item.line_number,
                    item.start_col,
                    item.end_col,
                )
        adjusted = [_adjust_span(item, base_indent) for item in nested]
        return tuple(adjusted)

    def _parse(self, text: str) -> Iterator[ParsedItem]:
        """Shared line-by-line parse loop yielding AST items."""
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

            clean = raw_line.strip()
            if not clean:
                yield from self._flush_all()
                continue

            start_col = len(raw_line) - len(raw_line.lstrip(" \t"))

            c0 = clean[0]
            if c0 == "#":
                if not clean.startswith("##"):
                    if not self._choice_buffer:
                        yield from self._flush_all()
                    continue
            elif "#" in clean and (" #" in clean or "\t#" in clean):
                clean = _INLINE_COMMENT_PATTERN.sub("", clean).rstrip()
                if not clean:
                    yield from self._flush_all()
                    continue

            end_col = start_col + len(clean)

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
                        body_items = self._parse_inline_block(block)
                        self._choice_buffer.append(choice_opt)
                        self._choice_bodies.append(list(body_items))
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
                    continue

                # ── Flush choices before processing non-choice lines ──
                if self._choice_buffer:
                    yield from self._flush_choices()

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

        yield from self._flush_all()

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
    "ScreenplayParser",
    "parse",
    "parse_iter",
    "slugify",
]
