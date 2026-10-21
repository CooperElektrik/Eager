"""Low-level image manipulation and geometry algorithms for Pillow rendering."""

from __future__ import annotations

from typing import Any

from ._compat import Image
from ._constants import _OPAQUE_LUT


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
    return img.resize(size, resample=resample)


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


def _max_rect(data: bytes, cw: int, ch: int) -> tuple[int, int, int, int] | None:
    """Largest all-``255`` rectangle in a ``cw`` x ``ch`` byte grid (cell coords, end-exclusive)."""
    heights = [0] * cw
    best: tuple[int, int, int, int] | None = None
    best_area = 0
    for y in range(ch):
        base = y * cw
        for x in range(cw):
            heights[x] = heights[x] + 1 if data[base + x] else 0
        stack: list[tuple[int, int]] = []
        for x in range(cw + 1):
            h_cur = heights[x] if x < cw else 0
            start = x
            while stack and stack[-1][1] > h_cur:
                sx, sh = stack.pop()
                area = sh * (x - sx)
                if area > best_area:
                    best_area = area
                    best = (sx, y - sh + 1, x, y + 1)
                start = sx
            stack.append((start, h_cur))
    return best


def _largest_opaque_rect(
    mask: Image.Image, *, min_frac: float = 0.15, min_area: int = 4096
) -> tuple[int, int, int, int] | None:
    """Largest axis-aligned rectangle of fully-opaque pixels in an ``L`` *mask*.

    The search runs on a coarse downsampled grid (a ``BOX`` average of a 0/255
    mask is 255 only when *every* contributing pixel is opaque), so it is cheap
    even for multi-megapixel sprites and never reports a rectangle containing
    partially-transparent pixels.  Returns ``None`` when no worthwhile interior
    exists (e.g. soft glows), leaving the caller on the general masked path.
    """
    w, h = mask.size
    if w * h < min_area:
        return None
    op = mask.point(_OPAQUE_LUT)
    if op.getbbox() is None:
        return None
    step = max(1, int((w * h / 8000) ** 0.5))
    cw, ch = w // step, h // step
    if cw < 1 or ch < 1:
        return None
    best = _max_rect(op.resize((cw, ch), Image.Resampling.BOX).tobytes(), cw, ch)
    if best is None:
        return None
    rect = (best[0] * step, best[1] * step, min(w, best[2] * step), min(h, best[3] * step))
    for _ in range(4):
        if rect[2] - rect[0] <= 0 or rect[3] - rect[1] <= 0:
            return None
        if op.crop(rect).getextrema() == (255, 255):
            break
        rect = (rect[0] + step, rect[1] + step, rect[2] - step, rect[3] - step)
    else:
        return None
    if (rect[2] - rect[0]) * (rect[3] - rect[1]) < min_frac * w * h:
        return None
    return rect


def _solid_band(
    color: Image.Image, mask: Image.Image, box: tuple[int, int, int, int]
) -> tuple[Image.Image, Image.Image | None, int, int] | None:
    """Build a compositing patch for *box*: unmasked when opaque, else masked."""
    m = mask.crop(box)
    lo, hi = m.getextrema()
    if hi == 0:
        return None  # fully transparent band — nothing to draw
    patch_mask = None if lo == 255 else m  # fully opaque band needs no mask
    return (color.crop(box), patch_mask, box[0], box[1])


def _split_patches(
    color: Image.Image, mask: Image.Image
) -> list[tuple[Image.Image, Image.Image | None, int, int]] | None:
    """Decompose a masked sprite into patches whose *interior* can be pasted unmasked.

    Masked ``paste`` blends every pixel in the bounding box; pasting a large
    fully-opaque interior without a mask is ~10x cheaper, so we split the sprite
    into that interior (unmasked) plus up to four masked fringe bands (which
    exactly tile the remaining pixels).  The result is byte-identical to a single
    masked paste.  Returns ``None`` when the decomposition would not pay off.
    """
    rect = _largest_opaque_rect(mask)
    if rect is None:
        return None
    x0, y0, x1, y1 = rect
    w, h = mask.size
    patches: list[tuple[Image.Image, Image.Image | None, int, int] | None] = [
        (color.crop(rect), None, x0, y0)
    ]
    if y0 > 0:
        patches.append(_solid_band(color, mask, (0, 0, w, y0)))
    if y1 < h:
        patches.append(_solid_band(color, mask, (0, y1, w, h)))
    if x0 > 0:
        patches.append(_solid_band(color, mask, (0, y0, x0, y1)))
    if x1 < w:
        patches.append(_solid_band(color, mask, (x1, y0, w, y1)))
    return [p for p in patches if p is not None]


def _split_rgba(img: Image.Image, *, shared: bool) -> tuple[Image.Image, Image.Image | None]:
    """Split straight RGBA *img* into ``(color with alpha=255, alpha mask | None)``."""
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] == 255:
        return img, None
    color = img.copy() if shared else img
    color.putalpha(255)
    return color, alpha


__all__ = [
    "_alpha_bbox",
    "_bboxes_intersect",
    "_image_nbytes",
    "_largest_opaque_rect",
    "_max_rect",
    "_resize_opaque",
    "_solid_band",
    "_split_patches",
    "_split_rgba",
    "_union_bboxes",
]
