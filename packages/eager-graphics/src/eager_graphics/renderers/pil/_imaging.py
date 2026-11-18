"""Low-level image manipulation and geometry algorithms for Pillow rendering."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from ._compat import Image, ImageDraw
from ._constants import _MAX_RGBA_LUTS

_FULL_LUT = list(range(256))


def _image_nbytes(img: Image.Image | None) -> int:
    """Approximate in-memory footprint of *img* (Pillow stores RGB as 4 bytes/px)."""
    if img is None:
        return 0
    return img.width * img.height * (1 if img.mode in ("L", "1", "P") else 4)


def _resize_opaque(img: Image.Image, size: tuple[int, int], resample: Any) -> Image.Image:
    """Resize an RGBA image that is known to be fully opaque.

    ``Image.resize`` converts RGBA to premultiplied ``RGBa`` and back around the
    filter, which costs two full-image passes.  For opaque pixels
    premultiplication is the identity, so the core resampler can be called
    directly with bit-identical results (~45% faster for 1080p backgrounds).
    Falls back to the public API if Pillow internals change.
    """
    if img.mode == "RGBA" and resample != Image.Resampling.NEAREST:
        try:
            return img._new(img.im.resize(size, resample, (0, 0, *img.size)))
        except (AttributeError, TypeError, ValueError):
            pass
    return img.resize(size, resample=resample, reducing_gap=3.0)


def _alpha_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    """Bounding box of non-transparent pixels (fast ``alpha_only`` path when available)."""
    try:
        return img.getbbox(alpha_only=True)
    except TypeError:  # Pillow < 9.4 lacks the alpha_only keyword
        return img.getchannel("A").getbbox()


def _union_bboxes(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    """Return the minimal bounding box enclosing both a and b."""
    return (
        min(a[0], b[0]),
        min(a[1], b[1]),
        max(a[2], b[2]),
        max(a[3], b[3]),
    )


def _bboxes_intersect(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
) -> bool:
    """Return True if two (x0, y0, x1, y1) bounding boxes intersect."""
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _cluster_dirty_boxes(
    boxes: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """Merge only overlapping or intersecting bounding boxes into disjoint clusters."""
    if not boxes:
        return []
    clusters = list(boxes)
    merged = True
    while merged:
        merged = False
        i = 0
        while i < len(clusters):
            j = i + 1
            while j < len(clusters):
                if _bboxes_intersect(clusters[i], clusters[j]):
                    clusters[i] = _union_bboxes(clusters[i], clusters[j])
                    clusters.pop(j)
                    merged = True
                else:
                    j += 1
            i += 1
    return clusters


def _split_rgba(img: Image.Image, *, shared: bool) -> tuple[Image.Image, Image.Image | None]:
    """Split straight RGBA *img* into ``(color with alpha=255, alpha mask | None)``."""
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] == 255:
        return img, None
    color = img.copy() if shared else img
    color.putalpha(255)
    return color, alpha


def rotate_expand_params(
    w: int, h: int, angle_deg: float
) -> tuple[tuple[int, int], tuple[float, float, float, float, float, float]]:
    """Compute output dimensions and reverse affine matrix identical to ``Image.rotate(expand=True)``."""
    angle = -math.radians(angle_deg % 360.0)
    matrix = [
        round(math.cos(angle), 15),
        round(math.sin(angle), 15),
        0.0,
        round(-math.sin(angle), 15),
        round(math.cos(angle), 15),
        0.0,
    ]
    center_x = w / 2.0
    center_y = h / 2.0
    a, b, _c, d, e, _f = matrix
    c_new = a * (-center_x) + b * (-center_y) + center_x
    f_new = d * (-center_x) + e * (-center_y) + center_y

    xx = [c_new, a * w + c_new, a * w + b * h + c_new, b * h + c_new]
    yy = [f_new, d * w + f_new, d * w + e * h + f_new, e * h + f_new]

    nw = math.ceil(max(xx)) - math.floor(min(xx))
    nh = math.ceil(max(yy)) - math.floor(min(yy))

    dx = -(nw - w) / 2.0
    dy = -(nh - h) / 2.0
    matrix[2] = c_new + (a * dx + b * dy)
    matrix[5] = f_new + (d * dx + e * dy)

    return (nw, nh), (matrix[0], matrix[1], matrix[2], matrix[3], matrix[4], matrix[5])


@lru_cache(maxsize=_MAX_RGBA_LUTS)
def get_rgba_lut(r: int, g: int, b: int, a: int, mode: str = "RGBA") -> list[int]:
    """Return a cached 768-entry (RGB) or 1024-entry (RGBA) point LUT for tint/alpha modulation."""
    r_lut = _FULL_LUT if r == 255 else [round(i * r / 255) for i in range(256)]
    g_lut = _FULL_LUT if g == 255 else [round(i * g / 255) for i in range(256)]
    b_lut = _FULL_LUT if b == 255 else [round(i * b / 255) for i in range(256)]
    if mode == "RGB":
        return r_lut + g_lut + b_lut
    a_lut = _FULL_LUT if a == 255 else [round(i * a / 255) for i in range(256)]
    return r_lut + g_lut + b_lut + a_lut


@lru_cache(maxsize=64)
def get_fade_lut(factor_q: int, r: int, g: int, b: int, mode: str) -> list[int]:
    """Return a cached point LUT for full-screen fade overlays."""
    inv = 1.0 - factor_q / 255.0
    r_lut = [round(i * inv + r * (1.0 - inv)) for i in range(256)]
    g_lut = [round(i * inv + g * (1.0 - inv)) for i in range(256)]
    b_lut = [round(i * inv + b * (1.0 - inv)) for i in range(256)]
    if mode == "RGBA":
        return r_lut + g_lut + b_lut + _FULL_LUT
    return r_lut + g_lut + b_lut


@lru_cache(maxsize=64)
def get_rect_mask(rw: int, rh: int, radius: int) -> Image.Image:
    """Return a cached rounded-rectangle alpha mask."""
    mask = Image.new("L", (rw, rh), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([(0, 0), (rw - 1, rh - 1)], radius=radius, fill=255)
    return mask


__all__ = [
    "_alpha_bbox",
    "_bboxes_intersect",
    "_cluster_dirty_boxes",
    "_image_nbytes",
    "_resize_opaque",
    "_split_rgba",
    "_union_bboxes",
    "get_fade_lut",
    "get_rect_mask",
    "get_rgba_lut",
    "rotate_expand_params",
]
