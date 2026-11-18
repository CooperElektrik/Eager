"""Pillow 2D stage renderer and immediate-mode UI drawing backend."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eager.backends.exceptions import RenderError
from eager.backends.types import RenderBackend, RenderItem
from eager.core.layout import ViewportTransform
from eager.core.timing import FrameClock
from eager.core.types import BLACK, WHITE, Color, RenderPreset, ScaleMode

from ._cache import _CachedSprite, _GeomEntry, _ImageLRU
from ._compat import (
    PIL_AVAILABLE,
    Image,
    ImageChops,
    ImageDraw,
    _check_pil_available,
)
from ._constants import (
    _ALPHA_LUTS,
    _QUANT_ALPHA_LUT,
    _WHITE_RGBA,
)
from ._imaging import (
    _alpha_bbox,
    _image_nbytes,
    _resize_opaque,
    _split_rgba,
    get_fade_lut,
    get_rgba_lut,
    rotate_expand_params,
)
from ._stage_cache import StageCacheManager
from ._telemetry import build_cache_info, build_debug_info, format_debug_repr
from ._ui_draw import PILUIDrawer
from .assets import PILAssetResolver

if TYPE_CHECKING:
    from eager.core.lighting import LightmapState



_PRESET_CONFIGS: dict[RenderPreset, dict[str, Any]] = {
    RenderPreset.PERFORMANCE: {
        "resampling": getattr(Image.Resampling, "NEAREST", 0) if PIL_AVAILABLE else 0,
        "adaptive_resampling": True,
        "enable_stage_cache": True,
        "enable_dirty_rects": True,
        "dirty_area_threshold": 0.85,
        "max_cached_sprites": 1024,
        "cache_budget_bytes": 256 * 1024 * 1024,
        "enable_patches": False,
    },
    RenderPreset.BALANCED: {
        "resampling": getattr(Image.Resampling, "BILINEAR", 2) if PIL_AVAILABLE else 2,
        "adaptive_resampling": True,
        "enable_stage_cache": True,
        "enable_dirty_rects": True,
        "dirty_area_threshold": 0.85,
        "max_cached_sprites": 512,
        "cache_budget_bytes": 128 * 1024 * 1024,
        "enable_patches": False,
    },
    RenderPreset.QUALITY: {
        "resampling": getattr(Image.Resampling, "BICUBIC", 3) if PIL_AVAILABLE else 3,
        "adaptive_resampling": False,
        "enable_stage_cache": True,
        "enable_dirty_rects": True,
        "dirty_area_threshold": 0.75,
        "max_cached_sprites": 1024,
        "cache_budget_bytes": 512 * 1024 * 1024,
        "enable_patches": False,
    },
    RenderPreset.DEBUG: {
        "resampling": getattr(Image.Resampling, "BILINEAR", 2) if PIL_AVAILABLE else 2,
        "adaptive_resampling": False,
        "enable_stage_cache": False,
        "enable_dirty_rects": False,
        "dirty_area_threshold": 0.50,
        "max_cached_sprites": 0,
        "cache_budget_bytes": 0,
        "enable_patches": False,
    },
}


_SolidFillAction = tuple[
    str,
    tuple[int, ...] | tuple[int, int, int] | tuple[int, int, int, int],
    tuple[int, int, int, int],
]
_FadeLutAction = tuple[str, list[int]]
_DirectDrawAction = _SolidFillAction | _FadeLutAction
_PreparedSprite = _CachedSprite | _DirectDrawAction | None


class PILRenderer(RenderBackend):
    """Pillow 2D stage renderer implementing RenderBackend protocol."""

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        *,
        mode: str = "RGB",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        window: Any | None = None,
        preset: str | RenderPreset = RenderPreset.BALANCED,
        resampling: Image.Resampling | None = None,
        max_cached_sprites: int | None = None,
        adaptive_resampling: bool | None = None,
        enable_stage_cache: bool | None = None,
        enable_dirty_rects: bool | None = None,
        dirty_area_threshold: float | None = None,
        cache_budget_bytes: int | None = None,
        enable_patches: bool | None = None,
        render_threads: int | None = None,
    ) -> None:
        _check_pil_available()
        self.preset = RenderPreset.from_str(preset) if isinstance(preset, str) else preset
        cfg = _PRESET_CONFIGS[self.preset]

        self.resampling = cfg["resampling"] if resampling is None else resampling
        self.adaptive_resampling = (
            cfg["adaptive_resampling"] if adaptive_resampling is None else adaptive_resampling
        )
        self.enable_stage_cache = (
            cfg["enable_stage_cache"] if enable_stage_cache is None else enable_stage_cache
        )
        self.enable_dirty_rects = (
            cfg["enable_dirty_rects"] if enable_dirty_rects is None else enable_dirty_rects
        )
        self.dirty_area_threshold = (
            cfg["dirty_area_threshold"] if dirty_area_threshold is None else dirty_area_threshold
        )
        self.max_cached_sprites = (
            cfg["max_cached_sprites"] if max_cached_sprites is None else max_cached_sprites
        )
        self.cache_budget_bytes = (
            cfg["cache_budget_bytes"] if cache_budget_bytes is None else cache_budget_bytes
        )
        self.enable_patches = (
            cfg["enable_patches"] if enable_patches is None else enable_patches
        )
        self.render_threads = render_threads

        self.asset_resolver = PILAssetResolver(asset_dir)
        self.scale_mode = scale_mode
        self.window = window
        self.mode = mode

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
        self._draw: ImageDraw.ImageDraw = ImageDraw.Draw(self._image)
        self._rgba_draw: ImageDraw.ImageDraw = ImageDraw.Draw(self._image, "RGBA")
        self._in_frame: bool = False
        self._frame_buffer: list[RenderItem] = []
        self._needs_clear: bool = False

        self.clock: FrameClock = FrameClock()

        # Consolidated stage sprite/geometry caches
        self._sprite_cache: _ImageLRU[tuple[object, ...], _CachedSprite] = _ImageLRU(
            max_items=self.max_cached_sprites,
            max_bytes=self.cache_budget_bytes,
        )
        self._geom_cache: _ImageLRU[tuple[object, ...], _GeomEntry] = _ImageLRU(
            max_items=self.max_cached_sprites,
            max_bytes=self.cache_budget_bytes,
        )
        self._cache_hits: int = 0
        self._cache_misses: int = 0

        # Subsystems: stage-layer caching, UI drawing
        self._stage_cache_mgr: StageCacheManager = StageCacheManager(self)
        self._ui: PILUIDrawer = PILUIDrawer(
            self,
            max_cached_sprites=self.max_cached_sprites,
            cache_budget_bytes=self.cache_budget_bytes,
            disable_gradients=self.preset == RenderPreset.DEBUG,
        )
        self._last_render_path: str = "None"

    @property
    def _last_dirty_bbox(self) -> tuple[int, int, int, int] | None:
        return self._stage_cache_mgr.last_dirty_bbox

    @property
    def _bg_cache(self) -> Image.Image | None:
        return self._stage_cache_mgr.bg_cache

    @property
    def _base_cache(self) -> Image.Image | None:
        return self._stage_cache_mgr.base_cache

    @property
    def _stage_cache(self) -> Image.Image | None:
        return self._stage_cache_mgr.stage_cache

    @property
    def _last_stage_items(self) -> list[RenderItem] | None:
        return self._stage_cache_mgr.last_stage_items

    @property
    def _last_transform(self) -> ViewportTransform | None:
        return self._stage_cache_mgr.last_transform

    @property
    def _in_motion_assets(self) -> set[str]:
        return self._stage_cache_mgr.in_motion_assets

    @property
    def _ui_dirty_bbox(self) -> tuple[int, int, int, int] | None:
        return self._stage_cache_mgr.ui_dirty_bbox

    @property
    def _ui_image_cache(self) -> _ImageLRU[tuple[object, ...], _CachedSprite]:
        return self._ui.ui_image_cache

    @property
    def _text_mask_cache(
        self,
    ) -> _ImageLRU[tuple[str, int, str, bool, bool, str | None], tuple[Image.Image | None, int, int]]:
        return self._ui.text_mask_cache

    @property
    def _font_cache(self) -> dict[int | tuple[int, str], Any]:
        return self._ui.font_cache

    @property
    def _measure_cache(self) -> dict[tuple[Any, ...], tuple[float, float]]:
        return self._ui.measure_cache

    def set_window(self, window: Any) -> None:
        """Bind or update the host window object."""
        self.window = window
        if window is not None:
            self.width = window.width
            self.height = window.height

    def _set_image(self, img: Image.Image) -> None:
        """Replace active framebuffer and refresh cached ImageDraw contexts."""
        self._image = img
        self._draw = ImageDraw.Draw(self._image)
        self._rgba_draw = ImageDraw.Draw(self._image, "RGBA")

    def _ensure_buffer(self) -> None:
        """Ensure internal PIL Image matches current viewport dimensions."""
        if self._image.size != (self.width, self.height):
            self._set_image(
                Image.new(self.mode, (self.width, self.height), self._clear_color_bytes)
            )
            self._stage_cache_mgr.stage_cache = None
            self._stage_cache_mgr.base_cache = None
            self._stage_cache_mgr.bg_cache = None
            self._stage_cache_mgr.ui_dirty_bbox = None

    def _snapshot(self, target: Image.Image | None) -> Image.Image:
        """Copy the active framebuffer into *target* in-place if dimensions match."""
        if target is not None and target.size == self._image.size and target.mode == self._image.mode:
            target.paste(self._image)
            return target
        return self._image.copy()

    def _mark_ui_dirty(self, left: int, top: int, right: int, bottom: int) -> None:
        self._stage_cache_mgr.mark_ui_dirty(left, top, right, bottom)

    def _execute_clear(self) -> None:
        """Execute deferred canvas clear."""
        self._image.paste(self._clear_color_bytes, (0, 0, self.width, self.height))
        self._needs_clear = False

    def close(self) -> None:
        """Release resources held by the renderer."""
        self.clear_cache()

    def clear_cache(self) -> None:
        """Clear sprite, geometry, UI, and stage caches and reset statistics."""
        self._sprite_cache.clear()
        self._geom_cache.clear()
        self._ui.clear()
        self._stage_cache_mgr.clear()
        get_rgba_lut.cache_clear()
        get_fade_lut.cache_clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self._last_render_path = "None"

    def cache_info(self) -> dict[str, Any]:
        """Return diagnostic metrics about cache hits, misses, and current size."""
        return build_cache_info(self)

    def debug_info(self) -> dict[str, Any]:
        """Return a structured diagnostic snapshot of the PIL renderer's optimization and cache state."""
        return build_debug_info(self)

    def debug_repr(self) -> str:
        """Render debug_info() as a multi-line human-readable string report."""
        return format_debug_repr(self)

    def preload_assets(self, compositor: Any) -> int:
        """Pre-load all stage assets into the image cache to avoid first-frame spikes."""
        seen: set[str] = set()
        count = 0
        for layer in compositor.stage.layers.values():
            for elem in layer.elements.values():
                if elem.asset_id in seen:
                    continue
                seen.add(elem.asset_id)
                is_bg = elem.asset_id.startswith("bg/") or "background" in elem.asset_id
                def_w, def_h = (1920, 1080) if is_bg else (400, 800)
                self.asset_resolver.get_image(elem.asset_id, def_w, def_h)
                count += 1
        return count

    def warm_sprite_cache(
        self, compositor: Any, window_width: int, window_height: int
    ) -> int:
        """Pre-render the current render list to populate the sprite cache."""
        misses_before = self._cache_misses
        saved_frame_count = self.frame_count
        self.render_compositor(compositor, window_width, window_height)
        self.frame_count = saved_frame_count
        return max(0, self._cache_misses - misses_before)

    def begin_frame(self) -> None:
        """Begin a new frame render pass."""
        if self._in_frame:
            msg = "begin_frame called without matching end_frame"
            raise RenderError(msg)
        self._frame_buffer = []
        self._in_frame = True
        self._ensure_buffer()

    def clear(self, color: Color = BLACK) -> None:
        """Clear the frame buffer with color using fast direct block fill."""
        self.clear_color = color
        if self.mode == "RGB":
            self._clear_color_bytes = (0, 0, 0) if color is BLACK else color.to_rgba_bytes()[:3]
        else:
            self._clear_color_bytes = (0, 0, 0, 255) if color is BLACK else color.to_rgba_bytes()
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
        def_w, def_h = (1920, 1080) if is_bg else (400, 800)
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
            cos_t, sin_t = math.cos(rad), math.sin(rad)
            xs = [anchor_s_x + (cx * cos_t - cy * sin_t) for cx, cy in corners]
            ys = [anchor_s_y + (cx * sin_t + cy * cos_t) for cx, cy in corners]
            dest_x0, dest_y0 = math.floor(min(xs)), math.floor(min(ys))
            dest_x1, dest_y1 = math.ceil(max(xs)), math.ceil(max(ys))

        x0 = max(0, min(self.width, dest_x0 - 1))
        y0 = max(0, min(self.height, dest_y0 - 1))
        x1 = max(0, min(self.width, dest_x1 + 1))
        y1 = max(0, min(self.height, dest_y1 + 1))

        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1, y1)

    def draw_particles(self, batch: Any) -> None:
        """Render a pre-baked particle batch via zero-resample Image.paste."""
        if not self._in_frame:
            msg = "draw_particles called outside of begin_frame/end_frame block"
            raise RenderError(msg)

        lut = batch.lut
        canvas_im_paste = self._image.im.paste
        w, h = self.width, self.height

        for x, y, scale_idx, angle_idx, alpha_idx in batch.particles:
            stamp = lut.get_stamp(scale_idx, angle_idx, alpha_idx)
            dest_x = x + round(stamp.off_x)
            dest_y = y + round(stamp.off_y)
            sw, sh = stamp.width, stamp.height
            if dest_x + sw <= 0 or dest_y + sh <= 0 or dest_x >= w or dest_y >= h:
                continue
            canvas_im_paste(stamp.color.im, (dest_x, dest_y, dest_x + sw, dest_y + sh), stamp.mask.im)

    def render_lightmap(self, lightmap: LightmapState) -> None:
        """Composite a screen-space low-res lightmap onto the display buffer."""
        intensity = getattr(lightmap, "ambient_intensity", 1.0)
        if not lightmap.enabled or (lightmap.ambient == WHITE and intensity == 1.0 and not lightmap.lights):
            return

        low_w = max(16, self.width // 8)
        low_h = max(9, self.height // 8)
        amb = lightmap.ambient
        amb_rgb = (
            max(0, min(255, round(amb.r * intensity * 255))),
            max(0, min(255, round(amb.g * intensity * 255))),
            max(0, min(255, round(amb.b * intensity * 255))),
        )
        lightmap_img = Image.new("RGB", (low_w, low_h), amb_rgb)
        screen_img: Image.Image | None = None
        screen_draw: ImageDraw.ImageDraw | None = None

        transform = self._current_transform
        sc_x = (transform.scale_x / 8.0) if transform else (1.0 / 8.0)
        sc_y = (transform.scale_y / 8.0) if transform else (1.0 / 8.0)
        off_x = (transform.offset_x / 8.0) if transform else 0.0
        off_y = (transform.offset_y / 8.0) if transform else 0.0

        if lightmap.lights:
            draw = ImageDraw.Draw(lightmap_img)
            for light in lightmap.lights:
                lx = off_x + light.x * sc_x
                ly = off_y + light.y * sc_y
                lr = max(1.0, light.radius * sc_x)
                x0, y0, x1, y1 = round(lx - lr), round(ly - lr), round(lx + lr), round(ly + lr)
                if x1 <= 0 or y1 <= 0 or x0 >= low_w or y0 >= low_h:
                    continue

                col = light.color
                c_rgb = (round(col.r * 255), round(col.g * 255), round(col.b * 255))
                is_screen = getattr(light, "mode", "multiply") == "screen"
                if is_screen and screen_img is None:
                    screen_img = Image.new("RGB", (low_w, low_h), (0, 0, 0))
                    screen_draw = ImageDraw.Draw(screen_img)

                steps = max(2, min(8, round(lr)))
                for s in range(steps, 0, -1):
                    f = s / steps
                    r_step = lr * f
                    bx0, by0 = round(lx - r_step), round(ly - r_step)
                    bx1, by1 = round(lx + r_step), round(ly + r_step)
                    alpha_factor = (1.0 - f) * light.intensity
                    if is_screen and screen_draw is not None:
                        fill_col = (
                            max(0, min(255, round(c_rgb[0] * alpha_factor))),
                            max(0, min(255, round(c_rgb[1] * alpha_factor))),
                            max(0, min(255, round(c_rgb[2] * alpha_factor))),
                        )
                        screen_draw.ellipse([bx0, by0, bx1, by1], fill=fill_col)
                    else:
                        fill_col = (
                            max(0, min(255, round(amb_rgb[0] + (c_rgb[0] - amb_rgb[0]) * alpha_factor))),
                            max(0, min(255, round(amb_rgb[1] + (c_rgb[1] - amb_rgb[1]) * alpha_factor))),
                            max(0, min(255, round(amb_rgb[2] + (c_rgb[2] - amb_rgb[2]) * alpha_factor))),
                        )
                        draw.ellipse([bx0, by0, bx1, by1], fill=fill_col)

        full_lightmap = lightmap_img.resize((self.width, self.height), Image.Resampling.BILINEAR)
        if lightmap.blend_mode == "screen":
            self._set_image(ImageChops.screen(self._image, full_lightmap))
        else:
            self._set_image(ImageChops.multiply(self._image, full_lightmap))

        if screen_img is not None:
            full_screen = screen_img.resize((self.width, self.height), Image.Resampling.BILINEAR)
            self._set_image(ImageChops.screen(self._image, full_screen))

    def _render_top_fx(
        self,
        top_items: list[RenderItem],
        particle_batches: list[Any],
    ) -> None:
        """Render foreground/overlay elements and particle batches in z-order."""
        entries: list[tuple[int, Any, bool]] = [(it.z_order, it, False) for it in top_items]
        for pb in particle_batches:
            if pb.z_order >= 200000:
                entries.append((pb.z_order, pb, True))
        entries.sort(key=lambda e: e[0])

        for _, obj, is_batch in entries:
            if is_batch:
                self.draw_particles(obj)
            else:
                self.draw_item(obj)

    def _prepare_item_sprite(self, item: RenderItem) -> tuple[_PreparedSprite, float, float]:
        """Compute item geometry, look up cache, or transform sprite."""
        if item.opacity <= 0.0 or not (item.scale_x and item.scale_y) or item.tint.a <= 0.0:
            return None, 0.0, 0.0

        transform = self._current_transform
        if transform is None:
            msg = "draw_item called before render_compositor set the viewport transform"
            raise RenderError(msg)

        is_bg = item.layer == "background" or item.asset_id.startswith("bg/")
        def_w, def_h = (1920, 1080) if is_bg else (400, 800)
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
            dest_x_approx = round(anchor_s_x - draw_w * fx)
            dest_y_approx = round(anchor_s_y - draw_h * fy)
            if (
                dest_x_approx + draw_w <= 0
                or dest_y_approx + draw_h <= 0
                or dest_x_approx >= self.width
                or dest_y_approx >= self.height
            ):
                return None, anchor_s_x, anchor_s_y
        else:
            rad = max(draw_w, draw_h)
            if (
                anchor_s_x + rad <= 0
                or anchor_s_y + rad <= 0
                or anchor_s_x - rad >= self.width
                or anchor_s_y - rad >= self.height
            ):
                return None, anchor_s_x, anchor_s_y

        t = item.tint
        tint_rgba = _WHITE_RGBA if t == WHITE else t.to_rgba_bytes()
        final_alpha_f = max(0.0, min(1.0, item.opacity * (tint_rgba[3] / 255.0)))
        final_alpha_byte = round(final_alpha_f * 255)
        color_tint = tint_rgba[:3]

        # Fast path for 1x1 solid color texture (UI blocks, screen fades, flashes)
        if base_tex.size == (1, 1) and rot_norm == 0.0:
            if final_alpha_byte == 0:
                return None, anchor_s_x, anchor_s_y
            dest_x = round(anchor_s_x - draw_w * fx)
            dest_y = round(anchor_s_y - draw_h * fy)
            px = base_tex.getpixel((0, 0))
            if not isinstance(px, (tuple, list)):
                px = (int(px or 0), int(px or 0), int(px or 0))
            r = round(px[0] * (tint_rgba[0] / 255.0))
            g = round(px[1] * (tint_rgba[1] / 255.0))
            b = round(px[2] * (tint_rgba[2] / 255.0))

            if final_alpha_byte == 255:
                c_fill = (r, g, b) if self.mode == "RGB" else (r, g, b, 255)
                return ("paste_solid", c_fill, (dest_x, dest_y, dest_x + draw_w, dest_y + draw_h)), anchor_s_x, anchor_s_y

            if (
                dest_x <= 0
                and dest_y <= 0
                and dest_x + draw_w >= self.width
                and dest_y + draw_h >= self.height
            ):
                inv_factor_q = round((1.0 - (255 - final_alpha_byte) / 255.0) * 255)
                lut = get_fade_lut(inv_factor_q, r, g, b, self.mode)
                return ("point_lut", lut), anchor_s_x, anchor_s_y

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

        is_in_motion = self.adaptive_resampling and (item.asset_id in self._stage_cache_mgr.in_motion_assets)
        cached = self._sprite_cache.lookup(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached, anchor_s_x, anchor_s_y

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
        sprite_bytes = (
            cached_sprite.nbytes if final_alpha_byte == 255 else _image_nbytes(cached_sprite.mask)
        )
        if not is_in_motion and self._sprite_cache.enabled:
            self._sprite_cache.put(cache_key, cached_sprite, sprite_bytes)

        return cached_sprite, anchor_s_x, anchor_s_y

    def _draw_cached_sprite(
        self,
        cached_sprite: _PreparedSprite,
        anchor_s_x: float,
        anchor_s_y: float,
    ) -> None:
        """Composite a transformed sprite onto the frame buffer."""
        if cached_sprite is None:
            return
        if isinstance(cached_sprite, tuple):
            if len(cached_sprite) == 3 and cached_sprite[0] == "paste_solid":
                _, c_fill, box = cached_sprite
                dest_x, dest_y, dest_x2, dest_y2 = box
                if dest_x <= 0 and dest_y <= 0 and dest_x2 >= self.width and dest_y2 >= self.height:
                    self._image.paste(c_fill, box)
                    self._needs_clear = False
                else:
                    if self._needs_clear:
                        self._execute_clear()
                    self._image.paste(c_fill, box)
                return
            if len(cached_sprite) == 2 and cached_sprite[0] == "point_lut":
                _, lut = cached_sprite
                if self._needs_clear:
                    self._execute_clear()
                self._set_image(self._image.point(lut))
                return
            return

        if cached_sprite.color is None:
            return
        dest_x = round(anchor_s_x + cached_sprite.off_x)
        dest_y = round(anchor_s_y + cached_sprite.off_y)
        spr_w, spr_h = cached_sprite.size

        if (
            dest_x + spr_w <= 0
            or dest_y + spr_h <= 0
            or dest_x >= self.width
            or dest_y >= self.height
        ):
            return

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
            self._image.im.paste(
                cached_sprite.color.im, (dest_x, dest_y, dest_x + spr_w, dest_y + spr_h)
            )
        else:
            if self._needs_clear:
                self._execute_clear()
            if cached_sprite.mask is not None:
                self._image.im.paste(
                    cached_sprite.color.im,
                    (dest_x, dest_y, dest_x + spr_w, dest_y + spr_h),
                    cached_sprite.mask.im,
                )
            elif self.mode == "RGBA":
                self._image.alpha_composite(cached_sprite.image, dest=(dest_x, dest_y))
            else:
                self._image.im.paste(
                    cached_sprite.color.im,
                    (dest_x, dest_y, dest_x + spr_w, dest_y + spr_h),
                )

    def draw_item(self, item: RenderItem) -> None:
        """Render a single compositor item."""
        if not self._in_frame:
            msg = "draw_item called outside of begin_frame/end_frame block"
            raise RenderError(msg)

        self._frame_buffer.append(item)
        cached_sprite, anchor_s_x, anchor_s_y = self._prepare_item_sprite(item)
        if cached_sprite is not None:
            self._draw_cached_sprite(cached_sprite, anchor_s_x, anchor_s_y)

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
        if base_tex.size == (1, 1) and rot_norm == 0.0:
            px = base_tex.getpixel((0, 0))
            if not isinstance(px, (tuple, list)):
                px = (int(px or 0), int(px or 0), int(px or 0))
            final_alpha_f = max(0.0, min(1.0, op_quant * (tint_rgba[3] / 255.0)))
            final_alpha_byte = round(final_alpha_f * 255)
            r = round(px[0] * (tint_rgba[0] / 255.0))
            g = round(px[1] * (tint_rgba[1] / 255.0))
            b = round(px[2] * (tint_rgba[2] / 255.0))
            c_fill = (r, g, b) if self.mode == "RGB" else (r, g, b, 255)
            color = Image.new(self.mode, (draw_w, draw_h), c_fill)
            mask = None if final_alpha_byte == 255 else Image.new("L", (draw_w, draw_h), final_alpha_byte)
            return _CachedSprite(color, mask, -(draw_w * fx), -(draw_h * fy))

        color_tint = tint_rgba[:3]
        is_in_motion = self.adaptive_resampling and (item.asset_id in self._stage_cache_mgr.in_motion_assets)
        is_morphing = self.adaptive_resampling and (item.asset_id in self._stage_cache_mgr.morphing_assets)
        cur_resample = Image.Resampling.NEAREST if is_in_motion else self.resampling

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
            cur_resample,
        )

        geom = self._geom_cache.lookup(geom_key)
        if geom is None:
            base_is_opaque = self.asset_resolver.is_asset_opaque(item.asset_id)
            img = base_tex
            shared_img = True

            # A. Scale
            if (img.width, img.height) != (draw_w, draw_h):
                is_rot_ortho = (
                    rot_norm == 0.0
                    or abs(rot_norm - 90.0) < 1e-3
                    or abs(rot_norm - 180.0) < 1e-3
                    or abs(rot_norm - 270.0) < 1e-3
                )
                if base_is_opaque and is_rot_ortho:
                    src_img = (
                        self.asset_resolver.get_opaque_rgb_image(item.asset_id)
                        if self.mode == "RGB"
                        else base_tex
                    )
                    img = _resize_opaque(src_img, (draw_w, draw_h), resample=cur_resample)
                elif cur_resample == Image.Resampling.NEAREST:
                    img = base_tex.resize((draw_w, draw_h), resample=Image.Resampling.NEAREST)
                else:
                    def_w, def_h = (
                        (1920, 1080)
                        if (item.layer == "background" or item.asset_id.startswith("bg/"))
                        else (400, 800)
                    )
                    base_pre = self.asset_resolver.get_premultiplied_image(item.asset_id, def_w, def_h)
                    img = base_pre.resize((draw_w, draw_h), resample=cur_resample, reducing_gap=3.0).convert("RGBA")
                shared_img = False

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
                vx, vy = -rel_anchor_x, -rel_anchor_y

                if abs(rot_norm - 90.0) < 1e-3:
                    img = img.transpose(Image.Transpose.ROTATE_270)
                    shared_img = False
                    new_vx, new_vy = -vy, vx
                    is_ortho = True
                elif abs(rot_norm - 180.0) < 1e-3:
                    img = img.transpose(Image.Transpose.ROTATE_180)
                    shared_img = False
                    new_vx, new_vy = -vx, -vy
                    is_ortho = True
                elif abs(rot_norm - 270.0) < 1e-3:
                    img = img.transpose(Image.Transpose.ROTATE_90)
                    shared_img = False
                    new_vx, new_vy = vy, -vx
                    is_ortho = True
                else:
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    rot_resample = (
                        Image.Resampling.BICUBIC
                        if cur_resample == getattr(Image.Resampling, "LANCZOS", 1)
                        else cur_resample
                    )
                    (rot_w, rot_h), rot_matrix = rotate_expand_params(img.width, img.height, -rot_norm)
                    img = img.transform((rot_w, rot_h), Image.Transform.AFFINE, rot_matrix, resample=rot_resample)
                    shared_img = False
                    rad = math.radians(rot_norm)
                    cos_t, sin_t = math.cos(rad), math.sin(rad)
                    new_vx = vx * cos_t - vy * sin_t
                    new_vy = vx * sin_t + vy * cos_t

                rot_w, rot_h = img.size
                off_x = new_vx - (rot_w / 2.0)
                off_y = new_vy - (rot_h / 2.0)

                if not is_ortho and not is_in_motion:
                    bbox = _alpha_bbox(img)
                    if bbox is not None and bbox != (0, 0, rot_w, rot_h):
                        img = img.crop(bbox)
                        off_x += bbox[0]
                        off_y += bbox[1]
                    elif bbox is None:
                        return _CachedSprite(None, None, off_x, off_y)

            # D. Color tint
            if color_tint != (255, 255, 255):
                img = img.point(
                    get_rgba_lut(color_tint[0], color_tint[1], color_tint[2], 255, img.mode)
                )
                shared_img = False

            # D2. Tighten axis-aligned masked sprites to alpha bounding box
            if is_ortho and not base_is_opaque:
                bbox = _alpha_bbox(img)
                if bbox is None:
                    return _CachedSprite(None, None, off_x, off_y)
                if bbox != (0, 0, img.width, img.height):
                    img = img.crop(bbox)
                    off_x += bbox[0]
                    off_y += bbox[1]
                    shared_img = False

            # E. Split into color + mask
            if img.mode == "RGB" or (base_is_opaque and is_ortho):
                geom_color = img
                natural_mask = None
            elif is_in_motion and not base_is_opaque:
                geom_color = img
                natural_mask = img
            else:
                geom_color, natural_mask = _split_rgba(img, shared=shared_img)

            is_large = (draw_w * draw_h >= 500_000) or (item.layer == "background")
            skip_geom_cache = (is_in_motion and not is_ortho) or (is_morphing and is_large)
            geom = _GeomEntry(geom_color, natural_mask, off_x, off_y)
            if self._geom_cache.enabled and not skip_geom_cache:
                self._geom_cache.put(geom_key, geom, geom.nbytes)

        # F. Opacity modulation
        final_alpha_f = max(0.0, min(1.0, op_quant * (tint_rgba[3] / 255.0)))
        final_alpha_byte = round(final_alpha_f * 255)

        if final_alpha_byte == 255:
            return _CachedSprite(geom.color, geom.natural_mask, geom.off_x, geom.off_y)

        effective_alpha = quant_alpha if quant_alpha is not None else final_alpha_byte
        mask = geom.alpha_masks.get(effective_alpha)
        if mask is None:
            if geom.natural_mask is None:
                mask = Image.new("L", geom.color.size, effective_alpha)
            elif geom.natural_mask is geom.color:
                mask = geom.color.getchannel("A").point(_ALPHA_LUTS[effective_alpha])
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
            raise RenderError(msg)

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
        self._stage_cache_mgr.prev_item_geom = self._stage_cache_mgr.curr_item_geom
        self._stage_cache_mgr.prev_item_bboxes = self._stage_cache_mgr.curr_item_bboxes
        self.frame_count += 1
        self.clock.tick()

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
        compositor: Any,
        window_width: int,
        window_height: int,
    ) -> Image.Image:
        """Render all active compositor layers to the window/buffer."""
        return self._stage_cache_mgr.render_compositor(compositor, window_width, window_height)

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
        self._ui.draw_rect(
            x, y, width, height, color, border_color=border_color, border_width=border_width
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
        self._ui.draw_rect_outline(x, y, width, height, color, line_width=line_width)

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
        self._ui.draw_gradient_rect(x, y, width, height, top_color, bottom_color)

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
        font_family: str | None = None,
    ) -> None:
        """Draw a single line of text, honouring the requested anchor point."""
        self._ui.draw_text(
            x,
            y,
            text,
            font_size=font_size,
            color=color,
            bold=bold,
            italic=italic,
            anchor_x=anchor_x,
            anchor_y=anchor_y,
            cache=cache,
            font_family=font_family,
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
        self._ui.draw_image(
            asset_id, x, y, width, height, tint=tint, anchor_x=anchor_x, anchor_y=anchor_y
        )

    def measure_text(
        self,
        text: str,
        *,
        font_size: int = 14,
        bold: bool = False,
        italic: bool = False,
        cache: bool = True,
        font_family: str | None = None,
    ) -> tuple[float, float]:
        """Measure the pixel extents *text* would occupy at *font_size*."""
        return self._ui.measure_text(
            text,
            font_size=font_size,
            bold=bold,
            italic=italic,
            cache=cache,
            font_family=font_family,
        )

    def _apply_tint_to_image(self, image: Image.Image, tint: Color) -> Image.Image:
        """Return *image* with *tint* multiplied into its colour channels."""
        r, g, b, a = tint.to_rgba_bytes()
        return image.convert("RGBA").point(get_rgba_lut(r, g, b, a))

    def __len__(self) -> int:
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"PILRenderer(size={self.width}x{self.height}, "
            f"scale_mode={self.scale_mode.name}, "
            f"cache_items={len(self._sprite_cache)}, "
            f"fps={self.fps:.1f})"
        )
