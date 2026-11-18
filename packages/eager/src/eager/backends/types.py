"""Shared rendering protocols and item types for backends, stage, and UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from eager.core.types import WHITE, Anchor, Color

__all__ = [
    "RenderBackend",
    "RenderItem",
    "UIDrawBackend",
]


@dataclass(frozen=True, slots=True)
class RenderItem:
    """An individual visual draw command output by the compositor in global render order."""

    asset_id: str
    x: float
    y: float
    opacity: float
    scale_x: float
    scale_y: float
    rotation: float
    anchor: Anchor
    tint: Color
    flip_h: bool
    flip_v: bool
    layer: str
    z_order: int


@runtime_checkable
class RenderBackend(Protocol):
    """Protocol implemented by the rendering backends (Null, Pyglet)."""

    def begin_frame(self) -> None:
        """Invoked at the beginning of each frame render pass."""
        ...

    def clear(self, color: Color) -> None:
        """Clear the frame buffer with the given background color."""
        ...

    def draw_item(self, item: RenderItem) -> None:
        """Render a single compositor item to the target display buffer."""
        ...

    def end_frame(self) -> None:
        """Invoked when all items for the frame have been submitted."""
        ...


@runtime_checkable
class UIDrawBackend(Protocol):
    """Low-level drawing primitives used by renderer-agnostic UI components."""

    def draw_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: Color,
        *,
        border_color: Color | None = None,
        border_width: float = 0.0,
    ) -> None:
        """Fill a rectangle, optionally stroking a border of *border_width* pixels."""
        ...

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        """Fill a rectangle with a vertical linear gradient from top_color to bottom_color."""
        ...

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: int = 14,
        color: Color = WHITE,
        bold: bool = False,
        italic: bool = False,
        anchor_x: str = "left",
        anchor_y: str = "top",
        cache: bool = True,
        font_family: str | None = None,
    ) -> None:
        """Draw a single line of text."""
        ...

    def draw_image(
        self,
        asset_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        tint: Color = WHITE,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        """Draw a resolved asset scaled into the given box, with optional tint."""
        ...

    def measure_text(
        self,
        text: str,
        *,
        font_size: int = 14,
        bold: bool = False,
        italic: bool = False,
        cache: bool = True,
        font_family: str | None = None,
    ) -> tuple[float, float]:
        """Return ``(width, height)`` in pixels for the given single-line text."""
        ...
