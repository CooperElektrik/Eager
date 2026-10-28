"""Backend-neutral input actions and keymapping for Eager."""

from __future__ import annotations

import logging
from enum import Enum
from typing import ClassVar

__all__ = [
    "InputAction",
    "Keymap",
]

logger = logging.getLogger(__name__)


class InputAction(str, Enum):
    """Semantic user input actions independent of concrete backend keys."""

    ADVANCE = "advance"
    ROLLBACK = "rollback"
    ROLL_FORWARD = "roll_forward"
    CHOOSE = "choose"
    POINTER_MOVE = "pointer_move"
    POINTER_CLICK = "pointer_click"
    SCROLL = "scroll"
    NAV_UP = "nav_up"
    NAV_DOWN = "nav_down"
    NAV_LEFT = "nav_left"
    NAV_RIGHT = "nav_right"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    SKIP_TOGGLE = "skip_toggle"
    SKIP_HOLD = "skip_hold"
    SKIP_RELEASE = "skip_release"
    AUTO_TOGGLE = "auto_toggle"
    QUICK_SAVE = "quick_save"
    QUICK_LOAD = "quick_load"
    GAME_MENU = "game_menu"
    HISTORY = "history"
    HIDE_UI = "hide_ui"
    SCREENSHOT = "screenshot"
    FULLSCREEN = "fullscreen"
    TEXT_CHAR = "text_char"
    TEXT_BACKSPACE = "text_backspace"
    RELOAD = "reload"
    DEBUG_OVERLAY = "debug_overlay"
    QUIT = "quit"


class Keymap:
    """Configurable mapping of backend-neutral key identifiers to semantic InputActions."""

    DEFAULT_BINDINGS: ClassVar[dict[str, InputAction]] = {
        "space": InputAction.ADVANCE,
        "enter": InputAction.ADVANCE,
        "return": InputAction.ADVANCE,
        "mouse_left": InputAction.ADVANCE,
        "pageup": InputAction.ROLLBACK,
        "backspace": InputAction.ROLLBACK,
        "mouse_wheel_up": InputAction.ROLLBACK,
        "pagedown": InputAction.ROLL_FORWARD,
        "mouse_wheel_down": InputAction.ROLL_FORWARD,
        "ctrl": InputAction.SKIP_HOLD,
        "lctrl": InputAction.SKIP_HOLD,
        "rctrl": InputAction.SKIP_HOLD,
        "tab": InputAction.SKIP_TOGGLE,
        "a": InputAction.AUTO_TOGGLE,
        "h": InputAction.HIDE_UI,
        "v": InputAction.HISTORY,
        "escape": InputAction.GAME_MENU,
        "mouse_right": InputAction.GAME_MENU,
        "f5": InputAction.QUICK_SAVE,
        "f9": InputAction.QUICK_LOAD,
        "s": InputAction.SCREENSHOT,
        "f": InputAction.FULLSCREEN,
        "f11": InputAction.FULLSCREEN,
        "shift+r": InputAction.RELOAD,
        "f3": InputAction.DEBUG_OVERLAY,
        "up": InputAction.NAV_UP,
        "down": InputAction.NAV_DOWN,
        "left": InputAction.NAV_LEFT,
        "right": InputAction.NAV_RIGHT,
        "q": InputAction.QUIT,
    }

    def __init__(self, bindings: dict[str, InputAction] | None = None) -> None:
        """Initialize Keymap with optional custom bindings overriding defaults.

        Args:
            bindings: Optional mapping of key names to InputAction enums.
        """
        self.bindings: dict[str, InputAction] = dict(self.DEFAULT_BINDINGS)
        if bindings:
            self.bindings.update(bindings)

    def map_key(self, key_name: str) -> InputAction | None:
        """Map normalized key name string to InputAction or None if unbound.

        Args:
            key_name: Key identifier string (e.g. 'space', 'escape', 'ctrl').

        Returns:
            Bound InputAction or None if key is not mapped.
        """
        return self.bindings.get(key_name.lower())

    def bind(self, key_name: str, action: InputAction) -> None:
        """Bind a key name to an InputAction.

        Args:
            key_name: Key identifier string.
            action: Semantic InputAction to assign.
        """
        logger.debug("Binding %r -> %s", key_name, action.value)
        self.bindings[key_name.lower()] = action

    def unbind(self, key_name: str) -> None:
        """Unbind a key name, removing its semantic mapping.

        Args:
            key_name: Key identifier string to remove.
        """
        logger.debug("Unbinding %r", key_name)
        _ = self.bindings.pop(key_name.lower(), None)
