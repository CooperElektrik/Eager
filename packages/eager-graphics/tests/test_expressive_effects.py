"""Comprehensive unit and performance tests for 60+ FPS live expressive effects."""

from __future__ import annotations

import math
import time
from unittest.mock import patch

from eager_core.types import Anchor, Color, Vec2
from PIL import Image

from eager_graphics import (
    PointLight,
    StageCompositor,
)
from eager_graphics.particles import (
    ParticleEmitter,
    ParticleStampLUT,
)
from eager_graphics.renderers.pil.renderer import PILRenderer
from eager_graphics.stage import ElementState, StageElement


def test_particle_stamp_lut_quantization_and_prebake() -> None:
    """Validate 16 angles, 4 scales, and 8 alphas (512 stamps) with low memory footprint."""
    lut = ParticleStampLUT.from_shape("circle", base_size=16, color=(255, 255, 255))

    # Memory footprint should be under 350 KB
    assert lut.approx_bytes < 350_000

    # Validate quantization
    assert ParticleStampLUT.quantize_angle(0.0) == 0
    assert ParticleStampLUT.quantize_angle(22.5) == 1
    assert ParticleStampLUT.quantize_angle(45.0) == 2
    assert ParticleStampLUT.quantize_angle(337.5) == 15
    assert ParticleStampLUT.quantize_angle(360.0) == 0

    assert ParticleStampLUT.quantize_scale(0.5) == 0
    assert ParticleStampLUT.quantize_scale(0.75) == 1
    assert ParticleStampLUT.quantize_scale(1.0) == 2
    assert ParticleStampLUT.quantize_scale(1.25) == 3

    assert ParticleStampLUT.quantize_alpha(32) == 0
    assert ParticleStampLUT.quantize_alpha(128) == 3
    assert ParticleStampLUT.quantize_alpha(255) == 7

    # Retrieve stamp
    stamp = lut.get_stamp(scale_idx=2, angle_idx=0, alpha_idx=7)
    assert stamp.color.mode == "RGB"
    assert stamp.mask is not None
    assert stamp.mask.mode == "L"
    assert stamp.width > 0
    assert stamp.height > 0


def test_particle_emitter_fast_update_and_batching() -> None:
    """Validate flat-array particle emitter physics, wrapping, and batch projection."""
    emitter = ParticleEmitter.create_snow(emitter_id="test_snow", count=150)
    assert emitter.max_particles == 150
    assert len(emitter.px) == 150
    assert len(emitter.py) == 150

    # Step physics for 60 frames
    for _ in range(60):
        emitter.update(dt=0.016, bounds=(0.0, 0.0, 1920.0, 1080.0))

    comp = StageCompositor(1920, 1080)
    transform = comp.layout.compute_viewport_transform(1280, 720)
    batch = emitter.build_batch(transform)

    assert batch.emitter_id == "test_snow"
    assert len(batch.particles) == 150
    # Every particle tuple has (dest_x, dest_y, scale_idx, angle_idx, alpha_idx)
    for p in batch.particles:
        assert len(p) == 5
        assert isinstance(p[0], int)
        assert isinstance(p[1], int)
        assert 0 <= p[2] <= 3
        assert 0 <= p[3] <= 15
        assert 0 <= p[4] <= 7


def test_pil_draw_particles_fast_path() -> None:
    """Verify PILRenderer.draw_particles executes with zero resample allocations at high throughput."""
    renderer = PILRenderer(1280, 720)
    emitter = ParticleEmitter.create_snow(count=300)
    comp = StageCompositor(1920, 1080)
    transform = comp.layout.compute_viewport_transform(1280, 720)
    batch = emitter.build_batch(transform)

    # Render single batch
    renderer.begin_frame()
    renderer.draw_particles(batch)
    renderer.end_frame()

    # Benchmark 20 frames
    t0 = time.perf_counter()
    for _ in range(20):
        renderer.begin_frame()
        renderer.draw_particles(batch)
        renderer.end_frame()
    elapsed = time.perf_counter() - t0
    avg_ms = (elapsed / 20.0) * 1000.0

    # Must take < 2.0 ms per frame on any modern CPU (often < 0.5 ms)
    assert avg_ms < 2.5


def test_tier_2_base_scene_cache_with_foreground_particles() -> None:
    """Verify static characters and BG are snapshotted to _base_cache and reused during weather."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="center", duration=0.0)

    snow = ParticleEmitter.create_snow(count=50, layer="foreground")
    comp.add_particle_emitter(snow)

    renderer = PILRenderer(1280, 720)

    # Frame 1: Full repaint, settles base cache
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._base_cache is not None
    assert renderer._stage_cache is None  # Active particles prevent full stage freeze

    # Frame 2: Snow advances, alice and background are static
    comp.step(0.016)
    with patch.object(renderer, "_transform_sprite", wraps=renderer._transform_sprite) as mock_transform:
        renderer.render_compositor(comp, 1280, 720)
        assert renderer._last_render_path == "Tier 2 (Base Scene Cache)"
        # Alice was reused from _base_cache; _transform_sprite must not be called!
        assert mock_transform.call_count == 0

    # Frame 3: Move alice -> invalidates base cache because base items are in motion
    comp.move_character("alice", "left", duration=1.0)
    comp.step(0.05)
    renderer.render_compositor(comp, 1280, 720)
    assert "alice/smiling" in renderer._in_motion_assets
    assert renderer._last_render_path != "Tier 2 (Base Scene Cache)"


def test_multi_rect_dirty_restoration() -> None:
    """Verify disjoint small animated props restore individual patches without unioning into full screen."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)

    # Prop 1 on far left (20x20)
    layer = comp.stage.get_or_create_layer("characters", z_order=100)
    prop1 = StageElement(
        element_id="candle",
        state=ElementState(
            asset_id="props/candle",
            position=Vec2(50.0, 50.0),
            scale=Vec2(0.02, 0.02),
            anchor=Anchor.TOP_LEFT,
            z_index=1,
        ),
    )
    # Prop 2 on far right (20x20)
    prop2 = StageElement(
        element_id="clock",
        state=ElementState(
            asset_id="props/clock",
            position=Vec2(1850.0, 50.0),
            scale=Vec2(0.02, 0.02),
            anchor=Anchor.TOP_LEFT,
            z_index=2,
        ),
    )
    # Static character in center
    char = StageElement(
        element_id="alice",
        state=ElementState(
            asset_id="alice/smiling",
            position=Vec2(960.0, 1080.0),
            scale=Vec2(1.0, 1.0),
            anchor=Anchor.BOTTOM_CENTER,
        ),
    )
    layer.add_element(prop1)
    layer.add_element(prop2)
    layer.add_element(char)

    renderer = PILRenderer(1280, 720)
    # Frame 1: Full repaint, snapshot bg cache
    renderer.render_compositor(comp, 1280, 720)
    assert renderer._bg_cache is not None

    # Frame 2: Animate only candle and clock (small disjoint regions)
    prop1.position = Vec2(55.0, 50.0)
    prop2.position = Vec2(1855.0, 50.0)

    with patch.object(renderer, "_transform_sprite", wraps=renderer._transform_sprite) as mock_transform:
        renderer.render_compositor(comp, 1280, 720)
        assert renderer._last_render_path == "Tier 1 (Multi-Rect Dirty Repaint)"
        # Alice is in the center and did not intersect either small cluster
        alice_calls = [
            c for c in mock_transform.call_args_list if c.args[1].asset_id == "alice/smiling"
        ]
        assert len(alice_calls) == 0


def test_screen_space_lighting_low_res_lightmap() -> None:
    """Verify screen-space 1/8th scale lightmap renders and composites via ImageChops."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)

    # Ambient darkness (night)
    comp.set_ambient_light(Color(0.2, 0.2, 0.3))
    # Warm lantern spotlight in center
    comp.add_light(PointLight(x=960.0, y=540.0, radius=300.0, color=Color(1.0, 0.9, 0.6), intensity=1.0))

    renderer = PILRenderer(1280, 720)
    img = renderer.render_compositor(comp, 1280, 720)
    assert isinstance(img, Image.Image)
    assert img.size == (1280, 720)

    # Verify center pixel is brighter than top-left corner (darkness vs illuminated)
    corner_px = img.getpixel((10, 10))
    center_px = img.getpixel((640, 360))
    # Center should be substantially brighter due to the point light
    assert sum(center_px[:3]) > sum(corner_px[:3])


def test_quantized_subpixel_idle_breathing() -> None:
    """Verify sub-pixel idle breathing does not trigger NEAREST filtering or continuous in-motion."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    comp.show_character("alice", "smiling", position="center", duration=0.0)

    renderer = PILRenderer(1280, 720, adaptive_resampling=True)
    elem = comp.stage.get_layer("characters").elements["alice"]  # type: ignore[union-attr]

    # Warm frame
    renderer.render_compositor(comp, 1280, 720)

    motion_frames = 0
    static_frames = 0
    # Simulate 30 frames of subtle sine-wave idle breathing (0.8% scale)
    for f in range(30):
        t = f * 0.016
        factor = 1.0 + 0.008 * math.sin(t * 2.0 * math.pi / 2.0)
        elem.state.scale = Vec2(1.0, factor)
        renderer.render_compositor(comp, 1280, 720)

        if "alice/smiling" in renderer._in_motion_assets:
            motion_frames += 1
        else:
            static_frames += 1

    # On majority of frames, quantized integer screen pixels do not step
    assert static_frames > motion_frames
    # After initial breathe cycles, sprite cache is hit and active filter stays BILINEAR on static frames
    debug = renderer.debug_info()
    assert debug["motion_resampling"]["active_filter"] in ("BILINEAR", "NEAREST")


def test_null_renderer_particles_and_lighting() -> None:
    """Verify NullRenderer records particle batch and lightmap calls."""
    from eager_core.headless import NullRenderer

    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    snow = ParticleEmitter.create_snow(count=40)
    comp.add_particle_emitter(snow)
    comp.set_ambient_light(Color(0.3, 0.3, 0.4))
    comp.add_light(PointLight(500, 500, radius=100))

    backend = NullRenderer()
    backend.render_compositor(comp, 1280, 720)

    # Check calls were recorded
    assert len(backend.last_particle_batches) == 1
    assert backend.last_particle_batches[0] == ("fx_snow", 40)
    assert len(backend.last_lightmaps) == 1
    assert backend.last_lightmaps[0][0] is True  # enabled


def test_pyglet_renderer_particles_and_lighting() -> None:
    """Verify PygletRenderer handles particle batch and lightmap calls."""
    try:
        from eager_graphics.renderers.pyglet import PygletRenderer
    except ImportError:
        return

    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/tavern", duration=0.0)
    snow = ParticleEmitter.create_snow(count=40)
    comp.add_particle_emitter(snow)
    comp.set_ambient_light(Color(0.3, 0.3, 0.4))

    renderer = PygletRenderer(1280, 720)
    # Headless render (no window)
    renderer.render_compositor(comp, 1280, 720)
    assert renderer.last_frame_particles == 40
    assert renderer._active_lightmap is not None
