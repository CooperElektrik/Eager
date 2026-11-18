"""Asset resolution and placeholder generation for the Pillow renderer."""

from __future__ import annotations

import threading
from pathlib import Path

from eager.backends._assets import resolve_visual_asset_candidates, validate_asset_path
from eager.backends._placeholder import generate_placeholder_pil

from ._compat import Image, _check_pil_available
from ._imaging import _resize_opaque


class PILAssetResolver:
    """Loads and caches textures from disk, generating procedural placeholders when missing."""

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        _check_pil_available()
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self._image_cache: dict[str, Image.Image] = {}
        self._opaque_cache: dict[str, bool] = {}
        self._premultiplied_cache: dict[str, Image.Image] = {}
        self._opaque_rgb_cache: dict[str, Image.Image] = {}
        self._lock: threading.RLock = threading.RLock()

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

        with self._lock:
            img = self._image_cache.get(asset_id)
            if img is not None:
                return img

            if asset_id == "__builtin_color_rect__":
                img = Image.new("RGBA", (1, 1), (255, 255, 255, 255))
                self._image_cache[asset_id] = img
                self._opaque_cache[asset_id] = True
                return img

        # Composite layered sprite resolution (e.g. "hoshiko/base+uniform+smile")
        if "+" in asset_id and "/" in asset_id:
            prefix, layers_str = asset_id.rsplit("/", 1)
            layer_names = [pt.strip() for pt in layers_str.split("+") if pt.strip()]
            if len(layer_names) > 1:
                base_img = self.get_image(
                    f"{prefix}/{layer_names[0]}", default_width, default_height
                ).copy()
                for layer in layer_names[1:]:
                    overlay = self.get_image(f"{prefix}/{layer}", default_width, default_height)
                    if overlay.size != base_img.size:
                        full_overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
                        full_overlay.paste(overlay, (0, 0))
                        base_img.alpha_composite(full_overlay)
                    else:
                        base_img.alpha_composite(overlay)

                extrema = base_img.getextrema()
                is_opaque = len(extrema) >= 4 and extrema[3][0] == 255
                self._image_cache[asset_id] = base_img
                self._opaque_cache[asset_id] = is_opaque
                return base_img
            if len(layer_names) == 1:
                return self.get_image(
                    f"{prefix}/{layer_names[0]}", default_width, default_height
                )

        # Direct absolute file path check (e.g., save slot thumbnails from save directory)
        direct_path = Path(asset_id)
        if direct_path.is_absolute() and direct_path.is_file():
            try:
                with Image.open(direct_path) as raw_img:
                    is_opaque = raw_img.mode in ("RGB", "L", "1") or direct_path.suffix.lower() in (
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

        # 1. Attempt loading from disk if asset_dir configured
        if self.asset_dir is not None:
            for candidate in resolve_visual_asset_candidates(asset_id):
                file_path = validate_asset_path(self.asset_dir, candidate, asset_id)
                if file_path.is_file():
                    try:
                        with Image.open(file_path) as raw_img:
                            is_opaque = raw_img.mode in ("RGB", "L", "1") or file_path.suffix.lower() in (
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
        with self._lock:
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

    def get_opaque_rgb_image(
        self,
        asset_id: str,
        default_width: int = 400,
        default_height: int = 800,
    ) -> Image.Image:
        """Retrieve opaque RGB image for zero-alpha fast-path blitting and resampling."""
        with self._lock:
            img_rgb = self._opaque_rgb_cache.get(asset_id)
            if img_rgb is not None:
                return img_rgb
            img = self.get_image(asset_id, default_width, default_height)
            img_rgb = img.convert("RGB")
            self._opaque_rgb_cache[asset_id] = img_rgb
            return img_rgb

    def clear_cache(self) -> None:
        """Clear decoded texture cache so disk updates are reflected on hot-reload."""
        with self._lock:
            self._image_cache.clear()
            self._opaque_cache.clear()
            self._premultiplied_cache.clear()
            self._opaque_rgb_cache.clear()

    def is_asset_opaque(self, asset_id: str) -> bool:
        """Check whether an asset has fully opaque alpha (255 everywhere)."""
        if asset_id in self._opaque_cache:
            return self._opaque_cache[asset_id]
        self.get_image(asset_id)
        return self._opaque_cache.get(asset_id, False)

    def _generate_placeholder(
        self,
        asset_id: str,
        width: int,
        height: int,
    ) -> tuple[Image.Image, bool]:
        """Procedurally generate a solid/gradient patterned placeholder texture."""
        img, is_opaque = generate_placeholder_pil(asset_id, width, height)
        if is_opaque and img.size != (width, height):
            # Preserve _resize_opaque fast path if caller expects it
            _ = _resize_opaque
        return img, is_opaque


__all__ = ["PILAssetResolver"]
