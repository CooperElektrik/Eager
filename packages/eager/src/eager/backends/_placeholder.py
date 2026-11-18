"""Shared procedural Pillow gradient placeholder generator for visual backends."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

_PLACEHOLDER_GRAD_LUT: list[int] = [int(200 + i * 0.21) for i in range(256)]

__all__ = [
    "generate_placeholder_pil",
    "placeholder_base_color",
]


def placeholder_base_color(asset_id: str, width: int, height: int) -> tuple[int, int, int, int, int]:
    """Return deterministic ``(target_width, target_height, r, g, b)`` for *asset_id*."""
    is_bg = asset_id.startswith("bg/") or "background" in asset_id
    w = 1920 if is_bg else width
    h = 1080 if is_bg else height

    h_val = int(hashlib.md5(asset_id.encode("utf-8")).hexdigest()[:8], 16)
    r = h_val & 0xFF
    g = (h_val >> 8) & 0xFF
    b = (h_val >> 16) & 0xFF

    if is_bg:
        r = 30 + (r % 60)
        g = 35 + (g % 60)
        b = 45 + (b % 70)
    else:
        r = 100 + (r % 120)
        g = 100 + (g % 120)
        b = 100 + (b % 120)

    return w, h, r, g, b


def generate_placeholder_pil(
    asset_id: str,
    width: int,
    height: int,
) -> tuple[Image.Image, bool]:
    """Procedurally generate an opaque RGBA gradient placeholder image using Pillow."""
    from PIL import Image, ImageChops, ImageDraw

    w, h, r, g, b = placeholder_base_color(asset_id, width, height)
    tw = min(w, 256)
    th = min(h, 256)

    base = Image.new("RGBA", (tw, th), (r, g, b, 255))
    grad_l = Image.linear_gradient("L").resize((tw, th), resample=Image.Resampling.BILINEAR)
    grad_mask = grad_l.point(_PLACEHOLDER_GRAD_LUT)
    base = ImageChops.multiply(
        base,
        Image.merge(
            "RGBA",
            (grad_mask, grad_mask, grad_mask, Image.new("L", (tw, th), 255)),
        ),
    )

    draw = ImageDraw.Draw(base)
    draw.rectangle((0, 0, tw - 1, th - 1), outline=(255, 255, 255, 255), width=2)

    if (tw, th) != (w, h):
        base = base.resize((w, h), resample=Image.Resampling.BILINEAR)

    return base, True
