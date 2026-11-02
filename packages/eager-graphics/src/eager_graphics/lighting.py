"""Screen-space lighting model and lightmap definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from eager_core.types import WHITE, Color, Vec2

__all__ = [
    "AmbientLight",
    "LightKind",
    "LightmapState",
    "PointLight",
]


class LightKind(str, Enum):
    """Classification of light sources."""

    POINT = "point"
    RADIAL = "radial"
    AMBIENT = "ambient"


@dataclass(slots=True)
class PointLight:
    """A radial point light source in virtual stage coordinates."""

    x: float
    y: float
    radius: float
    color: Color = WHITE
    intensity: float = 1.0
    mode: str = "multiply"  # "multiply" (ambient darkness cutout) or "screen" (bloom/additive)

    @property
    def position(self) -> Vec2:
        return Vec2(self.x, self.y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "radius": self.radius,
            "color": self.color.to_dict(),
            "intensity": self.intensity,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PointLight:
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            radius=float(data["radius"]),
            color=Color.from_dict(data.get("color", {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})),
            intensity=float(data.get("intensity", 1.0)),
            mode=str(data.get("mode", "multiply")),
        )


@dataclass(slots=True)
class AmbientLight:
    """Scene-wide ambient lighting level."""

    color: Color = WHITE
    intensity: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "color": self.color.to_dict(),
            "intensity": self.intensity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AmbientLight:
        return cls(
            color=Color.from_dict(data.get("color", {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})),
            intensity=float(data.get("intensity", 1.0)),
        )


@dataclass(slots=True)
class LightmapState:
    """Container for active stage lighting and atmospheric state."""

    ambient: Color = WHITE
    lights: list[PointLight] = field(default_factory=list)
    enabled: bool = False
    blend_mode: str = "multiply"  # "multiply" or "screen"

    def clear(self) -> None:
        """Reset lights to neutral state."""
        self.ambient = WHITE
        self.lights.clear()
        self.enabled = False
        self.blend_mode = "multiply"

    def add_light(self, light: PointLight) -> None:
        """Add a point light source and enable lighting pass."""
        self.lights.append(light)
        self.enabled = True

    def remove_light(self, light: PointLight) -> None:
        """Remove a point light source."""
        if light in self.lights:
            self.lights.remove(light)
        if not self.lights and self.ambient == WHITE:
            self.enabled = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ambient": self.ambient.to_dict(),
            "lights": [l.to_dict() for l in self.lights],
            "enabled": self.enabled,
            "blend_mode": self.blend_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LightmapState:
        return cls(
            ambient=Color.from_dict(data.get("ambient", {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})),
            lights=[PointLight.from_dict(d) for d in data.get("lights", [])],
            enabled=bool(data.get("enabled", False)),
            blend_mode=str(data.get("blend_mode", "multiply")),
        )
