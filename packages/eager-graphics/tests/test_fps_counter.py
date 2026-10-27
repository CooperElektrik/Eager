"""Tests for backend FPS integration and compositor timing."""

from __future__ import annotations

import time

import pytest
from eager_core.types import BLACK

from eager_graphics import NullRenderer, StageCompositor

# --------------------------------------------------------------------------- #
# NullRenderer FPS integration
# --------------------------------------------------------------------------- #


class TestNullRendererFPS:
    """Tests that NullRenderer ticks its FrameClock and exposes FPS."""

    def test_fps_zero_before_any_frame(self) -> None:
        backend = NullRenderer()
        assert backend.frame_count == 0
        assert backend.fps == 0.0

    def test_fps_after_frames(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/test", transition="cut")
        backend = NullRenderer()

        backend.begin_frame()
        backend.clear(BLACK)
        backend.end_frame()
        assert backend.frame_count == 1
        assert backend.fps == 0.0  # needs ≥2 frames for instantaneous

        # Add a tiny delay so the second frame has a measurable interval
        time.sleep(0.05)
        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 2
        assert backend.fps > 0.0
        assert backend.fps_avg > 0.0
        assert backend.fps_overall > 0.0

    def test_repr_includes_fps(self) -> None:
        backend = NullRenderer()
        backend.begin_frame()
        backend.end_frame()
        backend.begin_frame()
        backend.end_frame()
        r = repr(backend)
        assert "fps=" in r

    def test_render_compositor_ticks_clock(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/fps_test", transition="cut")
        backend = NullRenderer()

        backend.render_compositor(comp, 1280, 720)
        assert backend.frame_count == 1
        assert backend.clock.frame_count == 1


# --------------------------------------------------------------------------- #
# PILRenderer FPS integration
# --------------------------------------------------------------------------- #


class TestPILRendererFPS:
    """Tests that PILRenderer and PILPlayer expose and update the FPS counter."""

    def test_fps_zero_before_any_frame(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        backend = PILRenderer(1280, 720)
        assert backend.frame_count == 0
        assert backend.fps == 0.0

    def test_fps_after_frames(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/test", transition="cut")
        backend = PILRenderer(1280, 720)

        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 1
        assert backend.fps == 0.0

        time.sleep(0.05)
        backend.begin_frame()
        backend.end_frame()
        assert backend.frame_count == 2
        assert backend.fps > 0.0
        assert backend.fps_avg > 0.0
        assert backend.fps_overall > 0.0

    def test_repr_includes_fps(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        backend = PILRenderer(1280, 720)
        backend.begin_frame()
        backend.end_frame()
        backend.begin_frame()
        backend.end_frame()
        r = repr(backend)
        assert "fps=" in r

    def test_render_compositor_ticks_clock(self) -> None:
        try:
            from eager_graphics.renderers.pil import PILRenderer
        except ImportError:
            pytest.skip("Pillow is not installed")
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/fps_test", transition="cut")
        backend = PILRenderer(1280, 720)

        backend.render_compositor(comp, 1280, 720)
        assert backend.frame_count == 1
        assert backend.clock.frame_count == 1

    def test_pil_player_fps_toggle(self) -> None:
        try:
            from types import SimpleNamespace

            from eager_script import parse_graph

            from eager_graphics import DebugOverlayMode
            from eager_graphics.renderers.pil import PILPlayer
        except ImportError:
            pytest.skip("Pillow is not installed")

        from eager_runtime import GameSession

        graph = parse_graph("## Start --- start\nAlice: Hi!\n")
        session = GameSession(graph)

        player = PILPlayer(
            session=session,
            width=800,
            height=600,
            visible=False,
            show_fps=True,
        )
        try:
            assert player.show_fps is True
            assert player.debug_mode == DebugOverlayMode.FPS
            # Advance tick: step compositor so FPS clock ticks
            player.tick(0.016)
            assert session.compositor.clock.frame_count == 1
            # Render frame with FPS overlay
            player.on_draw()
            assert player.renderer.frame_count == 1
            assert "FPS:" in player.get_debug_overlay_text()

            # Cycle F3: FPS -> DETAILED
            player._on_key(SimpleNamespace(keysym="F3"))
            assert player.debug_mode == DebugOverlayMode.DETAILED
            assert player.show_fps is True
            detailed_text = player.get_debug_overlay_text()
            assert "Eager Debug: PIL Backend" in detailed_text
            assert "Cache Diagnostics" in detailed_text
            player.on_draw()
            assert player.renderer.frame_count == 2

            # Cycle F3: DETAILED -> OFF
            player._on_key(SimpleNamespace(keysym="F3"))
            assert player.debug_mode == DebugOverlayMode.OFF
            assert player.show_fps is False
            assert player.get_debug_overlay_text() == ""
            player.on_draw()
            assert player.renderer.frame_count == 3

            # Cycle F3: OFF -> FPS
            player._on_key(SimpleNamespace(keysym="F3"))
            assert player.debug_mode == DebugOverlayMode.FPS
            assert player.show_fps is True
        finally:
            player.close()


# --------------------------------------------------------------------------- #
# StageCompositor FPS integration
# --------------------------------------------------------------------------- #


class TestCompositorFPS:
    """Tests that the compositor ticks its clock and reports FPS in debug_info."""

    def test_fps_zero_initially(self) -> None:
        comp = StageCompositor(1920, 1080)
        assert comp.fps == 0.0
        assert comp.fps_avg == 0.0
        assert comp.fps_overall == 0.0

    def test_step_ticks_clock(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/step_fps", transition="cut")
        comp.step(dt=0.016)
        assert comp.clock.frame_count == 1
        comp.step(dt=0.016)
        assert comp.clock.frame_count == 2
        assert comp.fps > 0.0
        assert comp.fps_avg > 0.0
        assert comp.fps_overall > 0.0

    def test_step_does_not_tick_without_call(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/nostep", transition="cut")
        comp.update(0.016)  # update() alone should NOT tick the FPS clock
        assert comp.clock.frame_count == 0
        assert comp.fps == 0.0

    def test_update_does_not_tick_clock(self) -> None:
        """Only step() ticks the clock, not update() directly."""
        comp = StageCompositor(1920, 1080)
        comp.update(0.1)
        assert comp.clock.frame_count == 0

    def test_debug_info_includes_fps_section(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/dbg_fps", transition="cut")
        comp.step()
        comp.step()

        info = comp.debug_info()
        assert "fps" in info
        fps = info["fps"]
        assert set(fps.keys()) == {
            "instantaneous",
            "avg_60",
            "overall",
            "frames_stepped",
            "elapsed",
        }
        assert fps["frames_stepped"] == 2
        assert fps["instantaneous"] > 0
        assert fps["elapsed"] >= 0.0

    def test_debug_repr_contains_fps_line(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/repr_fps", transition="cut")
        comp.step()
        comp.step()

        text = comp.debug_repr(include_layers=False)
        assert "FPS" in text
        assert "avg" in text
        assert "frames" in text

    def test_debug_info_json_serializable_with_fps(self) -> None:
        import json

        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/json_fps", transition="cut")
        for _ in range(5):
            comp.step(dt=0.01)
        info = comp.debug_info()
        json.dumps(info)  # must not raise

    def test_run_headless_updates_fps(self) -> None:
        comp = StageCompositor(1920, 1080)
        comp.set_background("bg/run_fps", transition="cut")
        backend = NullRenderer()
        comp.run_headless(backend, max_steps=10, render=True)
        assert comp.clock.frame_count == 10
        assert backend.clock.frame_count == 10

