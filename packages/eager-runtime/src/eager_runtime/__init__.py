"""Eager: Lightweight narrative runtime engine for Eager-Script screenplays.

The headless VM, events, dispatcher, and state management are always
available.  The graphics-dependent
:class:`~eager_runtime.session.GameSession` controller is imported lazily so
that a bare ``import eager_runtime`` stays headless and dependency-free (it
does not require ``eager_graphics`` to be installed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eager_core.dispatcher import EventDispatcher
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
from eager_core.state import CallFrame, Checkpoint, CheckpointHistory, StorySnapshot

from eager_runtime.player import TerminalPlayer
from eager_runtime.runtime import StoryRuntimeError, StoryVM

if TYPE_CHECKING:
    from eager_core.backlog import Backlog, BacklogEntry
    from eager_core.persistent import PersistentData
    from eager_core.preferences import Preferences
    from eager_core.saves import (
        SaveData,
        SaveManager,
        SaveMetadata,
        SaveMigrationError,
    )
    from eager_core.watcher import FileWatcher

    from eager_runtime.assets import (
        AssetCheckReport,
        AssetReference,
        MissingAssetIssue,
        check_assets,
    )
    from eager_runtime.project import (
        ProjectConfig,
        load_project_graph,
        merge_graphs,
        resolve_project_scripts,
    )
    from eager_runtime.session import GameSession

__version__ = "0.8.0"

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
    "HookEvent",
    "InputAction",
    "InputPromptEvent",
    "Keymap",
    "MissingAssetIssue",
    "NarrationEvent",
    "PersistentData",
    "Preferences",
    "ProjectConfig",
    "SaveData",
    "SaveManager",
    "SaveMetadata",
    "SaveMigrationError",
    "SceneEnterEvent",
    "SceneExitEvent",
    "StoryEndEvent",
    "StoryEvent",
    "StoryRuntimeError",
    "StorySnapshot",
    "StoryVM",
    "TerminalPlayer",
    "check_assets",
    "load_project_graph",
    "merge_graphs",
    "resolve_project_scripts",
]


_LAZY_EXPORTS = {
    "AssetCheckReport": "eager_runtime.assets",
    "AssetReference": "eager_runtime.assets",
    "MissingAssetIssue": "eager_runtime.assets",
    "check_assets": "eager_runtime.assets",
    "GameSession": "eager_runtime.session",
    "SaveManager": "eager_core.saves",
    "SaveMetadata": "eager_core.saves",
    "SaveData": "eager_core.saves",
    "SaveMigrationError": "eager_core.saves",
    "PersistentData": "eager_core.persistent",
    "Preferences": "eager_core.preferences",
    "Backlog": "eager_core.backlog",
    "BacklogEntry": "eager_core.backlog",
    "FileWatcher": "eager_core.watcher",
    "ProjectConfig": "eager_runtime.project",
    "load_project_graph": "eager_runtime.project",
    "merge_graphs": "eager_runtime.project",
    "resolve_project_scripts": "eager_runtime.project",
}


def __getattr__(name: str) -> Any:
    """Lazy-load package exports when accessed dynamically."""
    if name in _LAZY_EXPORTS:
        import importlib

        module = importlib.import_module(_LAZY_EXPORTS[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
