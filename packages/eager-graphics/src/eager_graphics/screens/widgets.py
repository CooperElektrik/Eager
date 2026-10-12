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
        if hasattr(backend, "draw_rect_outline"):
            backend.draw_rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height, col)
            backend.draw_rect_outline(
                self.rect.x, self.rect.y, self.rect.width, self.rect.height, border_color, line_width=1.5
            )
        else:
            backend.draw_rect(
                self.rect.x,
                self.rect.y,
                self.rect.width,
                self.rect.height,
                col,
                border_color=border_color,
                border_width=1.5,
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


@dataclass
class Bar:
    """Progress or status meter bar widget."""

    rect: Rect
    value: float = 0.0
    max_value: float = 1.0

    def draw(
        self,
        backend: UIDrawBackend,
        bar_color: Color,
        fill_color: Color,
        border_color: Color | None = None,
        line_width: float = 1.0,
    ) -> None:
        """Render bar background, filled portion, and optional border."""
        ratio = max(0.0, min(1.0, self.value / self.max_value)) if self.max_value > 0 else 0.0
        fill_w = self.rect.width * ratio

        if border_color is not None:
            if hasattr(backend, "draw_rect_outline"):
                backend.draw_rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height, bar_color)
                if fill_w > 0:
                    backend.draw_rect(self.rect.x, self.rect.y, fill_w, self.rect.height, fill_color)
                backend.draw_rect_outline(
                    self.rect.x, self.rect.y, self.rect.width, self.rect.height, border_color, line_width=line_width
                )
            else:
                backend.draw_rect(
                    self.rect.x,
                    self.rect.y,
                    self.rect.width,
                    self.rect.height,
                    bar_color,
                    border_color=border_color,
                    border_width=line_width,
                )
                if fill_w > 0:
                    backend.draw_rect(self.rect.x, self.rect.y, fill_w, self.rect.height, fill_color)
        else:
            backend.draw_rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height, bar_color)
            if fill_w > 0:
                backend.draw_rect(self.rect.x, self.rect.y, fill_w, self.rect.height, fill_color)


@dataclass
class Grid:
    """Layout helper for positioning items in a row/column grid."""

    rect: Rect
    rows: int
    cols: int
    padding: float = 10.0
    spacing_x: float = 10.0
    spacing_y: float = 10.0

    def cell_rect(self, row: int, col: int) -> Rect:
        """Compute the Rect for the cell at (row, col)."""
        avail_w = self.rect.width - 2 * self.padding - (self.cols - 1) * self.spacing_x
        avail_h = self.rect.height - 2 * self.padding - (self.rows - 1) * self.spacing_y
        cell_w = max(0.0, avail_w / self.cols) if self.cols > 0 else 0.0
        cell_h = max(0.0, avail_h / self.rows) if self.rows > 0 else 0.0

        x = self.rect.x + self.padding + col * (cell_w + self.spacing_x)
        y = self.rect.y + self.padding + row * (cell_h + self.spacing_y)
        return Rect(x, y, cell_w, cell_h)

    def cell_rect_by_index(self, index: int) -> Rect:
        """Compute the Rect for the cell at flat index."""
        row = index // self.cols if self.cols > 0 else 0
        col = index % self.cols if self.cols > 0 else 0
        return self.cell_rect(row, col)


__all__ = ["Bar", "Button", "Grid", "Label", "Slider"]
