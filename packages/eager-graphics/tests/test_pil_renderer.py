"""Comprehensive unit and integration tests for PILRenderer, PILAssetResolver, and PILPlayer."""

from __future__ import annotations

from pathlib import Path

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






