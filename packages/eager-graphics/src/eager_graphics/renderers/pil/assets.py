"""Asset resolution and placeholder generation for the Pillow renderer."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ._compat import Image, ImageChops, ImageDraw, _check_pil_available
from ._constants import _EXTENSIONS, _PLACEHOLDER_GRAD_LUT
from ._imaging import _resize_opaque


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
            resolved_base = self.asset_dir.resolve()
            candidate_ids = [asset_id]
            if not asset_id.startswith("characters/"):
                candidate_ids.append(f"characters/{asset_id}")
            if asset_id.startswith("bg/"):
                candidate_ids.append(f"backgrounds/{asset_id[3:]}")
            elif asset_id.startswith("backgrounds/"):
                candidate_ids.append(f"bg/{asset_id[12:]}")

            for cid in candidate_ids:
                cand_path = (self.asset_dir / cid).resolve()
                if not cand_path.is_relative_to(resolved_base):
                    raise ValueError(f"Path traversal detected in asset ID: {asset_id}")
                for ext in _EXTENSIONS:
                    file_path = (self.asset_dir / f"{cid}{ext}").resolve()
                    if not file_path.is_relative_to(resolved_base):
                        raise ValueError(f"Path traversal detected in asset ID: {asset_id}")
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


__all__ = ["PILAssetResolver"]
