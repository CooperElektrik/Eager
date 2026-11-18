"""Font discovery and unified typeface registration (re-exported from backends)."""

from __future__ import annotations

from eager.backends.fonts import get_default_font_data, register_pyglet_default_font

__all__ = [
    "get_default_font_data",
    "register_pyglet_default_font",
]
