"""Rendering backends for Eager.

The ``NullRenderer`` is pure-Python and dependency-free, so it is always
available — even when no graphical backend (e.g. Pyglet) is installed.

Optional backends (Pyglet) are resolved lazily via ``__getattr__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager.backends.renderers.null import NullRenderBackend, NullRenderer

__all__ = [
    "NullRenderBackend",
    "NullRenderer",
    "PygletAssetResolver",
    "PygletRenderer",
]

if TYPE_CHECKING:
    from eager.backends.renderers.pyglet import PygletAssetResolver, PygletRenderer

_LAZY: dict[str, tuple[str, str]] = {
    "PygletAssetResolver": ("eager.backends.renderers.pyglet", "PygletAssetResolver"),
    "PygletRenderer": ("eager.backends.renderers.pyglet", "PygletRenderer"),
}

_CACHE: dict[str, object] = {}


def __getattr__(name: str) -> object:
    """Lazily import optional backends on first access."""
    if name in _LAZY:
        if name not in _CACHE:
            module_path, attr_name = _LAZY[name]
            try:
                mod = __import__(module_path, fromlist=[attr_name])
                _CACHE[name] = getattr(mod, attr_name)
            except ImportError as exc:
                _CACHE[name] = None
                raise ImportError(
                    f"Optional backend '{name}' is not available: {exc}"
                ) from exc
        result = _CACHE[name]
        if result is None:
            raise ImportError(f"Optional backend '{name}' is not available")
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
