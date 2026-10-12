"""Screens package exports."""

from eager_graphics.screens.builtin import (
    HistoryScreen,
    PreferencesScreen,
    SaveLoadScreen,
    TitleScreen,
)
from eager_graphics.screens.screen import Screen, ScreenManager
from eager_graphics.screens.theme import Theme
from eager_graphics.screens.widgets import Bar, Button, Grid, Label, Slider

__all__ = [
    "Bar",
    "Button",
    "Grid",
    "HistoryScreen",
    "Label",
    "PreferencesScreen",
    "SaveLoadScreen",
    "Screen",
    "ScreenManager",
    "Slider",
    "Theme",
    "TitleScreen",
]
