"""Execution state, snapshot serialization, and rollback management for Eager."""

from __future__ import annotations

from eager_core.state import (
    CallFrame,
    Checkpoint,
    CheckpointHistory,
    StorySnapshot,
)

__all__ = [
    "CallFrame",
    "Checkpoint",
    "CheckpointHistory",
    "StorySnapshot",
]
