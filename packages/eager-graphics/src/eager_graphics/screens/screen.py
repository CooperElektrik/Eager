"""Screen base class and screen manager for full UI displays (Title, Save/Load, Preferences, History)."""

from __future__ import annotations

from typing import Any

from eager_graphics.protocol import UIDrawBackend
from eager_graphics.screens.theme import Theme
from eager_graphics.screens.widgets import Button


class Screen:
    """Base class for visual novel modal/full-screen UI menus."""

    def __init__(self, name: str, theme: Theme | None = None) -> None:
        self.name = name
        self.theme: Theme = theme if theme is not None else Theme()
        self.buttons: list[Button] = []
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
        """Process click event, firing matching button action."""
        for b in self.buttons:
            if b.enabled and b.hit_test(x, y):
                if b.action:
                    b.action()
                return True
        return False

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render screen contents."""


class ScreenManager:
    """Stack and registry of screens."""

    def __init__(self) -> None:
        self.screens: dict[str, Screen] = {}
        self.active_screen: Screen | None = None

    def register(self, screen: Screen) -> None:
        self.screens[screen.name] = screen

    def show(self, name: str, session: Any) -> bool:
        if name not in self.screens:
            return False
        if self.active_screen is not None:
            self.active_screen.on_exit(session)
        self.active_screen = self.screens[name]
        self.active_screen.on_enter(session)
        return True

    def hide(self, session: Any) -> None:
        if self.active_screen is not None:
            self.active_screen.on_exit(session)
            self.active_screen = None

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        if self.active_screen and self.active_screen.visible:
            self.active_screen.draw(backend, width, height)
