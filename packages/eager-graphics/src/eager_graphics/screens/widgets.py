"""Immediate-mode UI widgets: Button, Label, Slider, Bar, Grid."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from eager_graphics.protocol import UIDrawBackend
from eager_graphics.types import Color, Rect
from eager_graphics.ui_components import TextAnchor


@dataclass
class Button:
    """Selectable interactive button widget."""

    rect: Rect
    text: str
    action: Callable[[], Any] | None = None
    enabled: bool = True
    hovered: bool = False

    def hit_test(self, x: float, y: float) -> bool:
        """Return True if (x, y) coordinates fall within the button boundary."""
        return (
            self.rect.x <= x <= self.rect.x + self.rect.width
            and self.rect.y <= y <= self.rect.y + self.rect.height
        )

    def draw(
        self,
        backend: UIDrawBackend,
        fill_color: Color,
        hover_color: Color,
        border_color: Color,
        text_color: Color,
        font_size: int = 16,
    ) -> None:
        """Render button rectangle and text."""
        col = hover_color if self.hovered else fill_color
        backend.draw_rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height, col)
        backend.draw_rect_outline(
            self.rect.x, self.rect.y, self.rect.width, self.rect.height, border_color, line_width=1.5
        )
        tx = self.rect.x + self.rect.width / 2
        ty = self.rect.y + self.rect.height / 2
        backend.draw_text(
            self.text,
            tx,
            ty,
            color=text_color,
            font_size=font_size,
            anchor_x=TextAnchor.CENTER,
            anchor_y=TextAnchor.MIDDLE,
        )


@dataclass
class Label:
    """Text label widget."""

    text: str
    x: float
    y: float
    color: Color
    font_size: int = 16
    anchor_x: str = TextAnchor.LEFT
    anchor_y: str = TextAnchor.TOP

    def draw(self, backend: UIDrawBackend) -> None:
        backend.draw_text(
            self.text,
            self.x,
            self.y,
            color=self.color,
            font_size=self.font_size,
            anchor_x=self.anchor_x,
            anchor_y=self.anchor_y,
        )


@dataclass
class Slider:
    """Numeric range slider widget."""

    rect: Rect
    value: float  # 0.0 - 1.0
    on_change: Callable[[float], None] | None = None

    def hit_test(self, x: float, y: float) -> bool:
        return (
            self.rect.x <= x <= self.rect.x + self.rect.width
            and self.rect.y <= y <= self.rect.y + self.rect.height
        )

    def handle_click(self, x: float, y: float) -> None:
        if self.hit_test(x, y):
            rel = (x - self.rect.x) / self.rect.width
            self.value = max(0.0, min(1.0, rel))
            if self.on_change:
                self.on_change(self.value)

    def draw(self, backend: UIDrawBackend, bar_color: Color, fill_color: Color) -> None:
        # Background bar
        backend.draw_rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height, bar_color)
        # Filled portion
        fill_w = self.rect.width * self.value
        backend.draw_rect(self.rect.x, self.rect.y, fill_w, self.rect.height, fill_color)
