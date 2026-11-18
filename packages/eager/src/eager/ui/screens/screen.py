"""Screen base class and screen manager for full UI displays (Title, Save/Load, Preferences, History)."""

from __future__ import annotations

from typing import Any
from typing import Any as GameSessionProtocol

from eager.backends.types import UIDrawBackend
from eager.ui.screens.widgets import Button, Label, Slider

__all__ = [
    "Screen",
    "ScreenManager",
]


class Screen:
    """Base class for visual novel modal/full-screen UI menus."""

    def __init__(
        self,
        name: str,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        self.name: str = name
        self.viewport_width: int = viewport_width
        self.viewport_height: int = viewport_height
        self.buttons: list[Button] = []
        self.sliders: list[Slider] = []
        self.labels: list[Label] = []
        self.visible: bool = False
        self._focused_button_index: int = -1
        self._focused_slider_index: int = -1
        self._dragging_slider: Slider | None = None

    def _restore_focus_highlight(self) -> None:
        """Re-apply keyboard focus highlight to the focused button after layout rebuild."""
        if 0 <= self._focused_button_index < len(self.buttons) and self.buttons[self._focused_button_index].enabled:
            for i, b in enumerate(self.buttons):
                b.hovered = (i == self._focused_button_index)
        elif self._focused_button_index >= len(self.buttons):
            self._focused_button_index = -1

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions and recompute layout."""
        if self.viewport_width != width or self.viewport_height != height:
            self.viewport_width = width
            self.viewport_height = height
            self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Recompute layout/geometry of widgets based on current viewport dimensions."""

    def on_enter(self, session: GameSessionProtocol) -> None:
        """Called when screen is displayed."""
        self.visible = True

    def on_exit(self, session: GameSessionProtocol) -> None:
        """Called when screen is hidden."""
        self.visible = False

    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Update hover state on buttons and handle slider dragging."""
        changed = False
        if self._dragging_slider is not None:
            self._dragging_slider.handle_click(x, y)
            changed = True
        for idx, b in enumerate(self.buttons):
            new_hover = b.hit_test(x, y)
            if b.hovered != new_hover:
                b.hovered = new_hover
                changed = True
            if new_hover and self._focused_button_index != idx:
                self._focused_button_index = idx
        return changed

    def handle_mouse_click(self, x: float, y: float) -> bool:
        """Process click event, firing matching button action or adjusting slider."""
        for b in self.buttons:
            if b.enabled and b.hit_test(x, y):
                if b.action:
                    b.action()
                return True
        for idx, s in enumerate(self.sliders):
            if s.hit_test(x, y):
                self._dragging_slider = s
                self._focused_slider_index = idx
                self._focused_button_index = -1
                s.handle_click(x, y)
                return True
        self._dragging_slider = None
        return False

    def handle_mouse_release(self, x: float, y: float) -> bool:
        """Process mouse release event, ending any active slider drag."""
        if getattr(self, "_dragging_slider", None) is not None:
            self._dragging_slider = None
            return True
        return False

    def handle_key(self, key_name: str, session: GameSessionProtocol | None = None) -> bool:
        """Process key event on the active screen, navigating buttons and sliders."""
        k = key_name.strip().lower()
        enabled_buttons = [i for i, b in enumerate(self.buttons) if b.enabled]

        # Adjust focused slider (or first slider when no buttons are enabled)
        if k in ("left", "nav_left", "right", "nav_right") and self.sliders:
            slider_idx = self._focused_slider_index
            if slider_idx < 0 and not enabled_buttons:
                slider_idx = 0
                self._focused_slider_index = 0
            if 0 <= slider_idx < len(self.sliders):
                slider = self.sliders[slider_idx]
                delta = -0.05 if k in ("left", "nav_left") else 0.05
                slider.value = max(0.0, min(1.0, slider.value + delta))
                if slider.on_change:
                    slider.on_change(slider.value)
                return True

        if k in ("up", "nav_up", "left", "nav_left", "shift+tab"):
            if not enabled_buttons:
                return False
            self._focused_slider_index = -1
            if self._focused_button_index in enabled_buttons:
                pos = enabled_buttons.index(self._focused_button_index)
                new_idx = enabled_buttons[(pos - 1) % len(enabled_buttons)]
            else:
                new_idx = enabled_buttons[-1]
            self._focused_button_index = new_idx
            for i, b in enumerate(self.buttons):
                b.hovered = (i == new_idx)
            return True

        if k in ("down", "nav_down", "right", "nav_right", "tab"):
            if not enabled_buttons:
                return False
            self._focused_slider_index = -1
            if self._focused_button_index in enabled_buttons:
                pos = enabled_buttons.index(self._focused_button_index)
                new_idx = enabled_buttons[(pos + 1) % len(enabled_buttons)]
            else:
                new_idx = enabled_buttons[0]
            self._focused_button_index = new_idx
            for i, b in enumerate(self.buttons):
                b.hovered = (i == new_idx)
            return True

        if k in ("enter", "return", "space", "confirm"):
            if 0 <= self._focused_button_index < len(self.buttons):
                btn = self.buttons[self._focused_button_index]
                if btn.enabled and btn.action:
                    btn.action()
                    return True
            return False

        scroll_up_fn = getattr(self, "scroll_up", None)
        if k in ("pageup", "scroll_up") and callable(scroll_up_fn):
            scroll_up_fn()
            return True

        scroll_down_fn = getattr(self, "scroll_down", None)
        if k in ("pagedown", "scroll_down") and callable(scroll_down_fn):
            scroll_down_fn()
            return True

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
    ) -> None:
        self.screens: dict[str, Screen] = {}
        self.active_screen: Screen | None = None
        self._history_stack: list[str] = []
        self.viewport_width: int = viewport_width
        self.viewport_height: int = viewport_height

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions for all registered screens."""
        self.viewport_width = width
        self.viewport_height = height
        for screen in self.screens.values():
            screen.set_viewport(width, height)

    def register(self, screen: Screen) -> None:
        """Register a Screen instance into the screen registry."""
        self.screens[screen.name] = screen
        screen.set_viewport(self.viewport_width, self.viewport_height)

    @property
    def is_active(self) -> bool:
        """True if there is an active screen currently visible."""
        return self.active_screen is not None and self.active_screen.visible

    def show(self, name: str, session: GameSessionProtocol) -> bool:
        """Activate and display the screen identified by name.

        Args:
            name: Screen identifier string.
            session: Active GameSession instance.

        Returns:
            True if the screen was found and displayed, False otherwise.
        """
        if name not in self.screens:
            return False
        if self.active_screen is not None:
            if self.active_screen.name != name:
                self._history_stack.append(self.active_screen.name)
            self.active_screen.on_exit(session)
        self.active_screen = self.screens[name]
        self.active_screen.set_viewport(self.viewport_width, self.viewport_height)
        self.active_screen.on_enter(session)
        return True

    def hide(self, session: GameSessionProtocol) -> None:
        """Hide current screen and pop previous screen from history if present."""
        if self.active_screen is not None:
            self.active_screen.on_exit(session)
            if self._history_stack:
                prev_name = self._history_stack.pop()
                prev_screen = self.screens.get(prev_name)
                if prev_screen is not None:
                    self.active_screen = prev_screen
                    self.active_screen.set_viewport(self.viewport_width, self.viewport_height)
                    self.active_screen.on_enter(session)
                    return
            self.active_screen = None

    def hide_all(self, session: GameSessionProtocol) -> None:
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

    def handle_mouse_release(self, x: float, y: float) -> bool:
        """Forward mouse release to the active screen."""
        if (
            self.active_screen is not None
            and self.active_screen.visible
            and hasattr(self.active_screen, "handle_mouse_release")
        ):
            return bool(self.active_screen.handle_mouse_release(x, y))
        return False

    def handle_key(self, key_name: str, session: GameSessionProtocol | Any = None) -> bool:
        """Forward key events to active screen or dismiss with escape/cancel."""
        if self.active_screen is not None and self.active_screen.visible:
            if key_name.lower() in ("escape", "cancel"):
                if self.active_screen.name == "title":
                    return True
                self.hide(session)
                return True
            return self.active_screen.handle_key(key_name, session)
        return False

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render the active screen if one is visible.

        Args:
            backend: UIDrawBackend primitive drawing interface.
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        if self.viewport_width != width or self.viewport_height != height:
            self.set_viewport(width, height)
        if self.active_screen and self.active_screen.visible:
            self.active_screen.draw(backend, width, height)
