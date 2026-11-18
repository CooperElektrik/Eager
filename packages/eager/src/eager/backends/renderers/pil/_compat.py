"""Pillow and Tkinter dependency detection and compatibility helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tkinter as tk

    import PIL
    from PIL import Image, ImageChops, ImageDraw, ImageFont

    PIL_AVAILABLE: bool = True
    TKINTER_AVAILABLE: bool = True
    _pil_import_error: Exception | None = None
    _TclError: type[BaseException] = Exception
else:
    try:
        import PIL
        from PIL import Image, ImageChops, ImageDraw, ImageFont

        PIL_AVAILABLE = True
        _pil_import_error = None
    except ImportError as err:
        PIL_AVAILABLE = False
        _pil_import_error = err
        PIL = None
        Image = None
        ImageChops = None
        ImageDraw = None
        ImageFont = None

    try:
        import tkinter as tk

        TKINTER_AVAILABLE = True
        _TclError = tk.TclError
    except (ImportError, AttributeError):
        tk = None
        TKINTER_AVAILABLE = False
        _TclError = Exception


def _detect_pillow_simd() -> str:
    """Detect whether Pillow is the standard build or the SIMD-accelerated fork."""
    if not PIL_AVAILABLE:
        return "None"
    try:
        from PIL import features

        if hasattr(features, "check_feature"):
            try:
                if features.check_feature("simd"):
                    return "SIMD"
            except (ValueError, TypeError):
                pass
    except Exception:  # noqa: BLE001, S110
        pass

    try:
        import importlib.metadata

        dist = importlib.metadata.distribution("pillow-simd")
        return f"SIMD {dist.version}"
    except Exception:  # noqa: BLE001, S110
        pass

    version = getattr(PIL, "__version__", "")
    if ".post" in version or "simd" in version.lower():
        return f"SIMD ({version})"

    return "Standard"


def _check_pil_available() -> None:
    if not PIL_AVAILABLE:
        msg = (
            "Pillow is not installed. Install with 'pip install eager-graphics[software]' "
            "(or 'pip install pillow'). For SIMD-accelerated software rendering use "
            "'pip install eager-graphics[software-simd]'."
        )
        raise ImportError(msg) from _pil_import_error


__all__ = [
    "PIL",
    "PIL_AVAILABLE",
    "TKINTER_AVAILABLE",
    "Image",
    "ImageChops",
    "ImageDraw",
    "ImageFont",
    "_TclError",
    "_check_pil_available",
    "_detect_pillow_simd",
    "_pil_import_error",
    "tk",
]
