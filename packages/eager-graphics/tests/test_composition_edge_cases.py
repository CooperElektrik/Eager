"""Edge case testing for stage composition, transformations, and layer ordering."""

from eager_core.types import Vec2

from eager_graphics import NullRenderer, StageCompositor
from eager_graphics.renderers.pil import PIL_AVAILABLE, PILRenderer
from eager_graphics.stage import Layer, Stage


def test_stage_composition_offscreen_and_negative_coords() -> None:
    comp = StageCompositor(1920, 1080)
    # Actor positioned far offscreen top-left (-9999, 50000) and bottom-right
    comp.show_character("actor_off_tl", "idle", position="center", transition="cut")
    elem_tl = comp.stage.get_element("characters", "actor_off_tl")
    assert elem_tl is not None
    elem_tl.state.position = Vec2(-9999.0, 50000.0)

    comp.show_character("actor_off_br", "idle", position="center", transition="cut")
    elem_br = comp.stage.get_element("characters", "actor_off_br")
    assert elem_br is not None
    elem_br.state.position = Vec2(3000.0, 2500.0)

    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)
    assert backend.frame_count == 1
    # Items exist in render list with exact coordinates for clipping
    items = {item.asset_id: item for item in backend.last_frame}
    assert items["actor_off_tl/idle"].x == -9999.0
    assert items["actor_off_tl/idle"].y == 50000.0
    assert items["actor_off_br/idle"].x == 3000.0

    if PIL_AVAILABLE:
        pil_backend = PILRenderer(1280, 720)
        img = pil_backend.render_compositor(comp, 1280, 720)
        assert img.size == (1280, 720)


def test_stage_composition_extreme_and_negative_scales() -> None:
    comp = StageCompositor(1920, 1080)
    comp.show_character("flipped_actor", "idle", position="center", transition="cut")
    elem = comp.stage.get_element("characters", "flipped_actor")
    assert elem is not None
    # Negative scale (inversion) and zero scale: Vec2(-2.0, 0.0)
    elem.state.scale = Vec2(-2.0, 0.0)

    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)
    item = next(it for it in backend.last_frame if "flipped_actor" in it.asset_id)
    assert item.scale_x == -2.0
    assert item.scale_y == 0.0

    if PIL_AVAILABLE:
        pil_backend = PILRenderer(1280, 720)
        img = pil_backend.render_compositor(comp, 1280, 720)
        assert img.size == (1280, 720)


def test_stage_composition_rotations_beyond_full_turn() -> None:
    comp = StageCompositor(1920, 1080)
    comp.show_character("spinning_actor", "idle", position="center", transition="cut")
    elem = comp.stage.get_element("characters", "spinning_actor")
    assert elem is not None
    elem.state.rotation = 1440.5  # Four full turns + 0.5 degrees

    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)
    item = next(it for it in backend.last_frame if "spinning_actor" in it.asset_id)
    assert item.rotation == 1440.5

    if PIL_AVAILABLE:
        pil_backend = PILRenderer(1280, 720)
        img = pil_backend.render_compositor(comp, 1280, 720)
        assert img.size == (1280, 720)


def test_stage_composition_zero_opacity_culling() -> None:
    comp = StageCompositor(1920, 1080)
    comp.show_character("invisible_actor", "idle", position="center", transition="cut")
    elem = comp.stage.get_element("characters", "invisible_actor")
    assert elem is not None
    elem.state.opacity = 0.0

    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)
    # Fully transparent items must be culled from draw calls
    assert all("invisible_actor" not in it.asset_id for it in backend.last_frame)

    if PIL_AVAILABLE:
        pil_backend = PILRenderer(1280, 720)
        img = pil_backend.render_compositor(comp, 1280, 720)
        assert img.size == (1280, 720)


def test_stage_custom_layer_z_order_sorting() -> None:
    stage = Stage()
    # Insert custom behind-background layer and top-overlay layer
    layer_sub = Layer("sub_bg", z_order=-10)
    layer_top = Layer("super_overlay", z_order=999)
    stage.add_layer(layer_sub)
    stage.add_layer(layer_top)

    sorted_names = [l.name for l in stage.get_sorted_layers()]
    assert sorted_names[0] == "sub_bg"
    assert sorted_names[-1] == "super_overlay"


def test_stage_element_nonexistent_removal_and_lookup() -> None:
    stage = Stage()
    # Query non-existent element or remove from non-existent layer
    assert stage.get_element("background", "ghost_elem") is None
    assert stage.get_element("unknown_layer", "any") is None
    assert stage.find_element("ghost_elem") is None
    assert stage.layers["background"].remove_element("ghost_elem") is None

