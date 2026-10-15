from __future__ import annotations

from pathlib import Path

import pytest

try:
    import pyglet

    from eager_graphics.renderers.pyglet import (
        PygletAssetResolver,
        PygletAudioBackend,
        PygletPlayer,
        PygletRenderer,
    )

    PYGLET_AVAILABLE = True
except ImportError:
    PYGLET_AVAILABLE = False

from eager_runtime import EventDispatcher, StoryVM
from eager_script import parse_graph

from eager_graphics import (
    Anchor,
    Color,
    LayoutResolver,
    RenderItem,
    ScaleMode,
    StageCompositor,
    StageDirector,
)

pytestmark = pytest.mark.skipif(not PYGLET_AVAILABLE, reason="Pyglet not installed")


@pytest.fixture
def invisible_window() -> pyglet.window.Window:
    """Fixture providing an invisible Pyglet window for headless test execution."""
    win = pyglet.window.Window(width=1280, height=720, visible=False)
    yield win
    try:
        win.close()
    except Exception:  # noqa: BLE001, S110
        pass


def test_pyglet_asset_resolver_placeholders() -> None:
    resolver = PygletAssetResolver(asset_dir=None)

    # 1. Background placeholder
    bg_tex = resolver.get_texture("bg/castle_gate")
    assert bg_tex is not None
    assert bg_tex.width == 1920
    assert bg_tex.height == 1080

    # Cache should return exact same instance
    assert resolver.get_texture("bg/castle_gate") is bg_tex

    # 2. Character placeholder
    char_tex = resolver.get_texture("alice/cheerful", default_width=400, default_height=800)
    assert char_tex is not None
    assert char_tex.width == 400
    assert char_tex.height == 800
    assert resolver.get_texture("alice/cheerful") is char_tex

    # Different asset_id should yield different texture
    guard_tex = resolver.get_texture("guard/stern")
    assert guard_tex is not char_tex


def test_pyglet_renderer_draw_items(invisible_window: pyglet.window.Window) -> None:
    renderer = PygletRenderer(scale_mode=ScaleMode.LETTERBOX, window=invisible_window)

    compositor = StageCompositor(1920, 1080)
    compositor.set_background("bg/castle", duration=0.0)
    compositor.show_character("alice", "happy", position="left", duration=0.0)
    compositor.show_character("bob", "serious", position="right", duration=0.0, flip_h=True)

    # Render compositor frame to invisible window (1280x720)
    renderer.render_compositor(compositor, invisible_window.width, invisible_window.height)

    # Verify that sprites were created and rendered
    assert len(renderer._active_sprites) == 3
    bg_sprite, alice_sprite, bob_sprite = renderer._active_sprites

    # Background fills 1280x720 window
    assert pytest.approx(bg_sprite.width, 0.1) == 1280
    assert pytest.approx(bg_sprite.height, 0.1) == 720
    assert bg_sprite.x == 0.0
    assert bg_sprite.y == 720.0

    # Alice (character on left: x=480 in 1920 space -> 320 in 1280 space)
    # Character size 400x800 -> 266.67 x 533.33 in 1280x720 window
    assert pytest.approx(alice_sprite.width, 0.1) == 400 * (1280 / 1920)
    assert pytest.approx(alice_sprite.height, 0.1) == 800 * (720 / 1080)
    assert pytest.approx(alice_sprite.x, 0.1) == 320.0
    assert pytest.approx(alice_sprite.y, 0.1) == 0.0

    # Bob (character on right: x=1440 in 1920 space -> 960 in 1280 space)
    assert pytest.approx(bob_sprite.width, 0.1) == 400 * (1280 / 1920)
    assert pytest.approx(bob_sprite.height, 0.1) == 800 * (720 / 1080)
    assert pytest.approx(bob_sprite.x, 0.1) == 960.0
    assert pytest.approx(bob_sprite.y, 0.1) == 0.0
    assert bob_sprite.scale_x < 0


def test_pyglet_renderer_draw_item_properties(invisible_window: pyglet.window.Window) -> None:
    renderer = PygletRenderer(scale_mode=ScaleMode.STRETCH, window=invisible_window)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(
        invisible_window.width,
        invisible_window.height,
        mode=ScaleMode.STRETCH,
    )

    renderer.begin_frame()

    item = RenderItem(
        asset_id="alice/happy",
        x=960.0,
        y=1080.0,
        opacity=0.75,
        scale_x=1.2,
        scale_y=1.2,
        rotation=15.0,
        anchor=Anchor.BOTTOM_CENTER,
        tint=Color(1.0, 0.5, 0.5, 1.0),
        flip_h=True,
        flip_v=False,
        layer="characters",
        z_order=100,
    )

    renderer.draw_item(item)
    assert len(renderer._active_sprites) == 1
    sprite = renderer._active_sprites[0]

    # Verify opacity calculation (0.75 * 255 = ~191)
    assert sprite.opacity == round(0.75 * 255)
    # Verify color tint
    assert sprite.color[:3] == (255, 128, 128)
    # Verify horizontal flip results in negative scale_x
    assert sprite.scale_x < 0
    # Verify rotation applied
    assert sprite.rotation == 15.0
    # Verify accurate position and dimension
    assert pytest.approx(sprite.x, 0.1) == 640.0
    assert pytest.approx(sprite.y, 0.1) == 0.0
    assert pytest.approx(sprite.width, 0.1) == 400 * 1.2 * (1280 / 1920)
    assert pytest.approx(sprite.height, 0.1) == 800 * 1.2 * (720 / 1080)

    renderer.end_frame()


def test_pyglet_player_story_progression() -> None:
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
    graph = parse_graph(screenplay)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()
    compositor = StageCompositor(1920, 1080)
    director = StageDirector(compositor)
    director.bind(dispatcher)

    # Initialize headless PygletPlayer
    player = PygletPlayer(
        vm=vm,
        compositor=compositor,
        director=director,
        dispatcher=dispatcher,
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

        # Advance to story end
        player.advance_story()
        assert player.is_finished

        # Test on_draw passes without error
        player.on_draw()

    finally:
        player.close()


def test_pyglet_renderer_anchors_and_rotation(invisible_window: pyglet.window.Window) -> None:
    """Verify that items with various anchors and rotation are correctly transformed."""
    renderer = PygletRenderer(scale_mode=ScaleMode.LETTERBOX, window=invisible_window)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(
        invisible_window.width,
        invisible_window.height,
        mode=ScaleMode.LETTERBOX,
    )

    renderer.begin_frame()

    # 1. Center-anchored element at screen center
    center_item = RenderItem(
        asset_id="alice/happy",
        x=960.0,
        y=540.0,
        opacity=1.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation=45.0,
        anchor=Anchor.CENTER,
        tint=Color(1.0, 1.0, 1.0, 1.0),
        flip_h=False,
        flip_v=False,
        layer="characters",
        z_order=10,
    )
    renderer.draw_item(center_item)
    assert len(renderer._active_sprites) == 1
    sp = renderer._active_sprites[0]
    # Anchor point in 1280x720 window: (640, 360)
    assert pytest.approx(sp.x, 0.1) == 640.0
    assert pytest.approx(sp.y, 0.1) == 360.0
    assert sp.rotation == 45.0

    # 2. Top-left anchored element
    tl_item = RenderItem(
        asset_id="alice/happy",
        x=100.0,
        y=100.0,
        opacity=1.0,
        scale_x=1.0,
        scale_y=1.0,
        rotation=0.0,
        anchor=Anchor.TOP_LEFT,
        tint=Color(1.0, 1.0, 1.0, 1.0),
        flip_h=False,
        flip_v=False,
        layer="characters",
        z_order=20,
    )
    renderer.draw_item(tl_item)
    assert len(renderer._active_sprites) == 2
    sp_tl = renderer._active_sprites[1]
    # Screen coord: (100 * 2/3, 100 * 2/3) = (66.67, 66.67). Pyglet Y: 720 - 66.67 = 653.33
    assert pytest.approx(sp_tl.x, 0.1) == 100.0 * (1280 / 1920)
    assert pytest.approx(sp_tl.y, 0.1) == 720.0 - (100.0 * (720 / 1080))

    renderer.end_frame()


def test_pyglet_player_choice_mouse_click() -> None:
    """Verify that clicking vertically centered choice buttons selects the proper option."""
    screenplay = """
    ## Start --- start
    Alice: Choose!
    ? Option A (opt_a)
    ? Option B (opt_b)

    ## Option A --- opt_a
    Alice: A selected.

    ## Option B --- opt_b
    Alice: B selected.
    """
    graph = parse_graph(screenplay)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()
    compositor = StageCompositor(1920, 1080)
    director = StageDirector(compositor)
    director.bind(dispatcher)

    player = PygletPlayer(
        vm=vm,
        compositor=compositor,
        director=director,
        dispatcher=dispatcher,
        width=800,
        height=600,
        visible=False,
    )

    try:
        player.advance_story()
        assert player.active_choice_prompt is not None

        # Calculate button positions for 2 options in 800x600 window:
        # btn_h = 42, spacing = 12, total_h = 2*42 + 12 = 96
        # top_y = (600 + 96) // 2 = 348
        # Opt 0 (A): by = 348 - 42 = 306. [306, 348]
        # Opt 1 (B): by = 306 - 54 = 252. [252, 294]
        # Center x = 400
        # Click on Option B (e.g. y = 270, x = 400)
        player.on_mouse_press(400, 270, pyglet.window.mouse.LEFT, 0)
        assert player.active_choice_prompt is None
        assert player.current_text == "B selected."
    finally:
        player.close()


def test_pyglet_renderer_size_repr_and_primitives(invisible_window: pyglet.window.Window) -> None:
    """Verify PygletRenderer constructor dimensions, len/repr, and drawing primitives."""
    # Custom dimensions without window
    r_custom = PygletRenderer(width=1280, height=720)
    assert r_custom.width == 1280
    assert r_custom.height == 720
    assert len(r_custom) == 0
    assert "PygletRenderer(width=1280, height=720" in repr(r_custom)

    # Attached to window
    r_win = PygletRenderer(window=invisible_window)
    assert r_win.width == invisible_window.width
    assert r_win.height == invisible_window.height

    # Test drawing primitives (draw_rect, draw_rect_outline, draw_text, draw_image)
    r_win.begin_frame()
    r_win.draw_rect(10, 10, 100, 50, Color(1, 0, 0, 1), border_color=Color(0, 1, 0, 1), border_width=2.0)
    r_win.draw_rect_outline(20, 20, 80, 40, Color(0, 0, 1, 1), line_width=1.5)
    r_win.draw_text(30, 30, "Hello Pyglet", font_size=16, color=Color(1, 1, 1, 1))
    r_win.draw_image("bg/castle", 0, 0, 200, 100)
    r_win.end_frame()

    w, h = r_win.measure_text("Hello Pyglet", font_size=16)
    assert w > 0
    assert h > 0

    # Verify asset resolver get_image alias
    assert r_win.asset_resolver.get_image("bg/castle", 200, 100) is not None


def test_pyglet_player_run_and_input_handling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify player.run, right-click, mouse drag, and numpad keyboard handling."""
    from eager_core.input import InputAction
    from eager_runtime.session import GameSession

    screenplay = """
    ## Start --- start
    Alice: Welcome!
    ? Choice 1 (c1)
    ? Choice 2 (c2)

    ## Choice 1 --- c1
    Alice: One.

    ## Choice 2 --- c2
    Alice: Two.
    """
    graph = parse_graph(screenplay)
    session = GameSession(graph)

    player = PygletPlayer(
        session=session,
        width=1280,
        height=720,
        visible=False,
        uncapped=True,
    )
    assert not player.vsync

    run_called = []
    monkeypatch.setattr(pyglet.app, "run", lambda *a, **kw: run_called.append(kw.get("interval", None)))
    player.run()
    assert run_called == [0.0]

    try:
        # FPS overlay toggle
        assert player.show_fps
        player.on_key_press(pyglet.window.key.F3, 0)
        assert not player.show_fps
        player.on_draw()  # FPS draw skipped when show_fps is False

        # Advance to choice prompt
        player.advance_story()
        assert player.active_choice_prompt is not None

        # Test numpad key press (NUM_1 selects choice 0)
        player.on_key_press(pyglet.window.key.NUM_1, 0)
        assert player.active_choice_prompt is None
        assert player.current_text == "One."

        # Right-click dispatches GAME_MENU
        game_menu_dispatched = []
        orig_handle_input = session.handle_input

        def spy_handle_input(action: InputAction, **kw: object) -> object:
            if action == InputAction.GAME_MENU:
                game_menu_dispatched.append(True)
            return orig_handle_input(action, **kw)

        monkeypatch.setattr(session, "handle_input", spy_handle_input)
        player.on_mouse_press(100, 100, pyglet.window.mouse.RIGHT, 0)
        assert game_menu_dispatched == [True]

        # Mouse drag forwards pointer move and does NOT spam synthetic click events
        drag_moves = []
        drag_clicks = []

        def spy_drag_events(action: InputAction, **kw: object) -> object:
            if action == InputAction.POINTER_MOVE:
                drag_moves.append(kw)
            elif action == InputAction.POINTER_CLICK:
                drag_clicks.append(kw)
            return orig_handle_input(action, **kw)

        monkeypatch.setattr(session, "handle_input", spy_drag_events)
        player.on_mouse_drag(150, 200, 5, 5, pyglet.window.mouse.LEFT, 0)
        assert len(drag_moves) == 1
        assert drag_moves[0]["x"] == 150
        assert drag_moves[0]["y"] == 720 - 200
        assert len(drag_clicks) == 0

        # Click press dispatches click
        player.on_mouse_press(150, 200, pyglet.window.mouse.LEFT, 0)
        assert len(drag_clicks) == 1
        assert drag_clicks[0]["x"] == 150
        assert drag_clicks[0]["y"] == 720 - 200

    finally:
        player.close()


def test_pyglet_stage_sprite_pooling(invisible_window: pyglet.window.Window) -> None:
    """Verify stage sprites are pooled, reused across frames, and hidden when unused."""
    renderer = PygletRenderer(scale_mode=ScaleMode.LETTERBOX, window=invisible_window)
    compositor = StageCompositor(1920, 1080)
    compositor.set_background("bg/castle", duration=0.0)
    compositor.show_character("alice", "happy", position="left", duration=0.0)

    # Frame 1: 2 items
    renderer.render_compositor(compositor, invisible_window.width, invisible_window.height)
    assert len(renderer._active_sprites) == 2
    assert len(renderer._pooled_stage_sprites) == 2
    bg_sp1, alice_sp1 = renderer._active_sprites
    assert bg_sp1.visible is True
    assert alice_sp1.visible is True

    # Frame 2: Same 2 items should reuse the exact same Sprite instances
    renderer.render_compositor(compositor, invisible_window.width, invisible_window.height)
    assert len(renderer._active_sprites) == 2
    assert renderer._active_sprites[0] is bg_sp1
    assert renderer._active_sprites[1] is alice_sp1

    # Frame 3: Add a 3rd character
    compositor.show_character("bob", "serious", position="right", duration=0.0)
    renderer.render_compositor(compositor, invisible_window.width, invisible_window.height)
    assert len(renderer._active_sprites) == 3
    assert len(renderer._pooled_stage_sprites) == 3
    assert renderer._active_sprites[0] is bg_sp1
    assert renderer._active_sprites[1] is alice_sp1

    # Frame 4: Hide both characters -> only background remains
    compositor.hide_character("alice", duration=0.0)
    compositor.hide_character("bob", duration=0.0)
    renderer.render_compositor(compositor, invisible_window.width, invisible_window.height)
    assert len(renderer._active_sprites) == 1
    assert renderer._active_sprites[0] is bg_sp1
    # Unused pooled sprites should be hidden (visible=False)
    assert len(renderer._pooled_stage_sprites) == 3
    assert renderer._pooled_stage_sprites[1].visible is False
    assert renderer._pooled_stage_sprites[2].visible is False


def test_pyglet_ui_pooling_and_batching(invisible_window: pyglet.window.Window) -> None:
    """Verify UI rectangles, boxes, gradient rects, labels, and sprites are pooled and batched."""
    renderer = PygletRenderer(scale_mode=ScaleMode.LETTERBOX, window=invisible_window)

    # Pass 1: Draw UI primitives
    renderer.begin_frame()
    renderer.draw_rect(10, 10, 200, 50, Color(0.1, 0.2, 0.3, 1.0), border_color=Color(1, 1, 1, 1), border_width=2.0)
    renderer.draw_rect_outline(15, 15, 100, 40, Color(0.5, 0.5, 0.5, 1.0), line_width=1.0)
    renderer.draw_gradient_rect(0, 0, 300, 80, Color(0.2, 0.2, 0.2, 1.0), Color(0.8, 0.8, 0.8, 1.0))
    renderer.draw_text(20, 20, "Test Line 1", font_size=16)
    renderer.draw_image("bg/castle", 0, 0, 100, 50)
    renderer.flush_ui()

    assert len(renderer._rect_pool) == 1
    assert len(renderer._box_pool) == 2  # 1 from border, 1 from outline
    assert len(renderer._grad_pool) == 1
    assert len(renderer._label_pool) == 1
    assert len(renderer._ui_sprite_pool) == 1

    rect_inst = renderer._rect_pool[0]
    label_inst = renderer._label_pool[0]
    grad_inst = renderer._grad_pool[0][0]

    # Pass 2: Re-render UI primitives -> should reuse pooled instances
    renderer.begin_frame()
    renderer.draw_rect(10, 10, 200, 50, Color(0.1, 0.2, 0.3, 1.0), border_color=Color(1, 1, 1, 1), border_width=2.0)
    renderer.draw_rect_outline(15, 15, 100, 40, Color(0.5, 0.5, 0.5, 1.0), line_width=1.0)
    renderer.draw_gradient_rect(0, 0, 300, 80, Color(0.2, 0.2, 0.2, 1.0), Color(0.8, 0.8, 0.8, 1.0))
    renderer.draw_text(20, 20, "Test Line 1", font_size=16)
    renderer.draw_image("bg/castle", 0, 0, 100, 50)
    renderer.flush_ui()

    assert renderer._rect_pool[0] is rect_inst
    assert renderer._label_pool[0] is label_inst
    assert renderer._grad_pool[0][0] is grad_inst

    # Pass 3: Draw empty frame -> pooled UI elements should be hidden
    renderer.begin_frame()
    renderer.flush_ui()
    assert rect_inst.visible is False
    assert label_inst.visible is False
    assert grad_inst.visible is False


def test_pyglet_measure_text_caching(invisible_window: pyglet.window.Window) -> None:
    """Verify that measure_text uses the LRU cache and avoids recalculations."""
    renderer = PygletRenderer(window=invisible_window)
    renderer._cached_measure_text.cache_clear()

    info_before = renderer._cached_measure_text.cache_info()
    assert info_before.hits == 0

    w1, h1 = renderer.measure_text("Cached text string", font_size=16, bold=True)
    assert w1 > 0
    assert h1 > 0

    w2, h2 = renderer.measure_text("Cached text string", font_size=16, bold=True)
    assert w1 == w2
    assert h1 == h2

    info_after = renderer._cached_measure_text.cache_info()
    assert info_after.hits >= 1


def test_pyglet_letterbox_caching(invisible_window: pyglet.window.Window) -> None:
    """Verify letterbox bars are computed and cached, avoiding recreation every frame."""
    renderer = PygletRenderer(width=1600, height=720, scale_mode=ScaleMode.LETTERBOX, window=invisible_window)
    compositor = StageCompositor(1920, 1080)
    compositor.set_background("bg/castle", duration=0.0)

    # 1600x720 window with 16:9 (1280x720) stage -> pillarbox bars with offset_x = (1600-1280)/2 = 160
    renderer.render_compositor(compositor, 1600, 720)
    assert len(renderer._letterbox_bars) == 2
    left_bar = renderer._bar_left
    right_bar = renderer._bar_right
    assert left_bar is not None and left_bar.visible is True
    assert right_bar is not None and right_bar.visible is True

    # Frame 2: Same size -> letterbox bars must be the exact same instances
    renderer.render_compositor(compositor, 1600, 720)
    assert renderer._bar_left is left_bar
    assert renderer._bar_right is right_bar


def test_pyglet_audio_backend_static_source_caching(tmp_path: Path) -> None:
    """Verify short sound effects (sfx) cache StaticSource instances."""
    import struct
    import wave

    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True)
    wav_file = audio_dir / "sfx.wav"
    with wave.open(str(wav_file), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(struct.pack("<h", 0) * 4410)

    backend = PygletAudioBackend()
    try:
        backend.play("sfx", str(wav_file), loop=False)
        assert str(wav_file) in backend._static_sources
        cached_source = backend._static_sources[str(wav_file)]

        # Second play of the same sfx should reuse the cached source
        backend.play("sfx", str(wav_file), loop=False)
        assert backend._static_sources[str(wav_file)] is cached_source
    finally:
        backend.shutdown()
        assert len(backend._static_sources) == 0


def test_pyglet_asset_resolver_preindexing(tmp_path: Path) -> None:
    """Verify asset directory is pre-indexed once on startup."""
    asset_dir = tmp_path / "assets"
    bg_dir = asset_dir / "bg"
    bg_dir.mkdir(parents=True)
    sample_file = bg_dir / "forest.png"
    sample_file.write_bytes(b"dummy")

    resolver = PygletAssetResolver(asset_dir=asset_dir)
    assert "bg/forest.png" in resolver._asset_index
    assert "bg/forest" in resolver._asset_index
    assert "forest" in resolver._asset_index
    assert resolver._asset_index["bg/forest"] == sample_file


