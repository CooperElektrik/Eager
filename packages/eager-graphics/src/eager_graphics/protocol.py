"""Render list protocol and backend abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from eager_graphics.types import WHITE, Anchor, Color


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

    def to_dict(self) -> dict[str, Any]:
        """Convert render item to dictionary for serialization / IPC transmission."""
        return {
            "asset_id": self.asset_id,
            "x": self.x,
            "y": self.y,
            "opacity": self.opacity,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "rotation": self.rotation,
            "anchor": self.anchor.value,
            "tint": self.tint.to_dict(),
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
            "layer": self.layer,
            "z_order": self.z_order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RenderItem:
        """Construct RenderItem from dictionary."""
        return cls(
            asset_id=data["asset_id"],
            x=float(data["x"]),
            y=float(data["y"]),
            opacity=float(data.get("opacity", 1.0)),
            scale_x=float(data.get("scale_x", 1.0)),
            scale_y=float(data.get("scale_y", 1.0)),
            rotation=float(data.get("rotation", 0.0)),
            anchor=Anchor.from_str(data.get("anchor", "bottom_center")),
            tint=Color.from_dict(data.get("tint", {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})),
            flip_h=bool(data.get("flip_h", False)),
            flip_v=bool(data.get("flip_v", False)),
            layer=data.get("layer", "characters"),
            z_order=int(data.get("z_order", 0)),
        )


class RenderBackend(Protocol):
    """Protocol implemented by rendering frontends (Pygame, Raylib, Godot, Web Canvas)."""

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


class UIDrawBackend(Protocol):
    """Low-level drawing primitives used by renderer-agnostic UI components.

    All coordinates are expressed in **window pixels with a top-left origin**
    (``y`` increases downward).  Backends whose native coordinate system
    differs (e.g. Pyglet's bottom-left origin) are responsible for flipping
    ``y`` before issuing the primitive.

    This protocol is deliberately separate from :class:`RenderBackend`: the
    stage compositor emits pre-transformed :class:`RenderItem` draw commands,
    whereas UI components need raw immediate-mode primitives (rectangles,
    text, images) that they position themselves.
    """

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

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: int = 14,
        color: Color = WHITE,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        """Draw a single line of text.

        ``anchor_x`` is one of ``"left"``, ``"center"``, ``"right"`` and
        ``anchor_y`` one of ``"top"``, ``"middle"``, ``"bottom"``.  Multi-line
        layout (wrapping, line spacing) is the caller's responsibility.
        """
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

    def measure_text(self, text: str, *, font_size: int = 14) -> tuple[float, float]:
        """Return the ``(width, height)`` the given text would occupy."""
        ...
