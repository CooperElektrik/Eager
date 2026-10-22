"""Comprehensive unit and integration tests for PILRenderer, PILAssetResolver, and PILPlayer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from eager_runtime import GameSession
from eager_script import parse_graph

from eager_graphics import (
    Anchor,
    Color,
    DebugOverlayMode,
    LayoutResolver,
    RenderItem,
    ScaleMode,
    StageCompositor,
)
from eager_graphics.renderers.pil import (
    PIL_AVAILABLE,
    PILAssetResolver,
    PILPlayer,
    PILRenderer,
)

pytestmark = pytest.mark.skipif(not PIL_AVAILABLE, reason="Pillow is not installed")

if PIL_AVAILABLE:
    from PIL import Image


# ---------------------------------------------------------------------- #
# PILAssetResolver Tests
# ---------------------------------------------------------------------- #


def test_pil_asset_resolver_placeholders() -> None:
    resolver = PILAssetResolver(asset_dir=None)

    # 1. Background placeholder
    bg_img = resolver.get_image("bg/castle_gate")
    assert bg_img is not None
    assert bg_img.width == 1920
    assert bg_img.height == 1080
    assert bg_img.mode == "RGBA"
    assert resolver.is_asset_opaque("bg/castle_gate") is True

    # Cache should return exact same instance
    assert resolver.get_image("bg/castle_gate") is bg_img

    # 2. Character placeholder
    char_img = resolver.get_image("alice/cheerful", default_width=400, default_height=800)
    assert char_img is not None
    assert char_img.width == 400
    assert char_img.height == 800
    assert char_img.mode == "RGBA"
    assert resolver.get_image("alice/cheerful") is char_img

    # Different asset_id should yield different texture
    guard_img = resolver.get_image("guard/stern")
    assert guard_img is not char_img


def test_pil_asset_resolver_disk_load(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()

    # Create dummy PNG and JPG
    test_png = Image.new("RGBA", (200, 300), (255, 0, 0, 255))
    test_png.save(asset_dir / "hero.png")

    test_jpg = Image.new("RGB", (640, 480), (0, 255, 0))
    test_jpg.save(asset_dir / "landscape.jpg")

    resolver = PILAssetResolver(asset_dir=asset_dir)

    hero_img = resolver.get_image("hero")
    assert hero_img.size == (200, 300)
    assert hero_img.mode == "RGBA"
    assert resolver.is_asset_opaque("hero") is True

    land_img = resolver.get_image("landscape")
    assert land_img.size == (640, 480)
    assert land_img.mode == "RGBA"
    assert resolver.is_asset_opaque("landscape") is True

    # Test candidate path resolution: characters/ and backgrounds/
    char_sub = asset_dir / "characters" / "guide"
    char_sub.mkdir(parents=True)
    guide_png = Image.new("RGBA", (100, 200), (0, 0, 255, 255))
    guide_png.save(char_sub / "smile.png")

    bg_sub = asset_dir / "backgrounds"
    bg_sub.mkdir(parents=True)
    room_jpg = Image.new("RGB", (320, 240), (128, 128, 128))
    room_jpg.save(bg_sub / "room.jpg")

    guide_img = resolver.get_image("guide/smile")
    assert guide_img.size == (100, 200)

    bg_img = resolver.get_image("bg/room")
    assert bg_img.size == (320, 240)


# ---------------------------------------------------------------------- #
# Protocol & Lifecycle Tests
# ---------------------------------------------------------------------- #


def test_pil_renderer_implements_render_backend() -> None:
    backend = PILRenderer(1280, 720)
    assert hasattr(backend, "begin_frame")
    assert hasattr(backend, "clear")
    assert hasattr(backend, "draw_item")
    assert hasattr(backend, "end_frame")
    assert hasattr(backend, "render_compositor")


def test_pil_renderer_lifecycle_errors() -> None:
    backend = PILRenderer(1280, 720)

    # Calling draw_item before begin_frame raises RuntimeError
    item = RenderItem(
        asset_id="bg/castle",
        x=0.0,
        y=0.0,
        opacity=1.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.TOP_LEFT,
        tint=Color(1, 1, 1, 1),
        flip_h=False,
        flip_v=False,
        layer="background",
        z_order=0,
    )
    with pytest.raises(RuntimeError, match="outside of begin_frame"):
        backend.draw_item(item)

    # Calling end_frame before begin_frame raises RuntimeError
    with pytest.raises(RuntimeError, match="without matching begin_frame"):
        backend.end_frame()

    # Calling begin_frame twice without end_frame raises RuntimeError
    backend.begin_frame()
    with pytest.raises(RuntimeError, match="without matching end_frame"):
        backend.begin_frame()

    backend.end_frame()


def test_pil_renderer_clear() -> None:
    backend = PILRenderer(100, 100)
    backend.begin_frame()
    backend.clear(Color(1.0, 0.0, 0.0, 1.0))
    backend.end_frame()

    img = backend.get_image()
    # Check top-left pixel is red
    pixel = img.getpixel((0, 0))
    assert pixel[:3] == (255, 0, 0)


# ---------------------------------------------------------------------- #
# Compositing & Transform Tests
# ---------------------------------------------------------------------- #


def test_pil_renderer_draw_items() -> None:
    renderer = PILRenderer(1280, 720, scale_mode=ScaleMode.LETTERBOX)

    compositor = StageCompositor(1920, 1080)
    compositor.set_background("bg/castle", duration=0.0)
    compositor.show_character("alice", "happy", position="left", duration=0.0)
    compositor.show_character("bob", "serious", position="right", duration=0.0, flip_h=True)

    result_img = renderer.render_compositor(compositor, 1280, 720)
    assert result_img.size == (1280, 720)
    assert renderer.frame_count == 1
    assert len(renderer.last_frame) == 3


def test_pil_renderer_draw_item_properties() -> None:
    renderer = PILRenderer(800, 600, scale_mode=ScaleMode.STRETCH)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(800, 600, mode=ScaleMode.STRETCH)
    renderer.begin_frame()
    renderer.clear(Color(0.1, 0.1, 0.1, 1.0))

    item = RenderItem(
        asset_id="alice/happy",
        x=400.0,
        y=300.0,
        opacity=0.8,
        scale_x=1.2,
        scale_y=1.2,
        rotation=15.0,
        anchor=Anchor.CENTER,
        tint=Color(1.0, 0.5, 0.5, 1.0),
        flip_h=True,
        flip_v=False,
        layer="characters",
        z_order=100,
    )

    renderer.draw_item(item)
    renderer.end_frame()

    assert renderer.frame_count == 1
    assert len(renderer.last_frame) == 1
    info = renderer.cache_info()
    assert info["currsize"] == 1
    assert info["misses"] == 1

    # Drawing the exact same item in next frame should trigger cache hit
    renderer.begin_frame()
    renderer.draw_item(item)
    renderer.end_frame()

    info2 = renderer.cache_info()
    assert info2["hits"] == 1


def test_pil_renderer_orthogonal_rotations() -> None:
    """Verify 90, 180, and 270 degree rotations use orthogonal fast-paths."""
    renderer = PILRenderer(500, 500)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(500, 500, mode=ScaleMode.STRETCH)

    for rot in (90.0, 180.0, 270.0):
        renderer.begin_frame()
        item = RenderItem(
            asset_id="box",
            x=250.0,
            y=250.0,
            opacity=1.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation=rot,
            anchor=Anchor.CENTER,
            tint=Color(1, 1, 1, 1),
            flip_h=False,
            flip_v=False,
            layer="props",
            z_order=10,
        )
        renderer.draw_item(item)
        renderer.end_frame()

    assert renderer.frame_count == 3


def test_pil_renderer_flips() -> None:
    renderer = PILRenderer(500, 500)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(500, 500, mode=ScaleMode.STRETCH)
    renderer.begin_frame()

    # Flip horizontal only
    renderer.draw_item(
        RenderItem(
            asset_id="char/h",
            x=100,
            y=100,
            opacity=1.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1, 1, 1, 1),
            flip_h=True,
            flip_v=False,
            layer="characters",
            z_order=1,
        )
    )

    # Flip vertical only
    renderer.draw_item(
        RenderItem(
            asset_id="char/v",
            x=200,
            y=100,
            opacity=1.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1, 1, 1, 1),
            flip_h=False,
            flip_v=True,
            layer="characters",
            z_order=2,
        )
    )

    # Flip both (180 deg)
    renderer.draw_item(
        RenderItem(
            asset_id="char/hv",
            x=300,
            y=100,
            opacity=1.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1, 1, 1, 1),
            flip_h=True,
            flip_v=True,
            layer="characters",
            z_order=3,
        )
    )

    renderer.end_frame()
    assert len(renderer.last_frame) == 3


def test_pil_renderer_culling_and_early_exits() -> None:
    renderer = PILRenderer(500, 500)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(500, 500, mode=ScaleMode.STRETCH)
    renderer.begin_frame()

    # Item with opacity 0 should be discarded
    renderer.draw_item(
        RenderItem(
            asset_id="invisible",
            x=250,
            y=250,
            opacity=0.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1, 1, 1, 1),
            flip_h=False,
            flip_v=False,
            layer="characters",
            z_order=1,
        )
    )

    # Item with scale 0 should be discarded
    renderer.draw_item(
        RenderItem(
            asset_id="zero_scale",
            x=250,
            y=250,
            opacity=1.0,
            scale_x=0.0,
            scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1, 1, 1, 1),
            flip_h=False,
            flip_v=False,
            layer="characters",
            z_order=2,
        )
    )

    # Item completely offscreen should be culled
    renderer.draw_item(
        RenderItem(
            asset_id="offscreen",
            x=-5000,
            y=-5000,
            opacity=1.0,
            scale_x=1.0,
            scale_y=1.0,
            rotation=0.0,
            anchor=Anchor.CENTER,
            tint=Color(1, 1, 1, 1),
            flip_h=False,
            flip_v=False,
            layer="characters",
            z_order=3,
        )
    )

    renderer.end_frame()
    assert renderer.frame_count == 1


def test_pil_renderer_scale_modes() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/field", transition="cut")

    for mode in (
        ScaleMode.LETTERBOX,
        ScaleMode.STRETCH,
        ScaleMode.CROP,
        ScaleMode.FIT_WIDTH,
        ScaleMode.FIT_HEIGHT,
    ):
        renderer = PILRenderer(1280, 720, scale_mode=mode)
        img = renderer.render_compositor(comp, 1280, 720)
        assert img.size == (1280, 720)


def test_pil_renderer_letterbox_borders() -> None:
    """In letterbox mode with wide aspect ratio, black bars must be drawn."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/sky", transition="cut")

    # Ultra-wide display (2560x720) will pillarbox left and right
    renderer = PILRenderer(2560, 720, scale_mode=ScaleMode.LETTERBOX)
    img = renderer.render_compositor(comp, 2560, 720)

    # Far-left column should be black letterbox bar
    assert img.getpixel((0, 360))[:3] == (0, 0, 0)


def test_pil_renderer_clear_cache() -> None:
    renderer = PILRenderer(800, 600)
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/sky", transition="cut")

    renderer.render_compositor(comp, 800, 600)
    assert renderer.cache_info()["currsize"] > 0

    renderer.clear_cache()
    assert renderer.cache_info()["currsize"] == 0
    assert renderer.cache_info()["hits"] == 0


def test_pil_renderer_save_and_bytes(tmp_path: Path) -> None:
    renderer = PILRenderer(400, 300)
    renderer.begin_frame()
    renderer.clear(Color(0.2, 0.4, 0.6, 1.0))
    renderer.end_frame()

    # 1. to_bytes
    png_bytes = renderer.to_bytes("PNG")
    assert png_bytes.startswith(b"\x89PNG")

    jpg_bytes = renderer.to_bytes("JPEG")
    assert jpg_bytes.startswith(b"\xff\xd8")

    # 2. save_frame
    file_path = tmp_path / "frame.png"
    renderer.save_frame(file_path)
    assert file_path.is_file()
    assert file_path.stat().st_size > 0


@pytest.mark.skipif(not PIL_AVAILABLE, reason="Pillow is not installed")
def test_pil_player_story_progression() -> None:
    """PILPlayer story logic runs headless (tkinter only needed for run())."""
    screenplay = """
    ## Start --- start
    ~ bg tavern with cut
    ~ show alice smiling at left with cut
    Alice: Welcome!
    ? Option 1 (opt1)
    ? Option 2 (opt2)

    ## Option 1 --- opt1
    Alice: You picked option 1.

    ## Option 2 --- opt2
    Alice: You picked option 2.
    """
    from eager_runtime import GameSession

    graph = parse_graph(screenplay)
    session = GameSession(graph)

    player = PILPlayer(
        session=session,
        width=800,
        height=450,
        visible=False,
    )

    try:
        # Upon init, advance_story stepped to the first dialogue: Alice: Welcome!
        assert player.current_speaker == "Alice"
        assert player.current_text == "Welcome!"
        assert player.active_choice_prompt is None

        # Next advance reaches the choice prompt
        player.advance_story()
        assert player.active_choice_prompt is not None
        assert len(player.active_choice_prompt.options) == 2

        # Selecting Option 1 (index 0) branches to opt1
        player.make_choice(0)
        assert player.active_choice_prompt is None
        assert player.current_text == "You picked option 1."

        # Test rollback
        assert player.rollback() is True

        # Advance to story end
        player.advance_story()
        if player.active_choice_prompt is not None:
            player.make_choice(0)
        player.advance_story()
        assert player.is_finished

        # Test on_draw passes without error
        player.on_draw()

    finally:
        player.close()


@pytest.mark.skipif(not PIL_AVAILABLE, reason="Pillow is not installed")
def test_pil_player_with_session() -> None:
    """PILPlayer operates correctly when wired with GameSession."""
    from eager_runtime import GameSession

    screenplay = """
    ## Start --- start
    Alice: Welcome from session!
    Alice: Second line.
    """
    graph = parse_graph(screenplay)
    session = GameSession(graph)

    player = PILPlayer(
        session=session,
        width=800,
        height=450,
        visible=False,
    )
    try:
        assert session.director.ui_state.text == "Welcome from session!"
        player.advance_story()
        assert session.director.ui_state.text == "Second line!" or "Second line." in session.director.ui_state.text

        # Test on_key routing through keymap (Backspace -> ROLLBACK)
        class FakeKeyEvent:
            keysym = "BackSpace"

        player._on_key(FakeKeyEvent())
        assert "Welcome from session!" in session.director.ui_state.text

        # Test on_draw
        player.on_draw()
    finally:
        player.close()


def test_pil_renderer_lazy_clear() -> None:
    """Lazy clear defers buffer clear until needed, skipping redundant fills."""
    renderer = PILRenderer(200, 200)

    # 1. Clear with red, but render opaque fullscreen item over it
    renderer.begin_frame()
    renderer.clear(Color(1.0, 0.0, 0.0, 1.0))
    assert renderer._needs_clear is True

    # Draw 1x1 opaque white rect scaled to fullscreen
    item = RenderItem(
        asset_id="__builtin_color_rect__",
        x=0,
        y=0,
        opacity=1.0,
        scale_x=200,
        scale_y=200,
        rotation=0,
        anchor=Anchor.TOP_LEFT,
        tint=Color(1, 1, 1, 1),
        flip_h=False,
        flip_v=False,
        layer="background",
        z_order=0,
    )
    renderer._current_transform = LayoutResolver(200, 200).compute_viewport_transform(200, 200, mode=ScaleMode.STRETCH)
    renderer.draw_item(item)
    # The clear should have been bypassed because the opaque item covers the entire canvas
    assert renderer._needs_clear is False
    renderer.end_frame()
    assert renderer.get_image().getpixel((0, 0))[:3] == (255, 255, 255)

    # 2. Clear with green and render translucent item -> clear must execute
    renderer.begin_frame()
    renderer.clear(Color(0.0, 1.0, 0.0, 1.0))
    assert renderer._needs_clear is True
    item_trans = RenderItem(
        asset_id="__builtin_color_rect__",
        x=0,
        y=0,
        opacity=0.5,
        scale_x=100,
        scale_y=100,
        rotation=0,
        anchor=Anchor.TOP_LEFT,
        tint=Color(1, 0, 0, 1),
        flip_h=False,
        flip_v=False,
        layer="characters",
        z_order=1,
    )
    renderer.draw_item(item_trans)
    assert renderer._needs_clear is False
    renderer.end_frame()
    # Bottom-right untouched pixel must be green
    assert renderer.get_image().getpixel((150, 150))[:3] == (0, 255, 0)


def test_pil_renderer_anchor_cache_isolation() -> None:
    """Same asset drawn with different anchors must have distinct destination coordinates."""
    renderer = PILRenderer(400, 400)
    layout = LayoutResolver(400, 400)
    renderer._current_transform = layout.compute_viewport_transform(400, 400, mode=ScaleMode.STRETCH)

    renderer.begin_frame()
    item_tl = RenderItem(
        asset_id="char",
        x=200,
        y=200,
        opacity=1.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.TOP_LEFT,
        tint=Color(1, 1, 1, 1),
        flip_h=False,
        flip_v=False,
        layer="characters",
        z_order=1,
    )
    renderer.draw_item(item_tl)

    item_c = RenderItem(
        asset_id="char",
        x=200,
        y=200,
        opacity=1.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.CENTER,
        tint=Color(1, 1, 1, 1),
        flip_h=False,
        flip_v=False,
        layer="characters",
        z_order=2,
    )
    renderer.draw_item(item_c)
    renderer.end_frame()

    # Cache must contain distinct entries for distinct anchors
    assert renderer.cache_info()["currsize"] == 2
    assert renderer.cache_info()["misses"] == 2


def test_pil_renderer_tinted_opaque_remains_opaque() -> None:
    """Color tinted items without opacity reduction remain opaque for fast direct paste."""
    renderer = PILRenderer(200, 200)
    renderer.asset_resolver.get_image("bg/castle")
    assert renderer.asset_resolver.is_asset_opaque("bg/castle") is True

    # Transform with color tint and opacity 1.0
    item = RenderItem(
        asset_id="bg/castle",
        x=0,
        y=0,
        opacity=1.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation=0,
        anchor=Anchor.TOP_LEFT,
        tint=Color(1.0, 0.5, 0.5, 1.0),
        flip_h=False,
        flip_v=False,
        layer="background",
        z_order=0,
    )
    _img, is_opaque, _off_x, _off_y = renderer._transform_sprite(
        renderer.asset_resolver.get_image("bg/castle"),
        item,
        200,
        200,
        0.0,
        1.0,
        (255, 128, 128, 255),
        0.0,
        0.0,
    )
    assert is_opaque is True


def test_pil_renderer_stage_caching() -> None:
    """Unchanged stage lists must reuse the rendered stage cache buffer."""
    renderer = PILRenderer(800, 600)
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/sky", transition="cut")

    img1 = renderer.render_compositor(comp, 800, 600)
    assert img1.size == (800, 600)
    assert renderer.frame_count == 1
    assert renderer._stage_cache is not None

    # Next frame with identical items reuses stage cache
    img2 = renderer.render_compositor(comp, 800, 600)
    assert renderer.frame_count == 2
    assert img2.size == (800, 600)


def test_pil_player_typewriter_reveal_progression() -> None:
    """Verify PILPlayer renders each character reveal step without freezing on static stage."""
    from eager_runtime.session import GameSession

    script = """
    ## Start --- start
    Alice: Testing typewriter.
    """
    graph = parse_graph(script)
    session = GameSession(graph)
    player = PILPlayer(session=session, visible=False)
    player._photo = "dummy"

    rendered_chars: list[int | None] = []
    orig_draw = player.overlay.draw

    def spy_draw(backend: object, ui_state: object, *a: object, **k: object) -> object:
        rendered_chars.append(getattr(ui_state, "visible_chars", None))
        return orig_draw(backend, ui_state, *a, **k)

    player.overlay.draw = spy_draw  # type: ignore[assignment]

    # Advance 15 frames while text reveals
    for _ in range(15):
        player.tick(1.0 / 60.0)
        player.on_draw()

    # All frames while revealing must have been drawn, not skipped
    assert len(rendered_chars) >= 10
    # First few frames should show incremental reveals (0, 1, 2, ...)
    assert rendered_chars[0] == 0
    assert rendered_chars[1] == 1
    assert rendered_chars[2] == 2

    # Advance until complete
    for _ in range(60):
        player.tick(1.0 / 60.0)
        player.on_draw()

    # Once complete, visible_chars is None
    assert session.text_reveal is not None and session.text_reveal.is_complete
    count_after_complete = len(rendered_chars)

    # Next frames with idle dialogue should use the static frame cache and not call overlay.draw
    for _ in range(5):
        player.tick(1.0 / 60.0)
        player.on_draw()

    assert len(rendered_chars) == count_after_complete
    player.close()


def test_pil_renderer_debug_info_and_repr() -> None:
    """PILRenderer.debug_info and debug_repr should snapshot optimization & cache state."""
    renderer = PILRenderer(width=640, height=360)
    info = renderer.debug_info()

    assert "performance" in info
    assert "stage_caching" in info
    assert "motion_resampling" in info
    assert "caches" in info
    assert "backend" in info

    assert info["backend"]["dimensions"] == (640, 360)
    assert info["stage_caching"]["last_render_path"] == "None"
    assert info["caches"]["sprite_lru"]["max_items"] == renderer.max_cached_sprites

    repr_str = renderer.debug_repr()
    assert "── Eager Debug: PIL Backend ──────────────────────────" in repr_str
    assert "FPS:" in repr_str
    assert "Render Path: None" in repr_str
    assert "Cache Diagnostics" in repr_str

    # Render with compositor and check updated debug info
    comp = StageCompositor(640, 360)
    comp.set_background("bg/room", transition="cut")
    renderer.render_compositor(comp, 640, 360)

    info_after = renderer.debug_info()
    assert info_after["stage_caching"]["last_render_path"] == "Full Repaint"
    assert info_after["stage_caching"]["bg_cached"] is True
    assert renderer.debug_repr().count("Render Path: Full Repaint") == 1


def test_pil_player_debug_overlay_modes_and_details() -> None:
    """PILPlayer debug overlay should support OFF, FPS, and DETAILED modes."""
    graph = parse_graph(
        "## Start --- start\n"
        "Alice: Welcome to the test!\n"
    )
    session = GameSession(graph)

    # Start in detailed mode
    player = PILPlayer(
        session=session,
        width=800,
        height=600,
        visible=False,
        show_fps=DebugOverlayMode.DETAILED,
    )
    try:
        assert player.debug_mode == DebugOverlayMode.DETAILED
        assert player.show_fps is True

        player.tick(0.016)
        player.on_draw()

        text = player.get_debug_overlay_text()
        assert "Eager Debug: PIL Backend" in text
        assert ("Render Path: Tier 3 (Stage Cache / UI Only)" in text) or ("Render Path: Full Repaint" in text)
        assert "Sprite LRU:" in text
        assert "UI: speaker: Alice" in text

        # Complete typewriter text reveal so the frame becomes idle
        if session.text_reveal is not None:
            session.text_reveal.update(10.0)
        player._sync_overlay()
        player._ui_dirty = False
        # Fake photo cache present so idle skip path is eligible
        player._photo = object()

        player.tick(0.016)
        player.on_draw()
        assert "Tier 0 (Idle Skip)" in player.get_debug_overlay_text()

        # Setter tests
        player.show_fps = False
        assert player.debug_mode == DebugOverlayMode.OFF
        assert player.show_fps is False
        assert player.get_debug_overlay_text() == ""

        player.show_fps = True
        assert player.debug_mode == DebugOverlayMode.FPS
        assert player.show_fps is True
        assert "FPS:" in player.get_debug_overlay_text()
        assert "Cache Diagnostics" not in player.get_debug_overlay_text()

        player.show_fps = "detailed"
        assert player.debug_mode == DebugOverlayMode.DETAILED
        assert "Cache Diagnostics" in player.get_debug_overlay_text()
    finally:
        player.close()


def test_pil_player_mouse_handlers_sync_active_input_prompt() -> None:
    """Verify _on_click, _on_scroll_up, and _on_scroll_down sync active_input_prompt."""
    screenplay = """
    ## Start --- start
    Alice: Hi!
    ~ input hero_name Enter your name:
    Alice: Welcome [hero_name]
    Alice: Another line
    """
    class DummyEvent:
        x = 100
        y = 100

    graph = parse_graph(screenplay)
    session = GameSession(graph)

    player = PILPlayer(
        session=session,
        width=800,
        height=600,
        visible=False,
    )
    try:
        assert player.active_input_prompt is None
        # Complete typewriter text reveal so next click advances to input prompt
        if session.text_reveal is not None:
            session.text_reveal.complete_immediately()
        # Click should advance into input prompt
        player._on_click(DummyEvent())
        assert player.active_input_prompt is not None
        assert player.active_input_prompt.var_name == "hero_name"

        # Submit input and advance to Another line
        session.submit_input("Champion")
        player.advance_story()
        assert player.active_input_prompt is None

        # Scroll up 1: rollback to 'Welcome Champion'
        player._on_scroll_up(DummyEvent())
        assert player.active_input_prompt is None

        # Scroll up 2: rollback onto input prompt
        player._on_scroll_up(DummyEvent())
        assert player.active_input_prompt is not None
        assert player.active_input_prompt.var_name == "hero_name"
    finally:
        player.close()


def test_pil_renderer_draw_rect_alpha_blending() -> None:
    """Verify PILRenderer.draw_rect properly alpha-blends semi-transparent colors."""
    renderer = PILRenderer(200, 200, mode="RGB")
    # Base background (51, 51, 51)
    renderer.draw_rect(0, 0, 200, 200, Color(0.2, 0.2, 0.2, 1.0))

    # Draw subtle white hover pill (alpha 0.08)
    hover_pill = Color(1.0, 1.0, 1.0, 0.08)
    renderer.draw_rect(10, 10, 80, 40, hover_pill)

    img = renderer.get_image()
    pixel = img.getpixel((20, 20))
    # Must NOT be solid white (255, 255, 255)
    assert pixel != (255, 255, 255)
    # Expected alpha blend: 51 + (255 - 51) * (20 / 255) = 67
    assert 60 <= pixel[0] <= 75
    assert pixel[0] == pixel[1] == pixel[2]


def test_pil_renderer_draw_rect_outline() -> None:
    """Verify PILRenderer.draw_rect_outline draws stroked borders with alpha."""
    renderer = PILRenderer(200, 200, mode="RGB")
    renderer.draw_rect(0, 0, 200, 200, Color(0.2, 0.2, 0.2, 1.0))

    border_color = Color(1.0, 1.0, 1.0, 0.50)
    renderer.draw_rect_outline(10, 10, 100, 50, border_color, line_width=2.0)

    img = renderer.get_image()
    # Border pixel at (10, 10) should be blended with 50% white: ~153
    border_px = img.getpixel((10, 10))
    assert 140 <= border_px[0] <= 165

    # Center pixel at (50, 35) must be untouched (51, 51, 51)
    center_px = img.getpixel((50, 35))
    assert center_px == (51, 51, 51)


def test_pil_quick_menu_hover_highlight() -> None:
    """Verify hovering over QuickMenu buttons produces subtle highlights without solid white rectangles."""
    from eager_graphics.ui_components import QuickMenu

    renderer = PILRenderer(1280, 720, mode="RGB")
    renderer.draw_rect(0, 0, 1280, 720, Color(0.2, 0.2, 0.2, 1.0))

    qm = QuickMenu(1280, 720)
    qm.hovered_action = "skip"
    qm.draw(renderer)

    layout = qm.layout()
    skip_box = next(item for item in layout if item[0] == "skip")
    bx, by = skip_box[2], skip_box[3]

    img = renderer.get_image()
    sample = img.getpixel((int(bx + 2), int(by + 2)))
    # Before the fix, sample was (255, 255, 255), completely covering content underneath
    assert sample != (255, 255, 255)
    assert 60 <= sample[0] <= 75

# ---------------------------------------------------------------------- #
# PIL Renderer Optimizations & Performance Tests
# ---------------------------------------------------------------------- #

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


def test_dirty_rectangle_tracking_single_moving_actor() -> None:
    """When a single character moves, only damaged region is restored and only moving actor redrawn."""
    from PIL import ImageChops

    comp = StageCompositor(1280, 720)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="left", duration=0.0)
    comp.show_character("bob", "smiling", position="right", duration=0.0)

    renderer = PILRenderer(1280, 720)
    # Frame 1: Full render populating _bg_cache
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._last_dirty_bbox is None
    assert renderer._bg_cache is not None

    drawn_items: list[str] = []
    orig_draw_item = renderer.draw_item

    def tracking_draw_item(item: RenderItem) -> None:
        drawn_items.append(item.asset_id)
        orig_draw_item(item)

    renderer.draw_item = tracking_draw_item  # type: ignore[method-assign]

    # Frame 2: Bob moves towards center; Alice remains stationary on the left
    comp.move_character("bob", "center", duration=1.0)
    comp.step(0.1)

    img = renderer.render_compositor(comp, 1280, 720)

    # Verify dirty rect optimization was used and tracked
    assert renderer._last_dirty_bbox is not None
    dx0, _dy0, _dx1, _dy1 = renderer._last_dirty_bbox
    # Bob is on the right/center; Alice is on the left (< 450)
    assert dx0 > 450
    assert "bob/smiling" in drawn_items
    assert "alice/smiling" not in drawn_items

    # Verify pixel-perfect fidelity against a fresh scratch render
    fresh_renderer = PILRenderer(1280, 720)
    fresh_img = fresh_renderer.render_compositor(comp, 1280, 720)
    diff = ImageChops.difference(img, fresh_img)
    assert diff.getbbox() is None


def test_dirty_rectangle_intersecting_actors_redrawn() -> None:
    """When a moving actor's bounding box intersects another actor, both are cleanly redrawn."""
    from PIL import ImageChops

    comp = StageCompositor(1280, 720)
    comp.set_background("bg/tavern", duration=0.0)
    # Place Alice and Bob close enough to overlap (left and center_left), Charlie far right
    comp.show_character("alice", "smiling", position="left", duration=0.0)
    comp.show_character("bob", "smiling", position="center_left", duration=0.0)
    comp.show_character("charlie", "smiling", position="right", duration=0.0)

    renderer = PILRenderer(1280, 720)
    renderer.render_compositor(comp, 1280, 720)

    drawn_items: list[str] = []
    orig_draw_item = renderer.draw_item

    def tracking_draw_item(item: RenderItem) -> None:
        drawn_items.append(item.asset_id)
        orig_draw_item(item)

    renderer.draw_item = tracking_draw_item  # type: ignore[method-assign]

    # Alice moves towards center_left (intersecting Bob)
    comp.move_character("alice", "center_left", duration=1.0)
    comp.step(0.1)

    img = renderer.render_compositor(comp, 1280, 720)

    # Intersecting actors Alice and Bob are redrawn; Charlie (far right) is untouched
    assert renderer._last_dirty_bbox is not None
    assert "alice/smiling" in drawn_items
    assert "bob/smiling" in drawn_items
    assert "charlie/smiling" not in drawn_items

    # Verify pixel accuracy
    fresh_renderer = PILRenderer(1280, 720)
    fresh_img = fresh_renderer.render_compositor(comp, 1280, 720)
    diff = ImageChops.difference(img, fresh_img)
    assert diff.getbbox() is None


def test_dirty_rectangle_actor_glow_tint_tracked() -> None:
    """When an actor's tint or opacity changes (e.g. glow effect), dirty rect tracking activates."""
    comp = StageCompositor(1280, 720)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="left", duration=0.0)
    comp.show_character("bob", "smiling", position="right", duration=0.0)

    renderer = PILRenderer(1280, 720)
    renderer.render_compositor(comp, 1280, 720)

    # Glow Alice: change tint
    char_layer = comp.stage.get_layer("characters")
    assert char_layer is not None
    elem = char_layer.get_element("alice")
    assert elem is not None
    elem.state.tint = Color(1.0, 0.8, 0.2, 1.0)

    drawn_items: list[str] = []
    orig_draw_item = renderer.draw_item

    def tracking_draw_item(item: RenderItem) -> None:
        drawn_items.append(item.asset_id)
        orig_draw_item(item)

    renderer.draw_item = tracking_draw_item  # type: ignore[method-assign]

    renderer.render_compositor(comp, 1280, 720)

    assert "alice/smiling" in renderer._in_motion_assets
    assert renderer._last_dirty_bbox is not None
    assert "alice/smiling" in drawn_items
    assert "bob/smiling" not in drawn_items


def test_adaptive_resampling_settles_to_high_quality_on_rest() -> None:
    """When a character finishes a fade or tween, the settled frame must re-render with high-quality resampling."""
    from PIL import Image

    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="left", duration=0.3)

    renderer = PILRenderer(1280, 720, resampling=Image.Resampling.BILINEAR, adaptive_resampling=True)

    resamples_used: list[tuple[str, str, bool]] = []
    orig_transform = renderer._transform_sprite

    def logged_transform(*args: Any, **kwargs: Any) -> Any:
        item = args[1]
        is_in_motion = renderer.adaptive_resampling and (item.asset_id in renderer._in_motion_assets)
        cur_resample = Image.Resampling.NEAREST if is_in_motion else renderer.resampling
        resamples_used.append((item.asset_id, cur_resample.name, is_in_motion))
        return orig_transform(*args, **kwargs)

    renderer._transform_sprite = logged_transform  # type: ignore[method-assign]

    # Step through 0.3s fade
    for _ in range(3):
        comp.step(0.1)
        renderer.render_compositor(comp, 1280, 720)

    # During the fade, alice was rendered with NEAREST
    fade_resamples = [r for r in resamples_used if r[0] == "alice/smiling"]
    assert any(r[1] == "NEAREST" for r in fade_resamples)

    # While still in motion on final step of tween, stage cache must NOT be snapshotted
    # (prevents freezing the in-motion NEAREST frame)
    assert "alice/smiling" in renderer._in_motion_assets
    assert renderer._stage_cache is None

    # Step once more to complete rest (no geometry change)
    comp.step(0.1)
    renderer.render_compositor(comp, 1280, 720)

    # Motion has ceased
    assert "alice/smiling" not in renderer._in_motion_assets
    # Settled render must have executed with BILINEAR (high quality)
    assert resamples_used[-1] == ("alice/smiling", "BILINEAR", False)
    # Stage cache is now populated with the clean high-quality render
    assert renderer._stage_cache is not None

    # On next static frame, Tier 3 cache hits without re-running transforms
    count_before = len(resamples_used)
    comp.step(0.1)
    renderer.render_compositor(comp, 1280, 720)
    assert len(resamples_used) == count_before


def test_in_motion_sprites_do_not_poison_sprite_cache() -> None:
    """Sprites scaled with NEAREST while in motion must not be stored in _sprite_cache."""
    from PIL import Image

    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="left", duration=0.0)

    renderer = PILRenderer(1280, 720, resampling=Image.Resampling.BILINEAR, adaptive_resampling=True)
    renderer.render_compositor(comp, 1280, 720)
    assert len(renderer._in_motion_assets) == 0

    # Clear sprite cache to start fresh
    renderer._sprite_cache.clear()

    # Move character across frames
    comp.move_character("alice", "center", duration=1.0)
    comp.step(0.5)
    renderer.render_compositor(comp, 1280, 720)
    assert "alice/smiling" in renderer._in_motion_assets

    # _sprite_cache must NOT contain alice while she is in motion
    alice_keys = [k for k in renderer._sprite_cache if k[0] == "alice/smiling"]
    assert len(alice_keys) == 0


def test_text_mask_and_measure_cache_bypass_flag() -> None:
    """draw_text and measure_text with cache=False must not populate text mask or measure caches."""
    renderer = PILRenderer(800, 600)
    renderer._text_mask_cache.clear()
    renderer._measure_cache.clear()

    # Measure with cache=False
    w1, h1 = renderer.measure_text("Transitory text", font_size=16, cache=False)
    assert w1 > 0 and h1 > 0
    assert len(renderer._measure_cache) == 0

    # Draw with cache=False
    renderer.draw_text(10, 10, "Transitory text", font_size=16, cache=False)
    assert len(renderer._text_mask_cache) == 0

    # With cache=True (default), both should be cached
    _w, _h = renderer.measure_text("Cached text", font_size=16)
    assert len(renderer._measure_cache) == 1

    renderer.draw_text(10, 30, "Cached text", font_size=16)
    assert len(renderer._text_mask_cache) == 1


def test_dialogue_box_typewriter_reveal_does_not_pollute_text_caches() -> None:
    """Typewriter text reveal character-by-character must not populate text_mask_cache with partial substrings."""
    from eager_graphics.ui_components import DialogueBox

    renderer = PILRenderer(1280, 720)
    box = DialogueBox(width=1280, height=720)

    # Long dialogue that would otherwise produce dozens of intermediate cache entries
    sentence = "This is a long sentence revealing character by character during animated typewriter presentation."

    # Simulate 50 frames of typewriter progress
    for char_count in range(1, 50):
        box.set_content("Alice", sentence, visible_chars=char_count)
        renderer._text_mask_cache.clear()
        renderer._measure_cache.clear()
        box.draw(renderer)

        # None of the intermediate substrings of the dialogue body should be cached in _text_mask_cache
        # Only the speaker name ("Alice") is static and allowed to be cached
        dialogue_masks = [k for k in renderer._text_mask_cache if k[0] != "Alice"]
        assert len(dialogue_masks) == 0, f"Found cached partial text masks: {dialogue_masks}"

    # Once fully revealed (visible_chars=None or visible_chars >= total), text IS cached
    box.set_content("Alice", sentence, visible_chars=None)
    renderer._text_mask_cache.clear()
    box.draw(renderer)

    dialogue_masks = [k for k in renderer._text_mask_cache if k[0] != "Alice"]
    assert len(dialogue_masks) >= 1, "Completed dialogue should be cached"


def test_pil_player_typewriter_reveal_cache_behavior() -> None:
    """Stepping PILPlayer through typewriter character reveals must not grow _text_mask_cache with partial prefixes."""
    from eager_runtime.session import GameSession
    from eager_script import parse_graph

    from eager_graphics.renderers.pil import PILPlayer

    script = """
    ## Start --- start
    Alice: This is an extended dialogue line revealing over many frames to verify cache bounds.
    """
    graph = parse_graph(script)
    session = GameSession(graph)
    player = PILPlayer(session=session, visible=False)
    player._photo = "dummy"

    # Step through 30 frames while text is actively revealing
    for _ in range(30):
        player.tick(1.0 / 60.0)
        player.on_draw()

    # While revealing, dialogue body prefixes must not be in _text_mask_cache
    cached_strings = {k[0] for k in player.renderer._text_mask_cache}
    # Only static UI elements like speaker "Alice" or quick menu labels may be cached
    partial_reveals = [s for s in cached_strings if s.startswith("This is an") and s != "This is an extended dialogue line revealing over many frames to verify cache bounds."]
    assert len(partial_reveals) == 0, f"Found leaked partial dialogue masks: {partial_reveals}"

    # Advance until text reveal finishes
    for _ in range(120):
        player.tick(1.0 / 60.0)
        player.on_draw()

    assert session.text_reveal is not None and session.text_reveal.is_complete

    # Now that reveal is complete, the final settled line should be in the cache
    final_cached = {k[0] for k in player.renderer._text_mask_cache}
    full_sentence = "This is an extended dialogue line revealing over many frames to verify cache bounds."
    assert any(full_sentence.startswith(s) or s in full_sentence for s in final_cached if s not in ("Alice",))
    player.close()






