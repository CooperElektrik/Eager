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


class RenderError(EagerGraphicsError):
    """Raised when a rendering or compositor operation fails."""


class ScreenError(EagerGraphicsError):
    """Raised when an error occurs during screen navigation or lifecycle."""


class AssetSecurityError(EagerGraphicsError):
    """Raised when an asset path traversal or security violation is detected."""
