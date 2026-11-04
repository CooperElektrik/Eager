"""Headless implementations of StageProtocol, UIProtocol, and ScreenManagerProtocol."""

from __future__ import annotations

from eager_core.headless import (
    HeadlessUIState,
    NullCompositor,
    NullRenderer,
    NullScreenManager,
    NullStage,
    NullUI,
)

__all__ = [
    "HeadlessUIState",
    "NullCompositor",
    "NullRenderer",
    "NullScreenManager",
    "NullStage",
    "NullUI",
]
