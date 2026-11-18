"""Diagnostic telemetry and cache-reporting helpers for PILRenderer."""

from __future__ import annotations

from typing import Any

from ._compat import PIL, PIL_AVAILABLE, _detect_pillow_simd
from ._imaging import get_fade_lut, get_rgba_lut


def build_cache_info(renderer: Any) -> dict[str, Any]:
    """Return diagnostic metrics about sprite cache hits, misses, and current size."""
    total = renderer._cache_hits + renderer._cache_misses
    hit_ratio = (renderer._cache_hits / total) if total > 0 else 0.0
    return {
        "hits": renderer._cache_hits,
        "misses": renderer._cache_misses,
        "currsize": len(renderer._sprite_cache),
        "maxsize": renderer.max_cached_sprites,
        "hit_ratio": hit_ratio,
    }


def build_debug_info(renderer: Any) -> dict[str, Any]:
    """Return a structured diagnostic snapshot of the PIL renderer's optimization and cache state."""
    total_hits_misses = renderer._cache_hits + renderer._cache_misses
    hit_ratio = (renderer._cache_hits / total_hits_misses) if total_hits_misses > 0 else 0.0

    screen_area = renderer.width * renderer.height
    dirty_pct = 0.0
    if renderer._last_dirty_bbox is not None and screen_area > 0:
        x0, y0, x1, y1 = renderer._last_dirty_bbox
        dirty_area = max(0, x1 - x0) * max(0, y1 - y0)
        dirty_pct = (dirty_area / screen_area) * 100.0

    ui = renderer._ui
    lru_caches = (
        renderer._sprite_cache,
        renderer._geom_cache,
        ui.ui_image_cache,
        ui.text_mask_cache,
        ui.gradient_cache,
    )
    total_lru_bytes = sum(c.nbytes for c in lru_caches)
    total_lru_items = sum(len(c) for c in lru_caches)

    in_motion = sorted(renderer._stage_cache_mgr.in_motion_assets)
    filter_mode = "NEAREST" if (renderer.adaptive_resampling and in_motion) else "BILINEAR"
    sc = renderer._stage_cache_mgr

    return {
        "performance": {
            "fps": round(renderer.fps, 1),
            "fps_avg": round(renderer.fps_avg, 1),
            "fps_overall": round(renderer.fps_overall, 1),
            "frame_count": renderer.frame_count,
            "dt_ms": round(renderer.clock.dt * 1000.0, 2),
        },
        "stage_caching": {
            "last_render_path": renderer._last_render_path,
            "bg_cached": sc.bg_cache is not None,
            "base_cached": sc.base_cache is not None,
            "stage_cached": sc.stage_cache is not None,
            "last_dirty_bbox": renderer._last_dirty_bbox,
            "dirty_area_pct": round(dirty_pct, 1),
        },
        "motion_resampling": {
            "in_motion_assets": in_motion,
            "in_motion_count": len(in_motion),
            "adaptive_resampling": renderer.adaptive_resampling,
            "active_filter": filter_mode,
        },
        "tuning": {
            "preset": renderer.preset.value,
            "enable_stage_cache": renderer.enable_stage_cache,
            "enable_dirty_rects": renderer.enable_dirty_rects,
            "dirty_area_threshold": renderer.dirty_area_threshold,
            "cache_budget_bytes": renderer.cache_budget_bytes,
            "enable_patches": renderer.enable_patches,
        },
        "caches": {
            "sprite_lru": {
                "items": len(renderer._sprite_cache),
                "max_items": renderer.max_cached_sprites,
                "bytes": renderer._sprite_cache.nbytes,
                "hits": renderer._cache_hits,
                "misses": renderer._cache_misses,
                "hit_ratio": round(hit_ratio, 3),
            },
            "geom_lru": {"items": len(renderer._geom_cache), "bytes": renderer._geom_cache.nbytes},
            "ui_image_lru": {"items": len(ui.ui_image_cache), "bytes": ui.ui_image_cache.nbytes},
            "text_mask_lru": {"items": len(ui.text_mask_cache), "bytes": ui.text_mask_cache.nbytes},
            "gradient_lru": {"items": len(ui.gradient_cache), "bytes": ui.gradient_cache.nbytes},
            "total_lru_items": total_lru_items,
            "total_lru_bytes": total_lru_bytes,
            "luts": {
                "rgba": get_rgba_lut.cache_info().currsize,
                "fade": get_fade_lut.cache_info().currsize,
            },
            "fonts": len(ui.font_cache),
            "measurements": len(ui.measure_cache),
            "loaded_assets": len(renderer.asset_resolver._image_cache),
        },
        "backend": {
            "mode": renderer.mode,
            "scale_mode": renderer.scale_mode.name,
            "dimensions": (renderer.width, renderer.height),
            "simd": _detect_pillow_simd(),
            "pillow_version": getattr(PIL, "__version__", "unknown") if PIL_AVAILABLE else "unknown",
        },
    }


def format_debug_repr(renderer: Any) -> str:
    """Render debug_info() as a multi-line human-readable string report."""
    info = build_debug_info(renderer)
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
        f"Preset: {renderer.preset.value} | Pillow: {p_ver} ({simd_str}) | Mode: {backend['mode']} ({backend['dimensions'][0]}x{backend['dimensions'][1]})",
        "── Stage & Repaint ───────────────────────────────────",
        f"Render Path: {stage['last_render_path']}",
    ]

    if stage["last_dirty_bbox"] is not None:
        bb = stage["last_dirty_bbox"]
        lines.append(
            f"Dirty Rect: [{bb[0]},{bb[1]} -> {bb[2]},{bb[3]}] ({stage['dirty_area_pct']:.1f}% screen)"
        )
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
        f"Sub-caches: text: {caches['text_mask_lru']['items']}, geom: {caches['geom_lru']['items']}, ui: {caches['ui_image_lru']['items']}",
        f"LUTs: rgba:{caches['luts']['rgba']} fade:{caches['luts']['fade']} | Fonts: {caches['fonts']} | Textures: {caches['loaded_assets']}",
    ])
    return "\n".join(lines)


__all__ = ["build_cache_info", "build_debug_info", "format_debug_repr"]
