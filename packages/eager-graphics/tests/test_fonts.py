"""Unit tests for eager_graphics.fonts discovery and unified registration."""

from __future__ import annotations

from unittest import mock

from eager_graphics.fonts import (
    _CANONICAL_FONT_NAME,
    _FALLBACK_FONT_NAME,
    get_default_font_data,
    register_pyglet_default_font,
)


def test_get_default_font_data_returns_bytes_or_none() -> None:
    data = get_default_font_data()
    if data is not None:
        assert isinstance(data, bytes)
        assert len(data) > 1000
        # Check standard OpenType / TrueType sfnt header signatures
        assert data.startswith((b"\x00\x01\x00\x00", b"OTTO"))


def test_get_default_font_data_graceful_on_missing_pil() -> None:
    with mock.patch.dict("sys.modules", {"PIL": None, "PIL.ImageFont": None}):
        assert get_default_font_data() is None


def test_register_pyglet_default_font_lifecycle() -> None:
    import eager_graphics.fonts as fonts_mod

    # Reset global state for test isolation
    orig_state = fonts_mod._PYGLET_FONT_REGISTERED
    try:
        fonts_mod._PYGLET_FONT_REGISTERED = False
        font_name = register_pyglet_default_font()
        assert font_name in (_CANONICAL_FONT_NAME, _FALLBACK_FONT_NAME)

        # Subsequent call should return cached font name
        assert register_pyglet_default_font() == font_name
    finally:
        fonts_mod._PYGLET_FONT_REGISTERED = orig_state


def test_register_pyglet_default_font_fallback_on_error() -> None:
    import eager_graphics.fonts as fonts_mod

    orig_state = fonts_mod._PYGLET_FONT_REGISTERED
    try:
        fonts_mod._PYGLET_FONT_REGISTERED = False
        with mock.patch("eager_graphics.fonts.get_default_font_data", return_value=None):
            assert register_pyglet_default_font() == _FALLBACK_FONT_NAME
    finally:
        fonts_mod._PYGLET_FONT_REGISTERED = orig_state
