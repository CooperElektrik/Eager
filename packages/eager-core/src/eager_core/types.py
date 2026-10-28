"""Core geometry and color types for Eager."""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from dataclasses import dataclass

from eager_core.exceptions import ColorParseError

__all__ = [
    "BLACK",
    "BLUE",
    "GREEN",
    "RED",
    "TRANSPARENT",
    "WHITE",
    "Color",
    "Rect",
    "Vec2",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Vec2:
    """Immutable 2D vector for coordinates, offsets, and scales."""

    x: float
    y: float

    def __add__(self, other: object) -> Vec2:
        """Add two vectors or a vector and a 2-tuple coordinate pair."""
        if isinstance(other, Vec2):
            return Vec2(self.x + other.x, self.y + other.y)
        if isinstance(other, (tuple, list)) and len(other) == 2:
            try:
                return Vec2(self.x + float(other[0]), self.y + float(other[1]))
            except (TypeError, ValueError):
                return NotImplemented
        return NotImplemented

    def __radd__(self, other: object) -> Vec2:
        """Add two vectors or a vector and a 2-tuple coordinate pair (reflected)."""
        return self.__add__(other)

    def __sub__(self, other: object) -> Vec2:
        """Subtract another vector or 2-tuple coordinate pair from this vector."""
        if isinstance(other, Vec2):
            return Vec2(self.x - other.x, self.y - other.y)
        if isinstance(other, (tuple, list)) and len(other) == 2:
            try:
                return Vec2(self.x - float(other[0]), self.y - float(other[1]))
            except (TypeError, ValueError):
                return NotImplemented
        return NotImplemented

    def __rsub__(self, other: object) -> Vec2:
        """Subtract this vector from a 2-tuple coordinate pair (reflected)."""
        if isinstance(other, (tuple, list)) and len(other) == 2:
            try:
                return Vec2(float(other[0]) - self.x, float(other[1]) - self.y)
            except (TypeError, ValueError):
                return NotImplemented
        return NotImplemented

    def __mul__(self, scalar: object) -> Vec2:
        """Multiply this vector by a scalar number."""
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        return Vec2(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: object) -> Vec2:
        """Multiply this vector by a scalar number (reflected)."""
        return self.__mul__(scalar)

    def __truediv__(self, scalar: object) -> Vec2:
        """Divide this vector by a non-zero scalar number."""
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        if scalar == 0:
            raise ZeroDivisionError("Cannot divide Vec2 by zero")
        return Vec2(self.x / scalar, self.y / scalar)

    def __neg__(self) -> Vec2:
        """Return the component-wise negation of this vector."""
        return Vec2(-self.x, -self.y)

    def lerp(self, target: Vec2, t: float) -> Vec2:
        """Linear interpolate towards target vector.

        Args:
            target: Destination Vec2.
            t: Interpolation factor in the range [0.0, 1.0].

        Returns:
            New interpolated Vec2.
        """
        return Vec2(
            self.x + (target.x - self.x) * t,
            self.y + (target.y - self.y) * t,
        )

    def distance_to(self, other: Vec2) -> float:
        """Calculate Euclidean distance between two vectors.

        Args:
            other: Target Vec2 to measure distance to.

        Returns:
            Euclidean distance as a float.
        """
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_tuple(self) -> tuple[float, float]:
        """Convert vector to an (x, y) coordinate tuple.

        Returns:
            Tuple of `(x, y)` floats.
        """
        return (self.x, self.y)

    def to_dict(self) -> dict[str, float]:
        """Serialize vector to a dictionary.

        Returns:
            Dictionary with `"x"` and `"y"` keys.
        """
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Vec2:
        """Create a Vec2 instance from a dictionary.

        Args:
            data: Mapping containing `"x"` and `"y"` numeric entries.

        Returns:
            Deserialized Vec2 instance.

        Raises:
            TypeError: If `data` is not a Mapping or values are not numeric.
            KeyError: If required `"x"` or `"y"` keys are missing.
            ValueError: If coordinate values cannot be converted to float.
        """
        if not isinstance(data, Mapping):
            raise TypeError(f"Vec2.from_dict expects a Mapping, got {type(data).__name__}")
        if "x" not in data or "y" not in data:
            raise KeyError(f"Vec2.from_dict requires 'x' and 'y' keys, got keys: {list(data.keys())}")
        x_val = data["x"]
        y_val = data["y"]
        if not isinstance(x_val, (int, float, str)) or not isinstance(y_val, (int, float, str)):
            logger.warning("Vec2.from_dict received non-numeric values: x=%r, y=%r", x_val, y_val)
            raise TypeError("Vec2 coordinates must be numbers or numeric strings")
        try:
            return cls(float(x_val), float(y_val))
        except ValueError as err:
            raise ValueError(f"Vec2 coordinates could not be converted to float: {err}") from err

    @classmethod
    def from_value(cls, val: Vec2 | tuple[float, float] | list[float] | float) -> Vec2:
        """Coerce various formats into a Vec2.

        Args:
            val: Vec2, 2-element sequence (x, y), or single scalar applied to both axes.

        Returns:
            Coerced Vec2 instance.
        """
        if isinstance(val, Vec2):
            return val
        if isinstance(val, (tuple, list)):
            return cls(float(val[0]), float(val[1]))
        return cls(float(val), float(val))


@dataclass(frozen=True, slots=True)
class Color:
    """Immutable RGBA color with normalized float components [0.0, 1.0]."""

    r: float
    g: float
    b: float
    a: float = 1.0

    def __post_init__(self) -> None:
        """Clamp and validate color component values to the [0.0, 1.0] interval."""
        object.__setattr__(self, "r", max(0.0, min(1.0, float(self.r))))
        object.__setattr__(self, "g", max(0.0, min(1.0, float(self.g))))
        object.__setattr__(self, "b", max(0.0, min(1.0, float(self.b))))
        object.__setattr__(self, "a", max(0.0, min(1.0, float(self.a))))

    def with_alpha(self, alpha: float) -> Color:
        """Return a copy of this color with a new alpha value.

        Args:
            alpha: New alpha channel value in the range [0.0, 1.0].

        Returns:
            New Color instance with updated alpha.
        """
        return Color(self.r, self.g, self.b, alpha)

    def lerp(self, target: Color, t: float) -> Color:
        """Linear interpolate between this color and a target color.

        Args:
            target: Target Color.
            t: Interpolation progress in the range [0.0, 1.0].

        Returns:
            New interpolated Color.
        """
        return Color(
            self.r + (target.r - self.r) * t,
            self.g + (target.g - self.g) * t,
            self.b + (target.b - self.b) * t,
            self.a + (target.a - self.a) * t,
        )

    def to_rgba_bytes(self) -> tuple[int, int, int, int]:
        """Convert normalized float channels to an 8-bit integer tuple.

        Returns:
            Tuple of `(r, g, b, a)` values each in the range [0, 255].
        """
        return (
            round(self.r * 255),
            round(self.g * 255),
            round(self.b * 255),
            round(self.a * 255),
        )

    def to_hex(self, include_alpha: bool = True) -> str:
        """Convert color to hexadecimal string (e.g. '#ffffff' or '#ffffffcc').

        Args:
            include_alpha: Whether to append the alpha hex pair if alpha < 255.
                Defaults to True.

        Returns:
            Hex string starting with `#`.
        """
        r, g, b, a = self.to_rgba_bytes()
        if include_alpha and a < 255:
            return f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"

    def to_dict(self) -> dict[str, float]:
        """Serialize color to a dictionary.

        Returns:
            Dictionary with `"r"`, `"g"`, `"b"`, and `"a"` channel floats.
        """
        return {"r": self.r, "g": self.g, "b": self.b, "a": self.a}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Color:
        """Create a Color instance from a dictionary.

        Args:
            data: Mapping containing `"r"`, `"g"`, `"b"`, and optional `"a"` values.

        Returns:
            Deserialized Color instance.

        Raises:
            TypeError: If `data` is not a Mapping or channel values are not numeric.
            KeyError: If required `"r"`, `"g"`, or `"b"` keys are missing.
            ColorParseError: If channel values cannot be parsed to floats.
        """
        if not isinstance(data, Mapping):
            raise TypeError(f"Color.from_dict expects a Mapping, got {type(data).__name__}")
        missing = [k for k in ("r", "g", "b") if k not in data]
        if missing:
            raise KeyError(f"Color.from_dict missing required keys {missing}, got keys: {list(data.keys())}")
        r_val = data["r"]
        g_val = data["g"]
        b_val = data["b"]
        a_val = data.get("a", 1.0)
        if (
            not isinstance(r_val, (int, float, str))
            or not isinstance(g_val, (int, float, str))
            or not isinstance(b_val, (int, float, str))
            or not isinstance(a_val, (int, float, str))
        ):
            raise TypeError("Color channels must be numbers or numeric strings")
        try:
            return cls(
                r=float(r_val),
                g=float(g_val),
                b=float(b_val),
                a=float(a_val),
            )
        except ValueError as err:
            raise ColorParseError(f"Color channels could not be converted to float: {err}") from err

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        """Parse hex color string (e.g. '#fff', '#ffffff', '#ffffff80', 'black').

        Args:
            hex_str: CSS-style hexadecimal color string or standard named color.

        Returns:
            Parsed Color instance.

        Raises:
            ColorParseError: If the hex color string is malformed or invalid.
        """
        lower = hex_str.lower().strip()
        named = {
            "white": (1.0, 1.0, 1.0, 1.0),
            "black": (0.0, 0.0, 0.0, 1.0),
            "red": (1.0, 0.0, 0.0, 1.0),
            "green": (0.0, 1.0, 0.0, 1.0),
            "blue": (0.0, 0.0, 1.0, 1.0),
            "yellow": (1.0, 1.0, 0.0, 1.0),
            "cyan": (0.0, 1.0, 1.0, 1.0),
            "magenta": (1.0, 0.0, 1.0, 1.0),
            "transparent": (0.0, 0.0, 0.0, 0.0),
        }
        if lower in named:
            c = named[lower]
            return cls(c[0], c[1], c[2], c[3])

        s = lower.removeprefix("#")
        import string

        if not s or not all(ch in string.hexdigits for ch in s):
            msg = f"Invalid hex color string: '{hex_str}'"
            raise ColorParseError(msg)

        if len(s) == 3:
            r = int(s[0] * 2, 16) / 255.0
            g = int(s[1] * 2, 16) / 255.0
            b = int(s[2] * 2, 16) / 255.0
            return cls(r, g, b, 1.0)
        if len(s) == 4:
            r = int(s[0] * 2, 16) / 255.0
            g = int(s[1] * 2, 16) / 255.0
            b = int(s[2] * 2, 16) / 255.0
            a = int(s[3] * 2, 16) / 255.0
            return cls(r, g, b, a)
        if len(s) == 6:
            r = int(s[0:2], 16) / 255.0
            g = int(s[2:4], 16) / 255.0
            b = int(s[4:6], 16) / 255.0
            return cls(r, g, b, 1.0)
        if len(s) == 8:
            r = int(s[0:2], 16) / 255.0
            g = int(s[2:4], 16) / 255.0
            b = int(s[4:6], 16) / 255.0
            a = int(s[6:8], 16) / 255.0
            return cls(r, g, b, a)

        msg = f"Invalid hex color string: '{hex_str}'"
        raise ColorParseError(msg)

    @classmethod
    def from_bytes(cls, r: int, g: int, b: int, a: int = 255) -> Color:
        """Create color from 0-255 byte integers.

        Args:
            r: Red channel byte (0-255).
            g: Green channel byte (0-255).
            b: Blue channel byte (0-255).
            a: Alpha channel byte (0-255). Defaults to 255.

        Returns:
            Constructed Color with normalized float components [0.0, 1.0].
        """
        return cls(r / 255.0, g / 255.0, b / 255.0, a / 255.0)


# Predefined Color Constants
WHITE = Color(1.0, 1.0, 1.0, 1.0)
BLACK = Color(0.0, 0.0, 0.0, 1.0)
TRANSPARENT = Color(0.0, 0.0, 0.0, 0.0)
RED = Color(1.0, 0.0, 0.0, 1.0)
GREEN = Color(0.0, 1.0, 0.0, 1.0)
BLUE = Color(0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True, slots=True)
class Rect:
    """Axis-aligned rectangle in 2D space.

    Attributes:
        x: Left X coordinate.
        y: Top Y coordinate.
        width: Horizontal extent.
        height: Vertical extent.
    """

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        """Left edge X coordinate."""
        return self.x

    @property
    def top(self) -> float:
        """Top edge Y coordinate."""
        return self.y

    @property
    def right(self) -> float:
        """Right edge X coordinate."""
        return self.x + self.width

    @property
    def bottom(self) -> float:
        """Bottom edge Y coordinate."""
        return self.y + self.height

    @property
    def center(self) -> Vec2:
        """Center position as a Vec2."""
        return Vec2(self.x + self.width / 2.0, self.y + self.height / 2.0)

    def contains(self, point: Vec2 | tuple[float, float]) -> bool:
        """Check if point is inside rectangle bounds.

        Args:
            point: Point to test, either a Vec2 or (x, y) tuple.

        Returns:
            True if the point lies inside or on the boundaries of this rectangle.
        """
        px, py = (point.x, point.y) if isinstance(point, Vec2) else point
        return self.left <= px <= self.right and self.top <= py <= self.bottom

    def intersects(self, other: Rect) -> bool:
        """Check if this rectangle overlaps with another rectangle.

        Args:
            other: Other Rect to check intersection against.

        Returns:
            True if rectangles overlap.
        """
        return not (
            self.right < other.left
            or self.left > other.right
            or self.bottom < other.top
            or self.top > other.bottom
        )
