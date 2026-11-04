"""Text tag parsing and typewriter reveal pacing for dialogue boxes."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from eager_core.types import Color

__all__ = [
    "_WRAP_CACHE",
    "FormattedText",
    "PausePoint",
    "TextAnchor",
    "TextReveal",
    "TextSegment",
    "_get_wrapped_lines",
    "parse_text_tags",
    "wrap_text",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TextSegment:
    """A formatted text segment with styling attributes.

    Attributes:
        text: Substring content of this segment.
        color: Optional text color override.
        bold: Whether bold typography is enabled.
        italic: Whether italic typography is enabled.
        size_mult: Font size multiplier relative to standard text size.
    """

    text: str
    color: Color | None = None
    bold: bool = False
    italic: bool = False
    size_mult: float = 1.0


@dataclass(frozen=True, slots=True)
class PausePoint:
    """Typewriter pause position in plain text.

    Attributes:
        char_index: Character index in the plain text where typewriter pause occurs.
        duration: Duration of the typewriter pause in seconds.
    """

    char_index: int
    duration: float  # In seconds


@dataclass(frozen=True, slots=True)
class FormattedText:
    """Parsed text containing plain text string, segment styles, and pause points.

    Attributes:
        plain_text: Unformatted text with all markup tags stripped.
        segments: Tuple of styled text segments.
        pauses: Tuple of pause points encountered during tag parsing.
        fast_index: Character index after which typewriter effect immediately displays.
    """

    plain_text: str
    segments: tuple[TextSegment, ...]
    pauses: tuple[PausePoint, ...]
    fast_index: int = 0


_TAG_RE = re.compile(r"\{(/?[a-zA-Z0-9_#:=.]+)\}")


def parse_text_tags(raw: str) -> FormattedText:
    """Parse inline markup tags from raw dialogue text.

    Supported tags include styling ({b}, {/b}, {i}, {/i}, {color=#hex}, {/color}, {size=N}, {/size}),
    pauses ({w}, {w=seconds}, {p}, {p=seconds}), and typewriter acceleration ({fast}).

    Args:
        raw: Raw text containing potential inline markup tags.

    Returns:
        FormattedText containing clean plain text, styled segments, and typewriter pauses.
    """
    plain_parts: list[str] = []
    segments: list[TextSegment] = []
    pauses: list[PausePoint] = []
    fast_index = 0

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
        elif tag_content == "fast":
            fast_index = current_char_offset
        elif tag_content.startswith("color="):
            hex_val = tag_content.split("=", 1)[1]
            try:
                c = Color.from_hex(hex_val)
                color_stack.append(c)
            except ValueError:
                logger.debug("Invalid color tag {color=%s}, ignoring", hex_val)
        elif tag_content == "/color":
            if color_stack:
                _ = color_stack.pop()
        elif tag_content.startswith("size="):
            val = tag_content.split("=", 1)[1]
            try:
                mult = float(val)
                size_stack.append(mult)
            except ValueError:
                logger.debug("Invalid size tag {size=%s}, ignoring", val)
        elif tag_content == "/size":
            if len(size_stack) > 1:
                _ = size_stack.pop()
        elif tag_content == "w" or tag_content.startswith("w="):
            # Wait tag: default 0.5s or explicit duration
            dur = 0.5
            if "=" in tag_content:
                try:
                    dur = float(tag_content.split("=", 1)[1])
                except ValueError:
                    logger.debug("Invalid wait tag {w=%s}, using default 0.5s", tag_content)
                    dur = 0.5
            pauses.append(PausePoint(char_index=current_char_offset, duration=dur))
        elif tag_content == "p" or tag_content.startswith("p="):
            # Paragraph wait tag
            dur = 1.0
            if "=" in tag_content:
                try:
                    dur = float(tag_content.split("=", 1)[1])
                except ValueError:
                    logger.debug("Invalid paragraph tag {p=%s}, using default 1.0s", tag_content)
                    dur = 1.0
            pauses.append(PausePoint(char_index=current_char_offset, duration=dur))
        else:
            tag_text = match.group(0)
            plain_parts.append(tag_text)
            cur_color = color_stack[-1] if color_stack else None
            segments.append(
                TextSegment(
                    text=tag_text,
                    color=cur_color,
                    bold=(bold_depth > 0),
                    italic=(italic_depth > 0),
                    size_mult=size_stack[-1],
                )
            )
            current_char_offset += len(tag_text)

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
        fast_index=fast_index,
    )


class TextReveal:
    """Typewriter text reveal controller for dialogue boxes.

    Paces character appearance over time based on characters-per-second, honoring
    embedded pause durations and instant reveal tags.
    """

    def __init__(
        self,
        formatted: FormattedText,
        chars_per_second: float = 50.0,
        initial_visible_chars: int = 0,
    ) -> None:
        """Initialize the typewriter reveal controller.

        Args:
            formatted: Parsed text structure containing plain text and pause points.
            chars_per_second: Text typing speed. Set <= 0 for immediate reveal.
            initial_visible_chars: Minimum number of initial characters already revealed.
        """
        self.formatted: FormattedText = formatted
        self.chars_per_second: float = chars_per_second
        self.total_chars: int = len(formatted.plain_text)

        if chars_per_second <= 0:
            self.visible_chars: float = float(self.total_chars)
        else:
            start_chars = max(0, initial_visible_chars, getattr(formatted, "fast_index", 0))
            self.visible_chars = float(min(self.total_chars, start_chars))
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
        """Advance reveal progress by dt seconds.

        Args:
            dt: Delta time elapsed in seconds.
        """
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


class TextAnchor:
    """Namespace of the anchor strings accepted by :class:`UIDrawBackend`."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


def wrap_text(
    text: str,
    max_width: float,
    measure: Any,
    *,
    font_size: int = 14,
    font_family: str | None = None,
) -> list[tuple[str, int, int]]:
    """Wrap text to fit within max_width using greedy word-wrapping.

    Respects explicit newlines and breaks overlong words that cannot fit on a single line.
    Returns a list of (line_str, start_char_idx, end_char_idx) character spans.
    """
    if not text or max_width <= 0:
        return []

    lines: list[tuple[str, int, int]] = []
    pos = 0
    paragraphs: list[tuple[str, int, int]] = []
    for m in re.finditer(r"\r\n|\r|\n", text):
        paragraphs.append((text[pos:m.start()], pos, m.start()))
        pos = m.end()
    paragraphs.append((text[pos:], pos, len(text)))

    for para_text, para_start, para_end in paragraphs:
        if not para_text:
            lines.append(("", para_start, para_end))
            continue

        word_matches = list(re.finditer(r"\S+", para_text))
        if not word_matches:
            lines.append((para_text, para_start, para_end))
            continue

        cur_line_words: list[tuple[str, int, int]] = []

        for wm in word_matches:
            w_text = wm.group()
            w_start = para_start + wm.start()
            w_end = para_start + wm.end()

            if not cur_line_words:
                w, _ = measure(w_text, font_size=font_size)
                if w <= max_width:
                    cur_line_words.append((w_text, w_start, w_end))
                else:
                    # Break overlong single word
                    sub_start = w_start
                    sub_str = ""
                    for ch in w_text:
                        cand = sub_str + ch
                        cw, _ = measure(cand, font_size=font_size)
                        if cw <= max_width:
                            sub_str = cand
                        else:
                            if sub_str:
                                lines.append((sub_str, sub_start, sub_start + len(sub_str)))
                                sub_start = sub_start + len(sub_str)
                            sub_str = ch
                    if sub_str:
                        cur_line_words.append((sub_str, sub_start, sub_start + len(sub_str)))
            else:
                line_start = cur_line_words[0][1]
                candidate = text[line_start:w_end]
                w, _ = measure(candidate, font_size=font_size)
                if w <= max_width:
                    cur_line_words.append((w_text, w_start, w_end))
                else:
                    l_start = cur_line_words[0][1]
                    l_end = cur_line_words[-1][2]
                    lines.append((text[l_start:l_end], l_start, l_end))
                    cur_line_words = []

                    ww, _ = measure(w_text, font_size=font_size)
                    if ww <= max_width:
                        cur_line_words.append((w_text, w_start, w_end))
                    else:
                        sub_start = w_start
                        sub_str = ""
                        for ch in w_text:
                            cand = sub_str + ch
                            cw, _ = measure(cand, font_size=font_size)
                            if cw <= max_width:
                                sub_str = cand
                            else:
                                if sub_str:
                                    lines.append((sub_str, sub_start, sub_start + len(sub_str)))
                                    sub_start = sub_start + len(sub_str)
                                sub_str = ch
                        if sub_str:
                            cur_line_words.append((sub_str, sub_start, sub_start + len(sub_str)))

        if cur_line_words:
            l_start = cur_line_words[0][1]
            l_end = cur_line_words[-1][2]
            lines.append((text[l_start:l_end], l_start, l_end))

    return lines


def _get_backend_key(measure: Any) -> str:
    backend = getattr(measure, "__self__", None)
    if backend is not None:
        return f"{backend.__class__.__module__}.{backend.__class__.__qualname__}"
    return f"{getattr(measure, '__module__', '')}.{getattr(measure, '__qualname__', type(measure).__name__)}"


def _get_font_family(measure: Any, font_family: str | None = None) -> str:
    if font_family is not None:
        return font_family
    backend = getattr(measure, "__self__", None)
    if backend is not None:
        if hasattr(backend, "_ui_font_name") and callable(backend._ui_font_name):
            try:
                return str(backend._ui_font_name())
            except Exception:  # noqa: BLE001, S110
                pass
        if hasattr(backend, "font_family"):
            return str(backend.font_family)
        if hasattr(backend, "font_name"):
            return str(backend.font_name)
    return "default"


_WRAP_CACHE: dict[tuple[str, float, int, str, str], list[tuple[str, int, int]]] = {}


def _get_wrapped_lines(
    text: str,
    max_width: float,
    measure: Any,
    font_size: int = 14,
    font_family: str | None = None,
) -> list[tuple[str, int, int]]:
    backend_key = _get_backend_key(measure)
    font_key = _get_font_family(measure, font_family)
    key = (text, max_width, font_size, backend_key, font_key)
    if key in _WRAP_CACHE:
        return _WRAP_CACHE[key]
    res = wrap_text(text, max_width, measure, font_size=font_size, font_family=font_family)
    if len(_WRAP_CACHE) > 500:
        _WRAP_CACHE.clear()
    _WRAP_CACHE[key] = res
    return res
