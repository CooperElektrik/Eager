"""Interactive Pyglet window shell driving a :class:`GameSession`."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    import pyglet
    from pyglet.graphics import Batch
    from pyglet.window import key, mouse
except ImportError as err:
    msg = "Pyglet is not installed. Install with 'pip install eager[pyglet]' or 'pip install pyglet'."
    raise ImportError(msg) from err

from eager.backends.renderers.pyglet import PygletRenderer
from eager.core.input import InputAction
from eager.core.types import ScaleMode
from eager.ui.player import BasePlayer

GameSessionProtocol = Any

logger = logging.getLogger(__name__)

__all__ = ["PygletPlayer"]


class PygletPlayer(BasePlayer, pyglet.window.Window):  # pyright: ignore[reportUnsafeMultipleInheritance]
    """Thin Pyglet window shell driving a :class:`GameSession`."""

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
            uncapped=uncapped,
        )

        self._ui_batch = Batch()

        self.renderer = PygletRenderer(
            width=width,
            height=height,
            asset_dir=asset_dir,
            scale_mode=scale_mode,
            window=self,
            ui_batch=self._ui_batch,
        )

        self.step_initial_beat()

        if self.uncapped:
            pyglet.clock.schedule(self.tick)
        else:
            pyglet.clock.schedule_interval(self.tick, 1.0 / 60.0)

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

    def on_draw(self) -> None:
        """Render frame: stage graphics followed by UI textbox, choices, and screens."""
        self.session.draw(self.renderer, self.width, self.height)
        self.renderer.flush_ui()

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

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        """Handle key releases (e.g. releasing Ctrl stops fast-forward skip)."""
        sym_str = key.symbol_string(symbol).lower()
        if sym_str in ("ctrl", "lctrl", "rctrl"):
            self.handle_skip_release()

    def on_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float) -> None:
        """Handle mouse wheel scrolling for rollback or screen scrolling."""
        self.handle_scroll(scroll_y)
