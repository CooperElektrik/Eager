"""Discrete narrative events emitted by the Eager story virtual machine."""

from __future__ import annotations

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

__all__ = [
    "AppendEvent",
    "ChoiceOption",
    "ChoicePromptEvent",
    "DialogueEvent",
    "FreshBoxEvent",
    "HookEvent",
    "InputPromptEvent",
    "NarrationEvent",
    "SceneEnterEvent",
    "SceneExitEvent",
    "StoryEndEvent",
    "StoryEvent",
]
