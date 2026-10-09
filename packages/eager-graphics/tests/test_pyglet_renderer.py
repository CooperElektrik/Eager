"""Tests for PygletRenderer and PygletPlayer."""

from __future__ import annotations

import pytest

try:
    import pyglet

    from eager_graphics.renderers.pyglet import PygletAssetResolver, PygletPlayer, PygletRenderer

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

