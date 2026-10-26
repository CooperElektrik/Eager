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


class AudioError(EagerCoreError, ValueError):
    """Raised when an audio operation, asset resolution, or backend fails.

    Inherits from ValueError for backward compatibility with existing path traversal guards.
    """


class ColorParseError(EagerCoreError, ValueError):
    """Raised when parsing or constructing a Color fails.

    Inherits from ValueError for backward compatibility with Color.from_hex callers.
    """


class StorageError(EagerCoreError, OSError):
    """Raised when atomic write or persistent storage operations fail.

    Inherits from OSError for backward compatibility with disk I/O exception handlers.
    """


class I18nError(EagerCoreError, ValueError):
    """Raised when translation catalog operations or locale switching fails.

    Inherits from ValueError for backward compatibility.
    """
