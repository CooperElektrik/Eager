"""Constants, lookup tables, and configuration tuning parameters for the Pillow renderer."""

from __future__ import annotations

_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
_ALPHA_LUTS: list[list[int]] = [
    [round(i * (a / 255.0)) for i in range(256)] for a in range(256)
]
_QUANT_ALPHA_LUT: list[int] = [
    255 if i == 255 else max(1, min(254, round(i / 4) * 4)) for i in range(256)
]
_PLACEHOLDER_GRAD_LUT: list[int] = [int(200 + p * 0.21) for p in range(256)]
_OPAQUE_LUT: list[int] = [255 if i == 255 else 0 for i in range(256)]
_WHITE_RGBA: tuple[int, int, int, int] = (255, 255, 255, 255)
_PIL_ANCHOR_X: dict[str, str] = {"left": "l", "center": "m", "right": "r"}
_PIL_ANCHOR_Y: dict[str, str] = {"top": "t", "middle": "m", "bottom": "b"}

_MAX_TEXT_CACHE: int = 1024
_MAX_RGBA_LUTS: int = 256
_MAX_MIP_CACHE: int = 128
_MAX_GRADIENT_CACHE: int = 256

__all__ = [
    "_ALPHA_LUTS",
    "_EXTENSIONS",
    "_MAX_GRADIENT_CACHE",
    "_MAX_MIP_CACHE",
    "_MAX_RGBA_LUTS",
    "_MAX_TEXT_CACHE",
    "_OPAQUE_LUT",
    "_PIL_ANCHOR_X",
    "_PIL_ANCHOR_Y",
    "_PLACEHOLDER_GRAD_LUT",
    "_QUANT_ALPHA_LUT",
    "_WHITE_RGBA",
]
