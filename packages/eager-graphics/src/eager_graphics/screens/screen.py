"""Screen base class and screen manager for full UI displays (Title, Save/Load, Preferences, History)."""

from __future__ import annotations

from typing import Any

from eager_graphics.protocol import UIDrawBackend
from eager_graphics.screens.theme import Theme
from eager_graphics.screens.widgets import Button, Label, Slider


class Screen:
    """Base class for visual novel modal/full-screen UI menus."""

    def __init__(self, name: str, theme: Theme | None = None) -> None:
        self.name = name
        self.theme: Theme = theme if theme is not None else Theme()
        self.buttons: list[Button] = []
        self.sliders: list[Slider] = []
        self.labels: list[Label] = []
        self.visible: bool = False

    def on_enter(self, session: Any) -> None:
        """Called when screen is displayed."""
        self.visible = True

    def on_exit(self, session: Any) -> None:
        """Called when screen is hidden."""
        self.visible = False

    def handle_mouse_move(self, x: float, y: float) -> None:
        """Update hover state on buttons."""
        for b in self.buttons:
            b.hovered = b.hit_test(x, y)

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


class ScreenManager:
    """Stack and registry of screens."""

    def __init__(self) -> None:
        self.screens: dict[str, Screen] = {}
        self.active_screen: Screen | None = None
        self._history_stack: list[str] = []

    def register(self, screen: Screen) -> None:
        self.screens[screen.name] = screen

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
                    self.active_screen.on_enter(session)
                    return
            self.active_screen = None

    def hide_all(self, session: Any) -> None:
        """Hide all screens and clear navigation history stack."""
        if self.active_screen is not None:
            self.active_screen.on_exit(session)
            self.active_screen = None
        self._history_stack.clear()

    def handle_mouse_move(self, x: float, y: float) -> None:
        """Forward mouse movement to the active screen."""
        if self.active_screen is not None and self.active_screen.visible:
            self.active_screen.handle_mouse_move(x, y)

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
        if self.active_screen and self.active_screen.visible:
            self.active_screen.draw(backend, width, height)
