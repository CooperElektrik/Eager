"""Audio playback backends for Eager."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager.core.audio import NullAudioBackend

__all__ = [
    "MiniaudioAudioBackend",
    "NullAudioBackend",
    "PygletAudioBackend",
]

if TYPE_CHECKING:
    from eager.backends.audio.miniaudio import MiniaudioAudioBackend
    from eager.backends.audio.pyglet import PygletAudioBackend

_LAZY_EXPORTS = {
    "MiniaudioAudioBackend": "eager.backends.audio.miniaudio",
    "PygletAudioBackend": "eager.backends.audio.pyglet",
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
