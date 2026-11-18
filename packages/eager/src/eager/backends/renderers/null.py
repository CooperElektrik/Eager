"""Null (headless) rendering backend that records draw calls for testing and headless sessions."""

from __future__ import annotations

from typing import Any, Protocol

from eager.backends.types import RenderItem
from eager.core.timing import FrameClock
from eager.core.types import BLACK, WHITE, Color

__all__ = [
    "NullRenderBackend",
    "NullRenderer",
]


class _CompositorLike(Protocol):
    def render_list(self) -> list[RenderItem]: ...


class NullRenderer:
    """A no-op renderer that records draw calls instead of issuing GPU commands."""

    def __init__(self) -> None:
        self.last_frame: list[RenderItem] = []
        self._frame_buffer: list[RenderItem] = []
        self.last_particle_batches: list[tuple[str, int]] = []
        self.last_lightmaps: list[tuple[bool, int]] = []
        self.frame_count: int = 0
        self.clear_color: Color = BLACK
        self._in_frame: bool = False
        self.clock: FrameClock = FrameClock()
        self.ui_calls: list[dict[str, Any]] = []

    def begin_frame(self) -> None:
        """Begin a new frame."""
        if self._in_frame:
            msg = "begin_frame called without matching end_frame"
            raise RuntimeError(msg)
        self._frame_buffer = []
        self._in_frame = True

    def clear(self, color: Color) -> None:
        """Record the framebuffer clear color."""
        self.clear_color = color

    def draw_item(self, item: RenderItem) -> None:
        """Record a render item."""
        if not self._in_frame:
            msg = "draw_item called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)
        self._frame_buffer.append(item)

    def draw_particles(self, batch: object) -> None:
        """Record a particle batch draw call."""
        if not self._in_frame:
            msg = "draw_particles called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)
        emitter_id = getattr(batch, "emitter_id", "")
        particles = getattr(batch, "particles", [])
        self.last_particle_batches.append((emitter_id, len(particles)))

    def render_lightmap(self, lightmap: object) -> None:
        """Record a screen-space lightmap draw call."""
        if not self._in_frame:
            msg = "render_lightmap called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)
        enabled = getattr(lightmap, "enabled", False)
        lights = getattr(lightmap, "lights", [])
        self.last_lightmaps.append((enabled, len(lights)))

    def end_frame(self) -> None:
        """Finalize the current frame, publishing draw calls."""
        if not self._in_frame:
            msg = "end_frame called without matching begin_frame"
            raise RuntimeError(msg)
        self.last_frame = self._frame_buffer
        self._frame_buffer = []
        self._in_frame = False
        self.frame_count += 1
        self.clock.tick()

    @property
    def fps(self) -> float:
        return self.clock.fps

    @property
    def fps_avg(self) -> float:
        return self.clock.fps_avg

    @property
    def fps_overall(self) -> float:
        return self.clock.fps_overall

    def render_compositor(
        self,
        compositor: _CompositorLike,
        window_width: int,
        window_height: int,
    ) -> None:
        self.begin_frame()
        self.clear(BLACK)
        items = compositor.render_list()
        for item in items:
            self.draw_item(item)
        get_batches = getattr(compositor, "get_particle_batches", None)
        layout = getattr(compositor, "layout", None)
        if get_batches is not None and layout is not None:
            transform = layout.compute_viewport_transform(window_width, window_height)
            for batch in get_batches(transform):
                self.draw_particles(batch)
        lighting = getattr(compositor, "lighting", None)
        if lighting is not None and lighting.enabled:
            self.render_lightmap(lighting)
        self.end_frame()

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
        self.ui_calls.append(
            {
                "kind": "rect",
                "x": float(x),
                "y": float(y),
                "width": float(width),
                "height": float(height),
                "color": color.to_hex(),
                "border_color": border_color.to_hex() if border_color else None,
                "border_width": float(border_width),
            }
        )

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        self.ui_calls.append(
            {
                "kind": "gradient_rect",
                "x": float(x),
                "y": float(y),
                "width": float(width),
                "height": float(height),
                "top_color": top_color.to_hex(),
                "bottom_color": bottom_color.to_hex(),
            }
        )

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
        self.ui_calls.append(
            {
                "kind": "text",
                "x": float(x),
                "y": float(y),
                "text": text,
                "font_size": int(font_size),
                "color": color.to_hex(),
                "bold": bold,
                "italic": italic,
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
                "cache": cache,
                "font_family": font_family,
            }
        )

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
        self.ui_calls.append(
            {
                "kind": "image",
                "asset_id": asset_id,
                "x": float(x),
                "y": float(y),
                "width": float(width),
                "height": float(height),
                "tint": tint.to_hex(),
                "anchor_x": anchor_x,
                "anchor_y": anchor_y,
            }
        )

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
        longest = max((len(line) for line in text.splitlines()), default=0)
        return (longest * font_size * 0.5, float(font_size) * 1.2)

    def clear_ui_calls(self) -> None:
        self.ui_calls.clear()

    def __len__(self) -> int:
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"NullRenderer(frame_count={self.frame_count}, "
            f"last_frame_items={len(self.last_frame)}, "
            f"fps={self.clock.fps:.1f})"
        )


NullRenderBackend = NullRenderer
