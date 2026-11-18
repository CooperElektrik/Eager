"""Exception hierarchy for eager-graphics presentation and rendering errors."""

from __future__ import annotations

from eager_core.exceptions import EagerCoreError

__all__ = [
    "AssetSecurityError",
    "EagerGraphicsError",
    "RenderError",
    "ScreenError",
]


class EagerGraphicsError(EagerCoreError):
    """Base exception for all errors raised within eager-graphics."""


class RenderError(EagerGraphicsError, RuntimeError):  # pyright: ignore[reportUnsafeMultipleInheritance]
    """Raised when a rendering or compositor operation fails."""


class ScreenError(EagerGraphicsError, RuntimeError):  # pyright: ignore[reportUnsafeMultipleInheritance]
    """Raised when an error occurs during screen navigation or lifecycle."""


class AssetSecurityError(EagerGraphicsError, ValueError):  # pyright: ignore[reportUnsafeMultipleInheritance]
    """Raised when an asset path traversal or security violation is detected."""
