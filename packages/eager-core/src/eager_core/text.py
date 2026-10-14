"""Text tag parsing and typewriter reveal pacing for dialogue boxes."""

from __future__ import annotations

import re
from dataclasses import dataclass

from eager_core.types import Color


@dataclass(frozen=True, slots=True)
class TextSegment:
    """A formatted text segment with styling attributes."""

    text: str
    color: Color | None = None
    bold: bool = False
    italic: bool = False
    size_mult: float = 1.0


@dataclass(frozen=True, slots=True)
class PausePoint:
    """Typewriter pause position in plain text."""

    char_index: int
    duration: float  # In seconds


@dataclass(frozen=True, slots=True)
class FormattedText:
    """Parsed text containing plain text string, segment styles, and pause points."""

    plain_text: str
    segments: tuple[TextSegment, ...]
    pauses: tuple[PausePoint, ...]


_TAG_RE = re.compile(r"\{(/?[a-zA-Z0-9_#:=.]+)\}")


def parse_text_tags(raw: str) -> FormattedText:
    """Parse inline markup tags: {b}, {/b}, {i}, {/i}, {color=#hex}, {/color}, {size=N}, {/size}, {w}, {p}, {fast}."""
    plain_parts: list[str] = []
    segments: list[TextSegment] = []
    pauses: list[PausePoint] = []

    bold_depth = 0
    italic_depth = 0
    color_stack: list[Color] = []
    size_stack: list[float] = [1.0]

    last_idx = 0
    current_char_offset = 0

    for match in _TAG_RE.finditer(raw):
        # Text before tag
        if match.start() > last_idx:
            chunk = raw[last_idx:match.start()]
            plain_parts.append(chunk)
            cur_color = color_stack[-1] if color_stack else None
            segments.append(
                TextSegment(
                    text=chunk,
                    color=cur_color,
                    bold=(bold_depth > 0),
                    italic=(italic_depth > 0),
                    size_mult=size_stack[-1],
                )
            )
            current_char_offset += len(chunk)

        tag_content = match.group(1).strip()
        last_idx = match.end()

        # Handle tags
        if tag_content == "b":
            bold_depth += 1
        elif tag_content == "/b":
            bold_depth = max(0, bold_depth - 1)
        elif tag_content == "i":
            italic_depth += 1
        elif tag_content == "/i":
            italic_depth = max(0, italic_depth - 1)
        elif tag_content.startswith("color="):
            hex_val = tag_content.split("=", 1)[1]
            try:
                c = Color.from_hex(hex_val)
                color_stack.append(c)
            except ValueError:
                pass
        elif tag_content == "/color":
            if color_stack:
                color_stack.pop()
        elif tag_content.startswith("size="):
            val = tag_content.split("=", 1)[1]
            try:
                mult = float(val)
                size_stack.append(mult)
            except ValueError:
                pass
        elif tag_content == "/size":
            if len(size_stack) > 1:
                size_stack.pop()
        elif tag_content == "w" or tag_content.startswith("w="):
            # Wait tag: default 0.5s or explicit duration
            dur = 0.5
            if "=" in tag_content:
                try:
                    dur = float(tag_content.split("=", 1)[1])
                except ValueError:
                    dur = 0.5
            pauses.append(PausePoint(char_index=current_char_offset, duration=dur))
        elif tag_content == "p" or tag_content.startswith("p="):
            # Paragraph wait tag
            dur = 1.0
            if "=" in tag_content:
                try:
                    dur = float(tag_content.split("=", 1)[1])
                except ValueError:
                    dur = 1.0
            pauses.append(PausePoint(char_index=current_char_offset, duration=dur))

    # Remaining text after last tag
    if last_idx < len(raw):
        chunk = raw[last_idx:]
        plain_parts.append(chunk)
        cur_color = color_stack[-1] if color_stack else None
        segments.append(
            TextSegment(
                text=chunk,
                color=cur_color,
                bold=(bold_depth > 0),
                italic=(italic_depth > 0),
                size_mult=size_stack[-1],
            )
        )

    full_plain = "".join(plain_parts)
    return FormattedText(
        plain_text=full_plain,
        segments=tuple(segments),
        pauses=tuple(pauses),
    )


class TextReveal:
    """Typewriter text reveal controller."""

    def __init__(
        self,
        formatted: FormattedText,
        chars_per_second: float = 50.0,
        initial_visible_chars: int = 0,
    ) -> None:
        self.formatted = formatted
        self.chars_per_second = chars_per_second
        self.total_chars = len(formatted.plain_text)

        if chars_per_second <= 0:
            self.visible_chars: float = float(self.total_chars)
        else:
            self.visible_chars = float(min(self.total_chars, max(0, initial_visible_chars)))
        self.is_complete: bool = (self.visible_chars >= self.total_chars)

        self._elapsed_time: float = 0.0
        self._pause_timer: float = 0.0
        self._current_pause_idx: int = 0
        while (
            self._current_pause_idx < len(self.formatted.pauses)
            and self.formatted.pauses[self._current_pause_idx].char_index < self.visible_chars
        ):
            self._current_pause_idx += 1

    def update(self, dt: float) -> None:
        """Advance reveal progress by dt seconds."""
        if self.is_complete:
            return

        if self._pause_timer > 0.0:
            self._pause_timer -= dt
            if self._pause_timer > 0.0:
                return
            dt = -self._pause_timer
            self._pause_timer = 0.0

        if self.chars_per_second <= 0:
            self.visible_chars = float(self.total_chars)
            self.is_complete = True
            return

        # Advance chars
        chars_to_reveal = dt * self.chars_per_second
        next_visible = min(float(self.total_chars), self.visible_chars + chars_to_reveal)

        # Check pause points between int(self.visible_chars) and int(next_visible)
        start_idx = int(self.visible_chars)
        target_idx = int(next_visible)

        while self._current_pause_idx < len(self.formatted.pauses):
            p = self.formatted.pauses[self._current_pause_idx]
            if start_idx <= p.char_index < target_idx:
                self.visible_chars = float(p.char_index)
                self._pause_timer = p.duration
                self._current_pause_idx += 1
                return
            elif p.char_index >= target_idx:
                break
            else:
                self._current_pause_idx += 1

        self.visible_chars = next_visible
        if int(self.visible_chars) >= self.total_chars:
            self.visible_chars = float(self.total_chars)
            self.is_complete = True

    def complete_immediately(self) -> None:
        """Skip typewriter effect and reveal all text."""
        self.visible_chars = float(self.total_chars)
        self.is_complete = True
        self._pause_timer = 0.0
        self._current_pause_idx = len(self.formatted.pauses)

    @property
    def current_visible_plain_text(self) -> str:
        """Slice of plain text currently visible."""
        return self.formatted.plain_text[: int(self.visible_chars)]
