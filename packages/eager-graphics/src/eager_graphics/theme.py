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

    def to_textbox_style(self, **overrides: Any) -> Any:
        """Create a TextboxStyle aligned with this theme."""
        import sys

        textbox_style_cls = getattr(
            sys.modules.get("eager_graphics.ui_components"),
            "TextboxStyle",
            None,
        )
        if textbox_style_cls is None:
            import importlib

            mod = importlib.import_module("eager_graphics.ui_components")
            textbox_style_cls = mod.TextboxStyle

        show_box = self.nameplate_fill.a > 0.05
        nameplate_border = self.dialogue_box_border if show_box else Color(0.0, 0.0, 0.0, 0.0)

        kwargs: dict[str, Any] = {
            "box_fill": self.dialogue_box_fill,
            "box_border": self.dialogue_box_border,
            "box_border_width": 1.0 if self.dialogue_box_border.a > 0.05 else 0.0,
            "gradient_mid": self.dialogue_box_fill,
            "gradient_bottom": self.dialogue_box_fill,
            "nameplate_fill": self.nameplate_fill,
            "nameplate_border": nameplate_border,
            "nameplate_text": self.nameplate_text,
            "show_nameplate_box": show_box,
            "text_color": self.text_color,
            "text_font_size": max(12, self.font_size - 1) if self.font_size != 16 else 15,
            "nameplate_font_size": max(12, self.font_size - 1) if self.font_size != 16 else 15,
            "arrow_color": self.accent_color,
            "arrow_font_size": max(10, self.font_size - 2) if self.font_size != 16 else 14,
        }
        kwargs.update(overrides)
        return textbox_style_cls(**kwargs)

    def to_choice_menu_style(self, **overrides: Any) -> Any:
        """Create a ChoiceMenuStyle aligned with this theme."""
        import sys

        choice_style_cls = getattr(
            sys.modules.get("eager_graphics.ui_components"),
            "ChoiceMenuStyle",
            None,
        )
        if choice_style_cls is None:
            import importlib

            mod = importlib.import_module("eager_graphics.ui_components")
            choice_style_cls = mod.ChoiceMenuStyle

        disabled_fill = Color(
            self.button_fill.r * 0.5,
            self.button_fill.g * 0.5,
            self.button_fill.b * 0.5,
            self.button_fill.a * 0.75,
        )
        disabled_border = Color(
            self.button_border.r * 0.5,
            self.button_border.g * 0.5,
            self.button_border.b * 0.5,
            self.button_border.a * 0.5,
        )
        kwargs: dict[str, Any] = {
            "button_fill": self.button_fill,
            "button_border": self.button_border,
            "button_border_width": 1.0 if self.button_border.a > 0.05 else 0.0,
            "button_hover_fill": self.button_hover,
            "button_hover_border": self.accent_color,
            "accent_bar_color": self.accent_color,
            "text_color": self.button_text,
            "disabled_text_color": self.muted_text_color,
            "disabled_button_fill": disabled_fill,
            "disabled_button_border": disabled_border,
            "text_font_size": max(12, self.font_size - 2) if self.font_size != 16 else 14,
        }
        kwargs.update(overrides)
        return choice_style_cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "font_family": self.font_family,
            "font_size": self.font_size,
        }


__all__ = ["Theme"]
