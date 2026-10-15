"""Eager-Script screenplay DSL parser."""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Any, TypeAlias

__version__ = "0.1.0"

CHOICE_PATTERN = re.compile(r"^\?\s+(.+?)\s*\(([^()]+)\)(?:\s+if\s+(.+))?\s*$")
CHOICE_INLINE_PATTERN = re.compile(r"^\?\s+(.+?)(?:\s+if\s+(.+))?\s*$")
VOICE_PATTERN = re.compile(r"^\{voice:([^}]+)\}\s*")
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


class ParseError(Exception):
    """Raised when screenplay syntax is invalid."""

    line_number: int

    def __init__(self, message: str, line_number: int) -> None:
        super().__init__(f"Line {line_number}: {message}")
        self.line_number = line_number


@dataclass(frozen=True, slots=True)
class ParsedLabel:
    """Parsed section label."""

    name: str
    display_name: str
    line_number: int

    @property
    def type(self) -> str:
        return "label"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "display_name": self.display_name,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedDialogue:
    """Parsed character dialogue beat."""

    speaker: str
    text: str
    voice: str | None
    line_number: int
    emotion: str | None = None

    @property
    def type(self) -> str:
        return "dialogue"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "speaker": self.speaker,
            "text": self.text,
            "voice": self.voice,
            "emotion": self.emotion,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedAppend:
    """Parsed append beat ('-')."""

    text: str
    line_number: int

    @property
    def type(self) -> str:
        return "append"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedFreshBox:
    """Parsed fresh box beat ('/')."""

    text: str
    line_number: int

    @property
    def type(self) -> str:
        return "fresh_box"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedNarration:
    """Parsed speakerless narration."""

    text: str
    line_number: int

    @property
    def type(self) -> str:
        return "narration"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedChoiceOption:
    """Parsed choice menu option ('? Text (target)' or '? Text' + indented block).

    A named option carries a ``target`` scene label.  An *inline* option omits the
    target and instead carries an indented ``body`` that is lowered into an
    anonymous scene (see :func:`eager_script.to_graph`).
    """

    text: str
    target: str | None
    line_number: int
    condition: str | None = None
    body: tuple[ParsedItem, ...] = ()

    @property
    def type(self) -> str:
        return "choice_option"

    @property
    def is_inline(self) -> bool:
        """True when the option carries an anonymous inline block instead of a target."""
        return bool(self.body)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "text": self.text,
            "target": self.target,
            "line_number": self.line_number,
            "condition": self.condition,
            "body": [item.to_dict() for item in self.body],
        }


@dataclass(frozen=True, slots=True)
class ParsedChoiceSet:
    """Parsed collection of consecutive choice options."""

    options: tuple[ParsedChoiceOption, ...]
    line_number: int

    @property
    def type(self) -> str:
        return "choice_set"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "options": [option.to_dict() for option in self.options],
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedJump:
    """Parsed unconditional jump ('>')."""

    target: str
    line_number: int

    @property
    def type(self) -> str:
        return "jump"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedCall:
    """Parsed subroutine call ('>>')."""

    target: str
    line_number: int

    @property
    def type(self) -> str:
        return "call"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedReturn:
    """Parsed subroutine return ('<<')."""

    line_number: int

    @property
    def type(self) -> str:
        return "return"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedHook:
    """Parsed hook invocation ('~')."""

    hook_name: str
    line_number: int

    @property
    def type(self) -> str:
        return "hook"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "hook_name": self.hook_name,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedSet:
    """Parsed variable set/mutation statement ('$ target op expr')."""

    target: str
    op: str
    expr_src: str
    line_number: int

    @property
    def type(self) -> str:
        return "set"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "op": self.op,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedDefault:
    """Parsed default variable definition ('@default name = expr')."""

    name: str
    expr_src: str
    line_number: int

    @property
    def type(self) -> str:
        return "default"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedCharacter:
    """Parsed character definition ('@character id \"name\" ...')."""

    id: str
    name: str
    attrs: tuple[tuple[str, str], ...]
    line_number: int

    @property
    def type(self) -> str:
        return "character"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "name": self.name,
            "attrs": list(self.attrs),
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedIf:
    """Parsed '@if expr'."""

    expr_src: str
    line_number: int

    @property
    def type(self) -> str:
        return "if"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedElif:
    """Parsed '@elif expr'."""

    expr_src: str
    line_number: int

    @property
    def type(self) -> str:
        return "elif"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "expr_src": self.expr_src,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedElse:
    """Parsed '@else'."""

    line_number: int

    @property
    def type(self) -> str:
        return "else"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedEnd:
    """Parsed '@end'."""

    line_number: int

    @property
    def type(self) -> str:
        return "end"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedCondJump:
    """Internal lowered conditional jump (jumps to target_index in scene if condition is false)."""

    condition: str
    target_index: int
    line_number: int

    @property
    def type(self) -> str:
        return "cond_jump"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "condition": self.condition,
            "target_index": self.target_index,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParsedLocalJump:
    """Internal lowered unconditional local jump within a scene."""

    target_index: int
    line_number: int

    @property
    def type(self) -> str:
        return "local_jump"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target_index": self.target_index,
            "line_number": self.line_number,
        }


ParsedItem: TypeAlias = (
    ParsedLabel
    | ParsedDialogue
    | ParsedAppend
    | ParsedFreshBox
    | ParsedNarration
    | ParsedChoiceSet
    | ParsedJump
    | ParsedCall
    | ParsedReturn
    | ParsedHook
    | ParsedSet
    | ParsedDefault
    | ParsedCharacter
    | ParsedIf
    | ParsedElif
    | ParsedElse
    | ParsedEnd
    | ParsedCondJump
    | ParsedLocalJump
)


_INLINE_COMMENT_PATTERN = re.compile(r"(?<!\\)\s+#(\s.*)?$")
_UNESCAPE_PATTERN = re.compile(r"\\([#:?\->\/~\\<@\$])")
_SLUG_NON_WORD = re.compile(r"[^\w\s-]")
_SLUG_DASH_SPACE = re.compile(r"[-\s]+")


def slugify(text: str) -> str:
    """Convert display name into a snake_case identifier."""
    slug = _SLUG_NON_WORD.sub("", text).strip().lower()
    return _SLUG_DASH_SPACE.sub("_", slug)


_slugify = slugify


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


def _strip_line_comment(line: str) -> str:
    """Strip standalone comments or unescaped inline comments."""
    if line.startswith("##"):
        return line
    if line.startswith("#"):
        return ""
    if "#" not in line:
        return line.rstrip()
    if " #" not in line and "\t#" not in line:
        return line.rstrip()
    # Strip trailing inline comments if preceded by whitespace and unescaped
    return _INLINE_COMMENT_PATTERN.sub("", line).rstrip()


def _parse_label(line: str, line_number: int) -> ParsedLabel:
    """Parse a label definition ('## Name --- id' or '## Name')."""
    rest = line[2:].strip()
    if not rest:
        raise ParseError("Empty label definition", line_number)
    if "---" in rest:
        display, name = rest.split("---", 1)
        name = sys.intern(name.strip())
        display = display.strip()
        if not display:
            raise ParseError("Empty label display name", line_number)
        if not name:
            raise ParseError("Empty label identifier", line_number)
        return ParsedLabel(name=name, display_name=display, line_number=line_number)

    slug = sys.intern(_slugify(rest))
    if not slug:
        raise ParseError(
            f"Invalid label '{rest}' cannot be converted to a valid identifier",
            line_number,
        )
    return ParsedLabel(name=slug, display_name=rest, line_number=line_number)


def _parse_choice(line: str, line_number: int) -> ParsedChoiceOption:
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
            )
        text = _unescape(inline_match.group(1).strip())
        raw_target = None
        condition = inline_match.group(2).strip() if inline_match.group(2) else None

    if not text:
        raise ParseError("Empty choice text", line_number)

    target: str | None = None
    if raw_target is not None:
        if not raw_target:
            raise ParseError("Empty choice target", line_number)
        target = raw_target
    return ParsedChoiceOption(
        text=text,
        target=sys.intern(target) if target else None,
        line_number=line_number,
        condition=condition,
    )


def _parse_dialogue(
    speaker: str, raw_text: str, emotion: str | None, line_number: int
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
    )


class ScreenplayParser:
    """Parses Eager-Script screenplay text into a sequence of parsed AST items.

    Supports the full DSL: hooks, subroutine calls, fresh-box/append
    beats, voice tags, and explicit label identifiers.
    """

    def __init__(self) -> None:
        self._narration_buffer: list[str] = []
        self._narration_line: int = 0
        self._choice_buffer: list[ParsedChoiceOption] = []
        self._choice_bodies: list[list[ParsedItem]] = []
        self._choice_indent: int = 0

    # ------------------------------------------------------------------
    # Flush helpers — each returns a list so both parse() and parse_iter()
    # can consume the result uniformly.
    # ------------------------------------------------------------------

    def _flush_narration(self) -> list[ParsedItem]:
        if self._narration_buffer:
            combined = self._narration_buffer[0] if len(self._narration_buffer) == 1 else " ".join(self._narration_buffer)
            self._narration_buffer.clear()
            return [
                ParsedNarration(
                    text=_unescape(combined),
                    line_number=self._narration_line,
                )
            ]
        return []

    def _flush_choices(self) -> list[ParsedItem]:
        if self._choice_buffer:
            first_line = self._choice_buffer[0].line_number
            options: list[ParsedChoiceOption] = []
            for opt, body in zip(self._choice_buffer, self._choice_bodies):
                if opt.target is None and not body:
                    raise ParseError(
                        f"Invalid choice syntax: option '{opt.text}' needs a '(target)' or an indented block",
                        opt.line_number,
                    )
                if opt.target is not None and body:
                    raise ParseError(
                        f"Choice option '{opt.text}' cannot combine a '(target)' with an indented block",
                        opt.line_number,
                    )
                options.append(replace(opt, body=tuple(body)) if body else opt)
            self._choice_buffer.clear()
            self._choice_bodies.clear()
            return [ParsedChoiceSet(options=tuple(options), line_number=first_line)]
        return []

    def _flush_all(self) -> list[ParsedItem]:
        items: list[ParsedItem] = []
        items.extend(self._flush_narration())
        items.extend(self._flush_choices())
        return items

    def _build_choice(self, clean: str, idx: int) -> ParsedChoiceOption:
        """Parse a ``?`` line into a :class:`ParsedChoiceOption`."""
        return _parse_choice(clean, idx)

    def _parse_prefixed(self, line: str, idx: int) -> ParsedItem | None:
        """Dispatch a line whose first character is a control symbol.

        Returns the parsed item, or *None* when the prefix is not a recognised
        control sequence (e.g. a bare ``<``) so the caller can fall through to
        the dialogue / narration logic.
        """
        if line.startswith("##"):
            return _parse_label(line, idx)
        elif line.startswith(">>"):
            target = line[2:].strip()
            if not target:
                raise ParseError("Empty call target", idx)
            return ParsedCall(target=sys.intern(target), line_number=idx)
        elif line.startswith("<<"):
            return ParsedReturn(line_number=idx)
        elif line.startswith(">"):
            target = line[1:].strip()
            if not target:
                raise ParseError("Empty jump target", idx)
            return ParsedJump(target=sys.intern(target), line_number=idx)
        elif line.startswith("~"):
            hook = line[1:].strip()
            if not hook:
                raise ParseError("Empty hook name", idx)
            return ParsedHook(hook_name=hook, line_number=idx)
        elif line.startswith("-"):
            return ParsedAppend(text=_unescape(line[1:].strip()), line_number=idx)
        elif line.startswith("/"):
            return ParsedFreshBox(text=_unescape(line[1:].strip()), line_number=idx)
        elif line.startswith("$"):
            match = SET_PATTERN.match(line)
            if not match:
                raise ParseError("Invalid set statement syntax. Expected '$ target = expr' or '$ target += expr'", idx)
            target, op, expr_src = match.groups()
            return ParsedSet(target=target.strip(), op=op.strip(), expr_src=expr_src.strip(), line_number=idx)
        elif line.startswith("@"):
            if line.startswith("@default"):
                match = DEFAULT_PATTERN.match(line)
                if not match:
                    raise ParseError("Invalid @default syntax. Expected '@default name = expr'", idx)
                name, expr_src = match.groups()
                return ParsedDefault(name=name.strip(), expr_src=expr_src.strip(), line_number=idx)
            elif line.startswith("@character"):
                match = CHARACTER_PATTERN.match(line)
                if not match:
                    raise ParseError("Invalid @character syntax. Expected '@character id \"Name\" key=value ...'", idx)
                char_id, name_d, name_s, rest = match.groups()
                display_name = name_d or name_s or char_id
                attrs: list[tuple[str, str]] = []
                if rest:
                    for token in rest.split():
                        if "=" in token:
                            k, v = token.split("=", 1)
                            attrs.append((k.strip(), v.strip().strip("\"'")))
                return ParsedCharacter(id=char_id.strip(), name=display_name.strip(), attrs=tuple(attrs), line_number=idx)
            elif line.startswith("@if"):
                match = IF_PATTERN.match(line)
                if not match:
                    raise ParseError("Invalid @if syntax. Expected '@if expr'", idx)
                return ParsedIf(expr_src=match.group(1).strip(), line_number=idx)
            elif line.startswith("@elif"):
                match = ELIF_PATTERN.match(line)
                if not match:
                    raise ParseError("Invalid @elif syntax. Expected '@elif expr'", idx)
                return ParsedElif(expr_src=match.group(1).strip(), line_number=idx)
            elif line.startswith("@else"):
                if not ELSE_PATTERN.match(line):
                    raise ParseError("Invalid @else syntax. Expected '@else'", idx)
                return ParsedElse(line_number=idx)
            elif line.startswith("@end"):
                if not END_PATTERN.match(line):
                    raise ParseError("Invalid @end syntax. Expected '@end'", idx)
                return ParsedEnd(line_number=idx)
            else:
                raise ParseError(f"Unknown directive '{line.split()[0]}'", idx)
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
        lines and inline blocks keep their relative structure.  Source line
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
                )
        return tuple(nested)

    def _parse(self, text: str) -> Iterator[ParsedItem]:
        """Shared line-by-line parse loop yielding AST items."""
        self._narration_buffer.clear()
        self._choice_buffer.clear()
        self._choice_bodies.clear()
        self._choice_indent = 0

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

            # ── Choice (?) ──────────────────────────────────────────
            if c0 == "?":
                if self._narration_buffer:
                    yield from self._flush_narration()
                choice_opt = self._build_choice(clean, idx)
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
                        )
                    body_items = self._parse_inline_block(block)
                    self._choice_buffer.append(choice_opt)
                    self._choice_bodies.append(list(body_items))
                else:
                    if choice_opt.target is None:
                        raise ParseError(
                            f"Invalid choice syntax: option '{choice_opt.text}' needs a '(target)' or an indented block",
                            choice_opt.line_number,
                        )
                    self._choice_buffer.append(choice_opt)
                    self._choice_bodies.append([])
                continue

            # ── Flush choices before processing non-choice lines ──
            if self._choice_buffer:
                yield from self._flush_choices()

            # ── Prefixed control lines (## >> << > ~ - / $ @) ─────
            if c0 in "#><~-/$@":
                item = self._parse_prefixed(clean, idx)
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
                    yield _parse_dialogue(speaker.strip(), text_content, emotion, idx)
                    continue

            # ── Narration ──────────────────────────────────────────
            if not self._narration_buffer:
                self._narration_line = idx
            self._narration_buffer.append(clean)

        yield from self._flush_all()

    def parse(self, text: str) -> list[ParsedItem]:
        """Parse screenplay text into a list of parsed items."""
        return list(self._parse(text))

    def parse_iter(self, text: str) -> Iterator[ParsedItem]:
        """Stream parsed AST items from screenplay text with O(1) memory."""
        return self._parse(text)


def parse(text: str) -> list[ParsedItem]:
    """Parse screenplay text into AST items."""
    return ScreenplayParser().parse(text)


def parse_iter(text: str) -> Iterator[ParsedItem]:
    """Stream screenplay text into AST items with O(1) memory."""
    return ScreenplayParser().parse_iter(text)


def to_dict(items: Sequence[ParsedItem]) -> list[dict[str, Any]]:
    """Convert a sequence of parsed AST items into dictionaries."""
    return [item.to_dict() for item in items]


def to_json(items: Sequence[ParsedItem], *, indent: int | None = 2) -> str:
    """Serialize parsed AST items to a JSON string."""
    import json

    return json.dumps(to_dict(items), indent=indent)


from eager_script.graph import (
    SceneEdge,
    SceneGraph,
    SceneNode,
    parse_graph,
    to_graph,
)
from eager_script.hooks import HookArgs, parse_hook_args
from eager_script.validator import ValidationError, ValidationResult, validate

__all__ = [
    "HookArgs",
    "ParseError",
    "ParsedAppend",
    "ParsedCall",
    "ParsedCharacter",
    "ParsedChoiceOption",
    "ParsedChoiceSet",
    "ParsedCondJump",
    "ParsedDefault",
    "ParsedDialogue",
    "ParsedElif",
    "ParsedElse",
    "ParsedEnd",
    "ParsedFreshBox",
    "ParsedHook",
    "ParsedIf",
    "ParsedItem",
    "ParsedJump",
    "ParsedLabel",
    "ParsedLocalJump",
    "ParsedNarration",
    "ParsedReturn",
    "ParsedSet",
    "SceneEdge",
    "SceneGraph",
    "SceneNode",
    "ScreenplayParser",
    "ValidationError",
    "ValidationResult",
    "__version__",
    "parse",
    "parse_graph",
    "parse_hook_args",
    "parse_iter",
    "slugify",
    "to_dict",
    "to_graph",
    "to_json",
    "validate",
]
