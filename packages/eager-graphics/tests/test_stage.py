"""Tests for Stage, Layer, and Element state management and serialization."""

from eager_core.types import Color, Vec2

from eager_graphics.stage import ElementState, Layer, Stage, StageElement
from eager_graphics.types import Anchor


def test_element_state_clone_and_mutation() -> None:
    state = ElementState(
        asset_id="alice/happy",
        position=Vec2(500.0, 900.0),
        anchor=Anchor.BOTTOM_CENTER,
        opacity=0.8,
    )
    cloned = state.clone()
    assert cloned.asset_id == state.asset_id
    assert cloned.position == state.position

    # Modifying clone shouldn't modify original
    cloned.position = Vec2(100.0, 200.0)
    assert state.position == Vec2(500.0, 900.0)


def test_element_state_serialization_roundtrip() -> None:
    state = ElementState(
        asset_id="bg/forest",
        position=Vec2(0.0, 0.0),
        anchor=Anchor.TOP_LEFT,
        opacity=0.75,
        scale=Vec2(1.2, 1.2),
        rotation=45.0,
        tint=Color(1.0, 0.5, 0.5, 1.0),
        flip_h=True,
        flip_v=False,
        z_index=10,
    )
    d = state.to_dict()
    restored = ElementState.from_dict(d)
    assert restored.asset_id == state.asset_id
    assert restored.position == state.position
    assert restored.anchor == state.anchor
    assert restored.opacity == state.opacity
    assert restored.scale == state.scale
    assert restored.rotation == state.rotation
    assert restored.tint == state.tint
    assert restored.flip_h is True
    assert restored.z_index == 10


def test_layer_operations() -> None:
    layer = Layer(name="test_layer", z_order=50)
    assert not layer.has_element("elem1")

    elem1 = StageElement("elem1", ElementState("asset1", z_index=5))
    elem2 = StageElement("elem2", ElementState("asset2", z_index=1))
    layer.add_element(elem1)
    layer.add_element(elem2)

    assert layer.has_element("elem1")
    assert layer.get_element("elem2") is elem2

    # Sorted by z_index
    sorted_elems = layer.get_sorted_elements()
    assert sorted_elems[0] is elem2  # z_index 1
    assert sorted_elems[1] is elem1  # z_index 5

    # Remove
    assert layer.remove_element("elem1") is elem1
    assert not layer.has_element("elem1")


def test_stage_layers_and_serialization() -> None:
    stage = Stage()
    # Check default layers
    assert "background" in stage.layers
    assert "characters" in stage.layers
    assert "foreground" in stage.layers
    assert "ui" in stage.layers
    assert "overlay" in stage.layers

    sorted_layers = stage.get_sorted_layers()
    assert [layer.name for layer in sorted_layers] == [
        "background",
        "characters",
        "foreground",
        "ui",
        "overlay",
    ]

    # Add element
    bg_elem = StageElement("bg", ElementState("bg/sky"))
    stage.layers["background"].add_element(bg_elem)

    # find_element
    res = stage.find_element("bg")
    assert res is not None
    assert res[0] == "background"
    assert res[1] is bg_elem

    # Serialize & Restore
    data = stage.to_dict()
    restored_stage = Stage.from_dict(data)
    assert "background" in restored_stage.layers
    restored_bg = restored_stage.get_element("background", "bg")
    assert restored_bg is not None
    assert restored_bg.asset_id == "bg/sky"


def test_layer_z_ordering_and_element_lookup_edge_cases() -> None:
    """Verify custom layer sorting with negative, zero, and high z-orders and element lookups."""
    stage = Stage()
    # Default layers: background(0), characters(100), foreground(200), ui(300), overlay(400)
    layer_sub = Layer("sub_underworld", z_order=-999)
    layer_zero = Layer("zero_layer", z_order=0)
    layer_mid = Layer("mid_layer", z_order=150)
    layer_sky = Layer("sky_layer", z_order=9999)

    stage.add_layer(layer_sub)
    stage.add_layer(layer_zero)
    stage.add_layer(layer_mid)
    stage.add_layer(layer_sky)

    sorted_layers = stage.get_sorted_layers()
    names = [l.name for l in sorted_layers]
    assert names[0] == "sub_underworld"
    assert names[-1] == "sky_layer"
    assert "mid_layer" in names

    # Lookup and removal edge cases
    assert stage.get_element("sub_underworld", "phantom") is None
    assert stage.get_element("nonexistent_layer", "any") is None
    assert stage.find_element("phantom") is None

    elem = StageElement("phantom_item", ElementState(asset_id="test_asset"))
    stage.layers["sub_underworld"].add_element(elem)

    found = stage.find_element("phantom_item")
    assert found is not None
    assert found[0] == "sub_underworld"
    assert found[1].element_id == "phantom_item"

    # Layer removal
    removed_layer = stage.remove_layer("sub_underworld")
    assert removed_layer is not None
    assert stage.get_layer("sub_underworld") is None
    assert stage.find_element("phantom_item") is None

