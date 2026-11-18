"""Screens package exports."""

from eager.ui.screens.builtin import (
    GameMenuScreen,
    HistoryScreen,
    PreferencesScreen,
    SaveLoadScreen,
    TitleScreen,
)
from eager.ui.screens.screen import Screen, ScreenManager
from eager.ui.screens.widgets import Button, Grid, Label, SaveSlotButton, Slider

__all__ = [
    "Button",
    "GameMenuScreen",
    "Grid",
    "HistoryScreen",
    "Label",
    "PreferencesScreen",
    "SaveLoadScreen",
    "SaveSlotButton",
    "Screen",
    "ScreenManager",
    "Slider",
    "TitleScreen",
]
