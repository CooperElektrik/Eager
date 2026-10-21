"""Core geometry and color types for Eager."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vec2:
    """Immutable 2D vector for coordinates, offsets, and scales."""

    x: float
    y: float

    def __add__(self, other: Vec2 | tuple[float, float]) -> Vec2:
        if isinstance(other, Vec2):
            return Vec2(self.x + other.x, self.y + other.y)
        return Vec2(self.x + other[0], self.y + other[1])

    def __sub__(self, other: Vec2 | tuple[float, float]) -> Vec2:
        if isinstance(other, Vec2):
            return Vec2(self.x - other.x, self.y - other.y)
        return Vec2(self.x - other[0], self.y - other[1])

    def __mul__(self, scalar: float) -> Vec2:
        return Vec2(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> Vec2:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vec2:
        return Vec2(self.x / scalar, self.y / scalar)

    def __neg__(self) -> Vec2:
        return Vec2(-self.x, -self.y)

    def lerp(self, target: Vec2, t: float) -> Vec2:
        """Linear interpolate towards target vector with factor t in [0.0, 1.0]."""
        return Vec2(
            self.x + (target.x - self.x) * t,
            self.y + (target.y - self.y) * t,
        )

    def distance_to(self, other: Vec2) -> float:
        """Euclidean distance between two vectors."""
        return math.hypot(self.x - other.x, self.y - other.y)

    def to_tuple(self) -> tuple[float, float]:
        """Convert vector to (x, y) tuple."""
        return (self.x, self.y)

    def to_dict(self) -> dict[str, float]:
        """Serialize vector to dictionary."""
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Vec2:
        """Create vector from dictionary."""
        x_val = data["x"]
        y_val = data["y"]
        if not isinstance(x_val, (int, float, str)) or not isinstance(y_val, (int, float, str)):
            raise TypeError("Vec2 coordinates must be numbers or numeric strings")
        return cls(float(x_val), float(y_val))

    @classmethod
    def from_value(cls, val: Vec2 | tuple[float, float] | list[float] | float) -> Vec2:
        """Coerce various formats into a Vec2."""
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
        object.__setattr__(self, "r", max(0.0, min(1.0, float(self.r))))
        object.__setattr__(self, "g", max(0.0, min(1.0, float(self.g))))
        object.__setattr__(self, "b", max(0.0, min(1.0, float(self.b))))
        object.__setattr__(self, "a", max(0.0, min(1.0, float(self.a))))

    def with_alpha(self, alpha: float) -> Color:
        """Return a copy of this color with a new alpha value."""
        return Color(self.r, self.g, self.b, alpha)

    def lerp(self, target: Color, t: float) -> Color:
        """Linear interpolate between two colors."""
        return Color(
            self.r + (target.r - self.r) * t,
            self.g + (target.g - self.g) * t,
            self.b + (target.b - self.b) * t,
            self.a + (target.a - self.a) * t,
        )

    def to_rgba_bytes(self) -> tuple[int, int, int, int]:
        """Convert to 8-bit integer tuple (0-255)."""
        return (
            round(self.r * 255),
            round(self.g * 255),
            round(self.b * 255),
            round(self.a * 255),
        )

    def to_hex(self, include_alpha: bool = True) -> str:
        """Convert color to hexadecimal string (e.g. '#ffffff' or '#ffffffcc')."""
        r, g, b, a = self.to_rgba_bytes()
        if include_alpha and a < 255:
            return f"#{r:02x}{g:02x}{b:02x}{a:02x}"
        return f"#{r:02x}{g:02x}{b:02x}"

    def to_dict(self) -> dict[str, float]:
        """Serialize color to dictionary."""
        return {"r": self.r, "g": self.g, "b": self.b, "a": self.a}

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> Color:
        """Create color from dictionary."""
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
        return cls(
            r=float(r_val),
            g=float(g_val),
            b=float(b_val),
            a=float(a_val),
        )

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        """Parse hex color string (e.g. '#fff', '#ffffff', '#ffffff80', 'black')."""
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

        s = lower.lstrip("#")
        import string

        if not s or not all(ch in string.hexdigits for ch in s):
            msg = f"Invalid hex color string: '{hex_str}'"
            raise ValueError(msg)

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
        raise ValueError(msg)

    @classmethod
    def from_bytes(cls, r: int, g: int, b: int, a: int = 255) -> Color:
        """Create color from 0-255 byte integers."""
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
    """Axis-aligned rectangle in 2D space."""

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        return self.x

    @property
    def top(self) -> float:
        return self.y

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def center(self) -> Vec2:
        return Vec2(self.x + self.width / 2.0, self.y + self.height / 2.0)

    def contains(self, point: Vec2 | tuple[float, float]) -> bool:
        """Check if point is inside rectangle bounds."""
        px, py = (point.x, point.y) if isinstance(point, Vec2) else point
        return self.left <= px <= self.right and self.top <= py <= self.bottom

    def intersects(self, other: Rect) -> bool:
        """Check if this rectangle overlaps with another."""
        return not (
            self.right < other.left
            or self.left > other.right
            or self.bottom < other.top
            or self.top > other.bottom
        )
