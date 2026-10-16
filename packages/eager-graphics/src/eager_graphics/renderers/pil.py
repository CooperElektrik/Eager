"""Pillow (PIL) software rendering backend and interactive player for Eager-Graphics."""

from __future__ import annotations

import hashlib
import math
import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    from PIL import Image, ImageChops, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError as err:
    PIL_AVAILABLE = False
    _pil_import_error = err

try:
    import tkinter as tk

    TKINTER_AVAILABLE = True
except ImportError:
    tk = None  # type: ignore[assignment]
    TKINTER_AVAILABLE = False

from eager_core.input import InputAction, Keymap
from eager_core.timing import FrameClock
from eager_core.types import BLACK, WHITE, Color

from eager_graphics.layout import ViewportTransform
from eager_graphics.protocol import RenderBackend, RenderItem
from eager_graphics.types import ScaleMode
from eager_graphics.ui_components import UIOverlay

if TYPE_CHECKING:
    from eager_runtime import ChoicePromptEvent

    from eager_graphics.compositor import StageCompositor

_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")
_IDENTITY_256: list[int] = list(range(256))
_ALPHA_LUTS: list[list[int]] = [
    [round(i * (a / 255.0)) for i in range(256)] for a in range(256)
]
_ALPHA_MODULATION_1024: list[list[int]] = [
    _IDENTITY_256 + _IDENTITY_256 + _IDENTITY_256 + _ALPHA_LUTS[a] for a in range(256)
]
_QUANT_ALPHA_LUT = [255 if i == 255 else max(1, min(254, round(i / 4) * 4)) for i in range(256)]
_PLACEHOLDER_GRAD_LUT: list[int] = [int(200 + p * 0.21) for p in range(256)]
_OPAQUE_LUT: list[int] = [255 if i == 255 else 0 for i in range(256)]
_WHITE_RGBA: tuple[int, int, int, int] = (255, 255, 255, 255)
_PIL_ANCHOR_X: dict[str, str] = {"left": "l", "center": "m", "right": "r"}
_PIL_ANCHOR_Y: dict[str, str] = {"top": "t", "middle": "m", "bottom": "s"}

# Downscales by more than this factor first run a cheap integer ``reduce()``
# (cached as a mip level) before the filtered resize.  Mirrors Pillow's own
# ``reducing_gap`` option, which ``Image.resize`` silently ignores for RGBA.
_REDUCING_GAP: float = 2.0
_DEFAULT_CACHE_BYTES: int = 256 * 1024 * 1024
_MAX_TEXT_CACHE: int = 1024
_MAX_RGBA_LUTS: int = 256
_MAX_MIP_CACHE: int = 128
_MAX_GRADIENT_CACHE: int = 256
_NO_CACHE: Any = object()


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


class _ImageLRU(OrderedDict):  # type: ignore[type-arg]
    """``OrderedDict`` LRU bounded by both entry count and approximate byte size."""

    def __init__(self, max_items: int, max_bytes: int) -> None:
        super().__init__()
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.nbytes = 0
        self._sizes: dict[Any, int] = {}

    def lookup(self, key: Any) -> Any:
        """Return the cached value (marking it most-recently used) or ``None``."""
        value = self.get(key)
        if value is not None:
            self.move_to_end(key)
        return value

    def put(self, key: Any, value: Any, nbytes: int) -> None:
        """Insert *value*, evicting least-recently-used entries over budget."""
        self.nbytes -= self._sizes.pop(key, 0)
        self[key] = value
        self.move_to_end(key)
        self._sizes[key] = nbytes
        self.nbytes += nbytes
        while len(self) > 1 and (len(self) > self.max_items or self.nbytes > self.max_bytes):
            old_key, _ = self.popitem(last=False)
            self.nbytes -= self._sizes.pop(old_key, 0)

    def clear(self) -> None:
        super().clear()
        self._sizes.clear()
        self.nbytes = 0


class _CachedSprite:
    """A transformed sprite split into an opaque colour plane and an optional mask.

    Storing ``color`` with alpha forced to 255 plus a separate ``L`` ``mask``
    lets the renderer composite with ``Image.paste(color, box, mask)``, which
    is bit-identical to ``alpha_composite`` on an opaque canvas but ~40%
    faster, clips off-screen regions natively, and makes opacity variants
    cheap (only the 1-byte-per-pixel mask differs between fade frames).

    Iterating yields ``(image, is_opaque, off_x, off_y)`` for compatibility
    with the previous tuple-based cache layout, where ``image`` is the
    straight-alpha RGBA sprite (materialised lazily).
    """

    __slots__ = ("_image", "color", "mask", "nbytes", "off_x", "off_y", "patches")

    def __init__(
        self,
        color: Image.Image | None,
        mask: Image.Image | None,
        off_x: float,
        off_y: float,
        patches: list[tuple[Image.Image, Image.Image | None, int, int]] | None = None,
    ) -> None:
        self.color = color
        self.mask = mask
        self.off_x = off_x
        self.off_y = off_y
        # Optional opaque-core + fringe decomposition.  When present it is
        # byte-identical to compositing ``color`` through ``mask`` but lets the
        # hot path use cheap unmasked pastes for the bulk of the sprite.
        self.patches = patches
        self.nbytes = _image_nbytes(color) + _image_nbytes(mask)
        self._image: Image.Image | None = None

    @property
    def is_opaque(self) -> bool:
        return self.mask is None and self.color is not None

    @property
    def image(self) -> Image.Image:
        """Straight-alpha RGBA version of the sprite (allocates when masked)."""
        if self._image is not None:
            return self._image
        if self.color is None:
            raise RuntimeError("Empty sprite")
        if self.mask is None:
            self._image = self.color
            return self.color
        img = self.color.copy()
        img.putalpha(self.mask)
        self._image = img
        return img

    @property
    def size(self) -> tuple[int, int]:
        if self.color is not None:
            return self.color.size
        return (0, 0)

    def __len__(self) -> int:
        return 4

    def __getitem__(self, idx: int) -> Any:
        match idx:
            case 0:
                return self.image
            case 1:
                return self.is_opaque
            case 2:
                return self.off_x
            case 3:
                return self.off_y
            case _:
                raise IndexError(idx)

    def __iter__(self):  # type: ignore[no-untyped-def]
        yield self.image
        yield self.is_opaque
        yield self.off_x
        yield self.off_y


class _GeomEntry:
    """Base geometry for a sprite before opacity modulation."""

    __slots__ = (
        "alpha_masks",
        "color",
        "natural_mask",
        "nbytes",
        "off_x",
        "off_y",
        "patches",
    )

    def __init__(
        self,
        color: Image.Image,
        natural_mask: Image.Image | None,
        off_x: float,
        off_y: float,
        patches: list[tuple[Image.Image, Image.Image | None, int, int]] | None = None,
    ) -> None:
        self.color = color
        self.natural_mask = natural_mask
        self.off_x = off_x
        self.off_y = off_y
        self.patches = patches
        self.alpha_masks: dict[int, Image.Image] = {}
        patch_bytes = (
            sum(_image_nbytes(p[0]) + _image_nbytes(p[1]) for p in patches)
            if patches is not None
            else 0
        )
        self.nbytes = _image_nbytes(color) + _image_nbytes(natural_mask) + patch_bytes

    def __len__(self) -> int:
        return 4

    def __getitem__(self, idx: int) -> Any:
        match idx:
            case 0:
                return self.color
            case 1:
                return self.natural_mask
            case 2:
                return self.off_x
            case 3:
                return self.off_y
            case _:
                raise IndexError(idx)

    def __iter__(self):  # type: ignore[no-untyped-def]
        yield self.color
        yield self.natural_mask
        yield self.off_x
        yield self.off_y


def _split_rgba(img: Image.Image, *, shared: bool) -> tuple[Image.Image, Image.Image | None]:
    """Split straight RGBA *img* into ``(color with alpha=255, alpha mask | None)``."""
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] == 255:
        return img, None
    color = img.copy() if shared else img
    color.putalpha(255)
    return color, alpha


def _check_pil_available() -> None:
    if not PIL_AVAILABLE:
        msg = (
            "Pillow is not installed. Install with 'pip install eager-graphics[software]' "
            "(or 'pip install pillow'). For SIMD-accelerated software rendering use "
            "'pip install eager-graphics[software-simd]'."
        )
        raise ImportError(msg) from _pil_import_error


class PILAssetResolver:
    """Loads and caches textures from disk, generating procedural placeholders when missing."""

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        _check_pil_available()
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self._image_cache: dict[str, Image.Image] = {}
        self._opaque_cache: dict[str, bool] = {}
        self._premultiplied_cache: dict[str, Image.Image] = {}

    def get_image(
        self,
        asset_id: str,
        default_width: int = 400,
        default_height: int = 800,
    ) -> Image.Image:
        """Retrieve pre-decoded RGBA image from cache, load from disk, or generate fallback."""
        img = self._image_cache.get(asset_id)
        if img is not None:
            return img

        if asset_id == "__builtin_color_rect__":
            img = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
            self._image_cache[asset_id] = img
            self._opaque_cache[asset_id] = True
            return img

        # 1. Attempt loading from disk if asset_dir configured
        if self.asset_dir is not None:
            candidate_ids = [asset_id]
            if not asset_id.startswith("characters/"):
                candidate_ids.append(f"characters/{asset_id}")
            if asset_id.startswith("bg/"):
                candidate_ids.append(f"backgrounds/{asset_id[3:]}")
            elif asset_id.startswith("backgrounds/"):
                candidate_ids.append(f"bg/{asset_id[12:]}")

            for cid in candidate_ids:
                for ext in _EXTENSIONS:
                    file_path = self.asset_dir / f"{cid}{ext}"
                    if file_path.is_file():
                        try:
                            with Image.open(file_path) as raw_img:
                                is_opaque = raw_img.mode in ("RGB", "L", "1") or ext in (
                                    ".jpg",
                                    ".jpeg",
                                )
                                img = raw_img.convert("RGBA")
                                if not is_opaque:
                                    extrema = img.getextrema()
                                    if len(extrema) >= 4 and extrema[3][0] == 255:
                                        is_opaque = True

                            self._image_cache[asset_id] = img
                            self._opaque_cache[asset_id] = is_opaque
                            return img
                        except (OSError, ValueError):
                            pass

        # 2. Generate procedural placeholder image
        img, is_opaque = self._generate_placeholder(asset_id, default_width, default_height)
        self._image_cache[asset_id] = img
        self._opaque_cache[asset_id] = is_opaque
        return img

    get_texture = get_image

    def get_premultiplied_image(
        self,
        asset_id: str,
        default_width: int = 400,
        default_height: int = 800,
    ) -> Image.Image:
        """Retrieve pre-multiplied RGBa (or opaque RGBA) image for high-speed resampling."""
        img_pre = self._premultiplied_cache.get(asset_id)
        if img_pre is not None:
            return img_pre
        img = self.get_image(asset_id, default_width, default_height)
        if self.is_asset_opaque(asset_id):
            img_pre = img
        else:
            img_pre = img.convert("RGBa")
        self._premultiplied_cache[asset_id] = img_pre
        return img_pre

    def clear_cache(self) -> None:
        """Clear all cached image textures, opacity flags, and premultiplied versions."""
        self._image_cache.clear()
        self._opaque_cache.clear()
        self._premultiplied_cache.clear()

    def is_asset_opaque(self, asset_id: str) -> bool:
        """Return True if the base asset has no transparent pixels."""
        is_op = self._opaque_cache.get(asset_id)
        if is_op is not None:
            return is_op
        self.get_image(asset_id)
        return self._opaque_cache.get(asset_id, False)

    def _generate_placeholder(
        self,
        asset_id: str,
        width: int,
        height: int,
    ) -> tuple[Image.Image, bool]:
        """Procedurally generate a solid/gradient patterned placeholder texture."""
        is_bg = asset_id.startswith("bg/") or "background" in asset_id
        w = 1920 if is_bg else width
        h = 1080 if is_bg else height

        # Deterministic color derivation from asset_id string hash
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
            base = _resize_opaque(base, (w, h), Image.Resampling.BILINEAR)

        return base, True


class PILRenderer(RenderBackend):
    """Pillow 2D stage renderer implementing RenderBackend protocol with full optimizations."""

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        *,
        mode: str = "RGB",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        window: Any | None = None,
        resampling: Image.Resampling = Image.Resampling.BILINEAR,
        max_cached_sprites: int = 512,
        adaptive_resampling: bool = True,
    ) -> None:
        _check_pil_available()
        self.asset_resolver = PILAssetResolver(asset_dir)
        self.scale_mode = scale_mode
        self.window = window
        self.resampling = resampling
        self.max_cached_sprites = max_cached_sprites
        self.mode = mode
        self.adaptive_resampling = adaptive_resampling

        self.width = window.width if window is not None else width
        self.height = window.height if window is not None else height
        self.clear_color: Color = BLACK
        self._clear_color_bytes: tuple[int, ...] = (
            (0, 0, 0) if self.mode == "RGB" else (0, 0, 0, 255)
        )
        self.frame_count: int = 0
        self.last_frame: list[RenderItem] = []

        self._current_transform: ViewportTransform | None = None
        self._image: Image.Image = Image.new(
            self.mode, (self.width, self.height), self._clear_color_bytes
        )
        self._in_frame: bool = False
        self._frame_buffer: list[RenderItem] = []
        self._needs_clear: bool = False

        # Frame timing clock (ticked in end_frame for FPS reporting)
        self.clock: FrameClock = FrameClock()

        # Optimization Caches
        self._sprite_cache: _ImageLRU = _ImageLRU(
            max_items=self.max_cached_sprites,
            max_bytes=_DEFAULT_CACHE_BYTES,
        )
        self._geom_cache: _ImageLRU = _ImageLRU(
            max_items=self.max_cached_sprites,
            max_bytes=_DEFAULT_CACHE_BYTES,
        )
        self._scaled_cache: _ImageLRU = _ImageLRU(
            max_items=self.max_cached_sprites,
            max_bytes=_DEFAULT_CACHE_BYTES,
        )
        self._ui_image_cache: _ImageLRU = _ImageLRU(
            max_items=self.max_cached_sprites,
            max_bytes=_DEFAULT_CACHE_BYTES,
        )
        self._text_mask_cache: _ImageLRU = _ImageLRU(
            max_items=_MAX_TEXT_CACHE,
            max_bytes=32 * 1024 * 1024,
        )
        self._font_cache: dict[int, ImageFont.ImageFont] = {}
        self._measure_cache: dict[tuple[str, int], tuple[float, float]] = {}
        self._alpha_lut_cache: dict[int, list[int]] = {}
        self._rgba_lut_cache: dict[tuple[int, int, int, int], list[int]] = {}
        self._fade_lut_cache: dict[tuple[Any, ...], list[int]] = {}
        self._mip_cache: dict[tuple[str, int], Image.Image] = {}
        self._gradient_cache: _ImageLRU = _ImageLRU(
            max_items=_MAX_GRADIENT_CACHE,
            max_bytes=64 * 1024 * 1024,
        )
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Compositor stage caching (3-tier hierarchy: Background, Base Scene, Full Stage)
        self._bg_cache: Image.Image | None = None
        self._last_bg_items: list[RenderItem] | None = None
        self._last_bg_transform: ViewportTransform | None = None

        self._base_cache: Image.Image | None = None
        self._last_base_items: list[RenderItem] | None = None
        self._last_base_transform: ViewportTransform | None = None

        self._stage_cache: Image.Image | None = None
        self._last_stage_items: list[RenderItem] | None = None
        self._last_transform: ViewportTransform | None = None

        # Localized UI dirty rect tracking
        self._ui_dirty_bbox: tuple[int, int, int, int] | None = None

        # Adaptive resampling & motion tracking
        self._prev_item_geom: dict[tuple[str, str, int], tuple[float, float, float, float, float]] = {}
        self._curr_item_geom: dict[tuple[str, str, int], tuple[float, float, float, float, float]] = {}
        self._in_motion_assets: set[str] = set()

    def set_window(self, window: Any) -> None:
        """Associate renderer with a player window (any object with .width/.height)."""
        self.window = window
        self.width = window.width
        self.height = window.height
        self._ensure_buffer()

    def _ensure_buffer(self) -> None:
        """Ensure internal Image buffer matches current width and height."""
        if self._image.size != (self.width, self.height) or self._image.mode != self.mode:
            self._image = Image.new(
                self.mode, (self.width, self.height), self._clear_color_bytes
            )
            self._needs_clear = False
            self._bg_cache = None
            self._base_cache = None
            self._stage_cache = None
            self._ui_dirty_bbox = None

    def _snapshot(self, target: Image.Image | None) -> Image.Image:
        """Snapshot current self._image into a pooled/reused target buffer without reallocating."""
        if target is not None and target.size == (self.width, self.height) and target.mode == self.mode:
            target.paste(self._image, (0, 0))
            return target
        return self._image.copy()

    def _mark_ui_dirty(self, left: int, top: int, right: int, bottom: int) -> None:
        """Record modified region bounds from immediate-mode UI operations."""
        l, t = max(0, min(self.width, left)), max(0, min(self.height, top))
        r, b = max(0, min(self.width, right)), max(0, min(self.height, bottom))
        if r <= l or b <= t:
            return
        if self._ui_dirty_bbox is None:
            self._ui_dirty_bbox = (l, t, r, b)
        else:
            bx0, by0, bx1, by1 = self._ui_dirty_bbox
            self._ui_dirty_bbox = (min(bx0, l), min(by0, t), max(bx1, r), max(by1, b))

    def _execute_clear(self) -> None:
        """Perform deferred canvas fill if pending."""
        if self._needs_clear:
            self._image.paste(self._clear_color_bytes, (0, 0, self.width, self.height))
            self._needs_clear = False

    def _frame_bytes_bottom_up(self) -> bytes:
        """Export current frame buffer as bottom-up raw bytes for OpenGL upload."""
        if self._needs_clear:
            self._execute_clear()
        return self._image.tobytes("raw", self.mode, 0, -1)

    def clear_cache(self) -> None:
        """Clear the transformed sprite cache, scaled texture cache, and statistics."""
        self._sprite_cache.clear()
        self._geom_cache.clear()
        self._scaled_cache.clear()
        self._ui_image_cache.clear()
        self._text_mask_cache.clear()
        self._font_cache.clear()
        self._measure_cache.clear()
        self._fade_lut_cache.clear()
        self._mip_cache.clear()
        self._gradient_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._bg_cache = None
        self._last_bg_items = None
        self._last_bg_transform = None
        self._base_cache = None
        self._last_base_items = None
        self._last_base_transform = None
        self._stage_cache = None
        self._last_stage_items = None
        self._last_transform = None
        self._ui_dirty_bbox = None
        self._prev_item_geom.clear()
        self._curr_item_geom.clear()
        self._in_motion_assets.clear()

    def cache_info(self) -> dict[str, Any]:
        """Return diagnostic metrics about cache hits, misses, and current size."""
        total = self._cache_hits + self._cache_misses
        hit_ratio = (self._cache_hits / total) if total > 0 else 0.0
        return {
            "hits": self._cache_hits,
            "misses": self._cache_misses,
            "currsize": len(self._sprite_cache),
            "maxsize": self.max_cached_sprites,
            "hit_ratio": hit_ratio,
        }

    def preload_assets(self, compositor: StageCompositor) -> int:
        """Pre-load all stage assets into the image cache to avoid first-frame spikes.

        Iterates over every element in the compositor's stage and resolves its
        asset through :class:`PILAssetResolver`, which loads from disk (if an
        ``asset_dir`` is configured) or generates a procedural placeholder.
        This moves all disk I/O and mode conversion off the render thread.

        Returns the number of unique assets resolved.
        """
        seen: set[str] = set()
        count = 0
        for layer in compositor.stage.layers.values():
            for elem in layer.elements.values():
                if elem.asset_id in seen:
                    continue
                seen.add(elem.asset_id)
                is_bg = elem.asset_id.startswith("bg/") or "background" in elem.asset_id
                def_w = 1920 if is_bg else 400
                def_h = 1080 if is_bg else 800
                self.asset_resolver.get_image(elem.asset_id, def_w, def_h)
                count += 1
        return count

    def warm_sprite_cache(
        self, compositor: StageCompositor, window_width: int, window_height: int
    ) -> int:
        """Pre-render the current render list to populate the sprite cache.

        Useful to call once at startup (or after a scene change) so that the
        first visible frame doesn't pay the cost of resizing/transforming
        sprites.  The expensive :meth:`_transform_sprite` work is done here
        rather than on the first real render frame.

        The warm-up render does *not* count towards :attr:`frame_count` or
        the FPS clock — it is pure caching overhead.

        Returns the number of sprites that were newly cached (cache misses).
        """
        misses_before = self._cache_misses
        saved_frame_count = self.frame_count
        # render_compositor populates the sprite cache as a side-effect of
        # drawing each item.  The resulting framebuffer is discarded.
        self.render_compositor(compositor, window_width, window_height)
        # Restore frame counter — warm-up render populates caches but should
        # not count as a visible frame (would skew frame_count and FPS).
        self.frame_count = saved_frame_count
        return max(0, self._cache_misses - misses_before)

    def _get_alpha_lut(self, alpha_byte: int) -> list[int]:
        """Retrieve precomputed 256-entry alpha modulation lookup table."""
        return _ALPHA_LUTS[alpha_byte]

    def _get_rgba_lut(self, r: int, g: int, b: int, a: int) -> list[int]:
        """Retrieve precomputed 1024-entry RGBA multiply lookup table."""
        key = (r, g, b, a)
        lut = self._rgba_lut_cache.get(key)
        if lut is not None:
            return lut
        rf, gf, bf, af = r / 255.0, g / 255.0, b / 255.0, a / 255.0
        lut = (
            [round(i * rf) for i in range(256)]
            + [round(i * gf) for i in range(256)]
            + [round(i * bf) for i in range(256)]
            + [round(i * af) for i in range(256)]
        )
        if len(self._rgba_lut_cache) >= _MAX_RGBA_LUTS:
            self._rgba_lut_cache.pop(next(iter(self._rgba_lut_cache)))
        self._rgba_lut_cache[key] = lut
        return lut

    def _put_mip(self, key: tuple[str, int], mip: Image.Image) -> None:
        """Store mip image in cache with eviction limit."""
        if len(self._mip_cache) >= _MAX_MIP_CACHE:
            self._mip_cache.pop(next(iter(self._mip_cache)))
        self._mip_cache[key] = mip

    def begin_frame(self) -> None:
        """Begin a new frame render pass."""
        if self._in_frame:
            msg = "begin_frame called without matching end_frame"
            raise RuntimeError(msg)
        self._frame_buffer = []
        self._in_frame = True
        self._ensure_buffer()

    def clear(self, color: Color = BLACK) -> None:
        """Clear the frame buffer with color using fast direct block fill."""
        self.clear_color = color
        if self.mode == "RGB":
            self._clear_color_bytes = (
                (0, 0, 0)
                if color is BLACK
                else color.to_rgba_bytes()[:3]
            )
        else:
            self._clear_color_bytes = (
                (0, 0, 0, 255)
                if color is BLACK
                else color.to_rgba_bytes()
            )
        self._ensure_buffer()
        self._needs_clear = True

    def draw_item(self, item: RenderItem) -> None:
        """Render a single compositor item."""
        if not self._in_frame:
            msg = "draw_item called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)

        self._frame_buffer.append(item)

        # 1. Early discard: invisible opacity, degenerate scale, or transparent tint
        if item.opacity <= 0.0 or not (item.scale_x and item.scale_y) or item.tint.a <= 0.0:
            return

        transform = self._current_transform
        if transform is None:
            msg = "draw_item called before render_compositor set the viewport transform"
            raise RuntimeError(msg)

        # Resolve base asset
        is_bg = item.layer == "background" or item.asset_id.startswith("bg/")
        def_w = 1920 if is_bg else 400
        def_h = 1080 if is_bg else 800
        base_tex = self.asset_resolver.get_image(item.asset_id, def_w, def_h)

        # 2. Dimensions in virtual coordinates
        eff_w = base_tex.width * abs(item.scale_x)
        eff_h = base_tex.height * abs(item.scale_y)

        # 3. Anchor offset factor
        fx, fy = item.anchor.get_offset_factor()

        # 4. Project dimensions to physical screen coordinates
        draw_w = max(1, round(eff_w * transform.scale_x))
        draw_h = max(1, round(eff_h * transform.scale_y))

        # Anchor screen position (rotation pivot)
        anchor_s_x = transform.offset_x + item.x * transform.scale_x
        anchor_s_y = transform.offset_y + item.y * transform.scale_y

        rot_norm = round(item.rotation % 360.0, 2) if item.rotation != 0.0 else 0.0

        # Early Viewport Frustum Culling
        if rot_norm == 0.0:
            dest_x_approx = round(anchor_s_x - draw_w * fx)
            dest_y_approx = round(anchor_s_y - draw_h * fy)
            if (
                dest_x_approx + draw_w <= 0
                or dest_y_approx + draw_h <= 0
                or dest_x_approx >= self.width
                or dest_y_approx >= self.height
            ):
                return
        else:
            rad = max(draw_w, draw_h)
            if (
                anchor_s_x + rad <= 0
                or anchor_s_y + rad <= 0
                or anchor_s_x - rad >= self.width
                or anchor_s_y - rad >= self.height
            ):
                return

        # Fast tint bytes computation
        t = item.tint
        if t is WHITE or (t.r == 1.0 and t.g == 1.0 and t.b == 1.0 and t.a == 1.0):
            tint_rgba = _WHITE_RGBA
        else:
            tint_rgba = t.to_rgba_bytes()

        final_alpha_f = max(0.0, min(1.0, item.opacity * (tint_rgba[3] / 255.0)))
        final_alpha_byte = round(final_alpha_f * 255)
        color_tint = tint_rgba[:3]

        # Fast path for 1x1 solid color texture (UI blocks, screen fades, flashes)
        if base_tex.size == (1, 1) and rot_norm == 0.0:
            if final_alpha_byte == 0:
                return
            dest_x = round(anchor_s_x - draw_w * fx)
            dest_y = round(anchor_s_y - draw_h * fy)
            px = base_tex.getpixel((0, 0))
            r = round(px[0] * (tint_rgba[0] / 255.0))
            g = round(px[1] * (tint_rgba[1] / 255.0))
            b = round(px[2] * (tint_rgba[2] / 255.0))

            if final_alpha_byte == 255:
                # Opaque shape of any size: bypass Image.new() allocation and use paste(color, box)
                c_fill = (r, g, b) if self.mode == "RGB" else (r, g, b, 255)
                box = (dest_x, dest_y, dest_x + draw_w, dest_y + draw_h)
                if (
                    dest_x <= 0
                    and dest_y <= 0
                    and dest_x + draw_w >= self.width
                    and dest_y + draw_h >= self.height
                ):
                    self._image.paste(c_fill, box)
                    self._needs_clear = False
                else:
                    if self._needs_clear:
                        self._execute_clear()
                    self._image.paste(c_fill, box)
                return

            if (
                dest_x <= 0
                and dest_y <= 0
                and dest_x + draw_w >= self.width
                and dest_y + draw_h >= self.height
            ):
                if self._needs_clear:
                    self._execute_clear()
                lut_key = (r, g, b, final_alpha_byte, self.mode)
                lut = self._fade_lut_cache.get(lut_key)
                if lut is None:
                    inv_a = 255 - final_alpha_byte
                    factor = inv_a / 255.0
                    lut_r = [round(i * factor + r * final_alpha_byte / 255.0) for i in range(256)]
                    lut_g = [round(i * factor + g * final_alpha_byte / 255.0) for i in range(256)]
                    lut_b = [round(i * factor + b * final_alpha_byte / 255.0) for i in range(256)]
                    if self.mode == "RGB":
                        lut = lut_r + lut_g + lut_b
                    else:
                        lut = lut_r + lut_g + lut_b + [255] * 256
                    if len(self._fade_lut_cache) < 256:
                        self._fade_lut_cache[lut_key] = lut
                self._image = self._image.point(lut)
                return

        # 5. Transform Cache Lookup with Quantized Alpha Decoupling
        op_quant = 1.0 if item.opacity == 1.0 else round(item.opacity, 3)
        quant_alpha = _QUANT_ALPHA_LUT[final_alpha_byte]
        cache_key = (
            item.asset_id,
            draw_w,
            draw_h,
            item.flip_h,
            item.flip_v,
            rot_norm,
            quant_alpha,
            color_tint,
            fx,
            fy,
        )

        cached = self._sprite_cache.lookup(cache_key)
        if cached is not None:
            self._cache_hits += 1
            cached_sprite = cached
        else:
            self._cache_misses += 1
            cached_sprite = self._transform_sprite(
                base_tex,
                item,
                draw_w,
                draw_h,
                rot_norm,
                op_quant,
                tint_rgba,
                fx,
                fy,
                quant_alpha=quant_alpha,
            )
            # Modulated fade sprites share geometry color buffer with _geom_cache;
            # charge only the mask size to avoid cache eviction thrashing.
            sprite_bytes = (
                cached_sprite.nbytes
                if final_alpha_byte == 255
                else _image_nbytes(cached_sprite.mask)
            )
            self._sprite_cache.put(cache_key, cached_sprite, sprite_bytes)

        # 6. Final destination coordinates on canvas
        if cached_sprite.color is None:
            return
        dest_x = round(anchor_s_x + cached_sprite.off_x)
        dest_y = round(anchor_s_y + cached_sprite.off_y)
        spr_w, spr_h = cached_sprite.size

        # 7. Viewport Frustum Culling (exact)
        if (
            dest_x + spr_w <= 0
            or dest_y + spr_h <= 0
            or dest_x >= self.width
            or dest_y >= self.height
        ):
            return

        # 8. High-Performance Compositing (paste is faster and auto-clips)
        if cached_sprite.is_opaque:
            if (
                dest_x <= 0
                and dest_y <= 0
                and dest_x + spr_w >= self.width
                and dest_y + spr_h >= self.height
            ):
                self._needs_clear = False
            elif self._needs_clear:
                self._execute_clear()
            self._image.paste(cached_sprite.color, (dest_x, dest_y))
        else:
            if self._needs_clear:
                self._execute_clear()
            patches = cached_sprite.patches
            if patches is not None:
                # Opaque-core + fringe decomposition: the bulk of the sprite is
                # pasted unmasked (no per-pixel blend), the rest exactly as the
                # single masked paste would have been.
                for patch_color, patch_mask, patch_dx, patch_dy in patches:
                    pos = (dest_x + patch_dx, dest_y + patch_dy)
                    if patch_mask is None:
                        self._image.paste(patch_color, pos)
                    else:
                        self._image.paste(patch_color, pos, patch_mask)
                return
            if cached_sprite.mask is not None:
                self._image.paste(cached_sprite.color, (dest_x, dest_y), cached_sprite.mask)
            elif self.mode == "RGBA":
                self._image.alpha_composite(cached_sprite.image, dest=(dest_x, dest_y))
            else:
                self._image.paste(cached_sprite.color, (dest_x, dest_y))

    def _transform_sprite(
        self,
        base_tex: Image.Image,
        item: RenderItem,
        draw_w: int,
        draw_h: int,
        rot_norm: float,
        op_quant: float,
        tint_rgba: tuple[int, int, int, int],
        fx: float,
        fy: float,
        *,
        quant_alpha: int = 255,
    ) -> _CachedSprite:
        """Apply scale, flips, rotation, tint, and opacity to create a ready-to-composite sprite."""
        # Fast-path for 1x1 solid color texture (e.g. __builtin_color_rect__ for flash/fades)
        if base_tex.size == (1, 1) and rot_norm == 0.0:
            px = base_tex.getpixel((0, 0))
            final_alpha_f = max(0.0, min(1.0, op_quant * (tint_rgba[3] / 255.0)))
            final_alpha_byte = round(final_alpha_f * 255)
            r = round(px[0] * (tint_rgba[0] / 255.0))
            g = round(px[1] * (tint_rgba[1] / 255.0))
            b = round(px[2] * (tint_rgba[2] / 255.0))
            is_opaque = (final_alpha_byte == 255)
            c_fill = (r, g, b) if self.mode == "RGB" else (r, g, b, 255)
            color = Image.new(self.mode, (draw_w, draw_h), c_fill)
            mask = None if is_opaque else Image.new("L", (draw_w, draw_h), final_alpha_byte)
            return _CachedSprite(color, mask, -(draw_w * fx), -(draw_h * fy))

        color_tint = tint_rgba[:3]
        geom_key = (
            item.asset_id,
            draw_w,
            draw_h,
            item.flip_h,
            item.flip_v,
            rot_norm,
            color_tint,
            fx,
            fy,
        )

        # Adaptive resampling: use lower-cost NEAREST filter while actively tweening
        is_in_motion = self.adaptive_resampling and (item.asset_id in self._in_motion_assets)
        cur_resample = Image.Resampling.NEAREST if is_in_motion else self.resampling

        geom = self._geom_cache.lookup(geom_key)
        if geom is not None and not is_in_motion:
            pass
        else:
            base_is_opaque = self.asset_resolver.is_asset_opaque(item.asset_id)
            img = base_tex
            shared_img = True

            # A. Scale
            if (img.width, img.height) != (draw_w, draw_h):
                scale_key = (item.asset_id, draw_w, draw_h)
                scaled = self._scaled_cache.lookup(scale_key) if not is_in_motion else None
                if scaled is not None:
                    img = scaled
                    shared_img = True
                else:
                    if base_is_opaque:
                        factor = min(base_tex.width // draw_w, base_tex.height // draw_h)
                        if factor >= 2 and cur_resample != Image.Resampling.NEAREST:
                            k = 1 << ((factor).bit_length() - 1)
                            mip_key = (item.asset_id, k)
                            mip = self._mip_cache.get(mip_key)
                            if mip is None:
                                mip = base_tex.reduce(k)
                                self._put_mip(mip_key, mip)
                            img = _resize_opaque(mip, (draw_w, draw_h), resample=cur_resample)
                        else:
                            img = _resize_opaque(base_tex, (draw_w, draw_h), resample=cur_resample)
                    else:
                        def_w = 1920 if item.layer == "background" or item.asset_id.startswith("bg/") else 400
                        def_h = 1080 if item.layer == "background" or item.asset_id.startswith("bg/") else 800
                        base_pre = self.asset_resolver.get_premultiplied_image(item.asset_id, def_w, def_h)
                        factor = min(base_pre.width // draw_w, base_pre.height // draw_h)
                        if factor >= 2 and cur_resample != Image.Resampling.NEAREST:
                            k = 1 << ((factor).bit_length() - 1)
                            mip_key = (item.asset_id, k)
                            mip = self._mip_cache.get(mip_key)
                            if mip is None:
                                mip = base_pre.reduce(k)
                                self._put_mip(mip_key, mip)
                            img = mip.resize((draw_w, draw_h), resample=cur_resample).convert("RGBA")
                        else:
                            img = base_pre.resize((draw_w, draw_h), resample=cur_resample).convert("RGBA")
                    if not is_in_motion:
                        self._scaled_cache.put(scale_key, img, _image_nbytes(img))
                    shared_img = True

            # B. Flips
            if item.flip_h and item.flip_v:
                img = img.transpose(Image.Transpose.ROTATE_180)
                shared_img = False
            elif item.flip_h:
                img = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                shared_img = False
            elif item.flip_v:
                img = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                shared_img = False

            # C. Rotation around anchor point
            is_ortho = False
            if abs(rot_norm) < 1e-3:
                off_x = -(draw_w * fx)
                off_y = -(draw_h * fy)
                is_ortho = True
            else:
                rel_anchor_x = draw_w * (fx - 0.5)
                rel_anchor_y = draw_h * (fy - 0.5)
                vx = -rel_anchor_x
                vy = -rel_anchor_y

                if abs(rot_norm - 90.0) < 1e-3:
                    img = img.transpose(Image.Transpose.ROTATE_270)
                    shared_img = False
                    new_vx = -vy
                    new_vy = vx
                    is_ortho = True
                elif abs(rot_norm - 180.0) < 1e-3:
                    img = img.transpose(Image.Transpose.ROTATE_180)
                    shared_img = False
                    new_vx = -vx
                    new_vy = -vy
                    is_ortho = True
                elif abs(rot_norm - 270.0) < 1e-3:
                    img = img.transpose(Image.Transpose.ROTATE_90)
                    shared_img = False
                    new_vx = vy
                    new_vy = -vx
                    is_ortho = True
                else:
                    img = img.rotate(-rot_norm, resample=cur_resample, expand=True)
                    shared_img = False
                    rad = math.radians(rot_norm)
                    cos_t = math.cos(rad)
                    sin_t = math.sin(rad)
                    new_vx = vx * cos_t - vy * sin_t
                    new_vy = vx * sin_t + vy * cos_t

                rot_w, rot_h = img.size
                off_x = new_vx - (rot_w / 2.0)
                off_y = new_vy - (rot_h / 2.0)

                if not is_ortho:
                    bbox = _alpha_bbox(img)
                    if bbox is not None and bbox != (0, 0, rot_w, rot_h):
                        img = img.crop(bbox)
                        off_x += bbox[0]
                        off_y += bbox[1]
                    elif bbox is None:
                        return _CachedSprite(None, None, off_x, off_y)

            # D. Color tint
            if color_tint != (255, 255, 255):
                lut = self._get_rgba_lut(color_tint[0], color_tint[1], color_tint[2], 255)
                img = img.point(lut)
                shared_img = False

            # D2. Tighten to the non-transparent region.
            #
            # ``paste(color, box, mask)`` blends *every* pixel in the sprite's
            # bounding box, including fully-transparent margins.  Cropping an
            # axis-aligned masked sprite to its alpha bounding box shrinks the
            # per-frame blend area (and the cached geometry) for free.  Rotated
            # sprites are already tightened above; opaque sprites keep their
            # full frame so the "background replaces the canvas" fast path
            # still applies.
            if is_ortho and not base_is_opaque:
                bbox = _alpha_bbox(img)
                if bbox is None:
                    return _CachedSprite(None, None, off_x, off_y)
                if bbox != (0, 0, img.width, img.height):
                    img = img.crop(bbox)
                    off_x += bbox[0]
                    off_y += bbox[1]
                    # ``img`` is now a private crop, so splitting can mutate it.
                    shared_img = False

            # E. Split into color + mask
            if base_is_opaque and is_ortho:
                geom_color = img
                natural_mask = None
            else:
                geom_color, natural_mask = _split_rgba(img, shared=shared_img)

            # The opaque-core decomposition costs a one-off search, so only build
            # it for geometry that gets cached.  In-motion sprites rebuild their
            # transform every frame; the search would then run per frame and cost
            # more than it saves, so they stay on the plain masked path.
            patches = (
                _split_patches(geom_color, natural_mask)
                if natural_mask is not None and not is_in_motion
                else None
            )
            geom = _GeomEntry(geom_color, natural_mask, off_x, off_y, patches)
            if not is_in_motion:
                self._geom_cache.put(geom_key, geom, geom.nbytes)

        # F. Opacity Modulation with cached mask reuse
        final_alpha_f = max(0.0, min(1.0, op_quant * (tint_rgba[3] / 255.0)))
        final_alpha_byte = round(final_alpha_f * 255)

        if final_alpha_byte == 255:
            # Full opacity: reuse the natural mask verbatim, along with the
            # opaque-core decomposition when one was prepared for this geometry.
            return _CachedSprite(
                geom.color, geom.natural_mask, geom.off_x, geom.off_y, geom.patches
            )
        else:
            effective_alpha = quant_alpha if quant_alpha is not None else round(final_alpha_f * 255)
            mask = geom.alpha_masks.get(effective_alpha)
            if mask is None:
                if geom.natural_mask is None:
                    mask = Image.new("L", geom.color.size, effective_alpha)
                else:
                    mask = geom.natural_mask.point(_ALPHA_LUTS[effective_alpha])
                if len(geom.alpha_masks) >= 64:
                    geom.alpha_masks.pop(next(iter(geom.alpha_masks)))
                geom.alpha_masks[effective_alpha] = mask

        return _CachedSprite(geom.color, mask, geom.off_x, geom.off_y)

    def end_frame(self) -> None:
        """Conclude frame render pass, applying letterbox bars if necessary."""
        if not self._in_frame:
            msg = "end_frame called without matching begin_frame"
            raise RuntimeError(msg)

        if self._needs_clear:
            self._execute_clear()

        trans = self._current_transform
        if trans is not None:
            win_w, win_h = self.width, self.height
            bar_color = (0, 0, 0) if self.mode == "RGB" else (0, 0, 0, 255)
            if trans.offset_x > 0:
                ox = int(trans.offset_x)
                self._image.paste(bar_color, (0, 0, ox, win_h))
                self._image.paste(bar_color, (win_w - ox, 0, win_w, win_h))

            if trans.offset_y > 0:
                oy = int(trans.offset_y)
                self._image.paste(bar_color, (0, 0, win_w, oy))
                self._image.paste(bar_color, (0, win_h - oy, win_w, win_h))

        self.last_frame = self._frame_buffer
        self._frame_buffer = []
        self._in_frame = False
        self._prev_item_geom = self._curr_item_geom
        self.frame_count += 1
        self.clock.tick()

    # ------------------------------------------------------------------ #
    # FPS properties (delegate to the FrameClock for a uniform API)
    # ------------------------------------------------------------------ #

    @property
    def fps(self) -> float:
        """Instantaneous frames-per-second (1 / last frame interval)."""
        return self.clock.fps

    @property
    def fps_avg(self) -> float:
        """Rolling-average FPS over the last 60 rendered frames."""
        return self.clock.fps_avg

    @property
    def fps_overall(self) -> float:
        """Average FPS across all frames rendered since the renderer was created."""
        return self.clock.fps_overall

    def render_compositor(
        self,
        compositor: StageCompositor,
        window_width: int,
        window_height: int,
    ) -> Image.Image:
        """Render all active compositor layers to the window/buffer."""
        self.width = window_width
        self.height = window_height
        self._current_transform = compositor.layout.compute_viewport_transform(
            window_width,
            window_height,
            mode=self.scale_mode,
        )

        items = compositor.render_list()

        # Fast-path (Tier 3): Check if full stage is identical to previous frame
        if (
            self._stage_cache is not None
            and self._last_stage_items is not None
            and len(self._last_stage_items) == len(items)
            and self._last_stage_items == items
            and self._last_transform == self._current_transform
            and self._stage_cache.size == (window_width, window_height)
        ):
            self.last_frame = items
            self.frame_count += 1
            self.clock.tick()
            self._in_motion_assets = set()
            if self._ui_dirty_bbox is not None:
                # Localized dirty subregion restore from clean stage cache
                x0, y0, x1, y1 = self._ui_dirty_bbox
                w_box, h_box = x1 - x0, y1 - y0
                if w_box > 0 and h_box > 0 and (w_box * h_box < 0.8 * window_width * window_height):
                    crop = self._stage_cache.crop(self._ui_dirty_bbox)
                    self._image.paste(crop, (x0, y0))
                else:
                    self._image.paste(self._stage_cache, (0, 0))
                self._ui_dirty_bbox = None
            else:
                self._image.paste(self._stage_cache, (0, 0))
            return self._image

        # Temporal filter adaptation: detect which items are actively moving/tweening
        if self.adaptive_resampling:
            curr_geom: dict[tuple[str, str, int], tuple[float, float, float, float, float]] = {}
            in_motion: set[str] = set()
            for it in items:
                k = (it.layer, it.asset_id, it.z_order)
                g = (
                    it.x,
                    it.y,
                    it.scale_x,
                    it.scale_y,
                    it.rotation,
                )
                curr_geom[k] = g
                prev = self._prev_item_geom.get(k)
                if prev is not None and prev != g:
                    in_motion.add(it.asset_id)
            self._curr_item_geom = curr_geom
            self._in_motion_assets = in_motion
        else:
            self._curr_item_geom = {}
            self._in_motion_assets = set()

        # Separate items into 3 composition tiers: Background, Actors, Overlay
        bg_items: list[RenderItem] = []
        actor_items: list[RenderItem] = []
        overlay_items: list[RenderItem] = []

        for it in items:
            if it.layer == "background":
                bg_items.append(it)
            elif it.layer == "overlay":
                overlay_items.append(it)
            else:
                actor_items.append(it)

        base_items = bg_items + actor_items

        # Tier 2: Check if base items (background + actors) are identical
        can_use_base_cache = (
            bool(overlay_items)
            and self._base_cache is not None
            and self._last_base_items is not None
            and len(self._last_base_items) == len(base_items)
            and self._last_base_items == base_items
            and self._last_base_transform == self._current_transform
            and self._base_cache.size == (window_width, window_height)
        )

        # Tier 1: Check if background items are identical
        can_use_bg_cache = (
            bool(bg_items)
            and self._bg_cache is not None
            and self._last_bg_items is not None
            and len(self._last_bg_items) == len(bg_items)
            and self._last_bg_items == bg_items
            and self._last_bg_transform == self._current_transform
            and self._bg_cache.size == (window_width, window_height)
        )

        self.begin_frame()
        if can_use_base_cache:
            self._image.paste(self._base_cache, (0, 0))
            self._needs_clear = False
            self._frame_buffer.extend(base_items)
            for item in overlay_items:
                self.draw_item(item)
        elif can_use_bg_cache:
            self._image.paste(self._bg_cache, (0, 0))
            self._needs_clear = False
            self._frame_buffer.extend(bg_items)
            for item in actor_items:
                self.draw_item(item)

            if overlay_items:
                self._base_cache = self._snapshot(self._base_cache)
                self._last_base_items = list(base_items)
                self._last_base_transform = self._current_transform
            else:
                self._base_cache = None
                self._last_base_items = None
                self._last_base_transform = None

            for item in overlay_items:
                self.draw_item(item)
        else:
            self.clear(BLACK)

            skip_count = 0
            if (
                len(bg_items) >= 2
                and bg_items[0].layer == "background"
                and bg_items[1].layer == "background"
                and bg_items[0].rotation == 0.0
                and bg_items[1].rotation == 0.0
                and bg_items[0].x == 0.0
                and bg_items[0].y == 0.0
                and bg_items[1].x == 0.0
                and bg_items[1].y == 0.0
                and not (bg_items[0].flip_h or bg_items[0].flip_v or bg_items[1].flip_h or bg_items[1].flip_v)
                and (bg_items[0].tint is WHITE or bg_items[0].tint == WHITE)
                and (bg_items[1].tint is WHITE or bg_items[1].tint == WHITE)
                and self.asset_resolver.is_asset_opaque(bg_items[0].asset_id)
                and self.asset_resolver.is_asset_opaque(bg_items[1].asset_id)
                and bg_items[0].opacity > 0.0
                and bg_items[1].opacity > 0.0
                and bg_items[0].anchor == bg_items[1].anchor
                and bg_items[0].scale_x == bg_items[1].scale_x
                and bg_items[0].scale_y == bg_items[1].scale_y
            ):
                trans = self._current_transform
                if trans is not None:
                    base0 = self.asset_resolver.get_image(bg_items[0].asset_id)
                    base1 = self.asset_resolver.get_image(bg_items[1].asset_id)
                    if base0.size == base1.size:
                        fx, fy = bg_items[0].anchor.get_offset_factor()
                        eff_w = base0.width * abs(bg_items[0].scale_x)
                        eff_h = base0.height * abs(bg_items[0].scale_y)
                        draw_w = max(1, round(eff_w * trans.scale_x))
                        draw_h = max(1, round(eff_h * trans.scale_y))
                        dest_x = round(trans.offset_x - draw_w * fx)
                        dest_y = round(trans.offset_y - draw_h * fy)

                        scale_key0 = (bg_items[0].asset_id, draw_w, draw_h)
                        tex0 = self._scaled_cache.lookup(scale_key0)
                        if tex0 is None:
                            tex0 = (
                                _resize_opaque(base0, (draw_w, draw_h), resample=self.resampling)
                                if base0.size != (draw_w, draw_h)
                                else base0
                            )
                            self._scaled_cache.put(scale_key0, tex0, _image_nbytes(tex0))

                        scale_key1 = (bg_items[1].asset_id, draw_w, draw_h)
                        tex1 = self._scaled_cache.lookup(scale_key1)
                        if tex1 is None:
                            tex1 = (
                                _resize_opaque(base1, (draw_w, draw_h), resample=self.resampling)
                                if base1.size != (draw_w, draw_h)
                                else base1
                            )
                            self._scaled_cache.put(scale_key1, tex1, _image_nbytes(tex1))

                        total_op = bg_items[0].opacity + bg_items[1].opacity
                        blend_alpha = (
                            min(1.0, max(0.0, bg_items[1].opacity / total_op))
                            if total_op > 0.0
                            else 0.5
                        )
                        blended = Image.blend(tex0, tex1, blend_alpha)
                        if self.mode == "RGB" and blended.mode == "RGBA":
                            blended = blended.convert("RGB")
                        if (
                            dest_x <= 0
                            and dest_y <= 0
                            and dest_x + draw_w >= self.width
                            and dest_y + draw_h >= self.height
                        ):
                            self._needs_clear = False
                            if dest_x == 0 and dest_y == 0 and draw_w == self.width and draw_h == self.height:
                                self._image = blended
                            else:
                                self._image.paste(blended, (dest_x, dest_y))
                        else:
                            if self._needs_clear:
                                self._execute_clear()
                            self._image.paste(blended, (dest_x, dest_y))
                        self._frame_buffer.extend(bg_items[:2])
                        skip_count = 2

            for item in bg_items[skip_count:]:
                self.draw_item(item)

            # Snapshot Tier 1 background cache if background items exist
            if bg_items:
                self._bg_cache = self._image.copy()
                self._last_bg_items = list(bg_items)
                self._last_bg_transform = self._current_transform
            else:
                self._bg_cache = None
                self._last_bg_items = None
                self._last_bg_transform = None

            for item in actor_items:
                self.draw_item(item)

            # Snapshot Tier 2 base scene cache if overlay items are present
            if overlay_items:
                self._base_cache = self._snapshot(self._base_cache)
                self._last_base_items = list(base_items)
                self._last_base_transform = self._current_transform
            else:
                self._base_cache = None
                self._last_base_items = None
                self._last_base_transform = None

            for item in overlay_items:
                self.draw_item(item)

        self.end_frame()

        # Snapshot clean stage buffer for static scene caching (Tier 3).
        if (
            self._last_stage_items is not None
            and len(self._last_stage_items) == len(items)
            and self._last_stage_items == items
        ) or self._stage_cache is None:
            self._stage_cache = self._snapshot(self._stage_cache)
        else:
            self._stage_cache = None
        self._last_stage_items = items
        self._last_transform = self._current_transform
        self._ui_dirty_bbox = None

        return self._image

    def get_image(self, copy: bool = False) -> Image.Image:
        """Return the current rendered frame buffer."""
        if self._needs_clear:
            self._execute_clear()
        return self._image.copy() if copy else self._image

    @property
    def image(self) -> Image.Image:
        """Convenience property returning the current image buffer."""
        if self._needs_clear:
            self._execute_clear()
        return self._image

    def save_frame(self, path: str | Path, format: str | None = None, **kwargs: Any) -> None:
        """Save the current frame buffer to an image file."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        img = self._image
        if format and format.upper() in ("JPEG", "JPG"):
            img = img.convert("RGB")
        img.save(str(target), format=format, **kwargs)

    def to_bytes(self, format: str = "PNG", **kwargs: Any) -> bytes:
        """Export current frame buffer as formatted image bytes in memory."""
        import io

        buf = io.BytesIO()
        img = self._image
        if format.upper() in ("JPEG", "JPG"):
            img = img.convert("RGB")
        img.save(buf, format=format, **kwargs)
        return buf.getvalue()

    # ------------------------------------------------------------------ #
    # UIDrawBackend primitives
    #
    # Immediate-mode primitives consumed by the renderer-agnostic components
    # in eager_graphics.ui_components.  Coordinates arrive in window pixels
    # with a top-left origin, which is already PIL's native convention.
    # ------------------------------------------------------------------ #

    def _ui_font(self, font_size: int) -> ImageFont.ImageFont:
        """Return a bitmap font at *font_size*, cached and tolerating older Pillow."""
        font = self._font_cache.get(font_size)
        if font is not None:
            return font
        try:
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            font = ImageFont.load_default()
        self._font_cache[font_size] = font
        return font

    def draw_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: Color,
        *,
        border_color: Color | None = None,
        border_width: float = 0.0,
    ) -> None:
        """Fill a rectangle on the frame buffer, optionally stroking a border."""
        if self._needs_clear:
            self._execute_clear()
        left, top = float(x), float(y)
        right, bottom = left + float(width), top + float(height)
        self._mark_ui_dirty(round(left), round(top), round(right + 1), round(bottom + 1))
        c_rgba = color.to_rgba_bytes()
        c_bytes = c_rgba[:3] if self.mode == "RGB" else c_rgba
        if border_color is None or border_width <= 0.0:
            self._image.paste(c_bytes, (round(left), round(top), round(right), round(bottom)))
        else:
            bw = round(border_width)
            r_left, r_top = round(left), round(top)
            r_right, r_bottom = round(right), round(bottom)
            if bw > 0 and (r_right - r_left) > 2 * bw and (r_bottom - r_top) > 2 * bw:
                b_rgba = (
                    _WHITE_RGBA
                    if (border_color is WHITE or border_color == WHITE)
                    else border_color.to_rgba_bytes()
                )
                b_bytes = b_rgba[:3] if self.mode == "RGB" else b_rgba
                self._image.paste(b_bytes, (r_left, r_top, r_right + 1, r_bottom + 1))
                self._image.paste(c_bytes, (r_left + bw, r_top + bw, r_right - bw + 1, r_bottom - bw + 1))
            else:
                draw = ImageDraw.Draw(self._image)
                draw.rectangle((left, top, right, bottom), fill=c_bytes)
                b_rgba = border_color.to_rgba_bytes()
                draw.rectangle(
                    (left, top, right, bottom),
                    outline=b_rgba[:3] if self.mode == "RGB" else b_rgba,
                    width=bw,
                )

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        """Fill a rectangle with a vertical linear gradient from top_color to bottom_color."""
        if self._needs_clear:
            self._execute_clear()
        w = max(1, round(width))
        h = max(2, round(height))
        left = round(x)
        top = round(y)
        self._mark_ui_dirty(left, top, left + w + 1, top + h + 1)

        tc = top_color.to_rgba_bytes()
        bc = bottom_color.to_rgba_bytes()
        cache_key = (w, h, tc, bc, self.mode)
        entry = self._gradient_cache.lookup(cache_key)

        if entry is None:
            # Generate and scale gradient once
            grad = Image.new("RGBA", (1, h))
            pixels = [
                tuple(int(tc[i] + (bc[i] - tc[i]) * y_step / (h - 1)) for i in range(4))
                for y_step in range(h)
            ]
            grad.putdata(pixels)
            grad_resized = grad.resize((w, h), Image.Resampling.BILINEAR)

            if self.mode == "RGBA":
                color_plane = grad_resized
                mask_plane = None
                nbytes = _image_nbytes(grad_resized)
            else:
                color_plane = grad_resized.convert("RGB")
                # A fully opaque ramp needs no mask; pasting the colour plane
                # directly is ~10x faster than a masked blend.
                if tc[3] == 255 and bc[3] == 255:
                    mask_plane = None
                    nbytes = _image_nbytes(color_plane)
                else:
                    mask_plane = grad_resized.getchannel("A")
                    nbytes = _image_nbytes(color_plane) + _image_nbytes(mask_plane)

            entry = (color_plane, mask_plane)
            self._gradient_cache.put(cache_key, entry, nbytes)

        color_plane, mask_plane = entry
        if self.mode == "RGBA":
            self._image.alpha_composite(color_plane, (left, top))
        elif mask_plane is not None:
            self._image.paste(color_plane, (left, top), mask_plane)
        else:
            self._image.paste(color_plane, (left, top))

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: int = 14,
        color: Color = WHITE,
        bold: bool = False,
        italic: bool = False,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        """Draw a single line of text, honouring the requested anchor point."""
        if not text:
            return
        if self._needs_clear:
            self._execute_clear()

        pil_anchor_x = _PIL_ANCHOR_X.get(anchor_x, "l")
        pil_anchor_y = _PIL_ANCHOR_Y.get(anchor_y, "t")
        anchor = f"{pil_anchor_x}{pil_anchor_y}"

        cache_key = (text, font_size, anchor, bold, italic)
        cached = self._text_mask_cache.lookup(cache_key)
        if cached is None:
            font = self._ui_font(font_size)
            try:
                stroke_w = 1 if bold else 0
                l, t, r, b = font.getbbox(text, anchor=anchor, stroke_width=stroke_w)
                w, h = r - l, b - t
                if w > 0 and h > 0:
                    mask = Image.new("L", (w, h), 0)
                    ImageDraw.Draw(mask).text(
                        (-l, -t), text, font=font, fill=255, anchor=anchor, stroke_width=stroke_w
                    )
                    cached = (mask, l, t)
                else:
                    cached = (None, 0, 0)
            except (AttributeError, ValueError, TypeError):
                try:
                    l, t, r, b = font.getbbox(text, anchor=anchor)
                    w, h = r - l, b - t
                    if w > 0 and h > 0:
                        mask = Image.new("L", (w, h), 0)
                        ImageDraw.Draw(mask).text((-l, -t), text, font=font, fill=255, anchor=anchor)
                        cached = (mask, l, t)
                    else:
                        cached = (None, 0, 0)
                except (AttributeError, ValueError, TypeError):
                    cached = (None, 0, 0)
            self._text_mask_cache.put(
                cache_key,
                cached,
                _image_nbytes(cached[0]) if cached[0] is not None else 0,
            )

        color_rgba = (
            _WHITE_RGBA
            if (color is WHITE or color == WHITE)
            else color.to_rgba_bytes()
        )
        color_bytes = color_rgba[:3] if self.mode == "RGB" else color_rgba
        mask, rel_x, rel_y = cached
        if mask is not None:
            dest_x = round(x + rel_x)
            dest_y = round(y + rel_y)
            self._mark_ui_dirty(dest_x, dest_y, dest_x + mask.width, dest_y + mask.height)
            self._image.paste(color_bytes, (dest_x, dest_y), mask)
        else:
            w_est, h_est = self.measure_text(text, font_size=font_size)
            self._mark_ui_dirty(round(x), round(y), round(x + w_est), round(y + h_est))
            draw = ImageDraw.Draw(self._image)
            draw.text(
                (float(x), float(y)),
                text,
                font=self._ui_font(font_size),
                fill=color_bytes,
                anchor=anchor,
            )

    def draw_image(
        self,
        asset_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        tint: Color = WHITE,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        """Blit a resolved asset into the frame buffer, scaled and tinted."""
        if self._needs_clear:
            self._execute_clear()
        source = self.asset_resolver.get_image(asset_id)
        if source is None:
            return

        target_w = max(1, round(width))
        target_h = max(1, round(height))
        t_rgba = _WHITE_RGBA if (tint is WHITE or tint == WHITE) else tint.to_rgba_bytes()
        cache_key = (asset_id, target_w, target_h, t_rgba)

        cached_sprite = self._ui_image_cache.lookup(cache_key)
        if cached_sprite is not None:
            sprite = cached_sprite
        else:
            img = source
            if img.size != (target_w, target_h):
                img = img.resize((target_w, target_h), resample=self.resampling)
            if tint != WHITE:
                img = self._apply_tint_to_image(img, tint)
            color, mask = _split_rgba(img, shared=False)
            sprite = _CachedSprite(color, mask, 0.0, 0.0)
            self._ui_image_cache.put(cache_key, sprite, sprite.nbytes)

        left = float(x)
        top = float(y)
        if anchor_x == "center":
            left -= target_w / 2.0
        elif anchor_x == "right":
            left -= target_w
        if anchor_y == "middle":
            top -= target_h / 2.0
        elif anchor_y == "bottom":
            top -= target_h

        dest_x = round(left)
        dest_y = round(top)
        self._mark_ui_dirty(dest_x, dest_y, dest_x + target_w, dest_y + target_h)
        if sprite.is_opaque:
            self._image.paste(sprite.color, (dest_x, dest_y))
        elif sprite.mask is not None:
            self._image.paste(sprite.color, (dest_x, dest_y), sprite.mask)
        elif self.mode == "RGBA":
            self._image.alpha_composite(sprite.image, dest=(dest_x, dest_y))
        else:
            self._image.paste(sprite.color, (dest_x, dest_y))

    def _apply_tint_to_image(self, image: Image.Image, tint: Color) -> Image.Image:
        """Return *image* with *tint* multiplied into its colour channels."""
        r, g, b, a = tint.to_rgba_bytes()
        lut = self._get_rgba_lut(r, g, b, a)
        return image.convert("RGBA").point(lut)

    def measure_text(
        self,
        text: str,
        *,
        font_size: int = 14,
        bold: bool = False,
        italic: bool = False,
    ) -> tuple[float, float]:
        """Measure the pixel extents *text* would occupy at *font_size*."""
        cache_key = (
            (text, font_size)
            if not bold and not italic
            else (text, font_size, bold, italic)
        )
        cached = self._measure_cache.get(cache_key)
        if cached is not None:
            return cached

        font = self._ui_font(font_size)
        stroke_w = 1 if bold else 0
        try:
            left, top, right, bottom = font.getbbox(text, stroke_width=stroke_w)
            result = (float(right - left), float(bottom - top))
        except (AttributeError, ValueError, TypeError):
            try:
                draw = ImageDraw.Draw(self._image)
                left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
                result = (float(right - left), float(bottom - top))
            except (AttributeError, ValueError, TypeError):
                result = (float(font_size) * 0.5 * len(text), float(font_size) * 1.2)

        if len(self._measure_cache) < 2048:
            self._measure_cache[cache_key] = result
        return result

    def __len__(self) -> int:
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"PILRenderer(width={self.width}, height={self.height}, "
            f"frame_count={self.frame_count}, last_frame_items={len(self.last_frame)}, "
            f"fps={self.fps:.1f})"
        )


if PIL_AVAILABLE:

    class PILPlayer:
        """Thin interactive window shell driving a :class:`GameSession` with Pillow frames.

        The player owns no narrative state: all story advancement, branching,
        rollback, typewriter reveal, and input semantics live in the injected
        :class:`~eager_runtime.session.GameSession`.  Window events are forwarded
        to ``session.handle_input(...)`` and frames are produced by
        ``session.draw(...)``.  Only Pillow is required to construct and drive
        the player headless; the tkinter window is created lazily by :meth:`run`,
        so only entering the event loop needs Tk bindings.
        """

        def __init__(
            self,
            *,
            session: Any,
            width: int = 1280,
            height: int = 720,
            title: str = "Eager-Graphics Visual Novel (PIL)",
            asset_dir: str | Path | None = None,
            scale_mode: ScaleMode = ScaleMode.LETTERBOX,
            vsync: bool = True,
            visible: bool = True,
            show_fps: bool = True,
            uncapped: bool = False,
        ) -> None:
            if uncapped:
                vsync = False
            self.uncapped: bool = uncapped
            self.vsync: bool = vsync
            self.visible: bool = visible
            self.title: str = title
            self.width: int = width
            self.height: int = height

            self.session = session
            self.vm = session.vm
            self.compositor = session.compositor
            self.director = session.director
            self.dispatcher = session.dispatcher
            self.audio = getattr(session, "audio", None)
            self.keymap = getattr(session, "keymap", None) or Keymap()
            self.overlay = getattr(session, "overlay", None) or UIOverlay(width=width, height=height)

            self.renderer = PILRenderer(
                width=width,
                height=height,
                asset_dir=asset_dir,
                scale_mode=scale_mode,
            )

            # On-screen FPS debug overlay (a tkinter label managed in run()).
            self.show_fps: bool = show_fps
            self._fps_widget: Any = None

            self._photo: Any = None
            self._ui_dirty: bool = True

            # Narrative UI State
            self.current_speaker: str | None = None
            self.current_text: str = ""
            self.current_emotion: str | None = None
            self.active_choice_prompt: ChoicePromptEvent | None = None
            self.is_finished: bool = False
            self._last_visible_chars: int | None = None

            # tkinter window objects — created lazily by run() so that
            # construction and story logic stay headless-safe.
            self._root: Any = None
            self._label: Any = None
            self._closed: bool = False
            self._last_tick: float = 0.0

            # Enable visual history rollback on director
            self.director.enable_visual_history()

            # Step first beat if not starting in active menu
            has_active_screen = getattr(getattr(self.session, "screens", None), "is_active", False)
            if not has_active_screen:
                self.advance_story()

            # Pre-load all assets and warm the sprite cache so the first
            # visible frame doesn't pay disk-I/O + resize costs (which would
            # cause a visible frame drop / hitch).
            self.renderer.preload_assets(self.compositor)
            self.renderer.warm_sprite_cache(
                self.compositor, self.width, self.height
            )

        def _sync_overlay(self) -> None:
            """Mirror current narrative state onto the UI components.

            Called whenever the active choice prompt or dialogue changes so that
            input handling sees up-to-date layout even before the next draw.
            """
            self.current_speaker = self.director.ui_state.speaker
            self.current_text = self.director.ui_state.text
            self.current_emotion = self.director.ui_state.emotion
            self.overlay.sync(self.director.ui_state, self.active_choice_prompt)

        def advance_story(self) -> None:
            """Advance the story by forwarding to the owning :class:`GameSession`."""
            self._ui_dirty = True
            self.session.advance()
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()

        def make_choice(self, choice_index: int) -> None:
            """Select a branching choice option and continue execution."""
            self._ui_dirty = True
            self.session.choose(choice_index)
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()

        def rollback(self) -> bool:
            """Rollback narrative and stage state by one beat."""
            self._ui_dirty = True
            success = self.session.rollback()
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()
            return success

        def tick(self, dt: float) -> None:
            """Advance compositor animations, audio, and session logic by dt."""
            self.session.update(dt)
            if getattr(self.session, "_ui_dirty", False):
                self._ui_dirty = True
                self.session._ui_dirty = False
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            if self.session.text_reveal is not None and not self.session.text_reveal.is_complete:
                self._ui_dirty = True
            cur_vc = self.director.ui_state.visible_chars
            if cur_vc != self._last_visible_chars:
                self._last_visible_chars = cur_vc
                self._ui_dirty = True

        def hot_reload(self) -> bool:
            """Hot-reload screenplay from disk, hot-swap VM, reconcile state, and force a redraw."""
            result = self.session.hot_reload()
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()
            self._ui_dirty = True
            return result

        def on_draw(self) -> None:
            """Render frame: stage graphics followed by UI textbox and choices."""
            # Fast-path for completely static frames (idle scene & UI):
            # skip re-rendering and re-present the cached frame.
            stage_items = self.compositor.render_list()
            is_stage_static = (
                self.renderer._stage_cache is not None
                and self.renderer._last_stage_items == stage_items
                and self.renderer._last_transform == self.renderer._current_transform
                and self.renderer._stage_cache.size == (self.width, self.height)
            )
            is_text_revealing = bool(
                self.session.text_reveal is not None
                and not self.session.text_reveal.is_complete
            )
            is_screen_active = bool(
                getattr(getattr(self.session, "screens", None), "is_active", False)
            )

            if (
                is_stage_static
                and not self._ui_dirty
                and not is_text_revealing
                and not is_screen_active
                and self._photo is not None
            ):
                self.renderer.frame_count += 1
                self.renderer.clock.tick()
                self._present_cached()
                self._draw_fps()
                return

            self.session.draw(self.renderer, self.width, self.height)
            self._ui_dirty = False

            # Present the composited PIL frame to the tkinter window
            # (no-op when running headless).
            self._present()
            self._draw_fps()

        def _present(self) -> None:
            """Push the current PIL frame to the tkinter label (no-op headless)."""
            if self._root is None or self._label is None:
                return
            from PIL import ImageTk

            img = self.renderer.get_image()
            if self._photo is not None and hasattr(self._photo, "paste"):
                try:
                    self._photo.paste(img)
                    return
                except Exception:  # noqa: BLE001, S110
                    pass

            self._photo = ImageTk.PhotoImage(img)
            self._label.configure(image=self._photo)

        def _present_cached(self) -> None:
            """Re-display the cached frame without re-rendering (no-op headless)."""
            if self._root is None or self._label is None or self._photo is None:
                return
            self._label.configure(image=self._photo)

        def _draw_fps(self) -> None:
            """Update the on-screen FPS counter overlay (no-op headless)."""
            if self._root is None:
                return
            if self._fps_widget is None:
                self._fps_widget = tk.Label(
                    self._root,
                    font=("TkDefaultFont", 9),
                    fg="#e6e6e6",
                    bg="#000000",
                )
            if self.show_fps:
                fps = self.renderer.fps
                fps_avg = self.renderer.fps_avg
                frames = self.renderer.frame_count
                self._fps_widget.configure(
                    text=f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})"
                )
                self._fps_widget.place(x=10, y=10)
            else:
                self._fps_widget.place_forget()

        def run(self) -> None:
            """Create the tkinter window and run the event loop (blocking).

            Requires Tk bindings in this Python (e.g. the ``python3-tk``
            system package on Debian/Ubuntu).  All story state prepared
            before this call is preserved.
            """
            if not TKINTER_AVAILABLE or tk is None:
                raise ImportError(
                    "tkinter is not available in this Python. "
                    "Install Tk bindings (e.g. 'apt install python3-tk') to use PILPlayer windows."
                )
            if self._root is not None:
                self._root.mainloop()
                return

            root = tk.Tk()
            root.title(self.title)
            root.geometry(f"{self.width}x{self.height}")
            root.resizable(True, True)
            root.protocol("WM_DELETE_WINDOW", self.close)

            label = tk.Label(root, borderwidth=0, highlightthickness=0)
            label.pack(fill="both", expand=True)

            root.bind("<Button-1>", self._on_click)
            root.bind("<Motion>", self._on_motion)
            root.bind("<Key>", self._on_key)
            root.bind("<Button-4>", self._on_scroll_up)
            root.bind("<Button-5>", self._on_scroll_down)
            root.bind("<MouseWheel>", self._on_mousewheel)
            root.bind("<KeyRelease-Control_L>", self._on_ctrl_release)
            root.bind("<KeyRelease-Control_R>", self._on_ctrl_release)
            root.bind("<Configure>", self._on_configure)

            self._root = root
            self._label = label
            if not self.visible:
                root.withdraw()

            # Present the already-stepped first beat, then enter the loop.
            self.on_draw()
            self._last_tick = time.perf_counter()
            self._run_loop()

        def _run_loop(self) -> None:
            """Drive the frame loop until the window closes (blocking).

            Tk's ``after(delay)`` timer has a coarse floor on many X11 setups
            (observed ~20 ms here), which hard-caps the whole loop near 50 FPS
            no matter what delay is requested -- including the ``uncapped``
            path, which only asks for ``after(1)``.  Instead we pump the event
            queue non-blockingly with ``update()`` and sleep out the remainder
            of the frame budget.  That keeps input responsive, honours the
            target cadence, and lets ``uncapped`` actually run unthrottled.
            """
            root = self._root
            period = (1.0 / 60.0) if (self.vsync and not self.uncapped) else 0.0
            while not self._closed and self._root is root:
                started = time.perf_counter()
                dt = started - self._last_tick if self._last_tick > 0.0 else (1.0 / 60.0)
                self._last_tick = started
                self.tick(dt)
                self.on_draw()
                try:
                    root.update()  # process pending input/window events
                except tk.TclError:  # window torn down from a callback
                    break
                if period:
                    remaining = period - (time.perf_counter() - started)
                    if remaining > 0.0:
                        time.sleep(remaining)

        def close(self) -> None:
            """Close the player window (marks closed when running headless)."""
            self._closed = True
            if self.audio is not None:
                self.audio.shutdown()
            root, self._root = self._root, None
            self._label = None
            if root is None:
                return
            # Best-effort teardown: the window may already be half-destroyed
            # (e.g. close from inside an event callback).
            for op in (root.quit, root.destroy):
                try:
                    op()
                except Exception:  # noqa: BLE001, S110
                    pass

        def _on_scroll_up(self, event: Any) -> None:
            self._ui_dirty = True
            self.session.handle_input(InputAction.ROLLBACK)
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()

        def _on_scroll_down(self, event: Any) -> None:
            self._ui_dirty = True
            self.session.handle_input(InputAction.ROLL_FORWARD)
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()

        def _on_mousewheel(self, event: Any) -> None:
            if getattr(event, "delta", 0) > 0:
                self._on_scroll_up(event)
            else:
                self._on_scroll_down(event)

        def _on_ctrl_release(self, event: Any) -> None:
            self.session.handle_input(InputAction.SKIP_RELEASE)

        def _on_motion(self, event: Any) -> None:
            """Handle mouse movement for screen and button hover states."""
            self.session.handle_input(InputAction.POINTER_MOVE, x=float(event.x), y=float(event.y))
            self._ui_dirty = True

        def _on_click(self, event: Any) -> None:
            """Handle mouse clicks for advancement or choice selection."""
            self._ui_dirty = True
            self.session.handle_input(InputAction.POINTER_CLICK, x=float(event.x), y=float(event.y))
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()

        def _on_configure(self, event: Any) -> None:
            """Keep the UI components laid out against the new window size."""
            if event.widget is not self._root:
                return
            width, height = event.width, event.height
            if width <= 0 or height <= 0:
                return
            if width == self.width and height == self.height:
                return
            self.width = width
            self.height = height
            self.overlay.set_viewport(width, height)
            self.renderer.set_window(self)
            self._photo = None
            self._ui_dirty = True

        def _on_key(self, event: Any) -> None:
            """Handle keyboard input for advancing, choices, rollback, and toggles."""
            keysym = event.keysym.lower()
            if keysym == "return":
                keysym = "enter"
            elif keysym == "prior":
                keysym = "pageup"
            elif keysym == "next":
                keysym = "pagedown"
            elif keysym in ("control_l", "control_r"):
                keysym = "ctrl"

            is_shift = bool(getattr(event, "state", 0) & 0x0001) or getattr(event, "keysym", "").isupper()
            combo = f"shift+{keysym}" if is_shift else keysym

            # 1-9 choice keys
            if self.active_choice_prompt is not None and keysym in "123456789":
                idx = int(keysym) - 1
                if idx < len(self.active_choice_prompt.options):
                    self._ui_dirty = True
                    self.session.handle_input(InputAction.CHOOSE, index=idx)
                    self.active_choice_prompt = self.session.active_choice_prompt
                    self.is_finished = self.session.is_finished
                    self._sync_overlay()
                    return

            action = self.keymap.map_key(combo) or self.keymap.map_key(keysym)
            if action == InputAction.QUIT:
                self.close()
            elif action == InputAction.DEBUG_OVERLAY:
                self.show_fps = not self.show_fps
            elif action:
                self._ui_dirty = True
                self.session.handle_input(action)
                self.active_choice_prompt = self.session.active_choice_prompt
                self.is_finished = self.session.is_finished
                self._sync_overlay()

else:

    class PILPlayer:  # type: ignore[no-redef]
        """Stub for PILPlayer when Pillow is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            msg = (
                "Pillow is not installed. Install with 'pip install eager-graphics[software]' "
                "or 'pip install Pillow' (SIMD build: 'eager-graphics[software-simd]')."
            )
            raise ImportError(msg)
