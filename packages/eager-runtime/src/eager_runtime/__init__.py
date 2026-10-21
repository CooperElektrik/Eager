"""Eager: Lightweight narrative runtime engine for Eager-Script screenplays.

The headless VM, events, dispatcher, and state management are always
available.  The graphics-dependent
:class:`~eager_runtime.session.GameSession` controller is imported lazily so
that a bare ``import eager_runtime`` stays headless and dependency-free (it
does not require ``eager_graphics`` to be installed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eager_core.events import (
    AppendEvent,
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    HookEvent,
    InputPromptEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
    StoryEvent,
)
from eager_core.input import InputAction, Keymap

from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.player import TerminalPlayer
from eager_runtime.runtime import StoryRuntimeError, StoryVM
from eager_runtime.state import CallFrame, HistoryManager, StorySnapshot

if TYPE_CHECKING:
    from eager_runtime.assets import (
        AssetCheckReport,
        AssetReference,
        MissingAssetIssue,
        check_assets,
    )
    from eager_runtime.backlog import Backlog, BacklogEntry
    from eager_runtime.persistent import PersistentData
    from eager_runtime.preferences import Preferences
    from eager_runtime.saves import SaveData, SaveManager, SaveMetadata
    from eager_runtime.session import Checkpoint, CheckpointHistory, GameSession
    from eager_runtime.watcher import FileWatcher

__version__ = "0.3.0"

__all__ = [
    "AppendEvent",
    "AssetCheckReport",
    "AssetReference",
    "Backlog",
    "BacklogEntry",
    "CallFrame",
    "Checkpoint",
    "CheckpointHistory",
    "ChoiceOption",
    "ChoicePromptEvent",
    "DialogueEvent",
    "EventDispatcher",
    "FileWatcher",
    "FreshBoxEvent",
    "GameSession",
    "HistoryManager",
    "HookEvent",
    "InputAction",
    "InputPromptEvent",
    "Keymap",
    "MissingAssetIssue",
    "NarrationEvent",
    "PersistentData",
    "Preferences",
    "SaveData",
    "SaveManager",
    "SaveMetadata",
    "SceneEnterEvent",
    "SceneExitEvent",
    "StoryEndEvent",
    "StoryEvent",
    "StoryRuntimeError",
    "StorySnapshot",
    "StoryVM",
    "TerminalPlayer",
    "check_assets",
]


_LAZY_EXPORTS = {
    "AssetCheckReport": "eager_runtime.assets",
    "AssetReference": "eager_runtime.assets",
    "MissingAssetIssue": "eager_runtime.assets",
    "check_assets": "eager_runtime.assets",
    "GameSession": "eager_runtime.session",
    "Checkpoint": "eager_runtime.session",
    "CheckpointHistory": "eager_runtime.session",
    "SaveManager": "eager_runtime.saves",
    "SaveMetadata": "eager_runtime.saves",
    "SaveData": "eager_runtime.saves",
    "PersistentData": "eager_runtime.persistent",
    "Preferences": "eager_runtime.preferences",
    "Backlog": "eager_runtime.backlog",
    "BacklogEntry": "eager_runtime.backlog",
    "FileWatcher": "eager_runtime.watcher",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        import importlib

        module = importlib.import_module(_LAZY_EXPORTS[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
