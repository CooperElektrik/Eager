"""Customizable visual theme definitions for Eager visual novels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eager_graphics.types import Color

_DEFAULT_BG_COLOR = Color(0.05, 0.05, 0.07, 1.0)
_DEFAULT_PRIMARY_COLOR = Color(0.2, 0.4, 0.8, 1.0)
_DEFAULT_ACCENT_COLOR = Color(1.0, 0.8, 0.2, 1.0)
_DEFAULT_TEXT_COLOR = Color(0.95, 0.95, 0.95, 1.0)
_DEFAULT_MUTED_TEXT_COLOR = Color(0.7, 0.7, 0.7, 1.0)

_DEFAULT_DIALOGUE_BOX_FILL = Color(0.06, 0.07, 0.1, 0.86)
_DEFAULT_DIALOGUE_BOX_BORDER = Color(0.47, 0.55, 0.71, 1.0)
_DEFAULT_NAMEPLATE_FILL = Color(0.14, 0.18, 0.26, 0.94)
_DEFAULT_NAMEPLATE_TEXT = Color(1.0, 0.9, 0.47, 1.0)

_DEFAULT_BUTTON_FILL = Color(0.1, 0.12, 0.18, 0.9)
_DEFAULT_BUTTON_HOVER = Color(0.2, 0.3, 0.5, 0.9)
_DEFAULT_BUTTON_BORDER = Color(0.35, 0.51, 0.78, 1.0)
_DEFAULT_BUTTON_TEXT = Color(1.0, 1.0, 1.0, 1.0)


@dataclass(frozen=True, slots=True)
class Theme:
    """Complete visual theme configuration for UI chrome, dialogue box, and menus."""

    name: str = "default"

    # Primary colors
    bg_color: Color = _DEFAULT_BG_COLOR
    primary_color: Color = _DEFAULT_PRIMARY_COLOR
    accent_color: Color = _DEFAULT_ACCENT_COLOR
    text_color: Color = _DEFAULT_TEXT_COLOR
    muted_text_color: Color = _DEFAULT_MUTED_TEXT_COLOR

    # Dialogue box
    dialogue_box_fill: Color = _DEFAULT_DIALOGUE_BOX_FILL
    dialogue_box_border: Color = _DEFAULT_DIALOGUE_BOX_BORDER
    nameplate_fill: Color = _DEFAULT_NAMEPLATE_FILL
    nameplate_text: Color = _DEFAULT_NAMEPLATE_TEXT

    # Buttons and choices
    button_fill: Color = _DEFAULT_BUTTON_FILL
    button_hover: Color = _DEFAULT_BUTTON_HOVER
    button_border: Color = _DEFAULT_BUTTON_BORDER
    button_text: Color = _DEFAULT_BUTTON_TEXT

    # Fonts
    font_family: str = "sans-serif"
    font_size: int = 16
    title_font_size: int = 32

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "font_family": self.font_family,
            "font_size": self.font_size,
        }
