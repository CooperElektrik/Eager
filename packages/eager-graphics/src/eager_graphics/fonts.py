"""Font discovery and unified typeface registration for render backends."""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pyglet

_CANONICAL_FONT_NAME = "Aileron"
_FALLBACK_FONT_NAME = "sans-serif"
_PYGLET_FONT_REGISTERED = False


def get_default_font_data() -> bytes | None:
    """Extract canonical Aileron TTF bytes from PIL if available."""
    try:
        from PIL import ImageFont

        for const in ImageFont.load_default.__code__.co_consts:
            if isinstance(const, bytes) and len(const) > 1000:
                return base64.b64decode(const)
    except Exception:
        pass
    return None


def register_pyglet_default_font() -> str:
    """Register the canonical typeface with Pyglet if possible, returning the font family name."""
    global _PYGLET_FONT_REGISTERED
    if _PYGLET_FONT_REGISTERED:
        return _CANONICAL_FONT_NAME

    try:
        import pyglet

        data = get_default_font_data()
        if data is not None:
            pyglet.font.add_file(io.BytesIO(data))
            _PYGLET_FONT_REGISTERED = True
            return _CANONICAL_FONT_NAME
    except Exception:
        pass

    return _FALLBACK_FONT_NAME


__all__ = [
    "get_default_font_data",
    "register_pyglet_default_font",
]
