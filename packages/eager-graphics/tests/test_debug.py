"""Tests for StageCompositor debug inspection (``debug_info`` / ``debug_repr``)."""

from __future__ import annotations

import json

from eager_core.types import BLACK

from eager_graphics.compositor import StageCompositor


def _build_sample_compositor() -> StageCompositor:
    comp = StageCompositor(1920, 1080, ground_y=1000.0)
    comp.set_background("bg/courtyard", transition="cut")
    comp.show_character("alice", "happy", position="left", transition="cut")
    comp.show_character("bob", "thinking", position="right", transition="fade", duration=0.4)
    comp.shake(intensity=1.5, duration=0.5)
    # Advance into the fade + shake so tweens are genuinely active.
    comp.update(0.1)
    return comp


def test_debug_info_structure() -> None:
    comp = _build_sample_compositor()
    info = comp.debug_info()

    # Top-level keys
    assert set(info.keys()) == {
        "virtual_stage",
        "fps",
        "shake",
        "timeline",
        "layers",
        "render_list",
    }

    # Virtual stage metadata
    assert info["virtual_stage"]["width"] == 1920
    assert info["virtual_stage"]["height"] == 1080
    assert info["virtual_stage"]["ground_y"] == 1000.0

    # Shake summary
    sh = info["shake"]
    assert sh["active"] is True
    assert sh["intensity"] == 1.5
    assert sh["duration"] == 0.5
    assert "offset" in sh and "x" in sh["offset"] and "y" in sh["offset"]

    # Timeline summary
    tl = info["timeline"]
    assert tl["active_tween_count"] >= 1
    for tw in tl["active_tweens"]:
        assert set(tw.keys()) == {
            "target",
            "property",
            "progress",
            "duration",
            "remaining",
            "delay",
        }
        assert 0.0 <= tw["progress"] <= 1.0

    # Layers should be sorted by z_order, starting with background (0)
    assert len(info["layers"]) >= 2
    layer_names = [layer["name"] for layer in info["layers"]]
    assert layer_names[0] == "background"
    z_orders = [layer["z_order"] for layer in info["layers"]]
    assert z_orders == sorted(z_orders)

    # Render list mirrors render_list() and is JSON serializable
    assert len(info["render_list"]) == len(comp.render_list())


def test_debug_info_json_serializable() -> None:
    comp = _build_sample_compositor()
    info = comp.debug_info()
    # Must round-trip through JSON without leaking dataclass objects.
    serialized = json.dumps(info)
    restored = json.loads(serialized)
    assert restored["layers"][0]["name"] == "background"


def test_debug_info_reflects_fade_out_overlay() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/night", transition="cut")
    # fade_out tweens the overlay's __screen_fade__ element opacity 0 -> 1.
    comp.fade_out(duration=0.5)
    comp.update(0.3)
    info = comp.debug_info()

    bg_layer = next(layer for layer in info["layers"] if layer["name"] == "background")
    # Background remains fully opaque; the tween targets the overlay fade element.
    assert bg_layer["element_count"] == 1
    assert bg_layer["elements"][0]["element_id"] == "bg_main"
    assert bg_layer["elements"][0]["asset_id"] == "bg/night"

    overlay = next(layer for layer in info["layers"] if layer["name"] == "overlay")
    assert overlay["element_count"] == 1
    fade_elem = overlay["elements"][0]
    assert fade_elem["element_id"] == "__screen_fade__"
    assert fade_elem["asset_id"] == "__builtin_color_rect__"
    assert fade_elem["tint"] == BLACK.to_hex()
    # Opacity should be ~60% at the 0.3s mark of a 0.5s tween from 0 -> 1.
    assert 0.4 < fade_elem["opacity"] < 0.9


def test_debug_repr_compact_mode() -> None:
    comp = _build_sample_compositor()
    text = comp.debug_repr(include_layers=False)

    assert "Eager-Graphics — StageCompositor debug report" in text
    assert "Camera shake" in text
    assert "Timeline" in text
    assert "Render list" in text
    # Compact mode must omit the per-layer element listing section, while the
    # compact render-list summary still shows asset ids.
    assert "Layers (sorted)" not in text
    assert "bg/courtyard at" not in text  # per-layer element lines use "pos=" format


def test_debug_repr_full_mode_lists_elements() -> None:
    comp = _build_sample_compositor()
    text = comp.debug_repr(include_layers=True)

    assert "Layers (sorted)" in text
    assert "alice/happy" in text
    assert "bob/thinking" in text
    # bob is mid-fade, so it should appear in the render list at reduced opacity
    assert "bob/thinking" in text


def test_debug_repr_shake_idle() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/empty", transition="cut")
    text = comp.debug_repr()
    assert "Camera shake" in text
    assert "[idle]" in text


def test_debug_repr_no_active_tweens() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/solid", transition="cut")
    info = comp.debug_info()
    assert info["timeline"]["active_tween_count"] == 0
    text = comp.debug_repr()
    assert "0 active tween(s)" in text
