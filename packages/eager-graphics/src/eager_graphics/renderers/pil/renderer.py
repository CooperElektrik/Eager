"""Pillow 2D stage renderer and immediate-mode UI drawing backend."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eager_core.timing import FrameClock
from eager_core.types import BLACK, WHITE, Color

from eager_graphics.layout import ViewportTransform
from eager_graphics.protocol import RenderBackend, RenderItem
from eager_graphics.types import ScaleMode

from ._cache import _CachedSprite, _GeomEntry, _ImageLRU
from ._compat import (
    PIL,
    PIL_AVAILABLE,
    Image,
    ImageDraw,
    ImageFont,
    _check_pil_available,
    _detect_pillow_simd,
)
from ._constants import (
    _ALPHA_LUTS,
    _DEFAULT_CACHE_BYTES,
    _MAX_GRADIENT_CACHE,
    _MAX_MIP_CACHE,
    _MAX_RGBA_LUTS,
    _MAX_TEXT_CACHE,
    _PIL_ANCHOR_X,
    _PIL_ANCHOR_Y,
    _QUANT_ALPHA_LUT,
    _WHITE_RGBA,
)
from ._imaging import (
    _alpha_bbox,
    _bboxes_intersect,
    _image_nbytes,
    _resize_opaque,
    _split_patches,
    _split_rgba,
    _union_bboxes,
)
from .assets import PILAssetResolver

if TYPE_CHECKING:
    from eager_graphics.compositor import StageCompositor


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
        self._font_cache: dict[int, Any] = {}
        self._measure_cache: dict[
            tuple[str, int] | tuple[str, int, bool, bool], tuple[float, float]
        ] = {}
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
        self._prev_item_geom: dict[tuple[str, str, int], tuple[Any, ...]] = {}
        self._curr_item_geom: dict[tuple[str, str, int], tuple[Any, ...]] = {}
        self._in_motion_assets: set[str] = set()
        self._prev_item_bboxes: dict[tuple[str, str, int], tuple[int, int, int, int]] = {}
        self._curr_item_bboxes: dict[tuple[str, str, int], tuple[int, int, int, int]] = {}
        self._last_had_overlay: bool = False
        self._last_dirty_bbox: tuple[int, int, int, int] | None = None
        self._last_render_path: str = "None"

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
            self._prev_item_bboxes.clear()
            self._curr_item_bboxes.clear()
            self._last_had_overlay = False
            self._last_dirty_bbox = None

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
        self._prev_item_bboxes.clear()
        self._curr_item_bboxes.clear()
        self._last_had_overlay = False
        self._last_dirty_bbox = None
        self._last_render_path = "None"

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

    def debug_info(self) -> dict[str, Any]:
        """Return a structured diagnostic snapshot of the PIL renderer's optimization and cache state."""
        total_hits_misses = self._cache_hits + self._cache_misses
        hit_ratio = (self._cache_hits / total_hits_misses) if total_hits_misses > 0 else 0.0

        screen_area = self.width * self.height
        dirty_pct = 0.0
        if self._last_dirty_bbox is not None and screen_area > 0:
            x0, y0, x1, y1 = self._last_dirty_bbox
            dirty_area = max(0, x1 - x0) * max(0, y1 - y0)
            dirty_pct = (dirty_area / screen_area) * 100.0

        total_lru_bytes = sum(
            c.nbytes
            for c in (
                self._sprite_cache,
                self._scaled_cache,
                self._geom_cache,
                self._ui_image_cache,
                self._text_mask_cache,
                self._gradient_cache,
            )
        )
        total_lru_items = sum(
            len(c)
            for c in (
                self._sprite_cache,
                self._scaled_cache,
                self._geom_cache,
                self._ui_image_cache,
                self._text_mask_cache,
                self._gradient_cache,
            )
        )

        in_motion = sorted(self._in_motion_assets)
        filter_mode = "NEAREST" if (self.adaptive_resampling and in_motion) else "BILINEAR"

        return {
            "performance": {
                "fps": round(self.fps, 1),
                "fps_avg": round(self.fps_avg, 1),
                "fps_overall": round(self.fps_overall, 1),
                "frame_count": self.frame_count,
                "dt_ms": round(self.clock.dt * 1000.0, 2),
            },
            "stage_caching": {
                "last_render_path": self._last_render_path,
                "bg_cached": self._bg_cache is not None,
                "base_cached": self._base_cache is not None,
                "stage_cached": self._stage_cache is not None,
                "last_dirty_bbox": self._last_dirty_bbox,
                "dirty_area_pct": round(dirty_pct, 1),
            },
            "motion_resampling": {
                "in_motion_assets": in_motion,
                "in_motion_count": len(in_motion),
                "adaptive_resampling": self.adaptive_resampling,
                "active_filter": filter_mode,
            },
            "caches": {
                "sprite_lru": {
                    "items": len(self._sprite_cache),
                    "max_items": self.max_cached_sprites,
                    "bytes": self._sprite_cache.nbytes,
                    "hits": self._cache_hits,
                    "misses": self._cache_misses,
                    "hit_ratio": round(hit_ratio, 3),
                },
                "scaled_lru": {"items": len(self._scaled_cache), "bytes": self._scaled_cache.nbytes},
                "geom_lru": {"items": len(self._geom_cache), "bytes": self._geom_cache.nbytes},
                "ui_image_lru": {"items": len(self._ui_image_cache), "bytes": self._ui_image_cache.nbytes},
                "text_mask_lru": {"items": len(self._text_mask_cache), "bytes": self._text_mask_cache.nbytes},
                "gradient_lru": {"items": len(self._gradient_cache), "bytes": self._gradient_cache.nbytes},
                "total_lru_items": total_lru_items,
                "total_lru_bytes": total_lru_bytes,
                "luts": {
                    "alpha": len(self._alpha_lut_cache),
                    "rgba": len(self._rgba_lut_cache),
                    "fade": len(self._fade_lut_cache),
                },
                "fonts": len(self._font_cache),
                "measurements": len(self._measure_cache),
                "loaded_assets": len(self.asset_resolver._image_cache),
            },
            "backend": {
                "mode": self.mode,
                "scale_mode": self.scale_mode.name,
                "dimensions": (self.width, self.height),
                "simd": _detect_pillow_simd(),
                "pillow_version": getattr(PIL, "__version__", "unknown") if PIL_AVAILABLE else "unknown",
            },
        }

    def debug_repr(self) -> str:
        """Render debug_info() as a multi-line human-readable string report."""
        info = self.debug_info()
        perf = info["performance"]
        stage = info["stage_caching"]
        motion = info["motion_resampling"]
        caches = info["caches"]
        backend = info["backend"]

        simd_str = backend["simd"]
        p_ver = backend["pillow_version"]
        fps = perf["fps"]
        fps_avg = perf["fps_avg"]
        frames = perf["frame_count"]
        dt = perf["dt_ms"]

        lines = [
            "── Eager Debug: PIL Backend ──────────────────────────",
            f"FPS: {fps:.1f} (avg: {fps_avg:.1f}) | Frames: {frames} | dt: {dt:.1f}ms",
            f"Pillow: {p_ver} ({simd_str}) | Mode: {backend['mode']} ({backend['dimensions'][0]}x{backend['dimensions'][1]})",
            "── Stage & Repaint ───────────────────────────────────",
            f"Render Path: {stage['last_render_path']}",
        ]

        if stage["last_dirty_bbox"] is not None:
            bb = stage["last_dirty_bbox"]
            lines.append(f"Dirty Rect: [{bb[0]},{bb[1]} -> {bb[2]},{bb[3]}] ({stage['dirty_area_pct']:.1f}% screen)")
        else:
            lines.append("Dirty Rect: None (full or cached)")

        m_count = motion["in_motion_count"]
        m_str = f"{m_count} asset(s)" if m_count > 0 else "None"
        lines.append(f"In-Motion: {m_str} | Filter: {motion['active_filter']}")

        sp = caches["sprite_lru"]
        sp_bytes_mb = sp["bytes"] / (1024 * 1024)
        sp_hr = sp["hit_ratio"] * 100.0
        lines.extend([
            "── Cache Diagnostics ─────────────────────────────────",
            f"Sprite LRU: {sp['items']}/{sp['max_items']} ({sp_bytes_mb:.1f} MB) | Hits: {sp_hr:.1f}% ({sp['hits']}H/{sp['misses']}M)",
            f"Total LRU: {caches['total_lru_items']} items ({caches['total_lru_bytes'] / (1024 * 1024):.1f} MB)",
            f"Sub-caches: text: {caches['text_mask_lru']['items']}, scaled: {caches['scaled_lru']['items']}, ui: {caches['ui_image_lru']['items']}",
            f"LUTs: α:{caches['luts']['alpha']} rgba:{caches['luts']['rgba']} fade:{caches['luts']['fade']} | Fonts: {caches['fonts']} | Textures: {caches['loaded_assets']}",
        ])
        return "\n".join(lines)

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

    def _compute_item_bbox(
        self,
        item: RenderItem,
        transform: ViewportTransform | None,
    ) -> tuple[int, int, int, int] | None:
        """Calculate the axis-aligned screen-space bounding box of a RenderItem."""
        if transform is None:
            return None
        if item.opacity <= 0.0 or not (item.scale_x and item.scale_y) or item.tint.a <= 0.0:
            return None

        is_bg = item.layer == "background" or item.asset_id.startswith("bg/")
        def_w = 1920 if is_bg else 400
        def_h = 1080 if is_bg else 800
        base_tex = self.asset_resolver.get_image(item.asset_id, def_w, def_h)

        eff_w = base_tex.width * abs(item.scale_x)
        eff_h = base_tex.height * abs(item.scale_y)
        fx, fy = item.anchor.get_offset_factor()

        draw_w = max(1, round(eff_w * transform.scale_x))
        draw_h = max(1, round(eff_h * transform.scale_y))

        anchor_s_x = transform.offset_x + item.x * transform.scale_x
        anchor_s_y = transform.offset_y + item.y * transform.scale_y

        rot_norm = round(item.rotation % 360.0, 2) if item.rotation != 0.0 else 0.0

        if rot_norm == 0.0:
            dest_x0 = round(anchor_s_x - draw_w * fx)
            dest_y0 = round(anchor_s_y - draw_h * fy)
            dest_x1 = dest_x0 + draw_w
            dest_y1 = dest_y0 + draw_h
        else:
            corners = (
                (-draw_w * fx, -draw_h * fy),
                (draw_w * (1.0 - fx), -draw_h * fy),
                (draw_w * (1.0 - fx), draw_h * (1.0 - fy)),
                (-draw_w * fx, draw_h * (1.0 - fy)),
            )
            rad = math.radians(rot_norm)
            cos_t = math.cos(rad)
            sin_t = math.sin(rad)
            xs = [anchor_s_x + (cx * cos_t - cy * sin_t) for cx, cy in corners]
            ys = [anchor_s_y + (cx * sin_t + cy * cos_t) for cx, cy in corners]
            dest_x0 = math.floor(min(xs))
            dest_y0 = math.floor(min(ys))
            dest_x1 = math.ceil(max(xs))
            dest_y1 = math.ceil(max(ys))

        # Clamp to canvas boundaries with a 1-pixel margin for anti-aliasing / filtering
        x0 = max(0, min(self.width, dest_x0 - 1))
        y0 = max(0, min(self.height, dest_y0 - 1))
        x1 = max(0, min(self.width, dest_x1 + 1))
        y1 = max(0, min(self.height, dest_y1 + 1))

        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1, y1)

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
        if t == WHITE:
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
            if not isinstance(px, (tuple, list)):
                px = (int(px or 0), int(px or 0), int(px or 0))
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

        is_in_motion = self.adaptive_resampling and (item.asset_id in self._in_motion_assets)

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
            if not is_in_motion:
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
            if not isinstance(px, (tuple, list)):
                px = (int(px or 0), int(px or 0), int(px or 0))
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
        self._prev_item_bboxes = self._curr_item_bboxes
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
            self._last_render_path = "Tier 3 (Stage Cache / UI Only)"
            self.last_frame = items
            self.frame_count += 1
            self.clock.tick()
            self._in_motion_assets = set()
            self._last_dirty_bbox = None
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

        # Motion tracking: detect which items are actively moving/tweening/changing
        curr_geom: dict[tuple[str, str, int], tuple[Any, ...]] = {}
        in_motion: set[str] = set()
        for it in items:
            k = (it.layer, it.asset_id, it.z_order)
            t = it.tint
            tint_key = t.to_rgba_bytes()
            g = (
                it.x,
                it.y,
                it.scale_x,
                it.scale_y,
                it.rotation,
                it.opacity,
                tint_key,
            )
            curr_geom[k] = g
            prev = self._prev_item_geom.get(k)
            if prev is not None and prev != g:
                in_motion.add(it.asset_id)
        self._curr_item_geom = curr_geom
        self._in_motion_assets = in_motion

        curr_bboxes: dict[tuple[str, str, int], tuple[int, int, int, int]] = {}
        for it in items:
            k = (it.layer, it.asset_id, it.z_order)
            bb = self._compute_item_bbox(it, self._current_transform)
            if bb is not None:
                curr_bboxes[k] = bb
        self._curr_item_bboxes = curr_bboxes

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
        if can_use_base_cache and self._base_cache is not None:
            self._last_render_path = "Tier 2 (Base Scene Cache)"
            self._image.paste(self._base_cache, (0, 0))
            self._needs_clear = False
            self._frame_buffer.extend(base_items)
            for item in overlay_items:
                self.draw_item(item)
            self._last_dirty_bbox = None
        elif can_use_bg_cache and self._bg_cache is not None:
            use_dirty_rect = False
            dirty_bbox: tuple[int, int, int, int] | None = None
            if (
                self._last_stage_items is not None
                and not overlay_items
                and not self._last_had_overlay
                and bool(self._in_motion_assets)
            ):
                dirty_boxes: list[tuple[int, int, int, int]] = []
                for it in actor_items:
                    k = (it.layer, it.asset_id, it.z_order)
                    if it.asset_id in self._in_motion_assets:
                        curr_bb = curr_bboxes.get(k)
                        prev_bb = self._prev_item_bboxes.get(k)
                        if curr_bb is not None and prev_bb is not None:
                            dirty_boxes.append(_union_bboxes(curr_bb, prev_bb))
                        elif curr_bb is not None:
                            dirty_boxes.append(curr_bb)
                        elif prev_bb is not None:
                            dirty_boxes.append(prev_bb)

                for k, prev_bb in self._prev_item_bboxes.items():
                    if k[0] not in ("background", "overlay") and k not in curr_bboxes:
                        dirty_boxes.append(prev_bb)

                if self._ui_dirty_bbox is not None:
                    dirty_boxes.append(self._ui_dirty_bbox)

                if dirty_boxes:
                    dirty_bbox = dirty_boxes[0]
                    for db in dirty_boxes[1:]:
                        dirty_bbox = _union_bboxes(dirty_bbox, db)

                    # Expand dirty_bbox to include any intersecting actors
                    expanded = True
                    while expanded:
                        expanded = False
                        for it in actor_items:
                            k = (it.layer, it.asset_id, it.z_order)
                            bb = curr_bboxes.get(k)
                            if bb is not None and _bboxes_intersect(bb, dirty_bbox):
                                new_dirty = _union_bboxes(dirty_bbox, bb)
                                if new_dirty != dirty_bbox:
                                    dirty_bbox = new_dirty
                                    expanded = True

                    x0, y0, x1, y1 = dirty_bbox
                    w_box, h_box = x1 - x0, y1 - y0
                    if w_box > 0 and h_box > 0 and (w_box * h_box < 0.85 * window_width * window_height):
                        use_dirty_rect = True

            if use_dirty_rect and dirty_bbox is not None:
                self._last_render_path = "Tier 1 (Dirty Rect Repaint)"
                crop = self._bg_cache.crop(dirty_bbox)
                self._image.paste(crop, (dirty_bbox[0], dirty_bbox[1]))
                self._needs_clear = False
                self._frame_buffer.extend(bg_items)

                for item in actor_items:
                    k = (item.layer, item.asset_id, item.z_order)
                    bb = curr_bboxes.get(k)
                    if bb is not None and _bboxes_intersect(bb, dirty_bbox):
                        self.draw_item(item)
                    else:
                        self._frame_buffer.append(item)

                self._ui_dirty_bbox = None
                self._last_dirty_bbox = dirty_bbox
            else:
                self._last_render_path = "Tier 1 (Full BG Blit)"
                self._image.paste(self._bg_cache, (0, 0))
                self._needs_clear = False
                self._frame_buffer.extend(bg_items)
                for item in actor_items:
                    self.draw_item(item)
                self._ui_dirty_bbox = None
                self._last_dirty_bbox = None

            if overlay_items and not self._in_motion_assets:
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
            self._last_render_path = "Full Repaint"
            self._last_dirty_bbox = None
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
                and bg_items[0].tint == WHITE
                and bg_items[1].tint == WHITE
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

                        if bg_items[0].opacity >= 1.0:
                            blend_alpha = min(1.0, max(0.0, bg_items[1].opacity))
                        else:
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
            if bg_items and not any(it.asset_id in self._in_motion_assets for it in bg_items):
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
            if overlay_items and not self._in_motion_assets:
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
        # Always snapshot the clean stage buffer when settled (no assets in motion)
        # after all stage layers finish (BG + Actors + Overlays) so UI redraws
        # can restore the stage without a full re-render.
        if not self._in_motion_assets:
            self._stage_cache = self._snapshot(self._stage_cache)
        else:
            self._stage_cache = None
        self._last_stage_items = items
        self._last_transform = self._current_transform
        self._ui_dirty_bbox = None
        self._last_had_overlay = bool(overlay_items)

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

    def _ui_font(self, font_size: int) -> Any:
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

    def _blend_rect(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color: Color,
    ) -> None:
        """Fill region (x0, y0, x1, y1) with *color*, alpha-blending if translucent."""
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            return
        c_rgba = (
            _WHITE_RGBA
            if color == WHITE
            else color.to_rgba_bytes()
        )
        alpha = c_rgba[3]
        if alpha <= 0:
            return
        if alpha == 255:
            c_bytes = c_rgba[:3] if self.mode == "RGB" else c_rgba
            self._image.paste(c_bytes, (x0, y0, x1, y1))
        elif self.mode == "RGBA":
            overlay = Image.new("RGBA", (w, h), c_rgba)
            self._image.alpha_composite(overlay, dest=(x0, y0))
        else:
            mask = Image.new("L", (w, h), alpha)
            self._image.paste(c_rgba[:3], (x0, y0, x1, y1), mask)

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
        r_left, r_top = round(left), round(top)
        r_right, r_bottom = round(right), round(bottom)
        if r_right <= r_left or r_bottom <= r_top:
            return

        self._mark_ui_dirty(r_left, r_top, r_right + 1, r_bottom + 1)
        self._blend_rect(r_left, r_top, r_right, r_bottom, color)

        if border_color is not None and border_width > 0.0:
            self.draw_rect_outline(
                x, y, width, height, border_color, line_width=border_width
            )

    def draw_rect_outline(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: Color,
        *,
        line_width: float = 1.0,
    ) -> None:
        """Draw an unfilled rectangle outline with thickness *line_width*."""
        if self._needs_clear:
            self._execute_clear()
        if line_width <= 0.0:
            return
        bw = max(1, round(line_width))
        left, top = float(x), float(y)
        right, bottom = left + float(width), top + float(height)
        r_left, r_top = round(left), round(top)
        r_right, r_bottom = round(right), round(bottom)
        rw = r_right - r_left
        rh = r_bottom - r_top
        if rw <= 0 or rh <= 0:
            return

        self._mark_ui_dirty(r_left, r_top, r_right + 1, r_bottom + 1)
        if rw <= 2 * bw or rh <= 2 * bw:
            self._blend_rect(r_left, r_top, r_right, r_bottom, color)
        else:
            self._blend_rect(r_left, r_top, r_right, r_top + bw, color)
            self._blend_rect(r_left, r_bottom - bw, r_right, r_bottom, color)
            self._blend_rect(r_left, r_top + bw, r_left + bw, r_bottom - bw, color)
            self._blend_rect(r_right - bw, r_top + bw, r_right, r_bottom - bw, color)

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
        cache: bool = True,
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
            if cache:
                self._text_mask_cache.put(
                    cache_key,
                    cached,
                    _image_nbytes(cached[0]) if cached[0] is not None else 0,
                )

        color_rgba = (
            _WHITE_RGBA
            if color == WHITE
            else color.to_rgba_bytes()
        )
        color_bytes = color_rgba[:3] if self.mode == "RGB" else color_rgba
        mask, rel_x, rel_y = cached
        if mask is not None:
            dest_x = round(x + rel_x)
            dest_y = round(y + rel_y)
            self._mark_ui_dirty(dest_x, dest_y, dest_x + mask.width, dest_y + mask.height)
            alpha = color_rgba[3]
            if alpha <= 0:
                return
            if alpha < 255:
                lut = _ALPHA_LUTS[alpha]
                eff_mask = mask.point(lut)
                dest_color = color_rgba[:3] if self.mode == "RGB" else color_rgba[:3] + (255,)
                self._image.paste(dest_color, (dest_x, dest_y), eff_mask)
            else:
                self._image.paste(color_bytes, (dest_x, dest_y), mask)
        else:
            w_est, h_est = self.measure_text(text, font_size=font_size, cache=cache)
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
        t_rgba = _WHITE_RGBA if tint == WHITE else tint.to_rgba_bytes()
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
        if sprite.color is not None:
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
        cache: bool = True,
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
        lines = text.split("\n")
        try:
            ascent, descent = font.getmetrics()
            line_height = float(ascent + descent)
            if line_height <= 0:
                line_height = float(font_size) * 1.2
            width = max((float(font.getlength(line)) for line in lines), default=0.0)
            if stroke_w > 0:
                width += stroke_w * 2
            height = line_height * max(1, len(lines))
            result = (width, height)
        except (AttributeError, ValueError, TypeError):
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

        if cache and len(self._measure_cache) < 2048:
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


__all__ = ["PILRenderer"]
