"""Cache containers and sprite representations for the Pillow renderer."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from ._compat import Image
from ._imaging import _image_nbytes


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


__all__ = [
    "_CachedSprite",
    "_GeomEntry",
    "_ImageLRU",
]
