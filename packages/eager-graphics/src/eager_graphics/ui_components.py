"""Renderer-agnostic UI components for visual-novel front-ends.

The stage compositor (:mod:`eager_graphics.compositor`) is responsible for
*what appears on the stage* — backgrounds, character sprites, fades and other
animated elements — and emits a flat list of :class:`~eager_graphics.protocol.RenderItem`
draw commands.  It knows nothing about dialogue boxes or choice menus.

This module provides the complementary *front-end* layer: the chrome that sits
above the stage and reacts to narrative state.  Components here own their own
layout maths and issue immediate-mode primitives through a
:class:`~eager_graphics.protocol.UIDrawBackend`, so a single implementation
serves every backend (PIL, Pyglet, or a headless recorder for tests).

Coordinate space
----------------
All layout is computed in **window pixels with a top-left origin** (``y``
increases downward), matching the convention used throughout
:mod:`eager_core.types`.  Backends with a different native origin (such as
Pyglet) flip ``y`` when issuing primitives, so components never need to care.

Typical use::

    overlay = UIOverlay(width=1280, height=720)
    ...
    overlay.draw(backend, ui_state, choice_prompt)
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from eager_core.text import parse_text_tags
from eager_core.types import Color

from eager_graphics.theme import Theme

if TYPE_CHECKING:
    from eager_graphics.protocol import UIDrawBackend
    from eager_graphics.ui_state import ChoiceOption, UIState

__all__ = [
    "ChoiceMenu",
    "ChoiceMenuStyle",
    "DialogueBox",
    "DialogueBoxLayout",
    "EndNotice",
    "InputBox",
    "QuickMenu",
    "TextAnchor",
    "TextboxStyle",
    "Theme",
    "UIOverlay",
    "wrap_text",
]

# Eye-friendly minimal / cinematic palette (Option B)
_CINEMATIC_BOX_FILL = Color(0.03, 0.04, 0.06, 0.90)
_CINEMATIC_TOP_BORDER = Color(1.0, 1.0, 1.0, 0.0)
_CINEMATIC_GRADIENT_TOP = Color(0.03, 0.04, 0.06, 0.0)
_CINEMATIC_GRADIENT_MID = Color(0.03, 0.04, 0.06, 0.88)
_CINEMATIC_GRADIENT_BOT = Color(0.03, 0.04, 0.06, 0.94)
_CINEMATIC_SPEAKER_COLOR = Color(0.95, 0.86, 0.62, 1.0)
_CINEMATIC_DIALOGUE_TEXT = Color(0.94, 0.95, 0.97, 1.0)
_CINEMATIC_ARROW_COLOR = Color(0.72, 0.76, 0.82, 0.70)

_CINEMATIC_CHOICE_FILL = Color(0.07, 0.09, 0.12, 0.86)
_CINEMATIC_CHOICE_BORDER = Color(1.0, 1.0, 1.0, 0.12)
_CINEMATIC_CHOICE_TEXT = Color(0.94, 0.95, 0.97, 1.0)
_CINEMATIC_CHOICE_HOVER_FILL = Color(0.15, 0.18, 0.25, 0.94)
_CINEMATIC_CHOICE_HOVER_BORDER = Color(0.95, 0.86, 0.62, 0.50)
_CINEMATIC_CHOICE_ACCENT = Color(0.95, 0.86, 0.62, 0.95)
_CINEMATIC_MUTED_TEXT_COLOR = Color(0.65, 0.68, 0.72, 0.60)
_CINEMATIC_CHOICE_DISABLED_FILL = Color(0.04, 0.05, 0.07, 0.60)
_CINEMATIC_CHOICE_DISABLED_BORDER = Color(1.0, 1.0, 1.0, 0.05)



_END_BANNER_FILL = Color(0.04, 0.05, 0.07, 0.78)
_END_TEXT = Color(0.85, 0.88, 0.92, 0.85)
_TRANSPARENT = Color(0.0, 0.0, 0.0, 0.0)


class TextAnchor:
    """Namespace of the anchor strings accepted by :class:`UIDrawBackend`."""

    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


@dataclass(frozen=True, slots=True)
class TextboxStyle:
    """Visual styling for :class:`DialogueBox`.

    Configures a clean, minimal cinematic scrim docked to the bottom of the screen.
    """

    layout_mode: str = "cinematic"  # "cinematic" or "classic"

    box_fill: Color = _CINEMATIC_BOX_FILL
    box_border: Color = _CINEMATIC_TOP_BORDER
    box_border_width: float = 0.0
    gradient_top: Color | None = _CINEMATIC_GRADIENT_TOP
    gradient_mid: Color | None = _CINEMATIC_GRADIENT_MID
    gradient_bottom: Color | None = _CINEMATIC_GRADIENT_BOT
    fade_height: float = 55.0

    nameplate_fill: Color = _TRANSPARENT
    nameplate_border: Color = _TRANSPARENT
    nameplate_text: Color = _CINEMATIC_SPEAKER_COLOR
    nameplate_font_size: int = 15
    show_nameplate_box: bool = False

    text_color: Color = _CINEMATIC_DIALOGUE_TEXT
    text_font_size: int = 15
    text_padding: float = 56.0

    arrow_color: Color = _CINEMATIC_ARROW_COLOR
    arrow_font_size: int = 14
    arrow_symbol: str = "▾"

    min_height: float = 160.0
    height_ratio: float = 0.28
    margin_ratio: float = 0.0
    min_margin: float = 0.0
    bottom_gap: float = 0.0
    nameplate_overlap: float = 0.0

    def box_height(self, viewport_height: float) -> float:
        """Return the textbox height for a viewport of *viewport_height* pixels."""
        return float(max(self.min_height, int(viewport_height * self.height_ratio)))

    def box_margin(self, viewport_width: float) -> float:
        """Return the horizontal gutter either side of the textbox."""
        return float(max(self.min_margin, int(viewport_width * self.margin_ratio)))

    @classmethod
    def from_theme(cls, theme: Theme, **overrides: Any) -> TextboxStyle:
        """Create a TextboxStyle aligned with a visual Theme configuration."""
        return theme.to_textbox_style(**overrides)


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


# Cache for wrap_text results: (text, max_width, font_size, backend_type, font_family) -> list[tuple[str, int, int]]
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


@dataclass(frozen=True, slots=True)
class DialogueBoxLayout:
    """Computed geometry for one frame of :class:`DialogueBox`."""

    box: tuple[float, float, float, float]
    nameplate: tuple[float, float, float, float] | None
    show_arrow: bool

    def contains(self, x: float, y: float) -> bool:
        """Return *True* if the point falls inside the textbox rectangle."""
        bx, by, bw, bh = self.box
        return bx <= x <= bx + bw and by <= y <= by + bh


class DialogueBox:
    """Bottom-docked dialogue textbox with a speaker nameplate and advance cue.

    The component is a pure state holder plus layout calculator: feed it a
    speaker and text via :meth:`set_content`, then either inspect
    :meth:`layout` (useful for tests and custom input handling) or hand it to
    :meth:`draw` along with a backend.
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        *,
        style: TextboxStyle | None = None,
        theme: Theme | None = None,
    ) -> None:
        if style is not None:
            self.style = style
        elif theme is not None:
            self.style = theme.to_textbox_style()
        else:
            self.style = TextboxStyle()
        self.theme: Theme | None = theme
        self.viewport_width = width
        self.viewport_height = height
        self.speaker: str | None = None
        self.text: str = ""
        self.emotion: str | None = None
        self.side_image: str | None = None
        self.show_advance_arrow: bool = True
        self.is_read: bool = False
        self.visible_chars: int | None = None
        self.speaker_color: Color | None = None

    def set_theme(self, theme: Theme) -> None:
        """Apply styling from a Theme."""
        self.theme = theme
        self.style = theme.to_textbox_style()

    # ── state ──────────────────────────────────────────────────────────

    def set_viewport(self, width: int, height: int) -> None:
        """Update the viewport the component lays itself out against."""
        self.viewport_width = width
        self.viewport_height = height

    def set_content(
        self,
        speaker: str | None,
        text: str,
        emotion: str | None = None,
        side_image: str | None = None,
        *,
        visible_chars: int | None = None,
        speaker_color: Color | None = None,
    ) -> None:
        """Set the speaker name, dialogue text, emotion tag, optional side image and speaker color."""
        self.speaker = speaker
        self.text = text
        self.emotion = emotion
        self.side_image = side_image
        self.visible_chars = visible_chars
        self.speaker_color = speaker_color

    def clear(self) -> None:
        """Reset to an empty, undrawn state."""
        self.speaker = None
        self.text = ""
        self.emotion = None
        self.side_image = None
        self.visible_chars = None
        self.speaker_color = None
        self.show_advance_arrow = True

    def cache_key(self) -> tuple[Any, ...]:
        """Return a hashable key covering everything that affects rendering."""
        return (
            self.viewport_width,
            self.viewport_height,
            self.speaker,
            self.text,
            self.emotion,
            self.side_image,
            self.show_advance_arrow,
            self.visible_chars,
        )

    def scale_font_size(self, base_size: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(self.viewport_height) / 720.0
        return max(1, round(float(base_size) * scale))

    # ── layout ─────────────────────────────────────────────────────────

    def nameplate_width(self) -> float:
        """Width of the speaker nameplate, sized to the speaker's name."""
        if not self.speaker:
            return 0.0
        return min(250.0, float(len(self.speaker) * 14 + 30))

    def layout(self) -> DialogueBoxLayout:
        """Compute the textbox and nameplate rectangles for the current state."""
        style = self.style
        vw, vh = self.viewport_width, self.viewport_height

        if style.layout_mode == "cinematic":
            box_w = float(vw)
            box_h = style.box_height(vh)
            box_x = 0.0
            box_y = float(vh) - box_h - style.bottom_gap
            nameplate = None
            return DialogueBoxLayout(
                box=(box_x, box_y, box_w, box_h),
                nameplate=nameplate,
                show_arrow=self.show_advance_arrow and bool(self.text),
            )
        else:
            box_w = float(vw - style.box_margin(vw) * 2)
            box_h = style.box_height(vh)
            box_x = style.box_margin(vw)
            box_y = float(vh) - box_h - style.bottom_gap

            has_speaker = bool(self.speaker)
            nameplate: tuple[float, float, float, float] | None = None
            if has_speaker and style.show_nameplate_box:
                name_w = self.nameplate_width()
                name_h = 30.0
                name_x = box_x + 15.0
                name_y = box_y - style.nameplate_overlap
                nameplate = (name_x, name_y, name_w, name_h)

            return DialogueBoxLayout(
                box=(box_x, box_y, box_w, box_h),
                nameplate=nameplate,
                show_arrow=self.show_advance_arrow and bool(self.text),
            )

    # ── drawing ────────────────────────────────────────────────────────

    def draw(self, backend: UIDrawBackend) -> None:
        """Render the textbox through *backend*."""
        if not self.text:
            return

        style = self.style
        layout = self.layout()
        box_x, box_y, box_w, box_h = layout.box

        # Background: gradient scrim or solid rect
        if (
            style.layout_mode == "cinematic"
            and style.gradient_top is not None
            and style.gradient_mid is not None
        ):
            mid_col = style.gradient_mid
            fade_h = min(getattr(style, "fade_height", 55.0), box_h * 0.45)
            body_h = box_h - fade_h
            # 1. Top transition fade
            backend.draw_gradient_rect(
                box_x,
                box_y,
                box_w,
                fade_h,
                style.gradient_top,
                mid_col,
            )
            # 2. Rich dark reading plate
            bot_col = (
                style.gradient_bottom
                if style.gradient_bottom is not None
                else mid_col
            )
            backend.draw_gradient_rect(
                box_x,
                box_y + fade_h,
                box_w,
                body_h,
                mid_col,
                bot_col,
            )
        elif (
            style.gradient_top is not None
            and style.gradient_bottom is not None
        ):
            backend.draw_gradient_rect(
                box_x,
                box_y,
                box_w,
                box_h,
                style.gradient_top,
                style.gradient_bottom,
            )
        else:
            backend.draw_rect(
                box_x,
                box_y,
                box_w,
                box_h,
                style.box_fill,
                border_color=style.box_border if style.box_border_width > 0 else None,
                border_width=style.box_border_width,
            )

        if style.layout_mode == "cinematic" and style.box_border_width > 0 and style.box_border.a > 0:
            backend.draw_rect(box_x, box_y, box_w, style.box_border_width, style.box_border)

        if layout.nameplate is not None:
            nx, ny, nw, nh = layout.nameplate
            backend.draw_rect(
                nx,
                ny,
                nw,
                nh,
                style.nameplate_fill,
                border_color=style.nameplate_border,
                border_width=1.0,
            )
            assert self.speaker is not None
            nameplate_fs = self.scale_font_size(style.nameplate_font_size)
            backend.draw_text(
                nx + 12.0,
                ny + (nh / 2.0),
                self.speaker,
                font_size=nameplate_fs,
                color=self.speaker_color if self.speaker_color is not None else style.nameplate_text,
                anchor_y=TextAnchor.MIDDLE,
            )

        # Side image offset
        text_start_x = box_x + style.text_padding
        text_max_w = box_w - style.text_padding * 2 - (40.0 if layout.show_arrow else 0.0)

        if self.side_image:
            img_size = box_h - 20.0
            img_x = box_x + 10.0
            img_y = box_y + 10.0
            backend.draw_image(self.side_image, img_x, img_y, img_size, img_size)
            text_start_x += img_size + 15.0
            text_max_w -= img_size + 15.0

        if style.layout_mode == "cinematic":
            content_y = box_y + getattr(style, "fade_height", 55.0) + 6.0
            speaker_offset_y = 0.0
            if self.speaker:
                nameplate_fs = self.scale_font_size(style.nameplate_font_size)
                backend.draw_text(
                    text_start_x,
                    content_y,
                    self.speaker,
                    font_size=nameplate_fs,
                    color=self.speaker_color if self.speaker_color is not None else style.nameplate_text,
                )
                speaker_offset_y = float(nameplate_fs) + 12.0
            dialogue_start_y = content_y + speaker_offset_y
        else:
            dialogue_start_y = box_y + 24.0

        formatted = parse_text_tags(self.text)
        if not formatted.plain_text:
            return

        text_fs = self.scale_font_size(style.text_font_size)
        line_height = text_fs * 1.35
        lines = _get_wrapped_lines(
            formatted.plain_text,
            text_max_w,
            backend.measure_text,
            font_size=text_fs,
        )

        visible_limit = (
            max(0, int(self.visible_chars))
            if self.visible_chars is not None
            else len(formatted.plain_text)
        )
        is_fully_revealed = (
            self.visible_chars is None or int(self.visible_chars) >= len(formatted.plain_text)
        )

        # Precompute segment spans (start, end, segment) in plain_text
        seg_spans: list[tuple[int, int, Any]] = []
        cur_pos = 0
        for seg in formatted.segments:
            seg_len = len(seg.text)
            seg_spans.append((cur_pos, cur_pos + seg_len, seg))
            cur_pos += seg_len

        for i, (line, line_start, line_end) in enumerate(lines):
            if line_start >= visible_limit:
                break

            visible_line_end = min(line_end, visible_limit)
            x_cursor = text_start_x
            line_y = dialogue_start_y + (i * line_height)

            for seg_start, seg_end, seg in seg_spans:
                overlap_start = max(line_start, seg_start)
                overlap_end = min(visible_line_end, seg_end)
                if overlap_start < overlap_end:
                    piece_text = seg.text[overlap_start - seg_start : overlap_end - seg_start]
                    seg_font_size = max(1, round(text_fs * seg.size_mult))
                    seg_color = seg.color if seg.color is not None else style.text_color
                    backend.draw_text(
                        x_cursor,
                        line_y,
                        piece_text,
                        font_size=seg_font_size,
                        color=seg_color,
                        bold=seg.bold,
                        italic=seg.italic,
                        cache=is_fully_revealed,
                    )
                    piece_w, _ = backend.measure_text(
                        piece_text,
                        font_size=seg_font_size,
                        bold=seg.bold,
                        italic=seg.italic,
                        cache=is_fully_revealed,
                    )
                    x_cursor += piece_w
        if layout.show_arrow and is_fully_revealed:
            arrow_sym = getattr(style, "arrow_symbol", "▼")
            arrow_x = (
                box_x + box_w - (style.text_padding if style.layout_mode == "cinematic" else 30.0)
            )
            # When previously read, use a subtle golden tint (_CINEMATIC_SPEAKER_COLOR)
            arrow_col = (
                _CINEMATIC_SPEAKER_COLOR if self.is_read else style.arrow_color
            )
            arrow_fs = self.scale_font_size(style.arrow_font_size)
            backend.draw_text(
                arrow_x,
                box_y + box_h - 25.0,
                arrow_sym,
                font_size=arrow_fs,
                color=arrow_col,
                anchor_x=TextAnchor.RIGHT if style.layout_mode == "cinematic" else TextAnchor.LEFT,
            )



@dataclass(frozen=True, slots=True)
class ChoiceMenuStyle:
    """Visual styling for :class:`ChoiceMenu`.

    Configures clean, minimal card buttons with subtle hover highlighting.
    """

    layout_mode: str = "cinematic"  # "cinematic" or "classic"
    button_fill: Color = _CINEMATIC_CHOICE_FILL
    button_border: Color = _CINEMATIC_CHOICE_BORDER
    button_border_width: float = 1.0
    button_hover_fill: Color = _CINEMATIC_CHOICE_HOVER_FILL
    button_hover_border: Color = _CINEMATIC_CHOICE_HOVER_BORDER
    accent_bar_color: Color = _CINEMATIC_CHOICE_ACCENT

    button_width: int = 640
    button_width_ratio: float = 0.65
    button_height: float = 44.0
    spacing: float = 12.0
    text_color: Color = _CINEMATIC_CHOICE_TEXT
    disabled_text_color: Color = _CINEMATIC_MUTED_TEXT_COLOR
    disabled_button_fill: Color = _CINEMATIC_CHOICE_DISABLED_FILL
    disabled_button_border: Color = _CINEMATIC_CHOICE_DISABLED_BORDER
    lock_symbol: str = "[Locked] "
    text_font_size: int = 14
    text_padding: float = 24.0
    show_numbering: bool = False

    def button_width_for(self, viewport_width: float) -> float:
        """Return the button width for a viewport of *viewport_width* pixels."""
        return float(min(self.button_width, int(viewport_width * self.button_width_ratio)))

    @classmethod
    def from_theme(cls, theme: Theme, **overrides: Any) -> ChoiceMenuStyle:
        """Create a ChoiceMenuStyle aligned with a visual Theme configuration."""
        return theme.to_choice_menu_style(**overrides)


class ChoiceMenu:
    """Vertically stacked, centre-aligned branch-selection buttons.

    Provides :meth:`hit_test` so players can route mouse input without
    duplicating the layout maths — the same geometry that is drawn is the
    geometry that is tested.
    """

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        *,
        style: ChoiceMenuStyle | None = None,
        theme: Theme | None = None,
    ) -> None:
        if style is not None:
            self.style = style
        elif theme is not None:
            self.style = theme.to_choice_menu_style()
        else:
            self.style = ChoiceMenuStyle()
        self.theme: Theme | None = theme
        self.viewport_width = width
        self.viewport_height = height
        self.options: tuple[ChoiceOption, ...] = ()
        self.selected_index: int | None = None

    def set_theme(self, theme: Theme) -> None:
        """Apply styling from a Theme."""
        self.theme = theme
        self.style = theme.to_choice_menu_style()

    def set_viewport(self, width: int, height: int) -> None:
        """Update the viewport the component lays itself out against."""
        self.viewport_width = width
        self.viewport_height = height

    def set_options(self, options: Sequence[ChoiceOption] | None) -> None:
        """Set the active options; *None* or an empty sequence clears the menu."""
        self.options = tuple(options) if options else ()
        self.selected_index = None

    def clear(self) -> None:
        """Remove all options."""
        self.options = ()
        self.selected_index = None

    def cache_key(self) -> tuple[Any, ...]:
        """Return a hashable key covering everything that affects rendering."""
        return (
            self.viewport_width,
            self.viewport_height,
            tuple((opt.index, opt.text, opt.enabled) for opt in self.options),
            self.selected_index,
        )

    def scale_font_size(self, base_size: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(self.viewport_height) / 720.0
        return max(1, round(float(base_size) * scale))

    def layout(self) -> tuple[tuple[float, float, float, float], ...]:
        """Compute one ``(x, y, w, h)`` rectangle per option, top to bottom."""
        if not self.options:
            return ()

        style = self.style
        vw, vh = self.viewport_width, self.viewport_height

        btn_w = style.button_width_for(vw)
        btn_h = style.button_height
        spacing = style.spacing

        total_h = len(self.options) * btn_h + (len(self.options) - 1) * spacing
        start_y = (vh - total_h) / 2.0
        start_x = (vw - btn_w) / 2.0

        return tuple(
            (start_x, start_y + i * (btn_h + spacing), btn_w, btn_h)
            for i in range(len(self.options))
        )

    def hit_test(self, x: float, y: float) -> int | None:
        """Return the index of the enabled option under the point, or *None*.

        Uses the exact same rectangles produced by :meth:`layout`, so hit
        testing stays correct across resolutions and option counts.
        Disabled options are non-selectable and return *None*.
        """
        for index, (bx, by, bw, bh) in enumerate(self.layout()):
            if bx <= x <= bx + bw and by <= y <= by + bh:
                opt = self.options[index]
                if not opt.enabled:
                    return None
                return index
        return None

    def draw(self, backend: UIDrawBackend) -> None:
        """Render every option button through *backend*."""
        if not self.options:
            return

        style = self.style
        for index, (bx, by, bw, bh) in enumerate(self.layout()):
            opt = self.options[index]
            is_enabled = opt.enabled
            is_selected = (self.selected_index == index) and is_enabled

            if not is_enabled:
                fill_col = style.disabled_button_fill
                border_col = style.disabled_button_border
            elif is_selected:
                fill_col = style.button_hover_fill
                border_col = style.button_hover_border
            else:
                fill_col = style.button_fill
                border_col = style.button_border

            backend.draw_rect(
                bx,
                by,
                bw,
                bh,
                fill_col,
                border_color=border_col,
                border_width=style.button_border_width,
            )

            # Left accent highlight bar on selection/hover in cinematic mode
            if is_selected and style.layout_mode == "cinematic":
                backend.draw_rect(bx, by, 3.0, bh, style.accent_bar_color)

            lock_prefix = style.lock_symbol if not is_enabled else ""
            if style.show_numbering:
                prefix = "> " if (is_selected and style.layout_mode == "classic") else ""
                label_text = f"{prefix}[{index + 1}]  {lock_prefix}{opt.text}"
            else:
                label_text = f"{lock_prefix}{opt.text}"

            text_col = style.text_color if is_enabled else style.disabled_text_color
            backend.draw_text(
                bx + style.text_padding,
                by + (bh / 2.0),
                label_text,
                font_size=self.scale_font_size(style.text_font_size),
                color=text_col,
                anchor_y=TextAnchor.MIDDLE,
            )


class InputBox:
    """Centered modal prompt for textual input with text buffer and blinking cursor."""

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        *,
        box_width: float = 600.0,
        box_height: float = 180.0,
    ) -> None:
        self.viewport_width = width
        self.viewport_height = height
        self.box_width = box_width
        self.box_height = box_height
        self.prompt: str = ""
        self.text_buffer: str = ""
        self.cursor_visible: bool = True
        self.cursor_timer: float = 0.0

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions."""
        self.viewport_width = width
        self.viewport_height = height

    def set_prompt(self, prompt: str, default: str = "") -> None:
        """Set active prompt string and initialize text buffer if empty."""
        self.prompt = prompt
        self.text_buffer = default

    def clear(self) -> None:
        """Clear prompt and buffer."""
        self.prompt = ""
        self.text_buffer = ""
        self.cursor_visible = True
        self.cursor_timer = 0.0

    def update(self, dt: float) -> None:
        """Update blinking cursor timer."""
        self.cursor_timer += dt
        if self.cursor_timer >= 0.53:
            self.cursor_timer = 0.0
            self.cursor_visible = not self.cursor_visible

    def layout(self) -> tuple[float, float, float, float]:
        """Compute the modal dialog (x, y, w, h) centered on screen."""
        bw = min(self.box_width, float(self.viewport_width) - 40.0)
        bh = min(self.box_height, float(self.viewport_height) - 40.0)
        bx = (float(self.viewport_width) - bw) / 2.0
        by = (float(self.viewport_height) - bh) / 2.0
        return (bx, by, bw, bh)

    def scale_font_size(self, base_size: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(self.viewport_height) / 720.0
        return max(1, round(float(base_size) * scale))

    def draw(self, backend: UIDrawBackend) -> None:
        """Render modal backdrop, dialog box, prompt label, input field, and blinking cursor."""
        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        # 1. Semi-transparent full-screen backdrop overlay
        backend.draw_rect(0.0, 0.0, vw, vh, Color(0.0, 0.0, 0.0, 0.65))

        # 2. Centered dialog box
        bx, by, bw, bh = self.layout()
        bg_col = Color(0.08, 0.10, 0.14, 0.95)
        border_col = Color(0.40, 0.45, 0.55, 0.85)
        backend.draw_rect(bx, by, bw, bh, bg_col, border_color=border_col, border_width=1.5)

        # 3. Prompt label
        prompt_x = bx + 28.0
        prompt_y = by + 26.0
        prompt_col = Color(0.95, 0.86, 0.62, 1.0)
        prompt_fs = self.scale_font_size(15)
        backend.draw_text(
            prompt_x,
            prompt_y,
            self.prompt or "Enter input:",
            font_size=prompt_fs,
            color=prompt_col,
            bold=True,
        )

        # 4. Text input field
        field_x = bx + 28.0
        field_y = by + 68.0
        field_w = bw - 56.0
        field_h = 42.0
        field_bg = Color(0.03, 0.04, 0.06, 0.90)
        field_border = Color(0.30, 0.36, 0.45, 0.90)
        backend.draw_rect(
            field_x,
            field_y,
            field_w,
            field_h,
            field_bg,
            border_color=field_border,
            border_width=1.0,
        )

        # 5. Text buffer content
        text_x = field_x + 14.0
        text_y = field_y + (field_h / 2.0)
        text_col = Color(0.95, 0.96, 0.98, 1.0)
        input_fs = self.scale_font_size(15)
        backend.draw_text(
            text_x,
            text_y,
            self.text_buffer,
            font_size=input_fs,
            color=text_col,
            anchor_y=TextAnchor.MIDDLE,
        )

        # 6. Blinking cursor
        if self.cursor_visible:
            # Measure width of current buffer to place cursor
            text_w, _ = backend.measure_text(self.text_buffer, font_size=input_fs)
            cursor_x = text_x + text_w + 2.0
            cursor_h = 20.0
            cursor_y = text_y - (cursor_h / 2.0)
            cursor_col = Color(0.95, 0.86, 0.62, 0.95)
            backend.draw_rect(cursor_x, cursor_y, 2.0, cursor_h, cursor_col)

        # 7. Help cue (Enter to submit)
        hint_y = by + bh - 24.0
        hint_col = Color(0.55, 0.60, 0.68, 0.70)
        backend.draw_text(
            bx + bw - 28.0,
            hint_y,
            "Press Enter to confirm",
            font_size=self.scale_font_size(11),
            color=hint_col,
            anchor_x=TextAnchor.RIGHT,
            anchor_y=TextAnchor.MIDDLE,
        )


class EndNotice:
    """Bottom banner announcing that the story has concluded."""

    DEFAULT_MESSAGE = "Story Concluded — Press Esc or Q to Exit"

    def __init__(
        self,
        width: int = 1280,
        height: int = 720,
        *,
        message: str | None = None,
        banner_height: float = 40.0,
        bottom_gap: float = 30.0,
        banner_fill: Color | None = None,
        text_color: Color | None = None,
        font_size: int = 16,
    ) -> None:
        self.viewport_width = width
        self.viewport_height = height
        self.message = message or self.DEFAULT_MESSAGE
        self.banner_height = banner_height
        self.bottom_gap = bottom_gap
        self.banner_fill = _END_BANNER_FILL if banner_fill is None else banner_fill
        self.text_color = _END_TEXT if text_color is None else text_color
        self.font_size = font_size

    def set_viewport(self, width: int, height: int) -> None:
        """Update the viewport the component lays itself out against."""
        self.viewport_width = width
        self.viewport_height = height

    def cache_key(self) -> tuple[Any, ...]:
        """Return a hashable key covering everything that affects rendering."""
        return (self.viewport_width, self.viewport_height, self.message)

    def layout(self) -> tuple[float, float, float, float]:
        """Return the banner ``(x, y, w, h)`` rectangle."""
        return (
            0.0,
            float(self.viewport_height) - self.banner_height - self.bottom_gap,
            float(self.viewport_width),
            self.banner_height,
        )

    def scale_font_size(self, base_size: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(self.viewport_height) / 720.0
        return max(1, round(float(base_size) * scale))

    def draw(self, backend: UIDrawBackend) -> None:
        """Render the end-of-story banner through *backend*."""
        bx, by, bw, bh = self.layout()
        backend.draw_rect(bx, by, bw, bh, self.banner_fill)
        backend.draw_text(
            bx + (bw / 2.0),
            by + (bh / 2.0),
            self.message,
            font_size=self.scale_font_size(self.font_size),
            color=self.text_color,
            anchor_x=TextAnchor.CENTER,
            anchor_y=TextAnchor.MIDDLE,
        )


class QuickMenu:
    """Bottom quick-access toolbar (Log, Skip, Auto, Save, Load, Q.Save, Q.Load, Prefs)."""

    ACTIONS = (
        ("log", "Log"),
        ("skip", "Skip"),
        ("auto", "Auto"),
        ("save", "Save"),
        ("load", "Load"),
        ("quicksave", "Q.Save"),
        ("quickload", "Q.Load"),
        ("prefs", "Prefs"),
    )

    def __init__(
        self,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        *,
        theme: Theme | None = None,
    ) -> None:
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.hovered_action: str | None = None
        self.is_read: bool = False
        self.theme: Theme | None = theme

    def set_theme(self, theme: Theme) -> None:
        """Apply styling from a Theme."""
        self.theme = theme

    def set_viewport(self, width: int, height: int) -> None:
        self.viewport_width = width
        self.viewport_height = height

    def layout(self) -> list[tuple[str, str, float, float, float, float]]:
        """Return list of (action_id, label, x, y, width, height) items."""
        item_w = 60.0
        item_h = 22.0
        gap = 8.0
        total_w = len(self.ACTIONS) * item_w + (len(self.ACTIONS) - 1) * gap
        margin_right = max(20.0, float(self.viewport_width) * 0.05)
        start_x = float(self.viewport_width) - margin_right - total_w
        # Position right at the bottom edge above gap
        y = float(self.viewport_height) - item_h - 6.0

        items = []
        for i, (act_id, label) in enumerate(self.ACTIONS):
            ix = start_x + i * (item_w + gap)
            items.append((act_id, label, ix, y, item_w, item_h))
        return items

    def hit_test(self, x: float, y: float) -> str | None:
        """Return action_id under (x, y) coordinates or None."""
        for act_id, _, bx, by, bw, bh in self.layout():
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return act_id
        return None

    def scale_font_size(self, base_size: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(self.viewport_height) / 720.0
        return max(1, round(float(base_size) * scale))

    def draw(self, backend: UIDrawBackend) -> None:
        """Render quick action buttons cleanly without harsh boxes."""
        if self.theme is not None:
            text_col = self.theme.muted_text_color
            hover_col = self.theme.text_color
            hover_pill = Color(self.theme.button_hover.r, self.theme.button_hover.g, self.theme.button_hover.b, 0.25)
            read_skip_col = self.theme.accent_color
        else:
            text_col = Color(0.68, 0.72, 0.78, 0.65)
            hover_col = Color(0.95, 0.96, 0.98, 1.0)
            hover_pill = Color(1.0, 1.0, 1.0, 0.08)
            read_skip_col = Color(0.95, 0.86, 0.62, 0.85)

        for act_id, label, bx, by, bw, bh in self.layout():
            is_hovered = getattr(self, "hovered_action", None) == act_id
            if is_hovered:
                backend.draw_rect(bx, by, bw, bh, hover_pill)
                col = hover_col
            elif act_id == "skip" and self.is_read:
                col = read_skip_col
            else:
                col = text_col

            backend.draw_text(
                bx + bw / 2.0,
                by + bh / 2.0,
                label,
                font_size=self.scale_font_size(11),
                color=col,
                anchor_x=TextAnchor.CENTER,
                anchor_y=TextAnchor.MIDDLE,
            )


@dataclass
class UIOverlay:
    """Container that owns the front-end UI components and draws them in order.

    This is the single object a player needs in order to render narrative UI.
    It holds no game logic — it mirrors whatever :class:`~eager_graphics.ui_state.UIState`
    and choice prompt it is handed, and delegates the actual drawing to its
    child components.

    Example
    -------
    ::

        overlay = UIOverlay(width=1280, height=720)
        # ... each frame, after stepping the story ...
        overlay.draw(renderer, director.ui_state, active_choice_prompt)
    """

    width: int = 1280
    height: int = 720
    dialogue_style: TextboxStyle | None = None
    choice_style: ChoiceMenuStyle | None = None
    theme: Theme | None = None
    error_overlay: str | None = None
    toast_text: str | None = None
    toast_timer: float = 0.0
    dialogue_box: DialogueBox = field(init=False)
    choice_menu: ChoiceMenu = field(init=False)
    input_box: InputBox = field(init=False)
    end_notice: EndNotice = field(init=False)
    quick_menu: QuickMenu = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.theme, dict):
            try:
                self.theme = Theme(**self.theme)
            except (TypeError, ValueError, AttributeError):
                self.theme = None
        if self.theme is not None:
            if self.dialogue_style is None:
                self.dialogue_style = self.theme.to_textbox_style()
            if self.choice_style is None:
                self.choice_style = self.theme.to_choice_menu_style()

        self.dialogue_box = DialogueBox(
            self.width,
            self.height,
            style=self.dialogue_style,
            theme=self.theme if self.dialogue_style is None else None,
        )
        self.choice_menu = ChoiceMenu(
            self.width,
            self.height,
            style=self.choice_style,
            theme=self.theme if self.choice_style is None else None,
        )
        self.input_box = InputBox(self.width, self.height)
        self.end_notice = EndNotice(self.width, self.height)
        self.quick_menu = QuickMenu(self.width, self.height, theme=self.theme)

    def set_theme(self, theme: Theme) -> None:
        """Apply a new Theme across the overlay and all child components."""
        self.theme = theme
        self.dialogue_style = theme.to_textbox_style()
        self.choice_style = theme.to_choice_menu_style()
        self.dialogue_box.set_theme(theme)
        self.choice_menu.set_theme(theme)
        self.quick_menu.set_theme(theme)

    # ── state ──────────────────────────────────────────────────────────

    def set_viewport(self, width: int, height: int) -> None:
        """Resize every child component."""
        self.width = width
        self.height = height
        self.dialogue_box.set_viewport(width, height)
        self.choice_menu.set_viewport(width, height)
        self.input_box.set_viewport(width, height)
        self.end_notice.set_viewport(width, height)
        self.quick_menu.set_viewport(width, height)

    def show_toast(self, text: str, duration: float = 2.0) -> None:
        """Display a transient toast message (e.g. quicksave/quickload confirmation)."""
        self.toast_text = text
        self.toast_timer = float(duration)

    def update_toast(self, dt: float) -> None:
        """Decrement the toast timer and clear the message when it expires."""
        if self.toast_text is not None and self.toast_timer > 0.0:
            self.toast_timer -= float(dt)
            if self.toast_timer <= 0.0:
                self.toast_text = None
                self.toast_timer = 0.0

    def sync(
        self,
        ui_state: UIState,
        choice_prompt: Any | None = None,
        input_prompt: Any | None = None,
        input_text: str | None = None,
        *,
        is_read: bool = False,
    ) -> None:
        """Mirror narrative state onto the child components."""
        self.dialogue_box.set_content(
            ui_state.speaker,
            ui_state.text,
            ui_state.emotion,
            side_image=ui_state.side_image,
            visible_chars=ui_state.visible_chars,
            speaker_color=getattr(ui_state, "speaker_color", None),
        )
        self.dialogue_box.is_read = is_read
        self.quick_menu.is_read = is_read
        plain_len = len(parse_text_tags(ui_state.text).plain_text) if ui_state.text else 0
        is_revealed = (
            ui_state.visible_chars is None or int(ui_state.visible_chars) >= plain_len
        )
        self.dialogue_box.show_advance_arrow = (
            choice_prompt is None and input_prompt is None and is_revealed
        )

        if choice_prompt is None:
            self.choice_menu.clear()
        else:
            self.choice_menu.set_options(choice_prompt.options)

        if input_prompt is None:
            self.input_box.clear()
        else:
            prompt_str = getattr(input_prompt, "prompt", "Enter input:")
            default_val = (
                input_text
                if input_text is not None
                else getattr(input_prompt, "default", "")
            )
            self.input_box.set_prompt(prompt_str, default=default_val)

    # ── drawing ────────────────────────────────────────────────────────

    def draw_nvl(
        self,
        backend: UIDrawBackend,
        ui_state: UIState,
        choice_prompt: Any | None = None,
    ) -> None:
        """Draw full-screen NVL mode text display."""
        margin_x = float(self.width) * 0.1
        margin_y = float(self.height) * 0.08
        box_w = float(self.width) - margin_x * 2.0
        box_h = float(self.height) - margin_y * 2.0

        # Semi-transparent dark background
        backend.draw_rect(
            margin_x,
            margin_y,
            box_w,
            box_h,
            Color(0.02, 0.03, 0.05, 0.88),
            border_color=Color(0.3, 0.4, 0.5, 0.8),
            border_width=1.5,
        )

        curr_y = margin_y + 25.0
        text_max_w = box_w - 40.0
        font_size = 14
        line_height = font_size * 1.4

        for entry in ui_state.nvl_entries:
            if curr_y + line_height > margin_y + box_h - 20.0:
                break
            if entry.speaker:
                backend.draw_text(
                    margin_x + 20.0,
                    curr_y,
                    entry.speaker,
                    font_size=13,
                    color=Color(1.0, 0.9, 0.45, 1.0),
                )
                curr_y += line_height * 1.1

            lines = _get_wrapped_lines(entry.text, text_max_w, backend.measure_text, font_size=font_size)
            for line_item in lines:
                line_str = line_item[0] if isinstance(line_item, tuple) else line_item
                if curr_y + line_height > margin_y + box_h - 20.0:
                    break
                backend.draw_text(
                    margin_x + 20.0,
                    curr_y,
                    line_str,
                    font_size=font_size,
                    color=Color(0.95, 0.95, 0.95, 1.0),
                )
                curr_y += line_height
            curr_y += 10.0

    def draw(
        self,
        backend: UIDrawBackend,
        ui_state: UIState,
        choice_prompt: Any | None = None,
        active_input_prompt: Any | None = None,
        input_text: str | None = None,
        *,
        is_finished: bool | None = None,
        show_quick_menu: bool = False,
        status_badge: str | None = None,
        is_read: bool = False,
    ) -> None:
        """Draw the dialogue box or NVL display, choice menu, input box, quick menu, status badge, and end notice."""
        self.sync(
            ui_state,
            choice_prompt,
            active_input_prompt,
            input_text=input_text,
            is_read=is_read,
        )
        finished = ui_state.is_finished if is_finished is None else is_finished

        if not finished:
            if ui_state.nvl_mode:
                self.draw_nvl(backend, ui_state, choice_prompt)
            elif self.dialogue_box.text:
                self.dialogue_box.draw(backend)
                if show_quick_menu and not self.choice_menu.options and not self.input_box.prompt:
                    self.quick_menu.draw(backend)

        if self.choice_menu.options:
            self.choice_menu.draw(backend)

        if self.input_box.prompt:
            self.input_box.draw(backend)

        if status_badge and not finished:
            badge_w, badge_h = 84.0, 26.0
            bx = float(self.width) - badge_w - 20.0
            by = 20.0
            fill = Color(0.06, 0.08, 0.11, 0.80)
            border = Color(1.0, 1.0, 1.0, 0.12)
            backend.draw_rect(bx, by, badge_w, badge_h, fill, border_color=border, border_width=1.0)
            backend.draw_text(
                bx + badge_w / 2.0,
                by + badge_h / 2.0,
                status_badge,
                font_size=self.scale_font_size(12),
                color=Color(0.92, 0.93, 0.95, 0.95),
                anchor_x=TextAnchor.CENTER,
                anchor_y=TextAnchor.MIDDLE,
            )

        if self.toast_text:
            tw = min(float(self.width) - 40.0, 520.0)
            th = 34.0
            tx = (float(self.width) - tw) / 2.0
            ty = float(self.height) - th - 40.0
            backend.draw_rect(
                tx,
                ty,
                tw,
                th,
                Color(0.05, 0.07, 0.10, 0.85),
                border_color=Color(1.0, 1.0, 1.0, 0.15),
                border_width=1.0,
            )
            backend.draw_text(
                tx + tw / 2.0,
                ty + th / 2.0,
                self.toast_text,
                font_size=self.scale_font_size(14),
                color=Color(0.95, 0.96, 0.98, 1.0),
                anchor_x=TextAnchor.CENTER,
                anchor_y=TextAnchor.MIDDLE,
            )

        if self.error_overlay:
            self._draw_error_overlay(backend, self.error_overlay)
        elif finished:
            self.end_notice.draw(backend)

    def scale_font_size(self, base_size: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(self.height) / 720.0
        return max(1, round(float(base_size) * scale))

    def _draw_error_overlay(self, backend: UIDrawBackend, message: str) -> None:
        """Draw a safe error overlay box centered on screen."""
        box_w = min(float(self.width) - 80.0, 680.0)
        box_h = 160.0
        bx = (float(self.width) - box_w) / 2.0
        by = (float(self.height) - box_h) / 2.0

        fill = Color(0.12, 0.03, 0.03, 0.94)
        border = Color(0.85, 0.25, 0.25, 0.95)
        backend.draw_rect(bx, by, box_w, box_h, fill, border_color=border, border_width=2.0)

        backend.draw_text(
            bx + 24.0,
            by + 24.0,
            "Scene Not Found",
            font_size=self.scale_font_size(18),
            color=Color(1.0, 0.4, 0.4, 1.0),
            bold=True,
        )
        backend.draw_text(
            bx + 24.0,
            by + 64.0,
            message,
            font_size=self.scale_font_size(14),
            color=Color(0.95, 0.95, 0.95, 1.0),
        )
        backend.draw_text(
            bx + 24.0,
            by + 112.0,
            "Hot-Reload: Edit screenplay and press Shift+R to reload.",
            font_size=self.scale_font_size(12),
            color=Color(0.7, 0.7, 0.75, 0.8),
        )


    # ── input ──────────────────────────────────────────────────────────

    def hit_test_choice(self, x: float, y: float) -> int | None:
        """Return the option index under the point, or *None*."""
        return self.choice_menu.hit_test(x, y)

    def hit_test_quick_action(self, x: float, y: float) -> str | None:
        """Return the quick menu action under the point (e.g. 'save', 'load'), or None."""
        if not self.dialogue_box.text:
            return None
        return self.quick_menu.hit_test(x, y)

    def get_selected_choice(self) -> int | None:
        """Return the index of the currently selected choice option, or None."""
        if hasattr(self, "choice_menu") and self.choice_menu is not None:
            return self.choice_menu.selected_index
        return None

    def set_selected_choice(self, index: int | None) -> None:
        """Update the selected choice option index."""
        if hasattr(self, "choice_menu") and self.choice_menu is not None:
            self.choice_menu.selected_index = index

    def set_choice_options(self, options: Any) -> None:
        """Update the displayed choice menu options."""
        if hasattr(self, "choice_menu") and self.choice_menu is not None:
            self.choice_menu.set_options(options)

    def set_input_text(self, text: str) -> None:
        """Update the text buffer displayed by the input box."""
        if hasattr(self, "input_box") and self.input_box is not None:
            self.input_box.text_buffer = text

    def update_input(self, dt: float) -> None:
        """Advance cursor animation or timers in the input box."""
        if hasattr(self, "input_box") and self.input_box is not None:
            self.input_box.update(dt)

    def set_dialogue_visible_chars(
        self,
        visible_chars: int | None = None,
        *,
        show_arrow: bool = True,
    ) -> None:
        """Update visible character limit and advance indicator on the dialogue box."""
        if hasattr(self, "dialogue_box") and self.dialogue_box is not None:
            self.dialogue_box.visible_chars = visible_chars
            self.dialogue_box.show_advance_arrow = show_arrow

    def complete_dialogue_reveal(self, *, show_arrow: bool = True) -> None:
        """Snap dialogue box typewriter reveal to fully revealed."""
        self.set_dialogue_visible_chars(None, show_arrow=show_arrow)

    def get_hovered_quick_action(self) -> str | None:
        """Return the currently hovered quick action identifier."""
        if hasattr(self, "quick_menu") and self.quick_menu is not None:
            return getattr(self.quick_menu, "hovered_action", None)
        return None

    def set_hovered_quick_action(self, action: str | None) -> None:
        """Update the hovered quick action identifier."""
        if hasattr(self, "quick_menu") and self.quick_menu is not None:
            self.quick_menu.hovered_action = action
