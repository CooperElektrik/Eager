"""Parallel execution pool and strip-split image kernels for Pillow rendering."""

from __future__ import annotations

import math
import os
import threading
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from ._compat import Image
from ._imaging import _resize_opaque

_MIN_STRIP_PIXELS: int = 500_000


class _ImmediateResult:
    """Synchronous result wrapper matching the Future interface."""

    __slots__ = ("_val",)

    def __init__(self, val: Any) -> None:
        self._val = val

    def result(self, timeout: float | None = None) -> Any:
        return self._val


class _RenderPool:
    """Manages worker threads for parallel image scaling and affine transformations.

    When ``max_workers <= 1``, runs all tasks synchronously on the calling thread
    with zero thread synchronization overhead.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        if max_workers is None:
            cpu_cnt = os.cpu_count() or 4
            self.num_workers = min(8, max(1, cpu_cnt))
        else:
            self.num_workers = max(1, max_workers)

        self._executor: ThreadPoolExecutor | None = None
        if self.num_workers > 1:
            self._executor = ThreadPoolExecutor(
                max_workers=self.num_workers,
                thread_name_prefix="EagerPILWorker",
            )

    @property
    def is_serial(self) -> bool:
        """True if running in single-threaded synchronous mode."""
        return self._executor is None or self.num_workers <= 1

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Submit *fn* to worker pool or execute synchronously if serial."""
        if self._executor is not None:
            return self._executor.submit(fn, *args, **kwargs)
        return _ImmediateResult(fn(*args, **kwargs))

    def map(self, fn: Callable[[Any], Any], iterable: Any) -> Iterator[Any]:
        """Map *fn* over *iterable* across worker threads (or sequentially if serial)."""
        if self._executor is not None:
            return self._executor.map(fn, iterable)
        return map(fn, iterable)

    def close(self) -> None:
        """Shutdown worker threads cleanly."""
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None


def rotate_expand_params(
    w: int, h: int, angle_deg: float
) -> tuple[tuple[int, int], tuple[float, float, float, float, float, float]]:
    """Compute output dimensions and reverse affine matrix identical to ``Image.rotate(expand=True)``."""
    angle = -math.radians(angle_deg % 360.0)
    matrix = [
        round(math.cos(angle), 15),
        round(math.sin(angle), 15),
        0.0,
        round(-math.sin(angle), 15),
        round(math.cos(angle), 15),
        0.0,
    ]
    center_x = w / 2.0
    center_y = h / 2.0
    a, b, _c, d, e, _f = matrix
    c_new = a * (-center_x) + b * (-center_y) + center_x
    f_new = d * (-center_x) + e * (-center_y) + center_y

    xx = [
        c_new,
        a * w + c_new,
        a * w + b * h + c_new,
        b * h + c_new,
    ]
    yy = [
        f_new,
        d * w + f_new,
        d * w + e * h + f_new,
        e * h + f_new,
    ]

    nw = math.ceil(max(xx)) - math.floor(min(xx))
    nh = math.ceil(max(yy)) - math.floor(min(yy))

    dx = -(nw - w) / 2.0
    dy = -(nh - h) / 2.0
    matrix[2] = c_new + (a * dx + b * dy)
    matrix[5] = f_new + (d * dx + e * dy)

    return (nw, nh), (matrix[0], matrix[1], matrix[2], matrix[3], matrix[4], matrix[5])


def resize_strips(
    pool: _RenderPool,
    img: Image.Image,
    size: tuple[int, int],
    resample: Any,
    *,
    is_opaque: bool = False,
) -> Image.Image:
    """Resize *img* to *size* across parallel horizontal strips (bit-identical to single resize)."""
    out_w, out_h = size
    if (
        pool.is_serial
        or (out_w * out_h < _MIN_STRIP_PIXELS)
        or out_h < (pool.num_workers * 8)
        or resample == Image.Resampling.NEAREST
        or threading.current_thread().name.startswith("EagerPILWorker")
    ):
        if is_opaque:
            return _resize_opaque(img, size, resample=resample)
        return img.resize(size, resample=resample)

    n = pool.num_workers
    rows = [(i * out_h // n, (i + 1) * out_h // n) for i in range(n)]
    src_w, src_h = img.width, img.height
    sy = src_h / out_h

    def _strip_task(r: tuple[int, int]) -> tuple[int, Any]:
        y0, y1 = r
        sub_h = y1 - y0
        box = (0, y0 * sy, src_w, y1 * sy)
        try:
            core_part = img.im.resize((out_w, sub_h), resample, box)
            return y0, img._new(core_part)
        except (AttributeError, TypeError, ValueError):
            crop = img.crop((0, round(y0 * sy), src_w, round(y1 * sy)))
            return y0, crop.resize((out_w, sub_h), resample=resample)

    strips = list(pool.map(_strip_task, rows))
    out = Image.new(img.mode, size)
    for y0, strip in strips:
        out.paste(strip, (0, y0))
    return out


def affine_strips(
    pool: _RenderPool,
    img: Image.Image,
    size: tuple[int, int],
    matrix: tuple[float, float, float, float, float, float],
    resample: Any,
) -> Image.Image:
    """Transform *img* via reverse affine *matrix* into *size* across horizontal strips."""
    out_w, out_h = size
    if (
        pool.is_serial
        or (out_w * out_h < _MIN_STRIP_PIXELS)
        or out_h < (pool.num_workers * 8)
        or resample == Image.Resampling.NEAREST
        or threading.current_thread().name.startswith("EagerPILWorker")
    ):
        return img.transform(size, Image.Transform.AFFINE, matrix, resample=resample)

    n = pool.num_workers
    rows = [(i * out_h // n, (i + 1) * out_h // n) for i in range(n)]
    a, b, c, d, e, f = matrix

    def _strip_task(r: tuple[int, int]) -> tuple[int, Image.Image]:
        y0, y1 = r
        sub_h = y1 - y0
        strip_mat = (a, b, c + b * y0, d, e, f + e * y0)
        return y0, img.transform(
            (out_w, sub_h), Image.Transform.AFFINE, strip_mat, resample=resample
        )

    strips = list(pool.map(_strip_task, rows))
    out = Image.new(img.mode, size)
    for y0, strip in strips:
        out.paste(strip, (0, y0))
    return out


__all__ = [
    "_RenderPool",
    "affine_strips",
    "resize_strips",
    "rotate_expand_params",
]
