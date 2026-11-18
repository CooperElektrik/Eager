"""Rendering and audio backends for Eager (Null, PIL, Pyglet, Miniaudio)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager.backends.audio.null import NullAudioBackend
from eager.backends.renderers.null import NullRenderBackend, NullRenderer
from eager.backends.types import RenderBackend, RenderItem, UIDrawBackend

__all__ = [
    "MiniaudioAudioBackend",
    "NullAudioBackend",
    "NullRenderBackend",
    "NullRenderer",
    "PILAssetResolver",
    "PILRenderer",
    "PygletAssetResolver",
    "PygletAudioBackend",
    "PygletRenderer",
    "RenderBackend",
    "RenderItem",
    "UIDrawBackend",
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


def __getattr__(name: str) -> object:
    if name in _LAZY:
        import importlib

        module_path, attr_name = _LAZY[name]
        mod = importlib.import_module(module_path)
        val = getattr(mod, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
