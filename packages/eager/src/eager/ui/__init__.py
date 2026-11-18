"""UI components, screens, and player shells for Eager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager.ui.components import (
    ChoiceMenu,
    ChoiceMenuStyle,
    DialogueBox,
    DialogueBoxLayout,
    EndNotice,
    InputBox,
    QuickMenu,
    TextboxStyle,
    UIOverlay,
    choice_menu_style_from_theme,
    textbox_style_from_theme,
)
from eager.ui.player import BasePlayer
from eager.ui.screens import (
    Button,
    GameMenuScreen,
    Grid,
    HistoryScreen,
    Label,
    PreferencesScreen,
    SaveLoadScreen,
    SaveSlotButton,
    Screen,
    ScreenManager,
    Slider,
    TitleScreen,
)
from eager.ui.terminal_player import TerminalPlayer

__all__ = [
    "BasePlayer",
    "Button",
    "ChoiceMenu",
    "ChoiceMenuStyle",
    "DialogueBox",
    "DialogueBoxLayout",
    "EndNotice",
    "GameMenuScreen",
    "Grid",
    "HistoryScreen",
    "InputBox",
    "Label",
    "PILPlayer",
    "PreferencesScreen",
    "PygletPlayer",
    "QuickMenu",
    "SaveLoadScreen",
    "SaveSlotButton",
    "Screen",
    "ScreenManager",
    "Slider",
    "TerminalPlayer",
    "TextboxStyle",
    "TitleScreen",
    "UIOverlay",
    "choice_menu_style_from_theme",
    "textbox_style_from_theme",
]

if TYPE_CHECKING:
    from eager.ui.pil_player import PILPlayer
    from eager.ui.pyglet_player import PygletPlayer

_LAZY = {
    "PILPlayer": ("eager.ui.pil_player", "PILPlayer"),
    "PygletPlayer": ("eager.ui.pyglet_player", "PygletPlayer"),
}


def __getattr__(name: str) -> object:
    if name in _LAZY:
        import importlib

        module_path, attr_name = _LAZY[name]
        mod = importlib.import_module(module_path)
        val = getattr(mod, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
