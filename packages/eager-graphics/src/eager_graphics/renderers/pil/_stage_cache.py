"""Stage-layer caching, motion tracking, and dirty-rect compositing for PILRenderer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eager_core.types import BLACK, WHITE

from ._cache import _GeomEntry
from ._compat import Image
from ._constants import _QUANT_ALPHA_LUT, _WHITE_RGBA
from ._imaging import (
    _bboxes_intersect,
    _cluster_dirty_boxes,
    _resize_opaque,
    _union_bboxes,
)

if TYPE_CHECKING:
    from eager_core.layout import ViewportTransform
    from eager_core.protocols import RenderItem

    from ...compositor import StageCompositor


class StageCacheManager:
    """Manages 3-tier stage-layer caching and dirty-rect repainting for PILRenderer."""

    def __init__(self, renderer: Any) -> None:
        self._r = renderer
        self.bg_cache: Image.Image | None = None
        self.last_bg_items: list[RenderItem] | None = None
        self.last_bg_transform: ViewportTransform | None = None

        self.base_cache: Image.Image | None = None
        self.last_base_items: list[RenderItem] | None = None
        self.last_base_transform: ViewportTransform | None = None

        self.stage_cache: Image.Image | None = None
        self.last_stage_items: list[RenderItem] | None = None
        self.last_transform: ViewportTransform | None = None

        self.ui_dirty_bbox: tuple[int, int, int, int] | None = None
        self.prev_item_geom: dict[tuple[str, str, int], tuple[Any, ...]] = {}
        self.curr_item_geom: dict[tuple[str, str, int], tuple[Any, ...]] = {}
        self.in_motion_assets: set[str] = set()
        self.morphing_assets: set[str] = set()
        self.prev_item_bboxes: dict[tuple[str, str, int], tuple[int, int, int, int]] = {}
        self.curr_item_bboxes: dict[tuple[str, str, int], tuple[int, int, int, int]] = {}
        self.last_had_overlay: bool = False
        self.last_dirty_bbox: tuple[int, int, int, int] | None = None

    def clear(self) -> None:
        """Reset all stage caches and motion/dirty-rect tracking."""
        self.bg_cache = None
        self.last_bg_items = None
        self.last_bg_transform = None
        self.base_cache = None
        self.last_base_items = None
        self.last_base_transform = None
        self.stage_cache = None
        self.last_stage_items = None
        self.last_transform = None
        self.ui_dirty_bbox = None
        self.prev_item_geom.clear()
        self.curr_item_geom.clear()
        self.in_motion_assets.clear()
        self.morphing_assets.clear()
        self.prev_item_bboxes.clear()
        self.curr_item_bboxes.clear()
        self.last_had_overlay = False
        self.last_dirty_bbox = None

    def mark_ui_dirty(self, left: int, top: int, right: int, bottom: int) -> None:
        """Accumulate a screen-clamped UI dirty bounding box."""
        r = self._r
        if not (r.enable_stage_cache or r.enable_dirty_rects):
            return
        x0 = max(0, left)
        y0 = max(0, top)
        x1 = min(r.width, right)
        y1 = min(r.height, bottom)
        if x1 <= x0 or y1 <= y0:
            return
        box = (x0, y0, x1, y1)
        self.ui_dirty_bbox = box if self.ui_dirty_bbox is None else _union_bboxes(self.ui_dirty_bbox, box)

    def _update_motion_tracking(
        self,
        items: list[RenderItem],
        transform: ViewportTransform,
    ) -> None:
        """Track per-item quantized screen-space geometry to detect motion and morphing."""
        r = self._r
        if not r.enable_stage_cache and not r.enable_dirty_rects and not r.adaptive_resampling:
            self.curr_item_geom = {}
            self.in_motion_assets = set()
            self.morphing_assets = set()
            return

        curr_geom: dict[tuple[str, str, int], tuple[Any, ...]] = {}
        in_motion: set[str] = set()
        morphing: set[str] = set()
        for it in items:
            k = (it.layer, it.asset_id, it.z_order)
            t = it.tint
            tint_rgba = _WHITE_RGBA if t == WHITE else t.to_rgba_bytes()
            final_alpha_f = max(0.0, min(1.0, it.opacity * (tint_rgba[3] / 255.0)))
            quant_alpha = _QUANT_ALPHA_LUT[round(final_alpha_f * 255)]

            is_bg = it.layer == "background" or it.asset_id.startswith("bg/")
            def_w, def_h = (1920, 1080) if is_bg else (400, 800)
            base_tex = r.asset_resolver.get_image(it.asset_id, def_w, def_h)
            draw_w = max(1, round(base_tex.width * abs(it.scale_x) * transform.scale_x))
            draw_h = max(1, round(base_tex.height * abs(it.scale_y) * transform.scale_y))
            anchor_s_x = round(transform.offset_x + it.x * transform.scale_x)
            anchor_s_y = round(transform.offset_y + it.y * transform.scale_y)
            rot_norm = round(it.rotation % 360.0, 2) if it.rotation != 0.0 else 0.0

            g = (anchor_s_x, anchor_s_y, draw_w, draw_h, rot_norm, quant_alpha, tint_rgba)
            curr_geom[k] = g
            prev = self.prev_item_geom.get(k)
            if prev is not None and prev != g:
                in_motion.add(it.asset_id)
                if prev[2] != draw_w or prev[3] != draw_h or prev[4] != rot_norm:
                    morphing.add(it.asset_id)

        self.curr_item_geom = curr_geom
        self.in_motion_assets = in_motion
        self.morphing_assets = morphing

    def _compute_dirty_regions(
        self,
        actor_items: list[RenderItem],
        curr_bboxes: dict[tuple[str, str, int], tuple[int, int, int, int]],
        window_width: int,
        window_height: int,
    ) -> tuple[bool, bool, tuple[int, int, int, int] | None, list[tuple[int, int, int, int]]]:
        """Compute single or multi-rect dirty regions when background is cached."""
        r = self._r
        dirty_boxes: list[tuple[int, int, int, int]] = []
        for it in actor_items:
            k = (it.layer, it.asset_id, it.z_order)
            if it.asset_id in self.in_motion_assets:
                curr_bb = curr_bboxes.get(k)
                prev_bb = self.prev_item_bboxes.get(k)
                if curr_bb is not None and prev_bb is not None:
                    dirty_boxes.append(_union_bboxes(curr_bb, prev_bb))
                elif curr_bb is not None:
                    dirty_boxes.append(curr_bb)
                elif prev_bb is not None:
                    dirty_boxes.append(prev_bb)

        for k, prev_bb in self.prev_item_bboxes.items():
            if k[0] not in ("background", "overlay", "foreground") and k not in curr_bboxes:
                dirty_boxes.append(prev_bb)

        if self.ui_dirty_bbox is not None:
            dirty_boxes.append(self.ui_dirty_bbox)

        if not dirty_boxes:
            return False, False, None, []

        disjoint_clusters = _cluster_dirty_boxes(dirty_boxes)
        dirty_bbox = disjoint_clusters[0]
        for db in disjoint_clusters[1:]:
            dirty_bbox = _union_bboxes(dirty_bbox, db)

        screen_area = window_width * window_height
        total_cluster_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in disjoint_clusters)
        union_area = (dirty_bbox[2] - dirty_bbox[0]) * (dirty_bbox[3] - dirty_bbox[1])

        can_expand = (union_area < r.dirty_area_threshold * screen_area) or (
            len(disjoint_clusters) > 1 and total_cluster_area < 0.25 * screen_area
        )
        if can_expand:
            expanded = True
            while expanded:
                expanded = False
                for it in actor_items:
                    bb = curr_bboxes.get((it.layer, it.asset_id, it.z_order))
                    if bb is not None:
                        for idx, cl in enumerate(disjoint_clusters):
                            if _bboxes_intersect(bb, cl):
                                new_cl = _union_bboxes(cl, bb)
                                if new_cl != cl:
                                    disjoint_clusters[idx] = new_cl
                                    expanded = True
                                    break
                if expanded:
                    disjoint_clusters = _cluster_dirty_boxes(disjoint_clusters)
                    dirty_bbox = disjoint_clusters[0]
                    for db in disjoint_clusters[1:]:
                        dirty_bbox = _union_bboxes(dirty_bbox, db)
            total_cluster_area = sum((b[2] - b[0]) * (b[3] - b[1]) for b in disjoint_clusters)
            union_area = (dirty_bbox[2] - dirty_bbox[0]) * (dirty_bbox[3] - dirty_bbox[1])

        if (
            len(disjoint_clusters) > 1
            and total_cluster_area < 0.25 * screen_area
            and total_cluster_area < 0.60 * union_area
        ):
            return False, True, dirty_bbox, disjoint_clusters
        if union_area < r.dirty_area_threshold * screen_area:
            return True, False, dirty_bbox, disjoint_clusters
        return False, False, dirty_bbox, disjoint_clusters

    def _try_crossfade_backgrounds(self, bg_items: list[RenderItem]) -> int:
        """Fast-path opaque 2-background crossfade via Image.blend; returns skipped item count."""
        r = self._r
        if not (
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
            and r.asset_resolver.is_asset_opaque(bg_items[0].asset_id)
            and r.asset_resolver.is_asset_opaque(bg_items[1].asset_id)
            and bg_items[0].opacity > 0.0
            and bg_items[1].opacity > 0.0
            and bg_items[0].anchor == bg_items[1].anchor
            and bg_items[0].scale_x == bg_items[1].scale_x
            and bg_items[0].scale_y == bg_items[1].scale_y
        ):
            return 0

        trans = r._current_transform
        if trans is None:
            return 0
        base0 = r.asset_resolver.get_image(bg_items[0].asset_id)
        base1 = r.asset_resolver.get_image(bg_items[1].asset_id)
        if base0.size != base1.size:
            return 0

        fx, fy = bg_items[0].anchor.get_offset_factor()
        draw_w = max(1, round(base0.width * abs(bg_items[0].scale_x) * trans.scale_x))
        draw_h = max(1, round(base0.height * abs(bg_items[0].scale_y) * trans.scale_y))
        dest_x = round(trans.offset_x - draw_w * fx)
        dest_y = round(trans.offset_y - draw_h * fy)

        def _get_scaled_bg(asset_id: str, base_img: Image.Image) -> Image.Image:
            gkey = ("bg_crossfade", asset_id, draw_w, draw_h, r.resampling, r.mode)
            entry = r._geom_cache.lookup(gkey)
            if entry is not None:
                return entry.color
            src = r.asset_resolver.get_opaque_rgb_image(asset_id) if r.mode == "RGB" else base_img
            t = _resize_opaque(src, (draw_w, draw_h), resample=r.resampling) if src.size != (draw_w, draw_h) else src
            if r.mode == "RGB" and t.mode == "RGBA":
                t = t.convert("RGB")
            if r._geom_cache.enabled:
                geom = _GeomEntry(t, None, 0.0, 0.0)
                r._geom_cache.put(gkey, geom, geom.nbytes)
            return t

        tex0 = _get_scaled_bg(bg_items[0].asset_id, base0)
        tex1 = _get_scaled_bg(bg_items[1].asset_id, base1)

        if bg_items[0].opacity >= 1.0:
            blend_alpha = min(1.0, max(0.0, bg_items[1].opacity))
        else:
            total_op = bg_items[0].opacity + bg_items[1].opacity
            blend_alpha = min(1.0, max(0.0, bg_items[1].opacity / total_op)) if total_op > 0.0 else 0.5

        blended = Image.blend(tex0, tex1, blend_alpha)
        if r.mode == "RGB" and blended.mode == "RGBA":
            blended = blended.convert("RGB")

        if dest_x <= 0 and dest_y <= 0 and dest_x + draw_w >= r.width and dest_y + draw_h >= r.height:
            r._needs_clear = False
            if dest_x == 0 and dest_y == 0 and draw_w == r.width and draw_h == r.height:
                r._set_image(blended)
            else:
                r._image.paste(blended, (dest_x, dest_y))
        else:
            if r._needs_clear:
                r._execute_clear()
            r._image.paste(blended, (dest_x, dest_y))

        r._frame_buffer.extend(bg_items[:2])
        return 2

    def render_compositor(
        self,
        compositor: StageCompositor,
        window_width: int,
        window_height: int,
    ) -> Image.Image:
        """Render all active compositor layers using 3-tier stage caching."""
        r = self._r
        r.width = window_width
        r.height = window_height
        r._current_transform = compositor.layout.compute_viewport_transform(
            window_width, window_height, mode=r.scale_mode
        )

        items = compositor.render_list()
        particle_batches = (
            compositor.get_particle_batches(r._current_transform)
            if hasattr(compositor, "get_particle_batches")
            else []
        )

        # Tier 3 fast-path: identical stage as previous frame
        if (
            r.enable_stage_cache
            and not particle_batches
            and self.stage_cache is not None
            and self.last_stage_items is not None
            and len(self.last_stage_items) == len(items)
            and self.last_stage_items == items
            and self.last_transform == r._current_transform
            and self.stage_cache.size == (window_width, window_height)
        ):
            r._last_render_path = "Tier 3 (Stage Cache / UI Only)"
            r.last_frame = items
            r.frame_count += 1
            r.clock.tick()
            self.in_motion_assets = set()
            self.last_dirty_bbox = None
            if self.ui_dirty_bbox is not None:
                x0, y0, x1, y1 = self.ui_dirty_bbox
                w_box, h_box = x1 - x0, y1 - y0
                if w_box > 0 and h_box > 0 and (w_box * h_box < 0.8 * window_width * window_height):
                    r._image.paste(self.stage_cache.crop(self.ui_dirty_bbox), (x0, y0))
                else:
                    r._image.paste(self.stage_cache, (0, 0))
                self.ui_dirty_bbox = None
            else:
                r._image.paste(self.stage_cache, (0, 0))

            if hasattr(compositor, "lighting") and compositor.lighting.enabled:
                r.render_lightmap(compositor.lighting)
            return r._image

        self._update_motion_tracking(items, r._current_transform)

        bg_items: list[RenderItem] = []
        actor_items: list[RenderItem] = []
        top_items: list[RenderItem] = []
        for it in items:
            if it.layer == "background":
                bg_items.append(it)
            elif it.layer in ("overlay", "foreground") or it.z_order >= 200000:
                top_items.append(it)
            else:
                actor_items.append(it)

        base_items = bg_items + actor_items
        has_active_top_fx = bool(top_items) or bool(particle_batches)
        base_in_motion = any(it.asset_id in self.in_motion_assets for it in base_items)

        curr_bboxes: dict[tuple[str, str, int], tuple[int, int, int, int]] = {}
        if r.enable_dirty_rects:
            for it in actor_items:
                bb = r._compute_item_bbox(it, r._current_transform)
                if bb is not None:
                    curr_bboxes[(it.layer, it.asset_id, it.z_order)] = bb
        self.curr_item_bboxes = curr_bboxes

        can_use_base_cache = (
            r.enable_stage_cache
            and has_active_top_fx
            and self.base_cache is not None
            and self.last_base_items is not None
            and len(self.last_base_items) == len(base_items)
            and self.last_base_items == base_items
            and not base_in_motion
            and self.last_base_transform == r._current_transform
            and self.base_cache.size == (window_width, window_height)
        )
        can_use_bg_cache = (
            r.enable_stage_cache
            and bool(bg_items)
            and self.bg_cache is not None
            and self.last_bg_items is not None
            and len(self.last_bg_items) == len(bg_items)
            and self.last_bg_items == bg_items
            and self.last_bg_transform == r._current_transform
            and self.bg_cache.size == (window_width, window_height)
        )

        r.begin_frame()
        if can_use_base_cache and self.base_cache is not None:
            r._last_render_path = "Tier 2 (Base Scene Cache)"
            r._image.paste(self.base_cache, (0, 0))
            r._needs_clear = False
            r._frame_buffer.extend(base_items)
            r._render_top_fx(top_items, particle_batches)
            self.last_dirty_bbox = None
        elif can_use_bg_cache and self.bg_cache is not None:
            use_dirty_rect = False
            use_multi_rect = False
            dirty_bbox: tuple[int, int, int, int] | None = None
            disjoint_clusters: list[tuple[int, int, int, int]] = []
            if (
                r.enable_dirty_rects
                and self.last_stage_items is not None
                and not has_active_top_fx
                and not self.last_had_overlay
                and bool(self.in_motion_assets)
            ):
                use_dirty_rect, use_multi_rect, dirty_bbox, disjoint_clusters = (
                    self._compute_dirty_regions(actor_items, curr_bboxes, window_width, window_height)
                )

            if use_multi_rect and disjoint_clusters:
                r._last_render_path = "Tier 1 (Multi-Rect Dirty Repaint)"
                for cl in disjoint_clusters:
                    r._image.paste(self.bg_cache.crop(cl), (cl[0], cl[1]))
                r._needs_clear = False
                r._frame_buffer.extend(bg_items)
                for item in actor_items:
                    bb = curr_bboxes.get((item.layer, item.asset_id, item.z_order))
                    if bb is not None and any(_bboxes_intersect(bb, cl) for cl in disjoint_clusters):
                        r.draw_item(item)
                    else:
                        r._frame_buffer.append(item)
                self.ui_dirty_bbox = None
                self.last_dirty_bbox = dirty_bbox
            elif use_dirty_rect and dirty_bbox is not None:
                r._last_render_path = "Tier 1 (Dirty Rect Repaint)"
                r._image.paste(self.bg_cache.crop(dirty_bbox), (dirty_bbox[0], dirty_bbox[1]))
                r._needs_clear = False
                r._frame_buffer.extend(bg_items)
                for item in actor_items:
                    bb = curr_bboxes.get((item.layer, item.asset_id, item.z_order))
                    if bb is not None and _bboxes_intersect(bb, dirty_bbox):
                        r.draw_item(item)
                    else:
                        r._frame_buffer.append(item)
                self.ui_dirty_bbox = None
                self.last_dirty_bbox = dirty_bbox
            else:
                r._last_render_path = "Tier 1 (Full BG Blit)"
                r._image.paste(self.bg_cache, (0, 0))
                r._needs_clear = False
                r._frame_buffer.extend(bg_items)
                for item in actor_items:
                    r.draw_item(item)
                self.ui_dirty_bbox = None
                self.last_dirty_bbox = None

            if r.enable_stage_cache and has_active_top_fx and not base_in_motion:
                self.base_cache = r._snapshot(self.base_cache)
                self.last_base_items = list(base_items)
                self.last_base_transform = r._current_transform
            else:
                self.base_cache = None
                self.last_base_items = None
                self.last_base_transform = None

            r._render_top_fx(top_items, particle_batches)
        else:
            r._last_render_path = "Full Repaint"
            self.last_dirty_bbox = None
            r.clear(BLACK)

            skip_count = self._try_crossfade_backgrounds(bg_items)
            for item in bg_items[skip_count:]:
                r.draw_item(item)

            for pb in particle_batches:
                if pb.z_order < 200000:
                    r.draw_particles(pb)

            if r.enable_stage_cache and bg_items and not any(it.asset_id in self.in_motion_assets for it in bg_items):
                self.bg_cache = r._image.copy()
                self.last_bg_items = list(bg_items)
                self.last_bg_transform = r._current_transform
            else:
                self.bg_cache = None
                self.last_bg_items = None
                self.last_bg_transform = None

            for item in actor_items:
                r.draw_item(item)

            if r.enable_stage_cache and has_active_top_fx and not base_in_motion:
                self.base_cache = r._snapshot(self.base_cache)
                self.last_base_items = list(base_items)
                self.last_base_transform = r._current_transform
            else:
                self.base_cache = None
                self.last_base_items = None
                self.last_base_transform = None

            r._render_top_fx(top_items, particle_batches)

        if hasattr(compositor, "lighting") and compositor.lighting.enabled:
            r.render_lightmap(compositor.lighting)

        r.end_frame()

        if r.enable_stage_cache and not self.in_motion_assets and not particle_batches:
            self.stage_cache = r._snapshot(self.stage_cache)
        else:
            self.stage_cache = None
        self.last_stage_items = items
        self.last_transform = r._current_transform
        self.ui_dirty_bbox = None
        self.last_had_overlay = has_active_top_fx

        return r._image


__all__ = ["StageCacheManager"]
