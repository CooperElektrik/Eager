"""Visual stage hierarchy and element state representation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eager_core.types import WHITE, Color, Vec2

from eager_graphics.types import Anchor

__all__ = [
    "ElementState",
    "Layer",
    "Stage",
    "StageElement",
]


@dataclass
class ElementState:
    """Mutable visual state of an individual element on the stage."""

    asset_id: str
    position: Vec2 = field(default_factory=lambda: Vec2(960.0, 540.0))
    anchor: Anchor = Anchor.BOTTOM_CENTER
    opacity: float = 1.0
    scale: Vec2 = field(default_factory=lambda: Vec2(1.0, 1.0))
    rotation: float = 0.0
    tint: Color = WHITE
    visible: bool = True
    flip_h: bool = False
    flip_v: bool = False
    z_index: int = 0

    def clone(self) -> ElementState:
        """Create an independent copy of this element state."""
        return ElementState(
            asset_id=self.asset_id,
            position=Vec2(self.position.x, self.position.y),
            anchor=self.anchor,
            opacity=self.opacity,
            scale=Vec2(self.scale.x, self.scale.y),
            rotation=self.rotation,
            tint=self.tint,
            visible=self.visible,
            flip_h=self.flip_h,
            flip_v=self.flip_v,
            z_index=self.z_index,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize element state to a dictionary."""
        return {
            "asset_id": self.asset_id,
            "position": self.position.to_dict(),
            "anchor": self.anchor.value,
            "opacity": self.opacity,
            "scale": self.scale.to_dict(),
            "rotation": self.rotation,
            "tint": self.tint.to_dict(),
            "visible": self.visible,
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
            "z_index": self.z_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ElementState:
        """Restore element state from a dictionary."""
        return cls(
            asset_id=data["asset_id"],
            position=Vec2.from_dict(data["position"]),
            anchor=Anchor.from_str(data.get("anchor", "bottom_center")),
            opacity=float(data.get("opacity", 1.0)),
            scale=Vec2.from_dict(data.get("scale", {"x": 1.0, "y": 1.0})),
            rotation=float(data.get("rotation", 0.0)),
            tint=Color.from_dict(data.get("tint", {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})),
            visible=bool(data.get("visible", True)),
            flip_h=bool(data.get("flip_h", False)),
            flip_v=bool(data.get("flip_v", False)),
            z_index=int(data.get("z_index", 0)),
        )


@dataclass
class StageElement:
    """An identified element hosted within a stage layer."""

    element_id: str
    state: ElementState

    @property
    def asset_id(self) -> str:
        """Visual asset identifier for this element."""
        return self.state.asset_id

    @asset_id.setter
    def asset_id(self, val: str) -> None:
        """Set visual asset identifier.

        Args:
            val: New asset identifier string.
        """
        self.state.asset_id = val

    @property
    def position(self) -> Vec2:
        """Current 2D position vector in virtual coordinates."""
        return self.state.position

    @position.setter
    def position(self, val: Vec2) -> None:
        """Set 2D position vector.

        Args:
            val: New Vec2 position coordinates.
        """
        self.state.position = val

    @property
    def opacity(self) -> float:
        """Opacity multiplier in the range [0.0, 1.0]."""
        return self.state.opacity

    @opacity.setter
    def opacity(self, val: float) -> None:
        """Set element opacity clamped to [0.0, 1.0].

        Args:
            val: Opacity value.
        """
        self.state.opacity = max(0.0, min(1.0, val))

    @property
    def visible(self) -> bool:
        """Visibility flag for this element."""
        return self.state.visible

    @visible.setter
    def visible(self, val: bool) -> None:
        """Set element visibility.

        Args:
            val: Boolean visibility flag.
        """
        self.state.visible = val

    def to_dict(self) -> dict[str, Any]:
        """Serialize element to dictionary.

        Returns:
            Dictionary containing element_id and serialized state.
        """
        return {
            "element_id": self.element_id,
            "state": self.state.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageElement:
        """Construct StageElement from serialized dictionary.

        Args:
            data: Dictionary containing element_id and state fields.

        Returns:
            Constructed StageElement instance.
        """
        return cls(
            element_id=data["element_id"],
            state=ElementState.from_dict(data["state"]),
        )


@dataclass
class Layer:
    """A visual container representing a stage layer with its own z-order and elements."""

    name: str
    z_order: int
    visible: bool = True
    opacity: float = 1.0
    elements: dict[str, StageElement] = field(default_factory=dict)
    _sorted_cache: list[StageElement] | None = field(default=None, repr=False, compare=False)

    def add_element(self, element: StageElement) -> None:
        """Add or replace an element in this layer."""
        self.elements[element.element_id] = element
        self._sorted_cache = None

    def remove_element(self, element_id: str) -> StageElement | None:
        """Remove and return an element by ID, or None if not present."""
        elem = self.elements.pop(element_id, None)
        if elem is not None:
            self._sorted_cache = None
        return elem

    def get_element(self, element_id: str) -> StageElement | None:
        """Retrieve an element by ID."""
        return self.elements.get(element_id)

    def has_element(self, element_id: str) -> bool:
        """Check if an element exists in this layer."""
        return element_id in self.elements

    def clear(self) -> None:
        """Clear all elements from this layer."""
        self.elements.clear()
        self._sorted_cache = None

    def get_sorted_elements(self) -> list[StageElement]:
        """Return elements sorted by their internal z-index (cached until structure changes)."""
        if self._sorted_cache is None:
            self._sorted_cache = sorted(self.elements.values(), key=lambda elem: elem.state.z_index)
        return self._sorted_cache

    def to_dict(self) -> dict[str, Any]:
        """Serialize layer to dictionary."""
        return {
            "name": self.name,
            "z_order": self.z_order,
            "visible": self.visible,
            "opacity": self.opacity,
            "elements": {k: elem.to_dict() for k, elem in self.elements.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Layer:
        """Restore layer from dictionary."""
        layer = cls(
            name=data["name"],
            z_order=int(data["z_order"]),
            visible=bool(data.get("visible", True)),
            opacity=float(data.get("opacity", 1.0)),
        )
        if "elements" in data:
            for elem_id, elem_data in data["elements"].items():
                layer.elements[elem_id] = StageElement.from_dict(elem_data)
        return layer


class Stage:
    """Root visual stage containing ordered layers of visual elements."""

    DEFAULT_LAYERS: tuple[tuple[str, int], ...] = (
        ("background", 0),
        ("characters", 100),
        ("foreground", 200),
        ("ui", 300),
        ("overlay", 400),
    )

    def __init__(self) -> None:
        self._layers: dict[str, Layer] = {}
        self._sorted_cache: list[Layer] | None = None
        for name, z in self.DEFAULT_LAYERS:
            self._layers[name] = Layer(name=name, z_order=z)

    @property
    def layers(self) -> dict[str, Layer]:
        """Dictionary of all layers by name."""
        return self._layers

    def get_layer(self, name: str) -> Layer | None:
        """Retrieve a layer by name."""
        return self._layers.get(name)

    def get_or_create_layer(self, name: str, z_order: int = 50) -> Layer:
        """Retrieve an existing layer or create a new one with the given z-order."""
        if name not in self._layers:
            self._layers[name] = Layer(name=name, z_order=z_order)
            self._sorted_cache = None
        return self._layers[name]

    def add_layer(self, layer: Layer) -> None:
        """Register a layer on the stage."""
        self._layers[layer.name] = layer
        self._sorted_cache = None

    def remove_layer(self, name: str) -> Layer | None:
        """Remove a layer by name."""
        layer = self._layers.pop(name, None)
        if layer is not None:
            self._sorted_cache = None
        return layer

    def get_sorted_layers(self) -> list[Layer]:
        """Return all layers sorted by ascending z-order (cached until structure changes)."""
        if self._sorted_cache is None:
            self._sorted_cache = sorted(self._layers.values(), key=lambda lay: lay.z_order)
        return self._sorted_cache

    def get_element(self, layer_name: str, element_id: str) -> StageElement | None:
        """Find an element inside a specific layer."""
        layer = self.get_layer(layer_name)
        if layer is None:
            return None
        return layer.get_element(element_id)

    def find_element(self, element_id: str) -> tuple[str, StageElement] | None:
        """Search all layers for an element by ID, returning (layer_name, element)."""
        for layer_name, layer in self._layers.items():
            elem = layer.get_element(element_id)
            if elem is not None:
                return (layer_name, elem)
        return None

    def clear(self) -> None:
        """Clear all elements across all layers."""
        for layer in self._layers.values():
            layer.clear()
        self._sorted_cache = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize complete stage state to dictionary."""
        return {"layers": {name: layer.to_dict() for name, layer in self._layers.items()}}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Stage:
        """Restore stage state from dictionary."""
        stage = cls()
        if "layers" in data:
            for name, layer_data in data["layers"].items():
                stage._layers[name] = Layer.from_dict(layer_data)
        return stage
