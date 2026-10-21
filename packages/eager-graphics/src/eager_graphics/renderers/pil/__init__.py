"""Pillow (PIL) software rendering backend and interactive player for Eager-Graphics."""

# ruff: noqa: F401

from __future__ import annotations

from ._cache import _CachedSprite, _GeomEntry, _ImageLRU
from ._compat import (
    PIL_AVAILABLE,
    TKINTER_AVAILABLE,
    _check_pil_available,
    _detect_pillow_simd,
    _pil_import_error,
    _TclError,
    tk,
)
from ._constants import (
    _ALPHA_LUTS,
    _ALPHA_MODULATION_1024,
    _DEFAULT_CACHE_BYTES,
    _EXTENSIONS,
    _IDENTITY_256,
    _MAX_GRADIENT_CACHE,
    _MAX_MIP_CACHE,
    _MAX_RGBA_LUTS,
    _MAX_TEXT_CACHE,
    _NO_CACHE,
    _OPAQUE_LUT,
    _PIL_ANCHOR_X,
    _PIL_ANCHOR_Y,
    _PLACEHOLDER_GRAD_LUT,
    _QUANT_ALPHA_LUT,
    _REDUCING_GAP,
    _WHITE_RGBA,
)
from ._imaging import (
    _alpha_bbox,
    _bboxes_intersect,
    _image_nbytes,
    _largest_opaque_rect,
    _max_rect,
    _resize_opaque,
    _solid_band,
    _split_patches,
    _split_rgba,
    _union_bboxes,
)
from .assets import PILAssetResolver
from .player import PILPlayer
from .renderer import PILRenderer

if PIL_AVAILABLE:
    import PIL
    from PIL import Image, ImageChops, ImageDraw, ImageFont
else:
    PIL = None
    Image = None
    ImageChops = None
    ImageDraw = None
    ImageFont = None

__all__ = [
    "PIL_AVAILABLE",
    "TKINTER_AVAILABLE",
    "PILAssetResolver",
    "PILPlayer",
    "PILRenderer",
]
