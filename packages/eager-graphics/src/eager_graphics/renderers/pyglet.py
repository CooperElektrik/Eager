"""Pyglet rendering backend and interactive player for Eager-Graphics."""

from __future__ import annotations

import functools
import hashlib
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

try:
    import pyglet
    from pyglet.graphics import Batch, Group
    from pyglet.image.codecs import ImageDecodeException
    from pyglet.shapes import Box, Rectangle
    from pyglet.text import Label
    from pyglet.window import Window, key, mouse
except ImportError as err:
    msg = "Pyglet is not installed. Install with 'pip install eager-graphics[hardware]' or 'pip install pyglet'."
    raise ImportError(msg) from err

from eager_core.input import InputAction
from eager_core.timing import FrameClock
from eager_core.types import BLACK, WHITE, Color

from eager_graphics.fonts import register_pyglet_default_font
from eager_graphics.layout import LayoutResolver, ViewportTransform
from eager_graphics.player import BasePlayer
from eager_graphics.protocol import RenderBackend, RenderItem
from eager_graphics.types import Anchor, ScaleMode

if TYPE_CHECKING:

    from eager_graphics.compositor import StageCompositor


logger = logging.getLogger(__name__)

__all__ = [
    "PygletAssetResolver",
    "PygletAudioBackend",
    "PygletPlayer",
    "PygletRenderer",
]


class PygletAssetResolver:
    """Loads and caches textures from disk, generating procedural placeholders when missing."""

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self._cache: dict[str, pyglet.image.AbstractImage] = {}
        self._asset_index: dict[str, Path] = {}
        if self.asset_dir is not None and self.asset_dir.is_dir():
            self._index_asset_dir(self.asset_dir)

    def _index_asset_dir(self, dir_path: Path) -> None:
        """Pre-index asset directory once at startup with a single directory walk."""
        try:
            for p in dir_path.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(dir_path).as_posix()
                    self._asset_index[rel] = p
                    rel_no_ext = str(Path(rel).with_suffix(""))
                    self._asset_index[rel_no_ext] = p
                    self._asset_index[p.stem] = p
        except OSError:
            pass

    def clear_cache(self) -> None:
        """Clear texture cache and refresh directory index."""
        self._cache.clear()
        self._asset_index.clear()
        if self.asset_dir is not None and self.asset_dir.is_dir():
            self._index_asset_dir(self.asset_dir)

    @staticmethod
    def _clamp_texture(tex: pyglet.image.AbstractImage) -> pyglet.image.AbstractImage:
        """Clamp texture edges to prevent filtering bleeding across boundaries."""
        try:
            from pyglet.gl import (
                GL_CLAMP_TO_EDGE,
                GL_TEXTURE_WRAP_S,
                GL_TEXTURE_WRAP_T,
                glBindTexture,
                glTexParameteri,
            )

            t = tex.get_texture()
            glBindTexture(t.target, t.id)
            glTexParameteri(t.target, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(t.target, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        except Exception:  # noqa: BLE001, S110
            pass
        return tex

    def get_texture(
        self,
        asset_id: str,
        default_width: int = 400,
        default_height: int = 800,
    ) -> pyglet.image.AbstractImage:
        """Retrieve texture from cache, load from disk, or generate fallback."""
        if asset_id in self._cache:
            return self._cache[asset_id]

        if asset_id == "__builtin_color_rect__":
            tex = pyglet.image.ImageData(1, 1, "RGBA", bytes([255, 255, 255, 255]))
            self._cache[asset_id] = tex
            return tex

        # 1. Attempt loading from disk if asset_dir configured
        if self.asset_dir is not None:
            resolved_base = self.asset_dir.resolve()
            candidate_ids = [asset_id]
            if not asset_id.startswith("characters/"):
                candidate_ids.append(f"characters/{asset_id}")
            if asset_id.startswith("bg/"):
                candidate_ids.append(f"backgrounds/{asset_id[3:]}")
            elif asset_id.startswith("backgrounds/"):
                candidate_ids.append(f"bg/{asset_id[12:]}")

            extensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"]
            for cid in candidate_ids:
                cand_path = (self.asset_dir / cid).resolve()
                if not cand_path.is_relative_to(resolved_base):
                    raise ValueError(f"Path traversal detected in asset ID: {asset_id}")
                if self._asset_index:
                    if cid in self._asset_index:
                        file_path = self._asset_index[cid].resolve()
                        if not file_path.is_relative_to(resolved_base):
                            raise ValueError(f"Path traversal detected in asset ID: {asset_id}")
                        try:
                            tex = self._clamp_texture(pyglet.image.load(str(file_path)).get_texture())
                            self._cache[asset_id] = tex
                            return tex
                        except (OSError, ImageDecodeException):
                            pass
                    for ext in extensions:
                        target = f"{cid}{ext}"
                        if target in self._asset_index:
                            file_path = self._asset_index[target].resolve()
                            if not file_path.is_relative_to(resolved_base):
                                raise ValueError(f"Path traversal detected in asset ID: {asset_id}")
                            try:
                                tex = self._clamp_texture(pyglet.image.load(str(file_path)).get_texture())
                                self._cache[asset_id] = tex
                                return tex
                            except (OSError, ImageDecodeException):
                                pass
                else:
                    for ext in extensions:
                        file_path = (self.asset_dir / f"{cid}{ext}").resolve()
                        if not file_path.is_relative_to(resolved_base):
                            raise ValueError(f"Path traversal detected in asset ID: {asset_id}")
                        if file_path.is_file():
                            try:
                                tex = self._clamp_texture(pyglet.image.load(str(file_path)).get_texture())
                                self._cache[asset_id] = tex
                                return tex
                            except (OSError, ImageDecodeException):
                                pass

        # 2. Generate placeholder texture
        img = self._generate_placeholder(asset_id, default_width, default_height)
        tex = self._clamp_texture(img.get_texture())
        self._cache[asset_id] = tex
        return tex

    # Alias matching the PIL resolver
    get_image = get_texture

    def _generate_placeholder(
        self,
        asset_id: str,
        width: int,
        height: int,
    ) -> pyglet.image.AbstractImage:
        """Procedurally generate a solid/gradient patterned placeholder texture."""
        is_bg = asset_id.startswith("bg/") or "background" in asset_id
        w = 1920 if is_bg else width
        h = 1080 if is_bg else height

        # Deterministic color derivation from asset_id string hash
        h_val = int(hashlib.md5(asset_id.encode("utf-8")).hexdigest()[:8], 16)
        r = (h_val & 0xFF)
        g = ((h_val >> 8) & 0xFF)
        b = ((h_val >> 16) & 0xFF)

        if is_bg:
            # Darker, muted tone for backgrounds
            r = 30 + (r % 60)
            g = 35 + (g % 60)
            b = 45 + (b % 70)
        else:
            # Vibrant, pastel tone for characters
            r = 100 + (r % 120)
            g = 100 + (g % 120)
            b = 100 + (b % 120)

        # 1. Attempt high-quality procedural generation via Pillow if available
        try:
            from PIL import Image, ImageChops, ImageDraw

            tw = min(w, 256)
            th = min(h, 256)
            base = Image.new("RGBA", (tw, th), (r, g, b, 255))
            grad_l = Image.linear_gradient("L").resize((tw, th), resample=Image.Resampling.BILINEAR)
            grad_mask = grad_l.point(lambda p: int(200 + p * 0.21))
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

            return pyglet.image.ImageData(w, h, "RGBA", base.tobytes(), pitch=-w * 4)
        except ImportError:
            pass

        # 2. Fast pure-Python gradient generation fallback
        num_bands = 32
        border_thickness = 4
        white4 = b"\xff\xff\xff\xff"
        w_mid = max(0, w - border_thickness * 2)

        parts: list[bytes] = []
        border_row = white4 * w
        parts.append(border_row * border_thickness)

        body_h = max(0, h - border_thickness * 2)
        band_h = body_h // num_bands
        rem = body_h % num_bands

        for i in range(num_bands):
            grad = 1.0 - (i / num_bands) * 0.25
            cr, cg, cb = int(r * grad), int(g * grad), int(b * grad)
            row = (
                (white4 * border_thickness)
                + (bytes([cr, cg, cb, 255]) * w_mid)
                + (white4 * border_thickness)
            )
            count = band_h + (1 if i < rem else 0)
            parts.append(row * count)

        parts.append(border_row * border_thickness)
        buf = b"".join(parts)
        return pyglet.image.ImageData(w, h, "RGBA", buf)


@functools.lru_cache(maxsize=4096)
def _cached_measure_text(
    font_name: str,
    font_size: int,
    bold: bool,
    italic: bool,
    text: str,
) -> tuple[float, float]:
    """Fast cached text extents calculation querying font metrics without instantiating Labels."""
    try:
        font = pyglet.font.load(
            font_name,
            size=font_size,
            weight="bold" if bold else "normal",
            italic=italic,
            dpi=72,
        )
        lines = text.split("\n")
        line_height = float(font.ascent - font.descent)
        if line_height <= 0:
            line_height = float(font_size) * 1.2
        width = max((float(font.get_text_size(line)[0]) for line in lines), default=0.0)
        height = line_height * max(1, len(lines))
        return (width, height)
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError):
        return (float(font_size) * 0.5 * len(text), float(font_size) * 1.2)


class PygletRenderer(RenderBackend):
    """Pyglet 2D stage renderer implementing RenderBackend and UIDrawBackend protocols."""

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        *,
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        window: Window | None = None,
        ui_batch: Batch | None = None,
    ) -> None:
        self.asset_resolver = PygletAssetResolver(asset_dir)
        self.scale_mode = scale_mode
        self.window = window
        self.width: int = window.width if window is not None else width
        self.height: int = window.height if window is not None else height
        self._current_transform: ViewportTransform | None = None
        self._cached_win_w: int = -1
        self._cached_win_h: int = -1
        self._cached_scale_mode: ScaleMode | None = None
        self._cached_virt_size: tuple[int, int] | None = None

        # Persistent Batches for Stage and UI
        self._stage_batch: Batch = Batch()
        self._ui_batch: Batch = ui_batch if ui_batch is not None else Batch()
        self._ui_flushed: bool = False

        # Group caches to allow draw call merging
        self._stage_groups: dict[int, Group] = {}
        self._ui_groups: dict[int, Group] = {}

        # Texture region cache keyed by (asset_id, anchor)
        self._region_cache: dict[tuple[str, Anchor], pyglet.image.TextureRegion] = {}

        # Stage Sprite pooling
        self._pooled_stage_sprites: list[pyglet.sprite.Sprite] = []
        self._active_sprites: list[pyglet.sprite.Sprite] = []
        self._sprite_cursor: int = 0

        # UI element pools
        self._rect_pool: list[Rectangle] = []
        self._box_pool: list[Box] = []
        self._grad_pool: list[tuple[Rectangle, tuple[tuple[int, int, int, int], tuple[int, int, int, int]] | None]] = []
        self._label_pool: list[Label] = []
        self._ui_sprite_pool: list[pyglet.sprite.Sprite] = []

        self._rect_cursor: int = 0
        self._box_cursor: int = 0
        self._grad_cursor: int = 0
        self._label_cursor: int = 0
        self._ui_sprite_cursor: int = 0
        self._ui_order: int = 0

        # Letterbox bars caching
        self._bar_left: Rectangle | None = None
        self._bar_right: Rectangle | None = None
        self._bar_bottom: Rectangle | None = None
        self._bar_top: Rectangle | None = None
        self._letterbox_bars: list[Rectangle] = []

        # Clear state tracking to deduplicate glClearColor calls
        self._last_clear_color: Color | None = None

        self.clock: FrameClock = FrameClock()
        self.frame_count: int = 0
        self.last_frame: list[RenderItem] = []

        # Initial viewport & letterbox setup
        self._update_viewport_and_letterbox()

    def set_window(self, window: Window) -> None:
        """Associate renderer with an active Pyglet Window."""
        self.window = window
        self.width = window.width
        self.height = window.height
        self._update_viewport_and_letterbox()

    def on_resize(self, width: int, height: int) -> None:
        """Update dimensions and recalculate viewport transform & letterbox bars."""
        self.width = width
        self.height = height
        self._update_viewport_and_letterbox()

    def clear_cache(self) -> None:
        """Clear cached textures, texture regions, and text metrics."""
        self.asset_resolver.clear_cache()
        self._region_cache.clear()
        self._stage_groups.clear()
        self._ui_groups.clear()
        _cached_measure_text.cache_clear()

    def _get_stage_group(self, z_order: int) -> Group:
        group = self._stage_groups.get(z_order)
        if group is None:
            group = Group(order=z_order)
            self._stage_groups[z_order] = group
        return group

    def _get_ui_group(self, order: int) -> Group:
        group = self._ui_groups.get(order)
        if group is None:
            group = Group(order=order)
            self._ui_groups[order] = group
        return group

    def _update_viewport_and_letterbox(self, layout: LayoutResolver | None = None) -> None:
        """Compute viewport transform and update persistent letterbox bars."""
        if layout is None:
            layout = LayoutResolver(1920, 1080)
        self._current_transform = layout.compute_viewport_transform(
            self.width,
            self.height,
            mode=self.scale_mode,
        )
        self._cached_win_w = self.width
        self._cached_win_h = self.height
        self._cached_scale_mode = self.scale_mode
        self._cached_virt_size = (layout.virtual_width, layout.virtual_height)

        trans = self._current_transform
        win_w, win_h = self.width, self.height
        lb_group = self._get_stage_group(10_000_000)

        # 1. Pillarbox bars (left & right)
        if trans.offset_x > 0:
            ox = float(trans.offset_x)
            if self._bar_left is None:
                self._bar_left = Rectangle(
                    0.0, 0.0, ox, float(win_h), color=(0, 0, 0, 255), batch=self._stage_batch, group=lb_group
                )
            else:
                if self._bar_left.x != 0.0:
                    self._bar_left.x = 0.0
                if self._bar_left.y != 0.0:
                    self._bar_left.y = 0.0
                if self._bar_left.width != ox:
                    self._bar_left.width = ox
                if self._bar_left.height != float(win_h):
                    self._bar_left.height = float(win_h)
                if not self._bar_left.visible:
                    self._bar_left.visible = True

            rx = float(win_w - trans.offset_x)
            if self._bar_right is None:
                self._bar_right = Rectangle(
                    rx, 0.0, ox, float(win_h), color=(0, 0, 0, 255), batch=self._stage_batch, group=lb_group
                )
            else:
                if self._bar_right.x != rx:
                    self._bar_right.x = rx
                if self._bar_right.y != 0.0:
                    self._bar_right.y = 0.0
                if self._bar_right.width != ox:
                    self._bar_right.width = ox
                if self._bar_right.height != float(win_h):
                    self._bar_right.height = float(win_h)
                if not self._bar_right.visible:
                    self._bar_right.visible = True
        else:
            if self._bar_left is not None and self._bar_left.visible:
                self._bar_left.visible = False
            if self._bar_right is not None and self._bar_right.visible:
                self._bar_right.visible = False

        # 2. Letterbox bars (bottom & top)
        if trans.offset_y > 0:
            oy = float(trans.offset_y)
            if self._bar_bottom is None:
                self._bar_bottom = Rectangle(
                    0.0, 0.0, float(win_w), oy, color=(0, 0, 0, 255), batch=self._stage_batch, group=lb_group
                )
            else:
                if self._bar_bottom.x != 0.0:
                    self._bar_bottom.x = 0.0
                if self._bar_bottom.y != 0.0:
                    self._bar_bottom.y = 0.0
                if self._bar_bottom.width != float(win_w):
                    self._bar_bottom.width = float(win_w)
                if self._bar_bottom.height != oy:
                    self._bar_bottom.height = oy
                if not self._bar_bottom.visible:
                    self._bar_bottom.visible = True

            ty = float(win_h - trans.offset_y)
            if self._bar_top is None:
                self._bar_top = Rectangle(
                    0.0, ty, float(win_w), oy, color=(0, 0, 0, 255), batch=self._stage_batch, group=lb_group
                )
            else:
                if self._bar_top.x != 0.0:
                    self._bar_top.x = 0.0
                if self._bar_top.y != ty:
                    self._bar_top.y = ty
                if self._bar_top.width != float(win_w):
                    self._bar_top.width = float(win_w)
                if self._bar_top.height != oy:
                    self._bar_top.height = oy
                if not self._bar_top.visible:
                    self._bar_top.visible = True
        else:
            if self._bar_bottom is not None and self._bar_bottom.visible:
                self._bar_bottom.visible = False
            if self._bar_top is not None and self._bar_top.visible:
                self._bar_top.visible = False

        self._letterbox_bars = [
            b for b in (self._bar_left, self._bar_right, self._bar_bottom, self._bar_top)
            if b is not None and b.visible
        ]

    def begin_frame(self) -> None:
        """Prepare for new frame rendering pass."""
        self._active_sprites.clear()
        self._sprite_cursor = 0
        self._rect_cursor = 0
        self._box_cursor = 0
        self._grad_cursor = 0
        self._label_cursor = 0
        self._ui_sprite_cursor = 0
        self._ui_order = 0
        self._ui_flushed = False

    def clear(self, color: Color = BLACK) -> None:
        """Clear OpenGL framebuffer with color, deduplicating glClearColor."""
        if self._last_clear_color != color:
            pyglet.gl.glClearColor(color.r, color.g, color.b, color.a)
            self._last_clear_color = color
        if self.window is not None:
            self.window.clear()

    def draw_item(self, item: RenderItem) -> None:
        """Render a single compositor item using pooled, batched sprites."""
        if self._current_transform is None:
            msg = "draw_item called before render_compositor set the viewport transform"
            raise RuntimeError(msg)

        if item.opacity <= 0.0 or not (item.scale_x and item.scale_y):
            return

        win_h = self.window.height if self.window is not None else self.height
        transform = self._current_transform

        # Load / resolve texture
        is_bg = item.layer == "background" or item.asset_id.startswith("bg/")
        def_w = 1920 if is_bg else 400
        def_h = 1080 if is_bg else 800
        texture = self.asset_resolver.get_texture(item.asset_id, def_w, def_h)

        # Compute effective element dimension in virtual coordinates
        eff_w = texture.width * abs(item.scale_x)
        eff_h = texture.height * abs(item.scale_y)

        # Anchor offset in virtual space
        fx, fy = item.anchor.get_offset_factor()

        # Project dimensions to physical screen coordinates
        draw_w = eff_w * transform.scale_x
        draw_h = eff_h * transform.scale_y

        # Anchor screen position in Pyglet coordinates (bottom-left origin, Y goes UP)
        anchor_s_x, anchor_s_y = transform.to_screen(item.x, item.y)
        pyglet_anchor_x = anchor_s_x
        pyglet_anchor_y = win_h - anchor_s_y

        # Configure or retrieve cached texture region with anchor matching item.anchor
        region_key = (item.asset_id, item.anchor)
        region = self._region_cache.get(region_key)
        if region is None:
            tex = texture.get_texture()
            region = tex.get_region(0, 0, tex.width, tex.height)
            region.anchor_x = round(texture.width * fx)
            region.anchor_y = round(texture.height * (1.0 - fy))
            self._region_cache[region_key] = region

        scale_x_dir = -1.0 if item.flip_h else 1.0
        if item.scale_x < 0:
            scale_x_dir = -scale_x_dir
        scale_y_dir = -1.0 if item.flip_v else 1.0
        if item.scale_y < 0:
            scale_y_dir = -scale_y_dir

        target_scale_x = scale_x_dir * (draw_w / texture.width)
        target_scale_y = scale_y_dir * (draw_h / texture.height)
        target_rotation = item.rotation

        # Opacity & Tint
        final_alpha = max(0.0, min(1.0, item.opacity * item.tint.a))
        target_color = (
            round(item.tint.r * 255),
            round(item.tint.g * 255),
            round(item.tint.b * 255),
            round(final_alpha * 255),
        )
        target_group = self._get_stage_group(item.z_order)

        if self._sprite_cursor < len(self._pooled_stage_sprites):
            sprite = self._pooled_stage_sprites[self._sprite_cursor]
        else:
            sprite = pyglet.sprite.Sprite(
                region,
                x=pyglet_anchor_x,
                y=pyglet_anchor_y,
                group=target_group,
                batch=self._stage_batch,
                subpixel=True,
            )
            self._pooled_stage_sprites.append(sprite)
        self._sprite_cursor += 1

        # Guard property mutations behind equality checks to prevent VBO re-uploads
        if sprite.image is not region:
            sprite.image = region
        if sprite.x != pyglet_anchor_x:
            sprite.x = pyglet_anchor_x
        if sprite.y != pyglet_anchor_y:
            sprite.y = pyglet_anchor_y
        if sprite.scale_x != target_scale_x:
            sprite.scale_x = target_scale_x
        if sprite.scale_y != target_scale_y:
            sprite.scale_y = target_scale_y
        if sprite.rotation != target_rotation:
            sprite.rotation = target_rotation
        if sprite.color != target_color:
            sprite.color = target_color
        if sprite.group is not target_group:
            sprite.group = target_group
        if not sprite.visible:
            sprite.visible = True

        self._active_sprites.append(sprite)

    def end_frame(self) -> None:
        """Conclude frame render pass, drawing stage elements and letterbox bars."""
        # Hide any unused stage sprites in the pool
        for i in range(self._sprite_cursor, len(self._pooled_stage_sprites)):
            sp = self._pooled_stage_sprites[i]
            if sp.visible:
                sp.visible = False

        self.frame_count += 1
        self.clock.tick()

        # Submit batched stage sprites and letterbox bars in a single OpenGL batch
        self._stage_batch.draw()

        # Flush any batched UI elements if UI drawing primitives were issued before end_frame
        if not self._ui_flushed and (
            self._rect_cursor > 0
            or self._box_cursor > 0
            or self._grad_cursor > 0
            or self._label_cursor > 0
            or self._ui_sprite_cursor > 0
        ):
            self.flush_ui()

    def flush_ui(self) -> None:
        """Draw all pending batched UI elements."""
        if self._ui_flushed:
            return

        # Hide any inactive pooled UI shapes & labels
        for i in range(self._rect_cursor, len(self._rect_pool)):
            r = self._rect_pool[i]
            if r.visible:
                r.visible = False
        for i in range(self._box_cursor, len(self._box_pool)):
            b = self._box_pool[i]
            if b.visible:
                b.visible = False
        for i in range(self._grad_cursor, len(self._grad_pool)):
            g, _ = self._grad_pool[i]
            if g.visible:
                g.visible = False
        for i in range(self._label_cursor, len(self._label_pool)):
            l = self._label_pool[i]
            if l.visible:
                l.visible = False
        for i in range(self._ui_sprite_cursor, len(self._ui_sprite_pool)):
            s = self._ui_sprite_pool[i]
            if s.visible:
                s.visible = False

        self._ui_batch.draw()
        self._ui_flushed = True

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
    ) -> None:
        """Render all active compositor layers to the window."""
        self.width = window_width
        self.height = window_height
        layout = compositor.layout
        if (
            self._current_transform is None
            or self._cached_win_w != window_width
            or self._cached_win_h != window_height
            or self._cached_scale_mode != self.scale_mode
            or self._cached_virt_size != (layout.virtual_width, layout.virtual_height)
        ):
            self._update_viewport_and_letterbox(layout)

        self.begin_frame()
        self.clear(BLACK)

        items = compositor.render_list()
        self.last_frame = items
        for item in items:
            self.draw_item(item)

        self.end_frame()

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"PygletRenderer(width={self.width}, height={self.height}, "
            f"frame_count={self.frame_count}, last_frame_items={len(self.last_frame)}, "
            f"fps={self.clock.fps:.1f})"
        )

    # ------------------------------------------------------------------ #
    # UIDrawBackend primitives
    #
    # Immediate-mode primitives consumed by the renderer-agnostic components
    # in eager_graphics.ui_components.  Those components work in window
    # pixels with a TOP-LEFT origin; Pyglet is natively bottom-left, so every
    # y coordinate is flipped through _flip_y before being issued.
    # ------------------------------------------------------------------ #

    def _flip_y(self, y: float, extent: float = 0.0) -> float:
        """Convert a top-left-origin *y* (optionally spanning *extent*) to Pyglet space."""
        win_h = float(self.window.height if self.window is not None else self.height)
        return win_h - y - extent

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
        """Draw a filled rectangle, optionally stroked with a border."""
        r_left, r_top = round(x), round(y)
        r_right, r_bottom = round(x + width), round(y + height)
        w = max(0.0, float(r_right - r_left))
        h = max(0.0, float(r_bottom - r_top))
        fx = float(r_left)
        fy = self._flip_y(float(r_top), h)
        col_rgba = color.to_rgba_bytes()
        group = self._get_ui_group(self._ui_order)
        self._ui_order += 1

        if self._rect_cursor < len(self._rect_pool):
            rect = self._rect_pool[self._rect_cursor]
        else:
            rect = Rectangle(fx, fy, w, h, color=col_rgba, batch=self._ui_batch, group=group)
            self._rect_pool.append(rect)
        self._rect_cursor += 1

        if rect.x != fx:
            rect.x = fx
        if rect.y != fy:
            rect.y = fy
        if rect.width != w:
            rect.width = w
        if rect.height != h:
            rect.height = h
        if rect.color != col_rgba:
            rect.color = col_rgba
        if rect.group is not group:
            rect.group = group
        if not rect.visible:
            rect.visible = True

        if border_color is not None and border_width > 0.0:
            b_group = self._get_ui_group(self._ui_order)
            self._ui_order += 1
            bw = float(border_width)
            b_col_rgba = border_color.to_rgba_bytes()

            if self._box_cursor < len(self._box_pool):
                box = self._box_pool[self._box_cursor]
            else:
                box = Box(fx, fy, w, h, thickness=bw, color=b_col_rgba, batch=self._ui_batch, group=b_group)
                self._box_pool.append(box)
            self._box_cursor += 1

            if box.x != fx:
                box.x = fx
            if box.y != fy:
                box.y = fy
            if box.width != w:
                box.width = w
            if box.height != h:
                box.height = h
            if box.thickness != bw:
                box.thickness = bw
            if box.color != b_col_rgba:
                box.color = b_col_rgba
            if box.group is not b_group:
                box.group = b_group
            if not box.visible:
                box.visible = True

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
        r_left, r_top = round(x), round(y)
        r_right, r_bottom = round(x + width), round(y + height)
        w = max(0.0, float(r_right - r_left))
        h = max(0.0, float(r_bottom - r_top))
        fx = float(r_left)
        fy = self._flip_y(float(r_top), h)
        bw = float(line_width)
        col_rgba = color.to_rgba_bytes()
        group = self._get_ui_group(self._ui_order)
        self._ui_order += 1

        if self._box_cursor < len(self._box_pool):
            box = self._box_pool[self._box_cursor]
        else:
            box = Box(fx, fy, w, h, thickness=bw, color=col_rgba, batch=self._ui_batch, group=group)
            self._box_pool.append(box)
        self._box_cursor += 1

        if box.x != fx:
            box.x = fx
        if box.y != fy:
            box.y = fy
        if box.width != w:
            box.width = w
        if box.height != h:
            box.height = h
        if box.thickness != bw:
            box.thickness = bw
        if box.color != col_rgba:
            box.color = col_rgba
        if box.group is not group:
            box.group = group
        if not box.visible:
            box.visible = True

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        """Draw a rectangle filled with a vertical linear gradient."""
        r_left, r_top = round(x), round(y)
        r_right, r_bottom = round(x + width), round(y + height)
        w = max(1.0, float(r_right - r_left))
        h = max(1.0, float(r_bottom - r_top))
        fx = float(r_left)
        fy = self._flip_y(float(r_top), h)
        group = self._get_ui_group(self._ui_order)
        self._ui_order += 1

        bot_rgba = bottom_color.to_rgba_bytes()
        top_rgba = top_color.to_rgba_bytes()
        grad_colors = (top_rgba, bot_rgba)

        if self._grad_cursor < len(self._grad_pool):
            rect, last_colors = self._grad_pool[self._grad_cursor]
        else:
            rect = Rectangle(fx, fy, w, h, color=bot_rgba, batch=self._ui_batch, group=group)
            last_colors = None
            self._grad_pool.append((rect, last_colors))
        idx = self._grad_cursor
        self._grad_cursor += 1

        if rect.x != fx:
            rect.x = fx
        if rect.y != fy:
            rect.y = fy
        if rect.width != w:
            rect.width = w
        if rect.height != h:
            rect.height = h
        if rect.group is not group:
            rect.group = group
        if not rect.visible:
            rect.visible = True

        if last_colors != grad_colors:
            bot = list(bot_rgba)
            top = list(top_rgba)
            vlist: Any = rect._vertex_list
            vlist.colors[:] = bot + bot + top + bot + top + top
            self._grad_pool[idx] = (rect, grad_colors)

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
        """Draw a single line of text at the requested anchor point."""
        pyglet_anchor_x: Literal["left", "center", "right"] = "left"
        if anchor_x == "center":
            pyglet_anchor_x = "center"
        elif anchor_x == "right":
            pyglet_anchor_x = "right"

        pyglet_anchor_y: Literal["top", "bottom", "center", "baseline"] = "top"
        if anchor_y == "middle":
            pyglet_anchor_y = "center"
        elif anchor_y == "bottom":
            pyglet_anchor_y = "bottom"

        fx = float(x)
        fy = self._flip_y(y)
        weight_str = "bold" if bold else "normal"
        col_rgba = color.to_rgba_bytes()
        group = self._get_ui_group(self._ui_order)
        self._ui_order += 1

        if self._label_cursor < len(self._label_pool):
            label = self._label_pool[self._label_cursor]
        else:
            label = Label(
                text,
                font_name=self._ui_font_name(),
                font_size=font_size,
                dpi=72,
                weight=weight_str,
                italic=italic,
                x=fx,
                y=fy,
                anchor_x=pyglet_anchor_x,
                anchor_y=pyglet_anchor_y,
                color=col_rgba,
                batch=self._ui_batch,
                group=group,
            )
            self._label_pool.append(label)
        self._label_cursor += 1

        # Guard property mutations behind equality checks to avoid layout recomputes
        if label.text != text:
            label.text = text
        if label.font_size != font_size:
            label.font_size = font_size
        if label.weight != weight_str:
            label.weight = weight_str
        if label.italic != italic:
            label.italic = italic
        if label.x != fx:
            label.x = fx
        if label.y != fy:
            label.y = fy
        if label.anchor_x != pyglet_anchor_x:
            label.anchor_x = pyglet_anchor_x
        if label.anchor_y != pyglet_anchor_y:
            label.anchor_y = pyglet_anchor_y
        if label.color != col_rgba:
            label.color = col_rgba
        if label.group is not group:
            label.group = group
        if not label.visible:
            label.visible = True

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
        """Draw a resolved asset scaled into the given box."""
        target_w = max(1, round(width))
        target_h = max(1, round(height))
        texture = self.asset_resolver.get_texture(asset_id, target_w, target_h)
        if texture is None:
            return

        dest_x = float(x)
        dest_y = float(y)
        if anchor_x == "center":
            dest_x -= target_w / 2.0
        elif anchor_x == "right":
            dest_x -= target_w
        if anchor_y == "middle":
            dest_y -= target_h / 2.0
        elif anchor_y == "bottom":
            dest_y -= target_h

        fy = self._flip_y(dest_y, target_h)
        target_scale_x = target_w / max(1, texture.width)
        target_scale_y = target_h / max(1, texture.height)
        target_color = tint.to_rgba_bytes() if tint != WHITE else (255, 255, 255, 255)
        group = self._get_ui_group(self._ui_order)
        self._ui_order += 1

        if self._ui_sprite_cursor < len(self._ui_sprite_pool):
            sprite = self._ui_sprite_pool[self._ui_sprite_cursor]
        else:
            sprite = pyglet.sprite.Sprite(
                texture,
                x=dest_x,
                y=fy,
                batch=self._ui_batch,
                group=group,
            )
            self._ui_sprite_pool.append(sprite)
        self._ui_sprite_cursor += 1

        if sprite.image is not texture:
            sprite.image = texture
        if sprite.x != dest_x:
            sprite.x = dest_x
        if sprite.y != fy:
            sprite.y = fy
        if sprite.scale_x != target_scale_x:
            sprite.scale_x = target_scale_x
        if sprite.scale_y != target_scale_y:
            sprite.scale_y = target_scale_y
        if sprite.color != target_color:
            sprite.color = target_color
        if sprite.group is not group:
            sprite.group = group
        if not sprite.visible:
            sprite.visible = True

    def _ui_font_name(self) -> str:
        """Return the font family used for UI text."""
        return register_pyglet_default_font()

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
        return _cached_measure_text(
            self._ui_font_name(),
            font_size,
            bold,
            italic,
            text,
        )

    # Alias for introspection and testing
    _cached_measure_text = staticmethod(_cached_measure_text)


class PygletAudioBackend:
    """Pyglet-based audio backend implementing AudioBackend protocol.

    Uses a `pyglet.media.Player` per channel for playback, volume, and looping.
    Supports whole-file looping and seamless loop points (loop_start/loop_end).
    Caches StaticSource for short SFX sounds to avoid repeated disk reads and decodes.
    """

    def __init__(self) -> None:
        self._players: dict[str, pyglet.media.Player] = {}
        self._loop_points: dict[str, tuple[float | None, float | None]] = {}
        self._static_sources: dict[str, pyglet.media.Source] = {}

    def play(
        self,
        channel: str,
        asset_path: str | Path,
        *,
        loop: bool = False,
        volume: float = 1.0,
        fade_in: float = 0.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        path_str = str(asset_path)
        if channel in self._players:
            old_player = self._players[channel]
            try:
                old_player.pause()
                old_player.delete()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to release previous player on channel %r: %s", channel, exc
                )

        is_sfx = not loop or channel in ("sfx", "voice", "ui", "sound")
        source: pyglet.media.Source | None = None

        if is_sfx:
            source = self._static_sources.get(path_str)
            if source is None:
                try:
                    loaded = pyglet.media.load(path_str, streaming=False)
                    static_src = (
                        pyglet.media.StaticSource(loaded)
                        if not isinstance(loaded, pyglet.media.StaticSource)
                        else loaded
                    )
                    self._static_sources[path_str] = static_src
                    source = static_src
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to load static audio source for channel %r from %r: %s",
                        channel,
                        path_str,
                        exc,
                    )

        if source is None:
            try:
                source = pyglet.media.load(path_str, streaming=True)
            except Exception as exc_stream:  # noqa: BLE001
                try:
                    source = pyglet.media.load(path_str, streaming=False)
                except Exception as exc_static:  # noqa: BLE001
                    logger.warning(
                        "Failed to load or decode audio for channel %r from %r "
                        "(streaming failed: %s; non-streaming failed: %s)",
                        channel,
                        path_str,
                        exc_stream,
                        exc_static,
                    )
                    return

        try:
            player = pyglet.media.Player()
            player.queue(source)
            player.volume = max(0.0, min(1.0, volume))
            self._loop_points[channel] = (loop_start, loop_end)

            if loop:
                if loop_start is None and loop_end is None:
                    player.loop = True
                else:
                    player.loop = False

                    @player.event
                    def on_player_eos() -> None:
                        seek_pos = loop_start if loop_start is not None else 0.0
                        try:
                            player.seek(seek_pos)
                            player.play()
                        except Exception as exc:  # noqa: BLE001
                            logger.warning(
                                "Failed to seek/loop audio on EOS for channel %r: %s",
                                channel,
                                exc,
                            )
            else:
                player.loop = False

            self._players[channel] = player
            player.play()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to play audio on channel %r from %r: %s",
                channel,
                path_str,
                exc,
            )
            self._players.pop(channel, None)
            self._loop_points.pop(channel, None)

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        player = self._players.get(channel)
        if player is not None:
            try:
                player.pause()
                player.delete()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error stopping player on channel %r: %s", channel, exc
                )
            del self._players[channel]
            self._loop_points.pop(channel, None)

    def set_volume(self, channel: str, volume: float) -> None:
        player = self._players.get(channel)
        if player is not None:
            player.volume = max(0.0, min(1.0, volume))

    def pause(self, channel: str) -> None:
        player = self._players.get(channel)
        if player is not None:
            player.pause()

    def resume(self, channel: str) -> None:
        player = self._players.get(channel)
        if player is not None:
            player.play()

    def is_playing(self, channel: str) -> bool:
        player = self._players.get(channel)
        return bool(player is not None and player.playing)

    def update(self, dt: float) -> None:
        for ch, player in list(self._players.items()):
            if not player.playing:
                continue
            loop_start, loop_end = self._loop_points.get(ch, (None, None))
            if loop_end is not None and player.time >= loop_end:
                seek_pos = loop_start if loop_start is not None else 0.0
                try:
                    player.seek(seek_pos)
                    player.play()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to seek/loop audio at loop_end on channel %r: %s",
                        ch,
                        exc,
                    )

    def shutdown(self) -> None:
        for ch, player in list(self._players.items()):
            try:
                player.pause()
                player.delete()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Error stopping player during shutdown on channel %r: %s", ch, exc
                )
        self._players.clear()
        self._loop_points.clear()
        self._static_sources.clear()


class PygletPlayer(BasePlayer, pyglet.window.Window):
    """Thin Pyglet window shell driving a :class:`GameSession`.

    The player owns no narrative state: story advancement, branching,
    rollback, typewriter reveal, and input semantics all live in the injected
    :class:`~eager_runtime.session.GameSession`.  Window events are forwarded to
    ``session.handle_input(...)`` and frames are produced by ``session.draw(...)``.
    """

    width: Any
    height: Any
    visible: Any
    vsync: Any

    def __init__(
        self,
        *,
        session: Any,
        width: int = 1280,
        height: int = 720,
        title: str = "Eager-Graphics Visual Novel (Pyglet)",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        vsync: bool = True,
        visible: bool = True,
        show_fps: bool = True,
        uncapped: bool = False,
    ) -> None:
        if uncapped:
            vsync = False
        pyglet.window.Window.__init__(
            self,
            width=width,
            height=height,
            caption=title,
            resizable=True,
            vsync=vsync,
            visible=visible,
        )
        BasePlayer.__init__(
            self,
            session=session,
            width=width,
            height=height,
            title=title,
            asset_dir=asset_dir,
            scale_mode=scale_mode,
            vsync=vsync,
            visible=visible,
            show_fps=show_fps,
            uncapped=uncapped,
        )

        # UI elements batch shared with PygletRenderer
        self._ui_batch = Batch()

        self.renderer = PygletRenderer(
            width=width,
            height=height,
            asset_dir=asset_dir,
            scale_mode=scale_mode,
            window=self,
            ui_batch=self._ui_batch,
        )

        # On-screen FPS debug overlay
        self._last_fps_update: float = 0.0
        self._fps_label: Label = Label(
            "",
            font_name="sans-serif",
            font_size=11,
            x=10,
            y=10,
            anchor_x="left",
            anchor_y="bottom",
            color=(230, 230, 230, 200),
        )

        # Step first beat if not starting in active menu
        self.step_initial_beat()

        # Schedule animation tick at 60 FPS or uncapped
        if self.uncapped:
            pyglet.clock.schedule(self.tick)
        else:
            pyglet.clock.schedule_interval(self.tick, 1.0 / 60.0)

    def on_resize(self, width: int, height: int) -> None:
        """Keep the UI components laid out against the new window size."""
        pyglet.window.Window.on_resize(self, width, height)
        BasePlayer.on_resize(self, width, height)
        self.renderer.on_resize(width, height)

    def close(self) -> None:
        """Close window and release audio mixer resources."""
        BasePlayer.close(self)
        pyglet.window.Window.close(self)

    def run(self) -> None:
        """Run the interactive visual-novel main loop (blocks until window closes)."""
        if self.uncapped:
            pyglet.app.run(interval=0.0)
        else:
            pyglet.app.run()

    def on_draw(self) -> None:
        """Render frame: stage graphics followed by UI textbox, choices, screens, and FPS."""
        self.session.draw(self.renderer, self.width, self.height)

        # Flush batched UI elements
        self.renderer.flush_ui()

        # 5. Render FPS counter
        if self.show_fps and self._fps_label is not None:
            self._draw_fps()

    def _draw_fps(self) -> None:
        """Update and draw the on-screen FPS counter overlay."""
        if self._fps_label is None:
            return
        now = time.monotonic()
        if not self._fps_label.text or (now - self._last_fps_update) >= 0.25:
            fps = self.renderer.fps
            fps_avg = self.renderer.fps_avg
            frames = self.renderer.frame_count
            self._fps_label.text = f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})"
            self._last_fps_update = now
        self._fps_label.draw()

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        """Handle mouse movement for screen and button hover states."""
        flipped_y = self.height - y
        self.handle_pointer_move(float(x), float(flipped_y))

    def on_mouse_drag(
        self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int
    ) -> None:
        """Handle mouse drag for sliders and interactive UI elements."""
        flipped_y = self.height - y
        self.handle_pointer_move(float(x), float(flipped_y))

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Handle mouse clicks for advancement, screens, or choice selection."""
        if button == mouse.RIGHT:
            self.session.handle_input(InputAction.GAME_MENU)
            self._sync_state()
            return

        if button != mouse.LEFT:
            return

        flipped_y = self.height - y
        self.handle_pointer_click(float(x), float(flipped_y))

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        """Handle keyboard input for advancing, choices, rollback, save/load, and menus."""
        sym_str = key.symbol_string(symbol)
        is_shift = bool(modifiers & key.MOD_SHIFT)
        self.handle_key_press(sym_str, is_shift=is_shift)

    def on_text(self, text: str) -> None:
        """Handle typed text input when an input prompt is active."""
        self.handle_text_input(text)

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        """Handle key releases (e.g. releasing Ctrl stops fast-forward skip)."""
        sym_str = key.symbol_string(symbol).lower()
        if sym_str in ("ctrl", "lctrl", "rctrl"):
            self.handle_skip_release()

    def on_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float) -> None:
        """Handle mouse wheel scrolling for rollback, roll-forward, or screen scrolling."""
        self.handle_scroll(scroll_y)
