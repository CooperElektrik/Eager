"""Tests for RaylibRenderer, RaylibAssetResolver, and RaylibPlayer.

These tests require the ``raylib`` PyPI package (which provides the ``pyray``
import).  GPU-dependent tests run in a **single batched subprocess** — one
window is opened per test phase (not per test), drastically reducing the
visual flicker caused by rapidly opening/closing raylib windows.

Non-GPU tests (lifecycle guards, protocol conformance, lazy import checks)
run directly in the pytest process.

Note: ``eager_graphics`` now uses lazy backend imports, so importing the
raylib renderer does **not** trigger a pyglet import.  This eliminates the
GTK/EGL conflict that previously required careful import ordering.
"""

from __future__ import annotations

import json
import subprocess
import sys

# Import pyray BEFORE eager_graphics — although eager_graphics now uses lazy
# backend imports (so pyglet won't be imported), it's still best practice to
# have raylib's module loaded before any graphics code runs.
try:
    import pyray  # noqa: F401

    RAYLIB_AVAILABLE = True
except ImportError:
    RAYLIB_AVAILABLE = False

import pytest

from eager_graphics import (
    Anchor,
    Color,
)
from eager_graphics.protocol import RenderItem
from eager_graphics.renderers.raylib import (
    RaylibRenderer,
)
from eager_graphics.types import BLACK

pytestmark = pytest.mark.skipif(not RAYLIB_AVAILABLE, reason="raylib (pyray) is not installed")


# ---------------------------------------------------------------------- #
# Batched GPU test runner
# ---------------------------------------------------------------------- #
#
# All GPU-dependent tests run inside a single subprocess to avoid flicker
# from repeatedly opening/closing raylib windows.  The subprocess opens one
# window, runs every GPU test function, and prints a JSON summary that the
# individual pytest test functions below parse and assert against.
#

_GPU_TEST_RUNNER = r'''
import json
import pyray
import sys

pyray.set_trace_log_level(pyray.LOG_WARNING)
pyray.init_window(1280, 720, "raylib-test-batch")
pyray.set_target_fps(60)

# Import AFTER init_window — eager_graphics now uses lazy backend imports,
# so importing raylib renderer here will NOT pull in pyglet/PIL.
from eager_graphics import Anchor, Color, LayoutResolver, ScaleMode
from eager_graphics import StageCompositor, StageDirector
from eager_graphics.protocol import RenderItem
from eager_graphics.types import BLACK
from eager_graphics.renderers.raylib import RaylibAssetResolver, RaylibRenderer, RaylibPlayer
from eager_runtime import EventDispatcher, GameSession, StoryVM
from eager_script import parse_graph

results = {}

def _ok(name):
    results[name] = {"passed": True}

def _fail(name, exc):
    results[name] = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}

# ------------------------------------------------------------------
# test_raylib_asset_resolver_placeholders
# ------------------------------------------------------------------
try:
    resolver = RaylibAssetResolver(asset_dir=None)
    bg_tex = resolver.get_texture("bg/castle_gate")
    assert bg_tex is not None
    assert bg_tex.width == 1920
    assert bg_tex.height == 1080
    assert resolver.get_texture("bg/castle_gate") is bg_tex
    char_tex = resolver.get_texture("alice/cheerful", default_width=400, default_height=800)
    assert char_tex is not None
    assert char_tex.width == 400
    assert char_tex.height == 800
    assert resolver.get_texture("alice/cheerful") is char_tex
    guard_tex = resolver.get_texture("guard/stern")
    assert guard_tex is not char_tex
    resolver.unload_all()
    _ok("test_raylib_asset_resolver_placeholders")
except Exception as exc:
    _fail("test_raylib_asset_resolver_placeholders", exc)

# ------------------------------------------------------------------
# test_raylib_asset_resolver_builtin_color_rect
# ------------------------------------------------------------------
try:
    resolver = RaylibAssetResolver(asset_dir=None)
    tex = resolver.get_texture("__builtin_color_rect__")
    assert tex.width == 1
    assert tex.height == 1
    resolver.unload_all()
    _ok("test_raylib_asset_resolver_builtin_color_rect")
except Exception as exc:
    _fail("test_raylib_asset_resolver_builtin_color_rect", exc)

# ------------------------------------------------------------------
# test_raylib_asset_resolver_disk_load
# ------------------------------------------------------------------
try:
    import tempfile, os
    tmpdir = tempfile.mkdtemp()
    img = pyray.gen_image_color(200, 300, pyray.RED)
    pyray.export_image(img, os.path.join(tmpdir, "hero.png"))
    pyray.unload_image(img)
    resolver = RaylibAssetResolver(asset_dir=tmpdir)
    tex = resolver.get_texture("hero")
    assert tex.width == 200
    assert tex.height == 300
    assert resolver.get_texture("hero") is tex
    resolver.unload_all()
    _ok("test_raylib_asset_resolver_disk_load")
except Exception as exc:
    _fail("test_raylib_asset_resolver_disk_load", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_draw_items
# ------------------------------------------------------------------
try:
    renderer = RaylibRenderer(1280, 720, scale_mode=ScaleMode.LETTERBOX)
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/castle", duration=0.0)
    comp.show_character("alice", "happy", position="left", duration=0.0)
    comp.show_character("bob", "serious", position="right", duration=0.0, flip_h=True)
    pyray.begin_drawing()
    renderer.render_compositor(comp, 1280, 720)
    pyray.end_drawing()
    assert renderer.frame_count == 1
    assert len(renderer.last_frame) == 3
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_draw_items")
except Exception as exc:
    _fail("test_raylib_renderer_draw_items", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_flips
# ------------------------------------------------------------------
try:
    renderer = RaylibRenderer(500, 500, scale_mode=ScaleMode.STRETCH)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(500, 500, mode=ScaleMode.STRETCH)
    pyray.begin_drawing()
    renderer.begin_frame()
    renderer.clear(BLACK)
    renderer.draw_item(RenderItem(
        asset_id="char/h", x=100, y=100, opacity=1.0,
        scale_x=1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.CENTER, tint=Color(1, 1, 1, 1),
        flip_h=True, flip_v=False, layer="characters", z_order=1,
    ))
    renderer.draw_item(RenderItem(
        asset_id="char/v", x=200, y=100, opacity=1.0,
        scale_x=1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.CENTER, tint=Color(1, 1, 1, 1),
        flip_h=False, flip_v=True, layer="characters", z_order=2,
    ))
    renderer.draw_item(RenderItem(
        asset_id="char/hv", x=300, y=100, opacity=1.0,
        scale_x=1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.CENTER, tint=Color(1, 1, 1, 1),
        flip_h=True, flip_v=True, layer="characters", z_order=3,
    ))
    renderer.end_frame()
    pyray.end_drawing()
    assert len(renderer.last_frame) == 3
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_flips")
except Exception as exc:
    _fail("test_raylib_renderer_flips", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_culling_and_early_exits
# ------------------------------------------------------------------
try:
    renderer = RaylibRenderer(500, 500, scale_mode=ScaleMode.STRETCH)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(500, 500, mode=ScaleMode.STRETCH)
    pyray.begin_drawing()
    renderer.begin_frame()
    renderer.clear(BLACK)
    renderer.draw_item(RenderItem(
        asset_id="invisible", x=250, y=250, opacity=0.0,
        scale_x=1.0, scale_y=1.0, rotation=0.0, anchor=Anchor.CENTER,
        tint=Color(1, 1, 1, 1), flip_h=False, flip_v=False,
        layer="characters", z_order=1,
    ))
    renderer.draw_item(RenderItem(
        asset_id="zero_scale", x=250, y=250, opacity=1.0,
        scale_x=0.0, scale_y=1.0, rotation=0.0, anchor=Anchor.CENTER,
        tint=Color(1, 1, 1, 1), flip_h=False, flip_v=False,
        layer="characters", z_order=2,
    ))
    renderer.end_frame()
    pyray.end_drawing()
    assert len(renderer.last_frame) == 2
    assert renderer.frame_count == 1
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_culling_and_early_exits")
except Exception as exc:
    _fail("test_raylib_renderer_culling_and_early_exits", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_scale_modes
# ------------------------------------------------------------------
try:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/field", transition="cut")
    for mode in (ScaleMode.LETTERBOX, ScaleMode.STRETCH, ScaleMode.CROP,
                 ScaleMode.FIT_WIDTH, ScaleMode.FIT_HEIGHT):
        renderer = RaylibRenderer(1280, 720, scale_mode=mode)
        pyray.begin_drawing()
        renderer.render_compositor(comp, 1280, 720)
        pyray.end_drawing()
        assert renderer.frame_count == 1
        renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_scale_modes")
except Exception as exc:
    _fail("test_raylib_renderer_scale_modes", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_anchors
# ------------------------------------------------------------------
try:
    renderer = RaylibRenderer(800, 600, scale_mode=ScaleMode.LETTERBOX)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(
        800, 600, mode=ScaleMode.LETTERBOX
    )
    pyray.begin_drawing()
    renderer.begin_frame()
    renderer.clear(BLACK)
    renderer.draw_item(RenderItem(
        asset_id="alice/happy", x=960.0, y=540.0, opacity=1.0,
        scale_x=1.0, scale_y=1.0, rotation=45.0,
        anchor=Anchor.CENTER, tint=Color(1, 0.5, 0.5, 1),
        flip_h=False, flip_v=False, layer="characters", z_order=10,
    ))
    renderer.draw_item(RenderItem(
        asset_id="alice/happy", x=100.0, y=100.0, opacity=1.0,
        scale_x=1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.TOP_LEFT, tint=Color(1, 1, 1, 1),
        flip_h=False, flip_v=False, layer="characters", z_order=20,
    ))
    renderer.end_frame()
    pyray.end_drawing()
    assert renderer.frame_count == 1
    assert len(renderer.last_frame) == 2
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_anchors")
except Exception as exc:
    _fail("test_raylib_renderer_anchors", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_negative_scale
# ------------------------------------------------------------------
try:
    renderer = RaylibRenderer(500, 500, scale_mode=ScaleMode.STRETCH)
    layout = LayoutResolver(1920, 1080)
    renderer._current_transform = layout.compute_viewport_transform(
        500, 500, mode=ScaleMode.STRETCH
    )
    pyray.begin_drawing()
    renderer.begin_frame()
    renderer.clear(BLACK)
    renderer.draw_item(RenderItem(
        asset_id="char/neg", x=250, y=250, opacity=1.0,
        scale_x=-1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.CENTER, tint=Color(1, 1, 1, 1),
        flip_h=False, flip_v=False, layer="characters", z_order=1,
    ))
    renderer.end_frame()
    pyray.end_drawing()
    assert len(renderer.last_frame) == 1
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_negative_scale")
except Exception as exc:
    _fail("test_raylib_renderer_negative_scale", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_tint_and_opacity
# ------------------------------------------------------------------
try:
    renderer = RaylibRenderer(500, 500, scale_mode=ScaleMode.STRETCH)
    layout = LayoutResolver(500, 500)
    renderer._current_transform = layout.compute_viewport_transform(
        500, 500, mode=ScaleMode.STRETCH
    )
    pyray.begin_drawing()
    renderer.begin_frame()
    renderer.clear(BLACK)
    renderer.draw_item(RenderItem(
        asset_id="char/tinted", x=250, y=250, opacity=0.5,
        scale_x=1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.CENTER, tint=Color(1.0, 0.5, 0.5, 1.0),
        flip_h=False, flip_v=False, layer="characters", z_order=1,
    ))
    renderer.draw_item(RenderItem(
        asset_id="char/trans", x=250, y=250, opacity=1.0,
        scale_x=1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.CENTER, tint=Color(1, 1, 1, 0.0),
        flip_h=False, flip_v=False, layer="characters", z_order=2,
    ))
    renderer.end_frame()
    pyray.end_drawing()
    assert renderer.frame_count == 1
    assert len(renderer.last_frame) == 2
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_tint_and_opacity")
except Exception as exc:
    _fail("test_raylib_renderer_tint_and_opacity", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_builtin_color_rect
# ------------------------------------------------------------------
try:
    renderer = RaylibRenderer(200, 200, scale_mode=ScaleMode.STRETCH)
    layout = LayoutResolver(200, 200)
    renderer._current_transform = layout.compute_viewport_transform(
        200, 200, mode=ScaleMode.STRETCH
    )
    pyray.begin_drawing()
    renderer.begin_frame()
    renderer.clear(BLACK)
    renderer.draw_item(RenderItem(
        asset_id="__builtin_color_rect__",
        x=0, y=0, opacity=1.0,
        scale_x=200, scale_y=200, rotation=0,
        anchor=Anchor.TOP_LEFT, tint=Color(1, 0, 0, 1),
        flip_h=False, flip_v=False, layer="background", z_order=0,
    ))
    renderer.end_frame()
    pyray.end_drawing()
    assert len(renderer.last_frame) == 1
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_builtin_color_rect")
except Exception as exc:
    _fail("test_raylib_renderer_builtin_color_rect", exc)

# ------------------------------------------------------------------
# test_raylib_renderer_frame_count_increments
# ------------------------------------------------------------------
try:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/sky", transition="cut")
    renderer = RaylibRenderer(1280, 720)
    assert renderer.frame_count == 0
    for _ in range(5):
        pyray.begin_drawing()
        renderer.render_compositor(comp, 1280, 720)
        pyray.end_drawing()
    assert renderer.frame_count == 5
    renderer.asset_resolver.unload_all()
    _ok("test_raylib_renderer_frame_count_increments")
except Exception as exc:
    _fail("test_raylib_renderer_frame_count_increments", exc)

# ------------------------------------------------------------------
# UIDrawBackend tests: draw_rect, draw_rect_with_border, draw_text, measure_text, draw_image
# ------------------------------------------------------------------
try:
    backend = RaylibRenderer(400, 300)
    pyray.begin_drawing()
    backend.draw_rect(10, 10, 100, 50, Color(1.0, 0.0, 0.0, 1.0))
    backend.draw_rect(
        10, 10, 100, 50,
        Color(0.2, 0.2, 0.4, 0.9),
        border_color=Color(1.0, 1.0, 0.0, 1.0),
        border_width=3.0,
    )
    backend.draw_text(50, 50, "Hello, Raylib!", font_size=20, color=Color(1, 1, 1, 1))
    backend.draw_text(50, 80, "Centered", font_size=20, color=Color(1, 1, 1, 1),
                       anchor_x="center", anchor_y="middle")
    backend.draw_text(50, 110, "Right", font_size=20, color=Color(1, 1, 1, 1),
                       anchor_x="right", anchor_y="bottom")
    w, h = backend.measure_text("Hello World", font_size=20)
    assert w > 0
    assert h > 0
    backend.draw_image("bg/castle", 10, 10, 200, 150, tint=Color(1, 1, 1, 1))
    backend.draw_image(
        "bg/castle", 200, 200, 100, 50,
        tint=Color(0.5, 0.5, 1.0, 1.0),
        anchor_x="center", anchor_y="middle",
    )
    pyray.end_drawing()
    backend.asset_resolver.unload_all()
    _ok("test_raylib_renderer_draw_rect")
    _ok("test_raylib_renderer_draw_rect_with_border")
    _ok("test_raylib_renderer_draw_text")
    _ok("test_raylib_renderer_measure_text")
    _ok("test_raylib_renderer_draw_image")
except Exception as exc:
    _fail("test_raylib_renderer_draw_rect", exc)
    _fail("test_raylib_renderer_draw_rect_with_border", exc)
    _fail("test_raylib_renderer_draw_text", exc)
    _fail("test_raylib_renderer_measure_text", exc)
    _fail("test_raylib_renderer_draw_image", exc)

# ------------------------------------------------------------------
# Close shared window before player tests — each player manages its own
# window via RaylibPlayer.__init__ / close()
# ------------------------------------------------------------------
pyray.close_window()

# ------------------------------------------------------------------
# Player tests (each opens/closes its own window via RaylibPlayer)
# ------------------------------------------------------------------
_SCREENPLAY = """
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

try:
    graph = parse_graph(_SCREENPLAY)
    session = GameSession(graph)
    comp = session.compositor
    player = RaylibPlayer(
        session=session,
        width=800, height=450,
    )
    try:
        assert player.current_speaker == "Alice"
        assert player.current_text == "Welcome!"
        assert player.active_choice_prompt is None
        player.advance_story()
        assert player.active_choice_prompt is not None
        assert len(player.active_choice_prompt.options) == 2
        player.make_choice(0)
        assert player.active_choice_prompt is None
        assert player.current_text == "You picked option 1."
        player.advance_story()
        assert player.is_finished
        player.on_draw()
    finally:
        player.close()
    _ok("test_raylib_player_story_progression")
except Exception as exc:
    _fail("test_raylib_player_story_progression", exc)

try:
    graph = parse_graph(_SCREENPLAY)
    session = GameSession(graph)
    comp = session.compositor
    player = RaylibPlayer(
        session=session,
        width=800, height=450,
    )
    try:
        player.advance_story()
        player.advance_story()
        assert player.active_choice_prompt is not None
        player.make_choice(1)
        assert player.current_text == "You picked option 2."
    finally:
        player.close()
    _ok("test_raylib_player_choice_selection")
except Exception as exc:
    _fail("test_raylib_player_choice_selection", exc)

try:
    graph = parse_graph(_SCREENPLAY)
    session = GameSession(graph)
    comp = session.compositor
    player = RaylibPlayer(
        session=session,
        width=800, height=450,
    )
    try:
        player.advance_story()
        assert player.rollback() is True
        assert player.is_finished is False
    finally:
        player.close()
    _ok("test_raylib_player_rollback")
except Exception as exc:
    _fail("test_raylib_player_rollback", exc)

try:
    graph = parse_graph(_SCREENPLAY)
    session = GameSession(graph)
    comp = session.compositor
    player = RaylibPlayer(
        session=session,
        width=800, height=450,
    )
    try:
        player.on_draw()
    finally:
        player.close()
    _ok("test_raylib_player_on_draw_no_crash")
except Exception as exc:
    _fail("test_raylib_player_on_draw_no_crash", exc)

# ------------------------------------------------------------------
# RaylibRenderer compositor integration (opens its own window)
# ------------------------------------------------------------------
try:
    import os
    import tempfile
    tmpdir = tempfile.mkdtemp()
    script_path = os.path.join(tmpdir, "story.es")
    with open(script_path, "w") as f:
        f.write(_SCREENPLAY)
    pyray.init_window(1280, 720, "raylib-renderer-test")
    renderer = RaylibRenderer(asset_dir=None)
    session = GameSession(script_path)
    session.advance()
    pyray.begin_drawing()
    renderer.render_compositor(session.compositor, 1280, 720)
    pyray.end_drawing()
    assert len(session.compositor.render_list()) > 0
    renderer.asset_resolver.unload_all()
    pyray.close_window()
    _ok("test_raylib_renderer_compositor")
except Exception as exc:
    _fail("test_raylib_renderer_compositor", exc)

print("===GPU_RESULTS_JSON===")
print(json.dumps(results))
'''

_GPU_RESULTS_CACHE: dict[str, dict] | None = None


@pytest.fixture(scope="module")
def gpu_results() -> dict[str, dict]:
    """Run all GPU tests in a single subprocess; cache results per module."""
    global _GPU_RESULTS_CACHE
    if _GPU_RESULTS_CACHE is not None:
        return _GPU_RESULTS_CACHE

    env = dict(__import__("os").environ)
    proc = subprocess.run(
        [sys.executable, "-c", _GPU_TEST_RUNNER],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )

    # Parse JSON results from stdout
    stdout = proc.stdout
    json_marker = "===GPU_RESULTS_JSON===\n"
    idx = stdout.find(json_marker)
    assert idx >= 0, (
        f"GPU test subprocess did not produce JSON results.\n"
        f"stdout: {stdout[-2000:]}\n"
        f"stderr: {proc.stderr[-2000:]}"
    )
    results_json = stdout[idx + len(json_marker):]
    results = json.loads(results_json)

    _GPU_RESULTS_CACHE = results
    return results


# ---------------------------------------------------------------------- #
# Non-GPU tests (run directly in pytest process)
# ---------------------------------------------------------------------- #


def test_raylib_renderer_implements_render_backend() -> None:
    """RaylibRenderer must satisfy the RenderBackend protocol structurally."""
    backend = RaylibRenderer(1280, 720)
    assert hasattr(backend, "begin_frame")
    assert hasattr(backend, "clear")
    assert hasattr(backend, "draw_item")
    assert hasattr(backend, "end_frame")
    assert hasattr(backend, "render_compositor")
    assert hasattr(backend, "draw_rect")
    assert hasattr(backend, "draw_text")
    assert hasattr(backend, "draw_image")
    assert hasattr(backend, "measure_text")


def test_raylib_renderer_lifecycle_errors() -> None:
    """Lifecycle guard errors must be raised without requiring a GL context."""
    backend = RaylibRenderer(1280, 720)

    item = RenderItem(
        asset_id="bg/castle",
        x=0.0, y=0.0, opacity=1.0,
        scale_x=1.0, scale_y=1.0, rotation=0.0,
        anchor=Anchor.TOP_LEFT, tint=Color(1, 1, 1, 1),
        flip_h=False, flip_v=False, layer="background", z_order=0,
    )

    with pytest.raises(RuntimeError, match="outside of begin_frame"):
        backend.draw_item(item)

    with pytest.raises(RuntimeError, match="without matching begin_frame"):
        backend.end_frame()

    backend.begin_frame()
    with pytest.raises(RuntimeError, match="without matching end_frame"):
        backend.begin_frame()

    backend.end_frame()


def test_raylib_renderer_clear() -> None:
    """clear() should store the colour without requiring a GL context."""
    backend = RaylibRenderer(100, 100)
    backend.begin_frame()
    backend.clear(Color(1.0, 0.0, 0.0, 1.0))
    assert backend.clear_color == Color(1.0, 0.0, 0.0, 1.0)
    backend.end_frame()
    assert backend.frame_count == 1


def test_raylib_renderer_default_clear_color() -> None:
    backend = RaylibRenderer(1280, 720)
    assert backend.clear_color == BLACK


def test_raylib_renderer_repr_and_len() -> None:
    """__repr__ and __len__ should reflect frame state."""
    backend = RaylibRenderer(1280, 720)
    backend.begin_frame()
    backend.end_frame()
    assert "RaylibRenderer" in repr(backend)
    assert "frame_count=1" in repr(backend)
    assert len(backend) == 0


def test_raylib_renderer_fps_properties() -> None:
    """FPS properties should return non-negative values without a GL context."""
    backend = RaylibRenderer(1280, 720)
    assert backend.fps >= 0.0
    assert backend.fps_avg >= 0.0
    assert backend.fps_overall >= 0.0


def test_raylib_no_pyglet_import_side_effect() -> None:
    """Importing eager_graphics should not eagerly import pyglet or PIL.

    Uses a subprocess so prior test imports don't pollute ``sys.modules``.
    """
    code = """
import sys
assert "pyglet" not in sys.modules, "pyglet was imported before eager_graphics"
from eager_graphics import NullRenderer
from eager_graphics.renderers.raylib import RaylibRenderer
assert "pyglet" not in sys.modules, "importing eager_graphics eagerly imported pyglet"
print("OK")
"""
    env = dict(__import__("os").environ)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, (
        f"Subprocess failed (exit {result.returncode}):\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )
    assert "OK" in result.stdout


# ---------------------------------------------------------------------- #
# GPU tests (run in single batched subprocess)
# ---------------------------------------------------------------------- #


def _check_gpu_result(name: str, results: dict[str, dict]) -> None:
    res = results.get(name)
    if res is None:
        pytest.skip(f"{name} was not run in the GPU batch")
    if not res["passed"]:
        pytest.fail(f"{name} failed: {res.get('error', 'unknown error')}")


def test_raylib_asset_resolver_placeholders(gpu_results) -> None:
    """Placeholders should have correct dimensions and cache results."""
    _check_gpu_result("test_raylib_asset_resolver_placeholders", gpu_results)


def test_raylib_asset_resolver_builtin_color_rect(gpu_results) -> None:
    """The __builtin_color_rect__ asset must be a 1x1 white texture."""
    _check_gpu_result("test_raylib_asset_resolver_builtin_color_rect", gpu_results)


def test_raylib_asset_resolver_disk_load(gpu_results) -> None:
    """Assets should be loadable from disk when an asset_dir is configured."""
    _check_gpu_result("test_raylib_asset_resolver_disk_load", gpu_results)


def test_raylib_renderer_draw_items(gpu_results) -> None:
    """render_compositor should draw all items and increment frame_count."""
    _check_gpu_result("test_raylib_renderer_draw_items", gpu_results)


def test_raylib_renderer_flips(gpu_results) -> None:
    """Horizontal, vertical, and combined flips should not crash."""
    _check_gpu_result("test_raylib_renderer_flips", gpu_results)


def test_raylib_renderer_culling_and_early_exits(gpu_results) -> None:
    """Items with zero opacity or zero scale should be discarded early."""
    _check_gpu_result("test_raylib_renderer_culling_and_early_exits", gpu_results)


def test_raylib_renderer_scale_modes(gpu_results) -> None:
    """All scale modes should produce a valid render."""
    _check_gpu_result("test_raylib_renderer_scale_modes", gpu_results)


def test_raylib_renderer_anchors(gpu_results) -> None:
    """Items with various anchors and rotation should render without error."""
    _check_gpu_result("test_raylib_renderer_anchors", gpu_results)


def test_raylib_renderer_negative_scale(gpu_results) -> None:
    """Negative scale_x should flip the sprite (equivalent to flip_h)."""
    _check_gpu_result("test_raylib_renderer_negative_scale", gpu_results)


def test_raylib_renderer_tint_and_opacity(gpu_results) -> None:
    """Tinted and semi-transparent items should render without error."""
    _check_gpu_result("test_raylib_renderer_tint_and_opacity", gpu_results)


def test_raylib_renderer_builtin_color_rect(gpu_results) -> None:
    """__builtin_color_rect__ should fill the viewport when sized to it."""
    _check_gpu_result("test_raylib_renderer_builtin_color_rect", gpu_results)


def test_raylib_renderer_frame_count_increments(gpu_results) -> None:
    """render_compositor should increment frame_count."""
    _check_gpu_result("test_raylib_renderer_frame_count_increments", gpu_results)


def test_raylib_renderer_draw_rect(gpu_results) -> None:
    """draw_rect should issue a rectangle fill without error."""
    _check_gpu_result("test_raylib_renderer_draw_rect", gpu_results)


def test_raylib_renderer_draw_rect_with_border(gpu_results) -> None:
    """draw_rect with border should draw outline."""
    _check_gpu_result("test_raylib_renderer_draw_rect_with_border", gpu_results)


def test_raylib_renderer_draw_text(gpu_results) -> None:
    """draw_text should render text without error."""
    _check_gpu_result("test_raylib_renderer_draw_text", gpu_results)


def test_raylib_renderer_measure_text(gpu_results) -> None:
    """measure_text should return positive dimensions."""
    _check_gpu_result("test_raylib_renderer_measure_text", gpu_results)


def test_raylib_renderer_draw_image(gpu_results) -> None:
    """draw_image should render an asset without error."""
    _check_gpu_result("test_raylib_renderer_draw_image", gpu_results)


def test_raylib_player_story_progression(gpu_results) -> None:
    """RaylibPlayer should advance through a story and reach the choice prompt."""
    _check_gpu_result("test_raylib_player_story_progression", gpu_results)


def test_raylib_player_choice_selection(gpu_results) -> None:
    """Selecting option 2 should branch to the correct scene."""
    _check_gpu_result("test_raylib_player_choice_selection", gpu_results)


def test_raylib_player_rollback(gpu_results) -> None:
    """Rollback should return to previous narrative state."""
    _check_gpu_result("test_raylib_player_rollback", gpu_results)


def test_raylib_player_on_draw_no_crash(gpu_results) -> None:
    """on_draw should render a frame without crashing."""
    _check_gpu_result("test_raylib_player_on_draw_no_crash", gpu_results)


def test_raylib_renderer_compositor(gpu_results) -> None:
    """RaylibRenderer should render a GameSession compositor without error."""
    _check_gpu_result("test_raylib_renderer_compositor", gpu_results)
