"""Rendering backends for Eager.

The ``NullRenderer`` is pure-Python and dependency-free, so it is always
available — even when no graphical backend (e.g. Pyglet) is installed.

Optional backends (Pyglet, PIL) are **not** eagerly imported here
because doing so can have global side effects (e.g. Pyglet initialises GTK/EGL
on Wayland). Instead, they are resolved lazily via ``__getattr__`` when
accessed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager.backends.renderers.null import NullRenderBackend, NullRenderer

__all__ = [
    "MiniaudioAudioBackend",
    "NullRenderBackend",
    "NullRenderer",
    "PILAssetResolver",
    "PILRenderer",
    "PygletAssetResolver",
    "PygletAudioBackend",
    "PygletRenderer",
]

if TYPE_CHECKING:
    from eager.backends.audio.miniaudio import MiniaudioAudioBackend
    from eager.backends.audio.pyglet import PygletAudioBackend
    from eager.backends.renderers.pil import PILAssetResolver, PILRenderer
    from eager.backends.renderers.pyglet import PygletAssetResolver, PygletRenderer

_LAZY: dict[str, tuple[str, str]] = {
    "MiniaudioAudioBackend": ("eager.backends.audio.miniaudio", "MiniaudioAudioBackend"),
    "PygletAssetResolver": ("eager.backends.renderers.pyglet", "PygletAssetResolver"),
    "PygletAudioBackend": ("eager.backends.audio.pyglet", "PygletAudioBackend"),
    "PygletRenderer": ("eager.backends.renderers.pyglet", "PygletRenderer"),
    "PILAssetResolver": ("eager.backends.renderers.pil", "PILAssetResolver"),
    "PILRenderer": ("eager.backends.renderers.pil", "PILRenderer"),
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
