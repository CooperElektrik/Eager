"""UI components, screens, and player shells for Eager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager.ui.components import (
    ChoiceMenu,
    ChoiceMenuStyle,
    DialogueBox,
    DialogueBoxLayout,
    EndNotice,
    QuickMenu,
    TextboxStyle,
    UIOverlay,
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
    "Label",
    "PreferencesScreen",
    "PygletPlayer",
    "QuickMenu",
    "SaveLoadScreen",
    "SaveSlotButton",
    "Screen",
    "ScreenManager",
    "Slider",
    "TextboxStyle",
    "TitleScreen",
    "UIOverlay",
]

if TYPE_CHECKING:
    from eager.ui.pyglet_player import PygletPlayer

_LAZY = {
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
