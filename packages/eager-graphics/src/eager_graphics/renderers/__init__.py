"""Rendering backends for Eager-Graphics.

The ``NullRenderer`` is pure-Python and dependency-free, so it is always
available — even when no graphical backend (e.g. Pyglet) is installed.

Optional backends (Pyglet, PIL) are **not** eagerly imported here
because doing so can have global side effects (e.g. Pyglet initialises GTK/EGL
on Wayland). Instead, they are resolved lazily via ``__getattr__`` when
accessed. This means importing a specific renderer module — e.g.
``from eager_graphics.renderers.pil import PILRenderer`` — will **not**
trigger an import of the pyglet backend module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# The NullRenderer is pure-Python and dependency-free, so it is always
# available — even when no graphical backend (e.g. Pyglet) is installed.
from eager_graphics.player import BasePlayer
from eager_graphics.renderers.null import NullRenderer

__all__ = [
    "BasePlayer",
    "MiniaudioAudioBackend",
    "NullRenderer",
    "PILAssetResolver",
    "PILPlayer",
    "PILRenderer",
    "PygletAssetResolver",
    "PygletAudioBackend",
    "PygletPlayer",
    "PygletRenderer",
]


if TYPE_CHECKING:
    # For type-checkers only — the real names are resolved lazily at runtime.
    from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend
    from eager_graphics.renderers.pil import PILAssetResolver, PILPlayer, PILRenderer
    from eager_graphics.renderers.pyglet import (
        PygletAssetResolver,
        PygletAudioBackend,
        PygletPlayer,
        PygletRenderer,
    )


# Map of lazy-backend class name → (module path, imported name).
# Resolved on first access via ``__getattr__``.
_LAZY: dict[str, tuple[str, str]] = {
    "MiniaudioAudioBackend": ("eager_graphics.renderers.miniaudio", "MiniaudioAudioBackend"),
    "PygletAssetResolver": ("eager_graphics.renderers.pyglet", "PygletAssetResolver"),
    "PygletAudioBackend": ("eager_graphics.renderers.pyglet", "PygletAudioBackend"),
    "PygletPlayer": ("eager_graphics.renderers.pyglet", "PygletPlayer"),
    "PygletRenderer": ("eager_graphics.renderers.pyglet", "PygletRenderer"),
    "PILAssetResolver": ("eager_graphics.renderers.pil", "PILAssetResolver"),
    "PILPlayer": ("eager_graphics.renderers.pil", "PILPlayer"),
    "PILRenderer": ("eager_graphics.renderers.pil", "PILRenderer"),
}

_CACHE: dict[str, object] = {}


def __getattr__(name: str) -> object:
    """Lazily import optional backends on first access.

    This avoids importing Pyglet (which has global side effects such as
    initialising GTK/EGL on Wayland) when the caller only wants a different
    backend like PIL.
    """
    if name in _LAZY:
        if name not in _CACHE:
            module_path, attr_name = _LAZY[name]
            try:
                mod = __import__(module_path, fromlist=[attr_name])
                _CACHE[name] = getattr(mod, attr_name)
            except ImportError as exc:
                _CACHE[name] = None  # cache the failure
                raise ImportError(
                    f"Optional backend '{name}' is not available: {exc}"
                ) from exc
        result = _CACHE[name]
        if result is None:
            raise ImportError(f"Optional backend '{name}' is not available")
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
