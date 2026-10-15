"""Headless, dependency-free rendering backend for Eager-Graphics.

The :class:`NullRenderer` implements the :class:`~eager_graphics.protocol.RenderBackend`
protocol without requiring a GPU, display server, or third-party graphics
library.  Instead of drawing pixels it records every :class:`~eager_graphics.protocol.RenderItem`
submitted during a frame so they can be inspected programmatically — perfect for
CI, headless game loops, snapshot-based testing, and debugging.

Example
-------
.. code-block:: python

    from eager_graphics import StageCompositor
    from eager_graphics.renderers.null import NullRenderer

    comp = StageCompositor(1920, 1080)
    backend = NullRenderer()

    comp.set_background("bg/castle", transition="cut")
    comp.update(0.016)

    backend.render_compositor(comp, window_width=1280, window_height=720)
    print(backend.frame_count)          # 1
    print(len(backend.last_frame))    # number of draw calls
    print(backend.last_frame[0].asset_id)
"""

from __future__ import annotations

from typing import Any

from eager_core.timing import FrameClock
from eager_core.types import BLACK, WHITE, Color

from eager_graphics.protocol import RenderBackend, RenderItem


class NullRenderer(RenderBackend):
    """A no-op renderer that records draw calls instead of issuing GPU commands.

    Implements the full :class:`~eager_graphics.protocol.RenderBackend` protocol and
    additionally exposes a convenience :meth:`render_compositor` method that
    mirrors :meth:`eager_graphics.renderers.pyglet.PygletRenderer.render_compositor`,
    so the two backends are interchangeable at call sites.

    Attributes
    ----------
    last_frame : list[RenderItem]
        A copy of every :class:`~eager_graphics.protocol.RenderItem` submitted during
        the most recent completed frame.  Useful for assertions and inspection.
    frame_count : int
        Number of frames that have been fully rendered (i.e.
        :meth:`end_frame` has been called that many times).
    clear_color : Color
        The color used to clear the (conceptually virtual) framebuffer.
    clock : FrameClock
        Frame timing helper.  Ticked once per ``end_frame``; exposes
        :attr:`~FrameClock.fps`, :attr:`~FrameClock.fps_avg`, and
        :attr:`~FrameClock.fps_overall` for debug overlays and benchmarks.
    """

    def __init__(self) -> None:
        # Pre-compute an empty viewport transform so draw_item calls that want
        # screen-space coordinates have *something* to use; the NullRenderer
        # never transforms items — it stores them verbatim.
        self.last_frame: list[RenderItem] = []
        self._frame_buffer: list[RenderItem] = []
        self.frame_count: int = 0
        self.clear_color: Color = BLACK
        self._in_frame: bool = False
        self.clock: FrameClock = FrameClock()

        # Immediate-mode UI primitives recorded since the last clear_ui_calls().
        self.ui_calls: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # RenderBackend protocol
    # ------------------------------------------------------------------ #

    def begin_frame(self) -> None:
        """Begin a new frame — clears the internal draw-call buffer."""
        if self._in_frame:
            msg = "begin_frame called without matching end_frame"
            raise RuntimeError(msg)
        self._frame_buffer = []
        self._in_frame = True

    def clear(self, color: Color) -> None:
        """Record the framebuffer clear color (no GPU call is made)."""
        self.clear_color = color

    def draw_item(self, item: RenderItem) -> None:
        """Record a render item instead of issuing a GPU draw call."""
        if not self._in_frame:
            msg = "draw_item called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)
        # Store a copy so later mutations to the compositor's render list
        # don't alias the recorded frame.
        self._frame_buffer.append(item)

    def end_frame(self) -> None:
        """Finalize the current frame, publishing its draw calls."""
        if not self._in_frame:
            msg = "end_frame called without matching begin_frame"
            raise RuntimeError(msg)
        self.last_frame = self._frame_buffer
        self._frame_buffer = []
        self._in_frame = False
        self.frame_count += 1
        self.clock.tick()

    # ------------------------------------------------------------------ #
    # FPS properties (delegate to the FrameClock for a uniform API)
    # ------------------------------------------------------------------ #

    @property
    def fps(self) -> float:
        """Instantaneous frames-per-second (1 / last frame interval).

        Returns ``0.0`` until at least two frames have been rendered.
        """
        return self.clock.fps

    @property
    def fps_avg(self) -> float:
        """Rolling-average FPS over the last 60 rendered frames.

        Returns ``0.0`` until at least two frames have been rendered.
        """
        return self.clock.fps_avg

    @property
    def fps_overall(self) -> float:
        """Average FPS across all frames since the renderer was created/reset."""
        return self.clock.fps_overall

    # ------------------------------------------------------------------ #
    # Convenience
    # ------------------------------------------------------------------ #

    def render_compositor(
        self,
        compositor: Any,
        window_width: int,
        window_height: int,
    ) -> None:
        """Render one frame from a :class:`~eager_graphics.compositor.StageCompositor`.

        This mirrors the signature of
        :meth:`eager_graphics.renderers.pyglet.PygletRenderer.render_compositor` so
        that code can swap backends transparently.

        Parameters
        ----------
        compositor : StageCompositor
            The compositor to read the render list from.  It is *not* advanced
            here — call ``compositor.update(dt)`` yourself before/after as your
            game-loop dictates.
        window_width, window_height : int
            Physical window dimensions (kept for API parity; the NullRenderer
            draws in virtual coordinates and does not scale).
        """
        self.begin_frame()
        self.clear(BLACK)
        items = compositor.render_list()
        for item in items:
            self.draw_item(item)
        self.end_frame()

    # ------------------------------------------------------------------ #
    # UIDrawBackend primitives
    #
    # These record immediate-mode UI primitives instead of drawing them, so
    # renderer-agnostic UI components (see eager_graphics.ui_components) can
    # be exercised and asserted on in headless tests.
    # ------------------------------------------------------------------ #

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
        """Record a rectangle primitive (fill plus optional stroke)."""
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
        """Record a vertical linear gradient rectangle."""
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
    ) -> None:
        """Record a text primitive."""
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
        """Record an image primitive."""
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
    ) -> tuple[float, float]:
        """Return a deterministic monospace-ish estimate of the text extents.

        The real backends measure with real font metrics; for headless
        assertion purposes a stable approximation is sufficient.
        """
        longest = max((len(line) for line in text.splitlines()), default=0)
        return (longest * font_size * 0.5, float(font_size) * 1.2)

    def clear_ui_calls(self) -> None:
        """Discard recorded UI primitives."""
        self.ui_calls.clear()

    # ------------------------------------------------------------------ #
    # Introspection helpers
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        """Return the number of items in the last rendered frame."""
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"NullRenderer(frame_count={self.frame_count}, "
            f"last_frame_items={len(self.last_frame)}, "
            f"fps={self.clock.fps:.1f})"
        )
