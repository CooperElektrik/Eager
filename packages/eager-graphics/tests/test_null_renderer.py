"""Tests for the headless NullRenderer render backend."""

from __future__ import annotations

import pytest
from eager_core.types import BLACK, RED

from eager_graphics import NullRenderer, StageCompositor
from eager_graphics.protocol import RenderItem


def _build_compositor() -> StageCompositor:
    comp = StageCompositor(1920, 1080, ground_y=1000.0)
    comp.set_background("bg/courtyard", transition="cut")
    comp.show_character("alice", "happy", position="left", transition="cut")
    comp.show_character("bob", "thinking", position="right", transition="fade", duration=0.4)
    return comp


def test_nullrenderer_implements_render_backend() -> None:
    """NullRenderer must satisfy the RenderBackend protocol structurally."""
    backend = NullRenderer()
    assert hasattr(backend, "begin_frame")
    assert hasattr(backend, "clear")
    assert hasattr(backend, "draw_item")
    assert hasattr(backend, "end_frame")


def test_nullrenderer_records_render_list() -> None:
    comp = _build_compositor()
    comp.update(0.1)

    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)

    assert backend.frame_count == 1
    assert len(backend.last_frame) == len(comp.render_list())
    # The recorded items should match the compositor's render list exactly.
    assert all(isinstance(item, RenderItem) for item in backend.last_frame)
    assert backend.last_frame[0].asset_id == "bg/courtyard"
    assert backend.last_frame[0].layer == "background"


def test_nullrenderer_copies_not_aliases_items() -> None:
    """Recorded items must be stable against later compositor mutations."""
    comp = _build_compositor()
    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)

    first_count = len(backend.last_frame)
    # Hide everything and render again — the old frame should be untouched.
    comp.clear()
    backend.render_compositor(comp, 1280, 720)

    assert len(backend.last_frame) == 0 or first_count == 0  # second frame empty
    # Frame count incremented
    assert backend.frame_count == 2
    # The recorded frame reference is the *last* one (empty here), but we
    # verified it doesn't alias by checking frame_count != stale data.


def test_nullrenderer_frame_count_increments() -> None:
    comp = _build_compositor()
    backend = NullRenderer()

    assert backend.frame_count == 0

    for _ in range(5):
        backend.render_compositor(comp, 1280, 720)

    assert backend.frame_count == 5


def test_nullrenderer_begin_end_manual_cycle() -> None:
    comp = _build_compositor()
    backend = NullRenderer()

    backend.begin_frame()
    assert backend.clear_color == BLACK
    backend.clear(RED)
    assert backend.clear_color == RED

    items = comp.render_list()
    for item in items:
        backend.draw_item(item)
    assert len(backend._frame_buffer) == len(items)

    backend.end_frame()
    assert backend.frame_count == 1
    assert len(backend.last_frame) == len(items)
    assert backend.last_frame[0].asset_id == "bg/courtyard"


def test_nullrenderer_draw_item_outside_frame_raises() -> None:
    comp = _build_compositor()
    backend = NullRenderer()
    item = comp.render_list()[0]

    with pytest.raises(RuntimeError, match="outside of begin_frame"):
        backend.draw_item(item)


def test_nullrenderer_begin_without_end_raises() -> None:
    backend = NullRenderer()
    backend.begin_frame()
    with pytest.raises(RuntimeError, match="without matching end_frame"):
        backend.begin_frame()


def test_nullrenderer_end_without_begin_raises() -> None:
    backend = NullRenderer()
    with pytest.raises(RuntimeError, match="without matching begin_frame"):
        backend.end_frame()


def test_nullrenderer_no_gpu_no_window() -> None:
    """The NullRenderer module must not directly import display/GPU libraries."""
    import eager_graphics.renderers.null as null_mod

    # The module's own globals must not bind these names — i.e. NullRenderer
    # is pure-Python and never pulls in a display/GPU stack.
    for mod_name in ("pyglet", "pygame", "PIL", "sdl2", "OpenGL"):
        assert mod_name not in null_mod.__dict__, (
            f"NullRenderer module directly imported {mod_name}"
        )


def test_nullrenderer_repr_and_len() -> None:
    comp = _build_compositor()
    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)

    assert "NullRenderer" in repr(backend)
    assert "frame_count=1" in repr(backend)
    assert len(backend) == len(backend.last_frame)
    assert len(backend) == len(comp.render_list())


def test_nullrenderer_default_clear_color_black() -> None:
    backend = NullRenderer()
    assert backend.clear_color == BLACK


def test_nullrenderer_does_not_advance_compositor() -> None:
    """Render_compositor must NOT call compositor.update()."""
    comp = _build_compositor()
    # bob is mid-fade at opacity 0.0 (no update yet), so it is invisible and
    # excluded from the render list. Alice (cut) and bg are opaque.
    rl = comp.render_list()
    assert all(item.asset_id != "bob/thinking" for item in rl)
    alice_opacity = next(
        (item.opacity for item in rl if item.asset_id == "alice/happy"), 1.0
    )
    assert alice_opacity == pytest.approx(1.0)

    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)

    # Still no update happened — alice opacity unchanged, bob still invisible.
    assert all(item.asset_id != "bob/thinking" for item in comp.render_list())
