"""Screen base class and screen manager for full UI displays (Title, Save/Load, Preferences, History)."""

from __future__ import annotations

from typing import Any

from eager_graphics.protocol import UIDrawBackend
from eager_graphics.screens.widgets import Button, Label, Slider
from eager_graphics.theme import Theme

__all__ = [
    "Screen",
    "ScreenManager",
]


class Screen:
    """Base class for visual novel modal/full-screen UI menus."""

    def __init__(
        self,
        name: str,
        theme: Theme | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        self.name: str = name
        self.theme: Theme = theme if theme is not None else Theme()
        self.viewport_width: int = viewport_width
        self.viewport_height: int = viewport_height
        self.buttons: list[Button] = []
        self.sliders: list[Slider] = []
        self.labels: list[Label] = []
        self.visible: bool = False

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions and recompute layout."""
        if self.viewport_width != width or self.viewport_height != height:
            self.viewport_width = width
            self.viewport_height = height
            self.rebuild_layout()

    def scale_font_size(self, base_size: float) -> int:
        """Scale a base font size proportionally with the viewport height (reference 720p)."""
        scale = float(self.viewport_height) / 720.0
        return max(1, round(float(base_size) * scale))

    def set_theme(self, theme: Theme) -> None:
        """Update screen visual theme and recompute layout."""
        self.theme = theme
        self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Recompute layout/geometry of widgets based on current viewport dimensions."""

    def on_enter(self, session: Any) -> None:
        """Called when screen is displayed."""
        self.visible = True

    def on_exit(self, session: Any) -> None:
        """Called when screen is hidden."""
        self.visible = False

    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Update hover state on buttons. Returns True if any hover state changed."""
        changed = False
        for b in self.buttons:
            new_hover = b.hit_test(x, y)
            if b.hovered != new_hover:
                b.hovered = new_hover
                changed = True
        return changed

    def handle_mouse_click(self, x: float, y: float) -> bool:
        """Process click event, firing matching button action or adjusting slider."""
        for b in self.buttons:
            if b.enabled and b.hit_test(x, y):
                if b.action:
                    b.action()
                return True
        for s in self.sliders:
            if s.hit_test(x, y):
                s.handle_click(x, y)
                return True
        return False

    def handle_key(self, key_name: str, session: Any = None) -> bool:
        """Process key event on the active screen."""
        return False

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render screen contents."""
        if self.viewport_width != width or self.viewport_height != height:
            self.set_viewport(width, height)


class ScreenManager:
    """Stack and registry of screens."""

    def __init__(
        self,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        theme: Theme | None = None,
    ) -> None:
        self.screens: dict[str, Screen] = {}
        self.active_screen: Screen | None = None
        self._history_stack: list[str] = []
        self.viewport_width: int = viewport_width
        self.viewport_height: int = viewport_height
        self.theme: Theme | None = theme

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions for all registered screens."""
        self.viewport_width = width
        self.viewport_height = height
        for screen in self.screens.values():
            if hasattr(screen, "set_viewport"):
                screen.set_viewport(width, height)

    def set_theme(self, theme: Theme) -> None:
        """Update visual theme across all registered screens."""
        self.theme = theme
        for screen in self.screens.values():
            if hasattr(screen, "set_theme"):
                screen.set_theme(theme)

    def register(self, screen: Screen) -> None:
        if self.theme is not None and (screen.theme is None or screen.theme.name == "default"):
            screen.set_theme(self.theme)
        self.screens[screen.name] = screen
        if hasattr(screen, "set_viewport"):
            screen.set_viewport(self.viewport_width, self.viewport_height)

    @property
    def is_active(self) -> bool:
        """True if there is an active screen currently visible."""
        return self.active_screen is not None and self.active_screen.visible

    def show(self, name: str, session: Any) -> bool:
        if name not in self.screens:
            return False
        if self.active_screen is not None:
            if self.active_screen.name != name:
                self._history_stack.append(self.active_screen.name)
            self.active_screen.on_exit(session)
        self.active_screen = self.screens[name]
        if hasattr(self.active_screen, "set_viewport"):
            self.active_screen.set_viewport(self.viewport_width, self.viewport_height)
        self.active_screen.on_enter(session)
        return True

    def hide(self, session: Any) -> None:
        """Hide current screen and pop previous screen from history if present."""
        if self.active_screen is not None:
            self.active_screen.on_exit(session)
            if self._history_stack:
                prev_name = self._history_stack.pop()
                prev_screen = self.screens.get(prev_name)
                if prev_screen is not None:
                    self.active_screen = prev_screen
                    if hasattr(self.active_screen, "set_viewport"):
                        self.active_screen.set_viewport(self.viewport_width, self.viewport_height)
                    self.active_screen.on_enter(session)
                    return
            self.active_screen = None

    def hide_all(self, session: Any) -> None:
        """Hide all screens and clear navigation history stack."""
        if self.active_screen is not None:
            self.active_screen.on_exit(session)
            self.active_screen = None
        self._history_stack.clear()

    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Forward mouse movement to the active screen. Returns True if any hover state changed."""
        if self.active_screen is not None and self.active_screen.visible:
            return bool(self.active_screen.handle_mouse_move(x, y))
        return False

    def handle_mouse_click(self, x: float, y: float) -> bool:
        """Forward mouse clicks to the active screen. Returns True if handled."""
        if self.active_screen is not None and self.active_screen.visible:
            return self.active_screen.handle_mouse_click(x, y)
        return False

    def handle_key(self, key_name: str, session: Any = None) -> bool:
        """Forward key events to active screen or dismiss with escape/cancel."""
        if self.active_screen is not None and self.active_screen.visible:
            if key_name.lower() in ("escape", "cancel"):
                self.hide(session)
                return True
            return self.active_screen.handle_key(key_name, session)
        return False

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        if self.viewport_width != width or self.viewport_height != height:
            self.set_viewport(width, height)
        if self.active_screen and self.active_screen.visible:
            self.active_screen.draw(backend, width, height)
