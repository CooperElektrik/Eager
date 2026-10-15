"""Resolution management, semantic positioning, and viewport scaling transforms."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from eager_core.types import Rect, Vec2

from eager_graphics.types import ScaleMode

PositionFactory: TypeAlias = Callable[[int, int], Vec2]


@dataclass(frozen=True, slots=True)
class ViewportTransform:
    """Coordinate transformation between virtual stage space and physical window pixels."""

    scale_x: float
    scale_y: float
    offset_x: float
    offset_y: float
    viewport_width: float
    viewport_height: float

    @property
    def scale(self) -> float:
        """Uniform horizontal scale factor."""
        return self.scale_x

    @property
    def dest_rect(self) -> Rect:
        """Destination rectangle in physical window pixels."""
        return Rect(self.offset_x, self.offset_y, self.viewport_width, self.viewport_height)

    def virtual_to_screen(self, v_pos: Vec2 | tuple[float, float]) -> Vec2:
        """Convert a virtual stage coordinate to physical screen pixel position."""
        vx, vy = (v_pos.x, v_pos.y) if isinstance(v_pos, Vec2) else v_pos
        return Vec2(
            self.offset_x + vx * self.scale_x,
            self.offset_y + vy * self.scale_y,
        )

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        """Convert (x, y) virtual coordinate to (x, y) physical screen pixel tuple."""
        p = self.virtual_to_screen((x, y))
        return (p.x, p.y)

    def screen_to_virtual(self, s_pos: Vec2 | tuple[float, float]) -> Vec2:
        """Convert a physical screen pixel coordinate back to virtual stage space."""
        sx, sy = (s_pos.x, s_pos.y) if isinstance(s_pos, Vec2) else s_pos
        return Vec2(
            (sx - self.offset_x) / self.scale_x,
            (sy - self.offset_y) / self.scale_y,
        )

    def to_virtual(self, x: float, y: float) -> tuple[float, float]:
        """Convert (x, y) physical screen pixel coordinate to (x, y) virtual stage coordinate tuple."""
        p = self.screen_to_virtual((x, y))
        return (p.x, p.y)


class LayoutResolver:
    """Manages virtual stage resolution, semantic named positions, and viewport scaling."""

    def __init__(
        self,
        virtual_width: int = 1920,
        virtual_height: int = 1080,
        ground_y: float = 1080.0,
    ) -> None:
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height
        self.ground_y = ground_y
        self._custom_positions: dict[str, Vec2 | PositionFactory] = {}

    def register_position(
        self,
        name: str,
        pos: Vec2 | tuple[float, float] | PositionFactory,
    ) -> None:
        """Register a custom semantic stage position by name."""
        clean = name.strip().lower().replace("-", "_")
        if callable(pos):
            self._custom_positions[clean] = pos
        else:
            self._custom_positions[clean] = Vec2.from_value(pos)

    def resolve_position(
        self,
        position: str | Vec2 | tuple[float, float],
        *,
        default_y: float | None = None,
    ) -> Vec2:
        """Resolve a position specification (name or coordinates) to a concrete virtual Vec2.

        Standard names:
        - 'left', 'center_left', 'center', 'center_right', 'right'
        - 'far_left', 'far_right'
        - 'offscreen_left', 'offscreen_right', 'offscreen_top', 'offscreen_bottom'
        - 'top_left', 'top_center', 'top_right', etc.
        """
        if isinstance(position, Vec2):
            return position
        if isinstance(position, (tuple, list)):
            return Vec2.from_value(position)

        name = position.strip().lower().replace("-", "_")

        # 1. Custom registered positions
        if name in self._custom_positions:
            val = self._custom_positions[name]
            if callable(val):
                return val(self.virtual_width, self.virtual_height)
            return val

        gy = default_y if default_y is not None else self.ground_y
        w = float(self.virtual_width)
        h = float(self.virtual_height)

        # 2. Standard character positions (anchored at ground baseline)
        character_positions = {
            "left": Vec2(w * 0.25, gy),
            "center_left": Vec2(w * 0.375, gy),
            "center": Vec2(w * 0.50, gy),
            "center_right": Vec2(w * 0.625, gy),
            "right": Vec2(w * 0.75, gy),
            "far_left": Vec2(w * 0.10, gy),
            "far_right": Vec2(w * 0.90, gy),
            "offscreen_left": Vec2(-w * 0.25, gy),
            "offscreen_right": Vec2(w * 1.25, gy),
            "offscreen_top": Vec2(w * 0.50, -h * 0.25),
            "offscreen_bottom": Vec2(w * 0.50, h * 1.25),
        }

        if name in character_positions:
            return character_positions[name]

        # 3. Standard screen grid positions
        grid_positions = {
            "top_left": Vec2(0.0, 0.0),
            "top_center": Vec2(w * 0.5, 0.0),
            "top_right": Vec2(w, 0.0),
            "middle_left": Vec2(0.0, h * 0.5),
            "middle_center": Vec2(w * 0.5, h * 0.5),
            "middle_right": Vec2(w, h * 0.5),
            "bottom_left": Vec2(0.0, h),
            "bottom_center": Vec2(w * 0.5, h),
            "bottom_right": Vec2(w, h),
        }

        if name in grid_positions:
            return grid_positions[name]

        # 4. Fallback: try parsing comma-separated 'x, y'
        if "," in name:
            try:
                parts = [float(p.strip()) for p in name.split(",", 1)]
                return Vec2(parts[0], parts[1])
            except ValueError:
                pass

        # Default fallback: center at ground
        return Vec2(w * 0.5, gy)

    def compute_viewport(
        self,
        screen_width: int,
        screen_height: int,
        mode: ScaleMode = ScaleMode.LETTERBOX,
    ) -> ViewportTransform:
        """Compute virtual-to-screen transform for a target window size."""
        vw = float(self.virtual_width)
        vh = float(self.virtual_height)
        sw = float(screen_width)
        sh = float(screen_height)

        match mode:
            case ScaleMode.STRETCH:
                return ViewportTransform(
                    scale_x=sw / vw,
                    scale_y=sh / vh,
                    offset_x=0.0,
                    offset_y=0.0,
                    viewport_width=sw,
                    viewport_height=sh,
                )

            case ScaleMode.CROP:
                scale = max(sw / vw, sh / vh)
                view_w = vw * scale
                view_h = vh * scale
                return ViewportTransform(
                    scale_x=scale,
                    scale_y=scale,
                    offset_x=(sw - view_w) / 2.0,
                    offset_y=(sh - view_h) / 2.0,
                    viewport_width=view_w,
                    viewport_height=view_h,
                )

            case ScaleMode.FIT_WIDTH:
                scale = sw / vw
                view_w = sw
                view_h = vh * scale
                return ViewportTransform(
                    scale_x=scale,
                    scale_y=scale,
                    offset_x=0.0,
                    offset_y=(sh - view_h) / 2.0,
                    viewport_width=view_w,
                    viewport_height=view_h,
                )

            case ScaleMode.FIT_HEIGHT:
                scale = sh / vh
                view_w = vw * scale
                view_h = sh
                return ViewportTransform(
                    scale_x=scale,
                    scale_y=scale,
                    offset_x=(sw - view_w) / 2.0,
                    offset_y=0.0,
                    viewport_width=view_w,
                    viewport_height=view_h,
                )

            case ScaleMode.LETTERBOX | _:
                scale = min(sw / vw, sh / vh)
                view_w = vw * scale
                view_h = vh * scale
                return ViewportTransform(
                    scale_x=scale,
                    scale_y=scale,
                    offset_x=(sw - view_w) / 2.0,
                    offset_y=(sh - view_h) / 2.0,
                    viewport_width=view_w,
                    viewport_height=view_h,
                )

    # Alias for API compatibility with spec
    compute_viewport_transform = compute_viewport
