"""Domain exception hierarchy for the Eager core subsystem."""

from __future__ import annotations

__all__ = [
    "AudioError",
    "ColorParseError",
    "EagerCoreError",
    "I18nError",
    "StorageError",
]


class EagerCoreError(Exception):
    """Base exception for all errors raised within eager-core."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args)
        for key, value in kwargs.items():
            setattr(self, key, value)


class AudioError(EagerCoreError):
    """Raised when an audio operation, asset resolution, or backend fails."""


class ColorParseError(EagerCoreError):
    """Raised when parsing or constructing a Color fails."""


class StorageError(EagerCoreError):
    """Raised when atomic write or persistent storage operations fail."""


class I18nError(EagerCoreError):
    """Raised when translation catalog operations or locale switching fails."""
