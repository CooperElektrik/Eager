"""Interactive Pyglet window shell driving a :class:`GameSession`."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

try:
    import pyglet
    from pyglet.graphics import Batch
    from pyglet.text import Label
    from pyglet.window import key, mouse
except ImportError as err:
    msg = "Pyglet is not installed. Install with 'pip install eager[pyglet]' or 'pip install pyglet'."
    raise ImportError(msg) from err

from eager.backends.fonts import register_pyglet_default_font
from eager.backends.renderers.pyglet import PygletRenderer
from eager.core.input import InputAction
from eager.core.types import DebugOverlayMode, ScaleMode
from eager.ui.player import BasePlayer

GameSessionProtocol = Any

logger = logging.getLogger(__name__)

__all__ = ["PygletPlayer"]


class PygletPlayer(BasePlayer, pyglet.window.Window):  # pyright: ignore[reportUnsafeMultipleInheritance]
    """Thin Pyglet window shell driving a :class:`GameSession`.

    The player owns no narrative state: story advancement, branching,
    rollback, typewriter reveal, and input semantics all live in the injected
    :class:`~eager.session.session.GameSession`.  Window events are forwarded to
    ``session.handle_input(...)`` and frames are produced by ``session.draw(...)``.
    """

    width: Any
    height: Any
    visible: Any
    vsync: Any

    def __init__(
        self,
        *,
        session: GameSessionProtocol,
        width: int = 1280,
        height: int = 720,
        title: str = "Eager-Graphics Visual Novel (Pyglet)",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        vsync: bool = True,
        visible: bool = True,
        show_fps: bool = True,
        uncapped: bool = False,
    ) -> None:
        if uncapped:
            vsync = False
        pyglet.window.Window.__init__(
            self,
            width=width,
            height=height,
            caption=title,
            resizable=True,
            vsync=vsync,
            visible=visible,
        )
        BasePlayer.__init__(
            self,
            session=session,
            width=width,
            height=height,
            title=title,
            asset_dir=asset_dir,
            scale_mode=scale_mode,
            vsync=vsync,
            visible=visible,
            show_fps=show_fps,
            uncapped=uncapped,
        )

        # UI elements batch shared with PygletRenderer
        self._ui_batch = Batch()

        self.renderer = PygletRenderer(
            width=width,
            height=height,
            asset_dir=asset_dir,
            scale_mode=scale_mode,
            window=self,
            ui_batch=self._ui_batch,
        )

        # On-screen FPS debug overlay
        self._last_fps_update: float = 0.0
        self._fps_label: Label = Label(
            "",
            font_name=register_pyglet_default_font(),
            font_size=11,
            x=10,
            y=10,
            anchor_x="left",
            anchor_y="bottom",
            color=(230, 230, 230, 200),
        )

        self._resizing_scale: bool = False

        # Step first beat if not starting in active menu
        self.step_initial_beat()

        # Apply saved resolution scale on startup if present
        prefs = getattr(session, "preferences", None)
        if prefs is not None:
            scale = getattr(prefs, "resolution_scale", 1.0)
            if scale != 1.0:
                self.set_resolution_scale(scale)

        # Schedule animation tick at 60 FPS or uncapped
        if self.uncapped:
            pyglet.clock.schedule(self.tick)
        else:
            pyglet.clock.schedule_interval(self.tick, 1.0 / 60.0)

    def set_resolution_scale(self, scale: float) -> None:
        """Update window/viewport resolution scale relative to base dimensions."""
        clamped = max(0.5, min(2.0, float(scale)))
        self._resolution_scale = clamped
        target_w = max(320, round(self._base_width * clamped))
        target_h = max(180, round(self._base_height * clamped))
        if not self.fullscreen and not getattr(self, "_resizing_scale", False):
            self._resizing_scale = True
            try:
                self.set_size(target_w, target_h)
            finally:
                self._resizing_scale = False
        else:
            BasePlayer.on_resize(self, target_w, target_h)
            self.renderer.on_resize(target_w, target_h)

    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen mode."""
        try:
            self.set_fullscreen(not self.fullscreen)
            if hasattr(self.session, "preferences") and self.session.preferences is not None:
                self.session.preferences.fullscreen = bool(self.fullscreen)
                if hasattr(self.session, "save_preferences"):
                    self.session.save_preferences()
        except Exception:  # noqa: BLE001, S110
            pass

    def on_resize(self, width: int, height: int) -> None:
        """Keep the UI components laid out against the new window size."""
        pyglet.window.Window.on_resize(self, width, height)
        BasePlayer.on_resize(self, width, height)
        self.renderer.on_resize(width, height)

    def close(self) -> None:
        """Close window and release audio mixer resources."""
        BasePlayer.close(self)
        pyglet.window.Window.close(self)

    def run(self) -> None:
        """Run the interactive visual-novel main loop (blocks until window closes)."""
        if self.uncapped:
            pyglet.app.run(interval=0.0)
        else:
            pyglet.app.run()

    def toggle_debug_overlay(self) -> None:
        """Cycle debug overlay mode for developer diagnostics."""
        _ = self.cycle_debug_overlay()

    def cycle_debug_overlay(self) -> DebugOverlayMode:
        """Cycle debug overlay mode: OFF -> FPS -> DETAILED -> OFF."""
        match self.debug_mode:
            case DebugOverlayMode.OFF:
                self.debug_mode = DebugOverlayMode.FPS
            case DebugOverlayMode.FPS:
                self.debug_mode = DebugOverlayMode.DETAILED
            case DebugOverlayMode.DETAILED:
                self.debug_mode = DebugOverlayMode.OFF
        if self._fps_label is not None:
            self._fps_label.text = ""
        return self.debug_mode

    def on_draw(self) -> None:
        """Render frame: stage graphics followed by UI textbox, choices, screens, and FPS."""
        self.session.draw(self.renderer, self.width, self.height)

        # Flush batched UI elements
        self.renderer.flush_ui()

        # 5. Render FPS / Debug overlay
        if self.show_fps and self._fps_label is not None:
            self._draw_fps()

    def _draw_fps(self) -> None:
        """Update and draw the on-screen FPS/debug overlay."""
        if self._fps_label is None or self.debug_mode == DebugOverlayMode.OFF:
            return
        now = time.monotonic()
        if not self._fps_label.text or (now - self._last_fps_update) >= 0.25:
            if self.debug_mode == DebugOverlayMode.FPS:
                fps = self.renderer.fps
                fps_avg = self.renderer.fps_avg
                frames = self.renderer.frame_count
                self._fps_label.multiline = False
                self._fps_label.text = f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})"
            elif self.debug_mode == DebugOverlayMode.DETAILED:
                self._fps_label.multiline = True
                self._fps_label.width = min(self.width - 20, 750)
                self._fps_label.text = self.renderer.debug_repr()
            self._last_fps_update = now
        self._fps_label.draw()

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        """Handle mouse movement for screen and button hover states."""
        flipped_y = self.height - y
        self.handle_pointer_move(float(x), float(flipped_y))

    def on_mouse_drag(
        self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int
    ) -> None:
        """Handle mouse drag for sliders and interactive UI elements."""
        flipped_y = self.height - y
        self.handle_pointer_move(float(x), float(flipped_y))

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Handle mouse clicks for advancement, screens, or choice selection."""
        if button == mouse.RIGHT:
            self.session.handle_input(InputAction.GAME_MENU)
            self.sync_state()
            return

        if button != mouse.LEFT:
            return

        flipped_y = self.height - y
        self.handle_pointer_click(float(x), float(flipped_y))

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Handle mouse release to terminate active slider dragging."""
        if button == mouse.LEFT:
            flipped_y = self.height - y
            screens = getattr(self.session, "screens", None)
            release_fn = getattr(screens, "handle_mouse_release", None)
            if callable(release_fn):
                release_fn(float(x), float(flipped_y))

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        """Handle keyboard input for advancing, choices, rollback, save/load, and menus."""
        sym_str = key.symbol_string(symbol)
        is_shift = bool(modifiers & key.MOD_SHIFT)
        self.handle_key_press(sym_str, is_shift=is_shift)

    def on_text(self, text: str) -> None:
        """Handle typed text input when an input prompt is active."""
        self.handle_text_input(text)

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        """Handle key releases (e.g. releasing Ctrl stops fast-forward skip)."""
        sym_str = key.symbol_string(symbol).lower()
        if sym_str in ("ctrl", "lctrl", "rctrl"):
            self.handle_skip_release()

    def on_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float) -> None:
        """Handle mouse wheel scrolling for rollback, roll-forward, or screen scrolling."""
        self.handle_scroll(scroll_y)
