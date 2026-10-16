"""Graphics-only presentation enums: anchoring, viewport scaling, and transitions.

Shared geometry, color, and coordinate primitives (``Color``, ``Rect``,
``Vec2``, and the named colors) live in :mod:`eager_core.types`; import them
from there rather than from this module.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "Anchor",
    "DebugOverlayMode",
    "ScaleMode",
    "TransitionKind",
]


class DebugOverlayMode(str, Enum):
    """Display modes for the on-screen developer debug overlay."""

    OFF = "off"
    FPS = "fps"
    DETAILED = "detailed"



class Anchor(str, Enum):
    """Anchor alignment reference point within an element's bounding box."""

    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    TOP_RIGHT = "top_right"
    CENTER_LEFT = "center_left"
    CENTER = "center"
    CENTER_RIGHT = "center_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"

    def get_offset_factor(self) -> tuple[float, float]:
        """Return (factor_x, factor_y) in [0.0, 1.0] relative to element origin.

        For example:
        - TOP_LEFT: (0.0, 0.0)
        - CENTER: (0.5, 0.5)
        - BOTTOM_CENTER: (0.5, 1.0)
        """
        match self:
            case Anchor.TOP_LEFT:
                return (0.0, 0.0)
            case Anchor.TOP_CENTER:
                return (0.5, 0.0)
            case Anchor.TOP_RIGHT:
                return (1.0, 0.0)
            case Anchor.CENTER_LEFT:
                return (0.0, 0.5)
            case Anchor.CENTER:
                return (0.5, 0.5)
            case Anchor.CENTER_RIGHT:
                return (1.0, 0.5)
            case Anchor.BOTTOM_LEFT:
                return (0.0, 1.0)
            case Anchor.BOTTOM_CENTER:
                return (0.5, 1.0)
            case Anchor.BOTTOM_RIGHT:
                return (1.0, 1.0)

    @classmethod
    def from_str(cls, val: str) -> Anchor:
        """Parse string to Anchor enum, handling common aliases."""
        clean = val.strip().lower().replace("-", "_")
        for member in cls:
            if member.value == clean or member.name.lower() == clean:
                return member
        # Common aliases
        aliases = {
            "top": Anchor.TOP_CENTER,
            "bottom": Anchor.BOTTOM_CENTER,
            "left": Anchor.CENTER_LEFT,
            "right": Anchor.CENTER_RIGHT,
            "middle": Anchor.CENTER,
        }
        if clean in aliases:
            return aliases[clean]
        msg = f"Unknown anchor value: '{val}'"
        raise ValueError(msg)


class ScaleMode(str, Enum):
    """Viewport scaling mode when mapping virtual stage to screen dimensions."""

    LETTERBOX = "letterbox"
    STRETCH = "stretch"
    CROP = "crop"
    FIT_WIDTH = "fit_width"
    FIT_HEIGHT = "fit_height"


class TransitionKind(str, Enum):
    """Standard visual transition types."""

    CUT = "cut"
    FADE = "fade"
    CROSSFADE = "crossfade"
    DISSOLVE = "dissolve"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"
    SLIDE_UP = "slide_up"
    SLIDE_DOWN = "slide_down"

    @classmethod
    def from_str(cls, val: str) -> TransitionKind:
        """Parse string to TransitionKind enum."""
        clean = val.strip().lower().replace("-", "_")
        for member in cls:
            if member.value == clean or member.name.lower() == clean:
                return member
        return cls.CUT
