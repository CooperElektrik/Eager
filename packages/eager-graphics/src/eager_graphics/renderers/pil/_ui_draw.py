"""Immediate-mode UI drawing and UI asset caching for the Pillow renderer."""

from __future__ import annotations

from typing import Any

from eager_core.types import WHITE, Color

from ._cache import _CachedSprite, _ImageLRU
from ._compat import Image, ImageDraw, ImageFont
from ._constants import (
    _ALPHA_LUTS,
    _MAX_GRADIENT_CACHE,
    _MAX_TEXT_CACHE,
    _PIL_ANCHOR_X,
    _PIL_ANCHOR_Y,
    _WHITE_RGBA,
)
from ._imaging import _image_nbytes, _split_rgba, get_rgba_lut


class PILUIDrawer:
    """Handles immediate-mode UI primitives, text rendering, and UI-specific caches."""

    def __init__(
        self,
        renderer: Any,
        *,
        max_cached_sprites: int,
        cache_budget_bytes: int,
        disable_gradients: bool = False,
    ) -> None:
        self._r = renderer
        self.ui_image_cache: _ImageLRU = _ImageLRU(
            max_items=max_cached_sprites,
            max_bytes=cache_budget_bytes,
        )
        self.text_mask_cache: _ImageLRU = _ImageLRU(
            max_items=_MAX_TEXT_CACHE,
            max_bytes=32 * 1024 * 1024,
        )
        self.gradient_cache: _ImageLRU = _ImageLRU(
            max_items=0 if disable_gradients else _MAX_GRADIENT_CACHE,
            max_bytes=0 if disable_gradients else 64 * 1024 * 1024,
        )
        self.font_cache: dict[int | tuple[int, str], Any] = {}
        self.measure_cache: dict[tuple[Any, ...], tuple[float, float]] = {}

    def clear(self) -> None:
        """Clear all UI caches."""
        self.ui_image_cache.clear()
        self.text_mask_cache.clear()
        self.gradient_cache.clear()
        self.font_cache.clear()
        self.measure_cache.clear()

    def ui_font(self, font_size: int, font_family: str | None = None) -> Any:
        """Return a font at *font_size* and optional *font_family*, cached."""
        cache_key = (font_size, font_family) if font_family else font_size
        font = self.font_cache.get(cache_key)
        if font is not None:
            return font
        if font_family and font_family not in ("sans-serif", "default"):
            try:
                font = ImageFont.truetype(font_family, font_size)
                self.font_cache[cache_key] = font
                return font
            except (OSError, ValueError):
                pass
        try:
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            font = ImageFont.load_default()
        self.font_cache[cache_key] = font
        return font

    def blend_rect(self, x0: int, y0: int, x1: int, y1: int, color: Color) -> None:
        """Fill region (x0, y0, x1, y1) with *color*, alpha-blending if translucent."""
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            return
        c_rgba = _WHITE_RGBA if color == WHITE else color.to_rgba_bytes()
        alpha = c_rgba[3]
        if alpha <= 0:
            return
        r = self._r
        if alpha == 255:
            c_bytes = c_rgba[:3] if r.mode == "RGB" else c_rgba
            r._image.paste(c_bytes, (x0, y0, x1, y1))
        elif r.mode == "RGB":
            r._rgba_draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=c_rgba)
        elif r.mode == "RGBA":
            overlay = Image.new("RGBA", (w, h), c_rgba)
            r._image.alpha_composite(overlay, dest=(x0, y0))
        else:
            mask = Image.new("L", (w, h), alpha)
            r._image.paste(c_rgba[:3], (x0, y0, x1, y1), mask)

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
        r = self._r
        if r._needs_clear:
            r._execute_clear()
        left, top = float(x), float(y)
        right, bottom = left + float(width), top + float(height)
        r_left, r_top = round(left), round(top)
        r_right, r_bottom = round(right), round(bottom)
        if r_right <= r_left or r_bottom <= r_top:
            return

        r._mark_ui_dirty(r_left, r_top, r_right + 1, r_bottom + 1)
        self.blend_rect(r_left, r_top, r_right, r_bottom, color)

        if border_color is not None and border_width > 0.0:
            self.draw_rect_outline(x, y, width, height, border_color, line_width=border_width)

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
        r = self._r
        if r._needs_clear:
            r._execute_clear()
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

        r._mark_ui_dirty(r_left, r_top, r_right + 1, r_bottom + 1)
        if rw <= 2 * bw or rh <= 2 * bw:
            self.blend_rect(r_left, r_top, r_right, r_bottom, color)
        else:
            self.blend_rect(r_left, r_top, r_right, r_top + bw, color)
            self.blend_rect(r_left, r_bottom - bw, r_right, r_bottom, color)
            self.blend_rect(r_left, r_top + bw, r_left + bw, r_bottom - bw, color)
            self.blend_rect(r_right - bw, r_top + bw, r_right, r_bottom - bw, color)

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
        r = self._r
        if r._needs_clear:
            r._execute_clear()
        w = max(1, round(width))
        h = max(2, round(height))
        left = round(x)
        top = round(y)
        r._mark_ui_dirty(left, top, left + w + 1, top + h + 1)

        tc = top_color.to_rgba_bytes()
        bc = bottom_color.to_rgba_bytes()
        cache_key = (w, h, tc, bc, r.mode)
        entry = self.gradient_cache.lookup(cache_key)

        if entry is None:
            grad = Image.new("RGBA", (1, h))
            inv = 1.0 / (h - 1)
            step_r = (bc[0] - tc[0]) * inv
            step_g = (bc[1] - tc[1]) * inv
            step_b = (bc[2] - tc[2]) * inv
            step_a = (bc[3] - tc[3]) * inv
            r0, g0, b0, a0 = tc
            pixels = [
                (
                    round(r0 + y_step * step_r),
                    round(g0 + y_step * step_g),
                    round(b0 + y_step * step_b),
                    round(a0 + y_step * step_a),
                )
                for y_step in range(h)
            ]
            grad.putdata(pixels)
            grad_resized = grad.resize((w, h), Image.Resampling.BILINEAR)

            if r.mode == "RGBA":
                entry = (grad_resized, None)
                nbytes = _image_nbytes(grad_resized)
            elif tc[3] == 255 and bc[3] == 255:
                color_plane = grad_resized.convert("RGB")
                entry = (color_plane, None)
                nbytes = _image_nbytes(color_plane)
            else:
                entry = (grad_resized, grad_resized)
                nbytes = _image_nbytes(grad_resized)

            if self.gradient_cache.enabled:
                self.gradient_cache.put(cache_key, entry, nbytes)

        color_plane, mask_plane = entry
        if r.mode == "RGBA":
            r._image.alpha_composite(color_plane, (left, top))
        elif mask_plane is not None:
            r._image.paste(color_plane, (left, top), mask_plane)
        else:
            r._image.paste(color_plane, (left, top))

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
        if not text:
            return
        r = self._r
        if r._needs_clear:
            r._execute_clear()

        pil_anchor_x = _PIL_ANCHOR_X.get(anchor_x, "l")
        pil_anchor_y = _PIL_ANCHOR_Y.get(anchor_y, "t")
        anchor = f"{pil_anchor_x}{pil_anchor_y}"

        color_rgba = _WHITE_RGBA if color == WHITE else color.to_rgba_bytes()
        color_bytes = color_rgba[:3] if r.mode == "RGB" else color_rgba

        if (
            color_rgba[3] == 255
            and not italic
            and not bold
            and (not cache or not self.text_mask_cache.enabled)
        ):
            font = self.ui_font(font_size, font_family=font_family)
            if r.enable_dirty_rects:
                w_est, h_est = self.measure_text(
                    text, font_size=font_size, cache=cache, font_family=font_family
                )
                left = (
                    (x - w_est / 2.0)
                    if anchor_x == "center"
                    else ((x - w_est) if anchor_x == "right" else x)
                )
                top = (
                    (y - h_est / 2.0)
                    if anchor_y == "middle"
                    else ((y - h_est) if anchor_y == "bottom" else y)
                )
                r._mark_ui_dirty(round(left), round(top), round(left + w_est + 2), round(top + h_est + 2))
            r._draw.text((float(x), float(y)), text, font=font, fill=color_bytes, anchor=anchor)
            return

        cache_key = (text, font_size, anchor, bold, italic, font_family)
        cached = self.text_mask_cache.lookup(cache_key)
        if cached is None:
            cached = self._rasterize_text_mask(
                text, font_size=font_size, anchor=anchor, bold=bold, italic=italic, font_family=font_family
            )
            if cache:
                self.text_mask_cache.put(
                    cache_key,
                    cached,
                    _image_nbytes(cached[0]) if cached[0] is not None else 0,
                )

        mask, rel_x, rel_y = cached
        if mask is not None:
            dest_x = round(x + rel_x)
            dest_y = round(y + rel_y)
            r._mark_ui_dirty(dest_x, dest_y, dest_x + mask.width, dest_y + mask.height)
            alpha = color_rgba[3]
            if alpha <= 0:
                return
            if alpha < 255:
                eff_mask = mask.point(_ALPHA_LUTS[alpha])
                dest_color = color_rgba[:3] if r.mode == "RGB" else color_rgba[:3] + (255,)
                r._image.paste(dest_color, (dest_x, dest_y), eff_mask)
            else:
                r._image.paste(color_bytes, (dest_x, dest_y), mask)
        else:
            w_est, h_est = self.measure_text(text, font_size=font_size, cache=cache)
            r._mark_ui_dirty(round(x), round(y), round(x + w_est), round(y + h_est))
            ImageDraw.Draw(r._image).text(
                (float(x), float(y)),
                text,
                font=self.ui_font(font_size),
                fill=color_bytes,
                anchor=anchor,
            )

    def _rasterize_text_mask(
        self,
        text: str,
        *,
        font_size: int,
        anchor: str,
        bold: bool,
        italic: bool,
        font_family: str | None,
    ) -> tuple[Image.Image | None, int, int]:
        """Rasterize *text* into an L-mode alpha mask with (rel_x, rel_y) offsets."""
        font = self.ui_font(font_size, font_family=font_family)
        stroke_w = 1 if bold else 0
        try:
            l, t, r_b, b = font.getbbox(text, anchor=anchor, stroke_width=stroke_w)
        except (AttributeError, ValueError, TypeError):
            try:
                l, t, r_b, b = font.getbbox(text, anchor=anchor)
                stroke_w = 0
            except (AttributeError, ValueError, TypeError):
                return (None, 0, 0)

        w, h = r_b - l, b - t
        if w <= 0 or h <= 0:
            return (None, 0, 0)
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).text(
            (-l, -t), text, font=font, fill=255, anchor=anchor, stroke_width=stroke_w
        )
        if italic:
            shear_pad = max(1, round(h * 0.22))
            mask = mask.transform(
                (w + shear_pad, h),
                Image.Transform.AFFINE,
                (1.0, 0.22, -shear_pad * 0.5, 0.0, 1.0, 0.0),
            )
        return (mask, l, t)

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
        r = self._r
        if r._needs_clear:
            r._execute_clear()
        source = r.asset_resolver.get_image(asset_id)
        if source is None:
            return

        target_w = max(1, round(width))
        target_h = max(1, round(height))
        t_rgba = _WHITE_RGBA if tint == WHITE else tint.to_rgba_bytes()
        cache_key = (asset_id, target_w, target_h, t_rgba)

        sprite = self.ui_image_cache.lookup(cache_key)
        if sprite is None:
            img = source
            if img.size != (target_w, target_h):
                img = img.resize((target_w, target_h), resample=r.resampling, reducing_gap=3.0)
            if tint != WHITE:
                tr, tg, tb, ta = tint.to_rgba_bytes()
                img = img.convert("RGBA").point(get_rgba_lut(tr, tg, tb, ta))
            color, mask = _split_rgba(img, shared=False)
            sprite = _CachedSprite(color, mask, 0.0, 0.0)
            self.ui_image_cache.put(cache_key, sprite, sprite.nbytes)

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
        r._mark_ui_dirty(dest_x, dest_y, dest_x + target_w, dest_y + target_h)
        if sprite.color is not None:
            if sprite.is_opaque:
                r._image.paste(sprite.color, (dest_x, dest_y))
            elif sprite.mask is not None:
                r._image.paste(sprite.color, (dest_x, dest_y), sprite.mask)
            elif r.mode == "RGBA":
                r._image.alpha_composite(sprite.image, dest=(dest_x, dest_y))
            else:
                r._image.paste(sprite.color, (dest_x, dest_y))

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
        cache_key = (
            (text, font_size)
            if not bold and not italic and not font_family
            else (text, font_size, bold, italic, font_family)
        )
        cached = self.measure_cache.get(cache_key)
        if cached is not None:
            return cached

        font = self.ui_font(font_size, font_family=font_family)
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
                    draw = ImageDraw.Draw(self._r._image)
                    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
                    result = (float(right - left), float(bottom - top))
                except (AttributeError, ValueError, TypeError):
                    result = (float(font_size) * 0.5 * len(text), float(font_size) * 1.2)

        if cache and len(self.measure_cache) < 2048:
            self.measure_cache[cache_key] = result
        return result


__all__ = ["PILUIDrawer"]
