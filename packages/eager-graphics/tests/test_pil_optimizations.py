"""Tests for PIL backend optimizations: putalpha path, lazy stage cache, preload."""

from __future__ import annotations

from pathlib import Path

import pytest

from eager_graphics import Anchor, Color, RenderItem, ScaleMode, StageCompositor
from eager_graphics.layout import LayoutResolver
from eager_graphics.renderers.pil import PIL_AVAILABLE, PILRenderer

pytestmark = pytest.mark.skipif(not PIL_AVAILABLE, reason="Pillow is not installed")


def test_putalpha_fastpath_produces_correct_alpha():
    """putalpha for opaque assets must produce alpha == final_alpha_byte in the cached sprite."""
    renderer = PILRenderer(800, 600)
    renderer._current_transform = LayoutResolver(1920, 1080).compute_viewport_transform(
        800, 600, mode=ScaleMode.STRETCH
    )

    item = RenderItem(
        asset_id="bg/test_bg",
        x=960.0, y=540.0,
        opacity=0.5, scale_x=1.0, scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.CENTER,
        tint=Color(1.0, 1.0, 1.0, 1.0),
        flip_h=False, flip_v=False,
        layer="background", z_order=0,
    )

    renderer.begin_frame()
    renderer.clear(Color(0.1, 0.1, 0.1, 1.0))
    renderer.draw_item(item)
    renderer.end_frame()

    # Check the sprite cache entry
    cache = renderer._sprite_cache
    assert len(cache) >= 1
    for transformed_img, is_opaque, _, _ in cache.values():
        # 0.5 * 255 = 127.5 → 128
        # With putalpha on an opaque asset, all pixels should have alpha=128
        pixels = list(transformed_img.get_flattened_data())
        assert pixels[0][3] == 128, f"Expected alpha=128, got {pixels[0]}"
        assert not is_opaque, "Sprite with opacity 0.5 should not be opaque"


def test_putalpha_fastpath_full_opacity_unchanged():
    """With opacity=1.0, putalpha shouldn't be called; sprite stays fully opaque."""
    renderer = PILRenderer(800, 600)
    renderer._current_transform = LayoutResolver(1920, 1080).compute_viewport_transform(
        800, 600, mode=ScaleMode.STRETCH
    )

    item = RenderItem(
        asset_id="bg/test_bg",
        x=960.0, y=540.0,
        opacity=1.0, scale_x=1.0, scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.CENTER,
        tint=Color(1.0, 1.0, 1.0, 1.0),
        flip_h=False, flip_v=False,
        layer="background", z_order=0,
    )

    renderer.begin_frame()
    renderer.clear(Color(0.1, 0.1, 0.1, 1.0))
    renderer.draw_item(item)
    renderer.end_frame()

    cache = renderer._sprite_cache
    for transformed_img, is_opaque, _, _ in cache.values():
        pixels = list(transformed_img.get_flattened_data())
        assert pixels[0][3] == 255, f"Expected alpha=255, got {pixels[0]}"
        assert is_opaque, "Full-opacity opaque sprite should be opaque"


def test_putalpha_does_not_corrupt_cached_texture():
    """putalpha must NOT modify the original base_tex in the asset resolver cache."""
    renderer = PILRenderer(800, 600)
    renderer._current_transform = LayoutResolver(1920, 1080).compute_viewport_transform(
        800, 600, mode=ScaleMode.STRETCH
    )

    for opacity in (0.5, 0.3, 1.0):
        renderer.clear_cache()
        renderer.begin_frame()
        renderer.clear(Color(0.1, 0.1, 0.1, 1.0))
        item = RenderItem(
            asset_id="bg/test_bg",
            x=960.0, y=540.0,
            opacity=opacity, scale_x=1.0, scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1.0, 1.0, 1.0, 1.0),
            flip_h=False, flip_v=False,
            layer="background", z_order=0,
        )
        renderer.draw_item(item)
        renderer.end_frame()

    # Verify the cached base texture still has alpha=255
    base_tex = renderer.asset_resolver._image_cache["bg/test_bg"]
    base_pixels = list(base_tex.get_flattened_data())
    assert base_pixels[0][3] == 255, "Base texture alpha was corrupted by putalpha!"


def test_lazy_stage_cache_copy_skipped_on_scene_change():
    """When render_list changes, stage cache should be cleared (no wasted copy)."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", transition="cut", duration=0.0)
    comp.show_character("alice", "smiling", position="left", transition="cut", duration=0.0)

    renderer = PILRenderer(1280, 720)
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._stage_cache is not None

    # Change the scene (move character instantly)
    comp.move_character("alice", "center", duration=0.0)
    renderer.render_compositor(comp, 1280, 720)
    # Scene changed → cache should be None (skipped copy)
    assert renderer._stage_cache is None


def test_lazy_stage_cache_preserved_when_static():
    """When render_list is identical, stage cache should be preserved."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", transition="cut", duration=0.0)
    comp.show_character("alice", "smiling", position="left", transition="cut", duration=0.0)

    renderer = PILRenderer(1280, 720)
    renderer.render_compositor(comp, 1280, 720)
    # First render creates the cache
    assert renderer._stage_cache is not None

    # Second render with same scene → cache hit, cache preserved
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._stage_cache is not None
    assert renderer._stage_cache.size == (1280, 720)


def test_sort_caching_invalidated_on_add():
    """Layer/Stage sort cache should be invalidated when elements are added."""
    from eager_graphics.stage import ElementState, Layer, Stage, StageElement

    layer = Layer(name="test", z_order=10)
    assert layer._sorted_cache is None
    layer.get_sorted_elements()
    assert layer._sorted_cache is not None
    # Adding element invalidates cache
    layer.add_element(StageElement("e1", ElementState(asset_id="a", z_index=1)))
    assert layer._sorted_cache is None
    # Re-sort works
    elems = layer.get_sorted_elements()
    assert len(elems) == 1
    assert layer._sorted_cache is not None

    # Stage sort cache
    stage = Stage()
    assert stage._sorted_cache is None
    stage.get_sorted_layers()
    assert stage._sorted_cache is not None
    # Adding a new layer invalidates cache
    stage.add_layer(Layer(name="new", z_order=1))
    assert stage._sorted_cache is None


def test_preload_assets():
    """preload_assets should resolve all stage assets and return count."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", transition="cut", duration=0.0)
    comp.show_character("alice", "smiling", position="left", transition="cut", duration=0.0)
    comp.show_character("bob", "serious", position="right", transition="cut", duration=0.0)

    renderer = PILRenderer(1280, 720)
    count = renderer.preload_assets(comp)
    assert count >= 3  # bg, alice, bob

    # Verify assets are cached
    assert renderer.asset_resolver._image_cache.get("bg/tavern") is not None
    assert renderer.asset_resolver._image_cache.get("alice/smiling") is not None
    assert renderer.asset_resolver._image_cache.get("bob/serious") is not None


def test_warm_sprite_cache():
    """warm_sprite_cache should populate sprite cache and return miss count."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", transition="cut", duration=0.0)
    comp.show_character("alice", "smiling", position="left", transition="cut", duration=0.0)

    renderer = PILRenderer(1280, 720)
    misses = renderer.warm_sprite_cache(comp, 1280, 720)
    assert misses > 0  # First warm should have misses
    assert renderer.cache_info()["currsize"] > 0
    assert renderer._stage_cache is not None
    assert renderer.frame_count == 0  # warm-up doesn't count

    # Second warm should have 0 new misses (all cached)
    misses2 = renderer.warm_sprite_cache(comp, 1280, 720)
    assert misses2 == 0


def test_scaled_cache_reuse_and_invalidation():
    """Verify scaled textures are cached across different opacities and cleared on clear_cache."""
    renderer = PILRenderer(1280, 720)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(1280, 720, mode=ScaleMode.LETTERBOX)

    item1 = RenderItem(
        asset_id="alice/smiling",
        x=960.0, y=540.0,
        opacity=1.0, scale_x=1.0, scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.CENTER,
        tint=Color(1.0, 1.0, 1.0, 1.0),
        flip_h=False, flip_v=False,
        layer="characters", z_order=1,
    )
    item2 = RenderItem(
        asset_id="alice/smiling",
        x=960.0, y=540.0,
        opacity=0.5, scale_x=1.0, scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.CENTER,
        tint=Color(1.0, 1.0, 1.0, 1.0),
        flip_h=False, flip_v=False,
        layer="characters", z_order=1,
    )

    renderer.begin_frame()
    renderer.draw_item(item1)
    renderer.end_frame()

    scale_key = ("alice/smiling", round(400 * renderer._current_transform.scale_x), round(800 * renderer._current_transform.scale_y))
    assert scale_key in renderer._scaled_cache
    cached_scaled = renderer._scaled_cache[scale_key]

    # Render with different opacity (cache miss in _sprite_cache, hit in _scaled_cache)
    renderer.begin_frame()
    renderer.draw_item(item2)
    renderer.end_frame()

    assert renderer._scaled_cache[scale_key] is cached_scaled

    # clear_cache clears _scaled_cache
    renderer.clear_cache()
    assert len(renderer._scaled_cache) == 0


def test_font_and_measure_cache():
    """Verify font and text measurement caching and invalidation."""
    renderer = PILRenderer(800, 600)
    assert len(renderer._font_cache) == 0
    assert len(renderer._measure_cache) == 0

    # Measuring text populates font and measurement caches
    dim1 = renderer.measure_text("Hello World", font_size=16)
    assert 16 in renderer._font_cache
    assert ("Hello World", 16) in renderer._measure_cache
    assert dim1[0] > 0 and dim1[1] > 0

    # Repeat call returns cached tuple
    dim2 = renderer.measure_text("Hello World", font_size=16)
    assert dim1 == dim2

    # clear_cache clears font and measure caches
    renderer.clear_cache()
    assert len(renderer._font_cache) == 0
    assert len(renderer._measure_cache) == 0


def test_ui_image_cache():
    """Verify draw_image caches scaled and tinted UI sprites."""
    renderer = PILRenderer(400, 300)
    renderer.begin_frame()
    renderer.clear(Color(0, 0, 0, 1))

    # Draw image
    renderer.draw_image("bg/test", 10, 10, 50, 50, tint=Color(1.0, 0.5, 0.5, 1.0))
    renderer.end_frame()

    assert len(renderer._ui_image_cache) == 1
    key = ("bg/test", 50, 50, Color(1.0, 0.5, 0.5, 1.0).to_rgba_bytes())
    assert key in renderer._ui_image_cache

    # clear_cache clears ui image cache
    renderer.clear_cache()
    assert len(renderer._ui_image_cache) == 0


def test_apply_tint_to_image_accuracy():
    """_apply_tint_to_image should multiply tint into RGBA channels via C-point LUT."""
    from PIL import Image

    renderer = PILRenderer(100, 100)
    im = Image.new("RGBA", (10, 10), (200, 100, 50, 255))
    tint = Color(0.5, 1.0, 0.0, 0.5)  # 128, 255, 0, 128
    tinted = renderer._apply_tint_to_image(im, tint)

    # Pixel should be (round(200*0.5), round(100*1.0), round(50*0.0), round(255*0.5))
    # -> (100, 100, 0, 128)
    px = tinted.getpixel((0, 0))
    assert px == (100, 100, 0, 128)


def test_background_crossfade_image_blend():
    """render_compositor should fast-path crossfade blending between two opaque backgrounds."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/bg1", duration=0.0)
    comp.set_background("bg/bg2", transition="crossfade", duration=1.0)
    comp.step(0.5)  # halfway through crossfade

    renderer = PILRenderer(1280, 720, scale_mode=ScaleMode.STRETCH)
    img = renderer.render_compositor(comp, 1280, 720)
    assert img.size == (1280, 720)
    assert renderer.frame_count == 1
    # Both items should be in last_frame
    assert len(renderer.last_frame) == 2


def test_pil_player_idle_frame_skipping():
    """PILPlayer should track _ui_dirty and skip redundant blits on static frames."""
    from eager_runtime import GameSession
    from eager_script import parse_graph

    from eager_graphics.renderers.pil import PILPlayer

    graph = parse_graph("## Start --- start\nAlice: Hello!\n")
    session = GameSession(graph)

    player = PILPlayer(
        session=session,
        width=800,
        height=600,
        visible=False,
    )
    try:
        # First draw should clear _ui_dirty
        assert player._ui_dirty is True
        player.on_draw()
        assert player._ui_dirty is False
        assert player.renderer.frame_count == 1

        # Second draw with no stage movement and no narrative change should use fast-path
        player.on_draw()
        assert player.renderer.frame_count == 2
        assert player._ui_dirty is False

        # Advancing or making a choice sets _ui_dirty back to True
        player.advance_story()
        assert player._ui_dirty is True
    finally:
        player.close()


def test_pil_player_uncapped_mode():
    """PILPlayer with uncapped=True should configure vsync=False and uncapped clock tick."""
    from eager_runtime import GameSession
    from eager_script import parse_graph

    from eager_graphics.renderers.pil import PILPlayer

    graph = parse_graph("## Start --- start\nAlice: Hello!\n")
    session = GameSession(graph)

    player = PILPlayer(
        session=session,
        width=800,
        height=600,
        visible=False,
        uncapped=True,
    )
    try:
        assert player.uncapped is True
        assert player.vsync is False
        player.tick(0.001)
        player.on_draw()
        assert player.renderer.frame_count == 1
    finally:
        player.close()


def test_hierarchical_background_layer_caching():
    """When characters change, pre-rendered background cache (_bg_cache) must be reused."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="left", duration=0.0)

    renderer = PILRenderer(1280, 720)
    renderer.render_compositor(comp, 1280, 720)

    # Both background cache and stage cache are populated
    assert renderer._bg_cache is not None
    assert renderer._stage_cache is not None
    cached_bg = renderer._bg_cache

    # Character changes emotion: stage cache invalidates, but _bg_cache MUST be preserved
    comp.show_character("alice", "surprised", position="left", duration=0.0)
    renderer.render_compositor(comp, 1280, 720)

    assert renderer._bg_cache is cached_bg
    # Character moved: _bg_cache still preserved
    comp.move_character("alice", "center", duration=0.0)
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._bg_cache is cached_bg

    # Changing the background updates _bg_cache with new background
    comp.set_background("bg/forest", transition="cut", duration=0.0)
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._bg_cache is not None
    assert renderer._bg_cache is not cached_bg


def test_alpha_fading_decoupled_from_geometry_cache():
    """Alpha fading over multiple frames must reuse base geometry and cache quantized masks."""
    renderer = PILRenderer(800, 600)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(800, 600, mode=ScaleMode.STRETCH)

    # Render a character fading across multiple opacity values
    opacities = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    for op in opacities:
        renderer.begin_frame()
        item = RenderItem(
            asset_id="alice/smiling",
            x=960.0,
            y=540.0,
            opacity=op,
            scale_x=1.0,
            scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1.0, 1.0, 1.0, 1.0),
            flip_h=False,
            flip_v=False,
            layer="characters",
            z_order=1,
        )
        renderer.draw_item(item)
        renderer.end_frame()

    # _geom_cache must contain exactly 1 entry for alice's geometry (not 10!)
    assert len(renderer._geom_cache) == 1
    geom_entry = next(iter(renderer._geom_cache.values()))
    # alpha_masks dict on the geom entry should have cached the quantized masks
    assert len(geom_entry.alpha_masks) > 0


def test_adaptive_resampling_during_transformation():
    """Actively moving/scaling items should use NEAREST resampling; resting items use high-quality filter."""
    from PIL import Image

    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="left", duration=0.0)

    renderer = PILRenderer(1280, 720, resampling=Image.Resampling.BILINEAR, adaptive_resampling=True)
    renderer.render_compositor(comp, 1280, 720)

    # Initial frame: resting, not in motion
    assert len(renderer._in_motion_assets) == 0

    # Frame 2: Start moving character across frames (motion in progress)
    comp.move_character("alice", "center", duration=1.0)
    comp.step(0.5)
    renderer.render_compositor(comp, 1280, 720)

    assert "alice/smiling" in renderer._in_motion_assets

    # Frame 3: Element reaches rest (no geometry change)
    comp.step(1.0)  # complete tween
    renderer.render_compositor(comp, 1280, 720)  # resting render
    renderer.render_compositor(comp, 1280, 720)  # stationary comparison
    assert "alice/smiling" not in renderer._in_motion_assets


def test_localized_ui_dirty_subregion_restore():
    """When only UI is drawn on a static stage, only the dirty subregion is restored from stage cache."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)

    renderer = PILRenderer(1280, 720)
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._stage_cache is not None

    # Immediate-mode UI draws a textbox at the bottom (y=500 to 700)
    renderer.draw_rect(50, 500, 1180, 200, Color(0.1, 0.1, 0.1, 0.8))
    assert renderer._ui_dirty_bbox is not None
    _x0, y0, _x1, y1 = renderer._ui_dirty_bbox
    assert y0 >= 500 and y1 <= 701

    # Next render_compositor call with unchanged stage: dirty bbox is used and reset
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._ui_dirty_bbox is None


def test_pil_player_shift_r_hot_reload(tmp_path: Path) -> None:
    """Pressing Shift+R in PILPlayer should reload script, set _ui_dirty = True, and update UI."""
    import time
    from types import SimpleNamespace

    from eager_runtime.session import GameSession

    from eager_graphics.renderers.pil import PILPlayer

    script_file = tmp_path / "game.es"
    script_file.write_text(
        "## Start --- start\nNarrator: First draft\n",
        encoding="utf-8",
    )

    session = GameSession(script_file)
    player = PILPlayer(session=session, width=800, height=600, visible=False)
    try:
        # First draw clears _ui_dirty
        player.on_draw()
        assert player._ui_dirty is False
        assert player.current_text == "First draft"

        # Edit script on disk
        time.sleep(0.05)
        script_file.write_text(
            "## Start --- start\nNarrator: Hot reloaded draft!\n",
            encoding="utf-8",
        )

        # Simulate Shift+R key event (keysym 'r', state with Shift mask 0x0001)
        player._on_key(SimpleNamespace(keysym="r", state=0x0001))

        # Check: _ui_dirty set to True and text updated
        assert player._ui_dirty is True
        assert player.current_text == "Hot reloaded draft!"
        assert session.director.ui_state.text == "Hot reloaded draft!"

        # Draw frame: forces redraw and clears _ui_dirty
        initial_frames = player.renderer.frame_count
        player.on_draw()
        assert player.renderer.frame_count == initial_frames + 1
        assert player._ui_dirty is False
    finally:
        player.close()



