"""Audio playback backends for Eager-Graphics."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = [
    "MiniaudioAudioBackend",
    "PygletAudioBackend",
]

if TYPE_CHECKING:
    from eager_graphics.audio.miniaudio import MiniaudioAudioBackend
    from eager_graphics.audio.pyglet import PygletAudioBackend

_LAZY_EXPORTS = {
    "MiniaudioAudioBackend": "eager_graphics.audio.miniaudio",
    "PygletAudioBackend": "eager_graphics.audio.pyglet",
}


def __getattr__(name: str) -> object:
    if name in _LAZY_EXPORTS:
        import importlib

        module = importlib.import_module(_LAZY_EXPORTS[name])
        val = getattr(module, name)
        globals()[name] = val
        return val
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
