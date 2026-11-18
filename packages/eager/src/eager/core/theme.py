"""Customizable visual theme definitions for Eager visual novels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from eager.core.types import Color

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

    # Layout modes
    layout_mode: str = "cinematic"  # "cinematic" or "classic"
    show_numbering: bool = False

    def scale_font_size(self, base_size: float, viewport_height: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(viewport_height) / 720.0
        return max(1, round(float(base_size) * scale))

    def scaled_font_size(self, viewport_height: float) -> int:
        """Return the theme font_size scaled to the given viewport height."""
        return self.scale_font_size(self.font_size, viewport_height)

    def scaled_title_font_size(self, viewport_height: float) -> int:
        """Return the theme title_font_size scaled to the given viewport height."""
        return self.scale_font_size(self.title_font_size, viewport_height)

    def to_dict(self) -> dict[str, Any]:
        """Serialize basic theme configuration to a dictionary."""
        return {
            "name": self.name,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "layout_mode": self.layout_mode,
            "show_numbering": self.show_numbering,
        }

    @classmethod
    def cinematic(cls) -> Theme:
        """Create a default cinematic theme preset."""
        return cls(name="cinematic", layout_mode="cinematic")

    @classmethod
    def classic(cls) -> Theme:
        """Create a classic visual novel theme preset."""
        return cls(
            name="classic",
            layout_mode="classic",
            show_numbering=True,
            nameplate_fill=Color(0.08, 0.10, 0.14, 0.95),
            dialogue_box_fill=Color(0.05, 0.07, 0.10, 0.92),
        )

    @classmethod
    def from_name(cls, name: str) -> Theme:
        """Resolve a named preset theme."""
        clean = name.strip().lower()
        if clean == "classic":
            return cls.classic()
        if clean in ("cinematic", "default"):
            return cls.cinematic()
        return cls(name=name)


__all__ = ["Theme"]
