"""Customizable visual theme definitions for Eager visual novels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eager_core.types import Color

_CINEMATIC_BG_COLOR = Color(0.06, 0.07, 0.09, 1.0)
_CINEMATIC_PRIMARY_COLOR = Color(0.28, 0.38, 0.52, 1.0)
_CINEMATIC_ACCENT_COLOR = Color(0.90, 0.83, 0.65, 1.0)
_CINEMATIC_TEXT_COLOR = Color(0.92, 0.93, 0.95, 1.0)
_CINEMATIC_MUTED_TEXT_COLOR = Color(0.65, 0.68, 0.72, 1.0)

_CINEMATIC_DIALOGUE_BOX_FILL = Color(0.04, 0.05, 0.07, 0.85)
_CINEMATIC_DIALOGUE_BOX_BORDER = Color(1.0, 1.0, 1.0, 0.08)
_CINEMATIC_NAMEPLATE_FILL = Color(0.0, 0.0, 0.0, 0.0)
_CINEMATIC_NAMEPLATE_TEXT = Color(0.90, 0.83, 0.65, 1.0)

_CINEMATIC_BUTTON_FILL = Color(0.08, 0.10, 0.14, 0.80)
_CINEMATIC_BUTTON_HOVER = Color(0.14, 0.17, 0.22, 0.92)
_CINEMATIC_BUTTON_BORDER = Color(1.0, 1.0, 1.0, 0.12)
_CINEMATIC_BUTTON_TEXT = Color(0.93, 0.94, 0.96, 1.0)

# Legacy retro palette
_CLASSIC_BG_COLOR = Color(0.05, 0.05, 0.07, 1.0)
_CLASSIC_PRIMARY_COLOR = Color(0.2, 0.4, 0.8, 1.0)
_CLASSIC_ACCENT_COLOR = Color(1.0, 0.8, 0.2, 1.0)
_CLASSIC_TEXT_COLOR = Color(0.95, 0.95, 0.95, 1.0)
_CLASSIC_MUTED_TEXT_COLOR = Color(0.7, 0.7, 0.7, 1.0)
_CLASSIC_DIALOGUE_BOX_FILL = Color(0.06, 0.07, 0.1, 0.86)
_CLASSIC_DIALOGUE_BOX_BORDER = Color(0.47, 0.55, 0.71, 1.0)
_CLASSIC_NAMEPLATE_FILL = Color(0.14, 0.18, 0.26, 0.94)
_CLASSIC_NAMEPLATE_TEXT = Color(1.0, 0.9, 0.47, 1.0)
_CLASSIC_BUTTON_FILL = Color(0.1, 0.12, 0.18, 0.9)
_CLASSIC_BUTTON_HOVER = Color(0.2, 0.3, 0.5, 0.9)
_CLASSIC_BUTTON_BORDER = Color(0.35, 0.51, 0.78, 1.0)
_CLASSIC_BUTTON_TEXT = Color(1.0, 1.0, 1.0, 1.0)


@dataclass(frozen=True, slots=True)
class Theme:
    """Complete visual theme configuration for UI chrome, dialogue box, and menus."""

    name: str = "default"

    # Primary colors
    bg_color: Color = _CINEMATIC_BG_COLOR
    primary_color: Color = _CINEMATIC_PRIMARY_COLOR
    accent_color: Color = _CINEMATIC_ACCENT_COLOR
    text_color: Color = _CINEMATIC_TEXT_COLOR
    muted_text_color: Color = _CINEMATIC_MUTED_TEXT_COLOR

    # Dialogue box
    dialogue_box_fill: Color = _CINEMATIC_DIALOGUE_BOX_FILL
    dialogue_box_border: Color = _CINEMATIC_DIALOGUE_BOX_BORDER
    nameplate_fill: Color = _CINEMATIC_NAMEPLATE_FILL
    nameplate_text: Color = _CINEMATIC_NAMEPLATE_TEXT

    # Buttons and choices
    button_fill: Color = _CINEMATIC_BUTTON_FILL
    button_hover: Color = _CINEMATIC_BUTTON_HOVER
    button_border: Color = _CINEMATIC_BUTTON_BORDER
    button_text: Color = _CINEMATIC_BUTTON_TEXT

    # Fonts
    font_family: str = "sans-serif"
    font_size: int = 16
    title_font_size: int = 32

    @classmethod
    def cinematic(cls) -> Theme:
        """Clean, minimal, eye-friendly theme with soft dark tones and subtle highlights."""
        return cls(name="cinematic")

    @classmethod
    def classic(cls) -> Theme:
        """Legacy boxed theme with retro high-contrast blue borders and bright yellow nameplate."""
        return cls(
            name="classic",
            bg_color=_CLASSIC_BG_COLOR,
            primary_color=_CLASSIC_PRIMARY_COLOR,
            accent_color=_CLASSIC_ACCENT_COLOR,
            text_color=_CLASSIC_TEXT_COLOR,
            muted_text_color=_CLASSIC_MUTED_TEXT_COLOR,
            dialogue_box_fill=_CLASSIC_DIALOGUE_BOX_FILL,
            dialogue_box_border=_CLASSIC_DIALOGUE_BOX_BORDER,
            nameplate_fill=_CLASSIC_NAMEPLATE_FILL,
            nameplate_text=_CLASSIC_NAMEPLATE_TEXT,
            button_fill=_CLASSIC_BUTTON_FILL,
            button_hover=_CLASSIC_BUTTON_HOVER,
            button_border=_CLASSIC_BUTTON_BORDER,
            button_text=_CLASSIC_BUTTON_TEXT,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "font_family": self.font_family,
            "font_size": self.font_size,
        }
