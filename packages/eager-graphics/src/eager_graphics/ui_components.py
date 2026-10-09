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
:mod:`eager_graphics.types`.  Backends with a different native origin (such as
Pyglet) flip ``y`` when issuing primitives, so components never need to care.

Typical use::

    overlay = UIOverlay(width=1280, height=720)
    ...
    overlay.draw(backend, ui_state, choice_prompt)
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from eager_graphics.types import Color

if TYPE_CHECKING:
    from eager_graphics.protocol import UIDrawBackend
    from eager_graphics.ui_state import ChoiceOption, UIState

__all__ = [
    "ChoiceMenu",
    "ChoiceMenuStyle",
    "DialogueBox",
    "DialogueBoxLayout",
    "EndNotice",
    "TextAnchor",
    "TextboxStyle",
    "UIOverlay",
    "wrap_text",
]

# Palette used by the default component styling.  Mirrors the colours the
# bundled players hard-coded before these components were extracted.
_TEXTBOX_FILL = Color(0.059, 0.071, 0.098, 0.863)
_TEXTBOX_BORDER = Color(0.471, 0.549, 0.706, 1.0)
_NAMEPLATE_FILL = Color(0.137, 0.176, 0.255, 0.941)
_NAMEPLATE_BORDER = Color(0.627, 0.706, 0.863, 1.0)
_NAMEPLATE_TEXT = Color(1.0, 0.902, 0.471, 1.0)
_DIALOGUE_TEXT = Color(0.961, 0.961, 0.961, 1.0)
_ADVANCE_ARROW = Color(0.784, 0.784, 0.784, 0.784)

_CHOICE_FILL = Color(0.098, 0.118, 0.176, 0.902)
_CHOICE_BORDER = Color(0.353, 0.510, 0.784, 1.0)
_CHOICE_TEXT = Color(1.0, 1.0, 1.0, 1.0)

_END_BANNER_FILL = Color(0.0, 0.0, 0.0, 0.706)
_END_TEXT = Color(0.784, 0.784, 0.784, 0.863)


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

    Defaults reproduce the look the bundled players shipped with before the
    components were extracted, so existing screenplays render unchanged.
    """

    box_fill: Color = _TEXTBOX_FILL
    box_border: Color = _TEXTBOX_BORDER
    box_border_width: float = 2.0

    nameplate_fill: Color = _NAMEPLATE_FILL
    nameplate_border: Color = _NAMEPLATE_BORDER
    nameplate_text: Color = _NAMEPLATE_TEXT
    nameplate_font_size: int = 13

    text_color: Color = _DIALOGUE_TEXT
    text_font_size: int = 14
    text_padding: float = 20.0

    arrow_color: Color = _ADVANCE_ARROW
    arrow_font_size: int = 12

    min_height: float = 110.0
    height_ratio: float = 0.22
    margin_ratio: float = 0.05
    min_margin: float = 20.0
    bottom_gap: float = 25.0
    nameplate_overlap: float = 15.0

    def box_height(self, viewport_height: float) -> float:
        """Return the textbox height for a viewport of *viewport_height* pixels."""
        return float(max(self.min_height, int(viewport_height * self.height_ratio)))

    def box_margin(self, viewport_width: float) -> float:
        """Return the horizontal gutter either side of the textbox."""
        return float(max(self.min_margin, int(viewport_width * self.margin_ratio)))


def wrap_text(
    text: str,
    max_width: float,
    measure: Any,
    *,
    font_size: int = 14,
) -> list[str]:
    """Wrap text to fit within max_width using greedy word-wrapping.

    Respects explicit newlines and breaks overlong words that cannot fit on a single line.
    """
    if not text or max_width <= 0:
        return []

    lines: list[str] = []
    paragraphs = text.split("\n")

    for para in paragraphs:
        if not para:
            lines.append("")
            continue

        words = para.split(" ")
        current_line = ""

        for word in words:
            candidate = f"{current_line} {word}" if current_line else word
            w, _ = measure(candidate, font_size=font_size)
            if w <= max_width:
                current_line = candidate
            else:
                if current_line:
                    lines.append(current_line)
                    current_line = ""

                # Check if word alone fits
                word_w, _ = measure(word, font_size=font_size)
                if word_w <= max_width:
                    current_line = word
                else:
                    # Break overlong word character by character
                    sub = ""
                    for char in word:
                        sub_candidate = sub + char
                        cw, _ = measure(sub_candidate, font_size=font_size)
                        if cw <= max_width:
                            sub = sub_candidate
                        else:
                            if sub:
                                lines.append(sub)
                            sub = char
                    current_line = sub

        if current_line:
            lines.append(current_line)

    return lines


# Cache for wrap_text results: (text, max_width, font_size) -> list[str]
_WRAP_CACHE: dict[tuple[str, float, int], list[str]] = {}


def _get_wrapped_lines(
    text: str,
    max_width: float,
    measure: Any,
    font_size: int = 14,
) -> list[str]:
    key = (text, max_width, font_size)
    if key in _WRAP_CACHE:
        return _WRAP_CACHE[key]
    res = wrap_text(text, max_width, measure, font_size=font_size)
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
    ) -> None:
        self.style = style or TextboxStyle()
        self.viewport_width = width
        self.viewport_height = height
        self.speaker: str | None = None
        self.text: str = ""
        self.emotion: str | None = None
        self.side_image: str | None = None
        self.show_advance_arrow: bool = True

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
    ) -> None:
        """Set the speaker name, dialogue text, emotion tag, and optional side image."""
        self.speaker = speaker
        self.text = text
        self.emotion = emotion
        self.side_image = side_image

    def clear(self) -> None:
        """Reset to an empty, undrawn state."""
        self.speaker = None
        self.text = ""
        self.emotion = None
        self.side_image = None
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
        )

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

        box_w = float(vw - style.box_margin(vw) * 2)
        box_h = style.box_height(vh)
        box_x = style.box_margin(vw)
        box_y = float(vh) - box_h - style.bottom_gap

        has_speaker = bool(self.speaker)
        nameplate: tuple[float, float, float, float] | None = None
        if has_speaker:
            name_w = self.nameplate_width()
            name_h = 30.0
            # The nameplate straddles the top edge of the box, as is
            # conventional for visual-novel dialogue.
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

        backend.draw_rect(
            box_x,
            box_y,
            box_w,
            box_h,
            style.box_fill,
            border_color=style.box_border,
            border_width=style.box_border_width,
        )

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
            backend.draw_text(
                nx + 12.0,
                ny + (nh / 2.0),
                self.speaker,
                font_size=style.nameplate_font_size,
                color=style.nameplate_text,
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

        line_height = style.text_font_size * 1.35
        lines = _get_wrapped_lines(self.text, text_max_w, backend.measure_text, font_size=style.text_font_size)

        for i, line in enumerate(lines):
            backend.draw_text(
                text_start_x,
                box_y + 24.0 + (i * line_height),
                line,
                font_size=style.text_font_size,
                color=style.text_color,
            )

        if layout.show_arrow:
            backend.draw_text(
                box_x + box_w - 30.0,
                box_y + box_h - 25.0,
                "▼",
                font_size=style.arrow_font_size,
                color=style.arrow_color,
            )



@dataclass(frozen=True, slots=True)
class ChoiceMenuStyle:
    """Visual styling for :class:`ChoiceMenu`."""

    button_fill: Color = _CHOICE_FILL
    button_border: Color = _CHOICE_BORDER
    button_border_width: float = 2.0
    button_width: int = 600
    button_width_ratio: float = 0.6
    button_height: float = 42.0
    spacing: float = 12.0
    text_color: Color = _CHOICE_TEXT
    text_font_size: int = 13
    text_padding: float = 20.0

    def button_width_for(self, viewport_width: float) -> float:
        """Return the button width for a viewport of *viewport_width* pixels."""
        return float(min(self.button_width, int(viewport_width * self.button_width_ratio)))


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
    ) -> None:
        self.style = style or ChoiceMenuStyle()
        self.viewport_width = width
        self.viewport_height = height
        self.options: tuple[ChoiceOption, ...] = ()

    def set_viewport(self, width: int, height: int) -> None:
        """Update the viewport the component lays itself out against."""
        self.viewport_width = width
        self.viewport_height = height

    def set_options(self, options: Sequence[ChoiceOption] | None) -> None:
        """Set the active options; *None* or an empty sequence clears the menu."""
        self.options = tuple(options) if options else ()

    def clear(self) -> None:
        """Remove all options."""
        self.options = ()

    def cache_key(self) -> tuple[Any, ...]:
        """Return a hashable key covering everything that affects rendering."""
        return (
            self.viewport_width,
            self.viewport_height,
            tuple((opt.index, opt.text) for opt in self.options),
        )

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
        """Return the index of the option under the point, or *None*.

        Uses the exact same rectangles produced by :meth:`layout`, so hit
        testing stays correct across resolutions and option counts.
        """
        for index, (bx, by, bw, bh) in enumerate(self.layout()):
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return index
        return None

    def draw(self, backend: UIDrawBackend) -> None:
        """Render every option button through *backend*."""
        if not self.options:
            return

        style = self.style
        for index, (bx, by, bw, bh) in enumerate(self.layout()):
            backend.draw_rect(
                bx,
                by,
                bw,
                bh,
                style.button_fill,
                border_color=style.button_border,
                border_width=style.button_border_width,
            )
            opt = self.options[index]
            backend.draw_text(
                bx + style.text_padding,
                by + (bh / 2.0),
                f"[{index + 1}]  {opt.text}",
                font_size=style.text_font_size,
                color=style.text_color,
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

    def draw(self, backend: UIDrawBackend) -> None:
        """Render the end-of-story banner through *backend*."""
        bx, by, bw, bh = self.layout()
        backend.draw_rect(bx, by, bw, bh, self.banner_fill)
        backend.draw_text(
            bx + (bw / 2.0),
            by + (bh / 2.0),
            self.message,
            font_size=self.font_size,
            color=self.text_color,
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
    dialogue_box: DialogueBox = field(init=False)
    choice_menu: ChoiceMenu = field(init=False)
    end_notice: EndNotice = field(init=False)

    def __post_init__(self) -> None:
        self.dialogue_box = DialogueBox(self.width, self.height)
        self.choice_menu = ChoiceMenu(self.width, self.height)
        self.end_notice = EndNotice(self.width, self.height)

    # ── state ──────────────────────────────────────────────────────────

    def set_viewport(self, width: int, height: int) -> None:
        """Resize every child component."""
        self.width = width
        self.height = height
        self.dialogue_box.set_viewport(width, height)
        self.choice_menu.set_viewport(width, height)
        self.end_notice.set_viewport(width, height)

    def sync(self, ui_state: UIState, choice_prompt: Any | None = None) -> None:
        """Mirror narrative state onto the child components."""
        self.dialogue_box.set_content(
            ui_state.speaker,
            ui_state.text,
            ui_state.emotion,
            side_image=ui_state.side_image,
        )
        self.dialogue_box.show_advance_arrow = choice_prompt is None

        if choice_prompt is None:
            self.choice_menu.clear()
        else:
            self.choice_menu.set_options(choice_prompt.options)

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
            for line in lines:
                if curr_y + line_height > margin_y + box_h - 20.0:
                    break
                backend.draw_text(
                    margin_x + 20.0,
                    curr_y,
                    line,
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
        *,
        is_finished: bool | None = None,
    ) -> None:
        """Draw the dialogue box or NVL display, choice menu, and end notice."""
        self.sync(ui_state, choice_prompt)
        finished = ui_state.is_finished if is_finished is None else is_finished

        if not finished:
            if ui_state.nvl_mode:
                self.draw_nvl(backend, ui_state, choice_prompt)
            elif self.dialogue_box.text:
                self.dialogue_box.draw(backend)

        if self.choice_menu.options:
            self.choice_menu.draw(backend)

        if finished:
            self.end_notice.draw(backend)


    # ── input ──────────────────────────────────────────────────────────

    def hit_test_choice(self, x: float, y: float) -> int | None:
        """Return the option index under the point, or *None*."""
        return self.choice_menu.hit_test(x, y)
