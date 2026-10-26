"""Tests for StageCompositor visual composition, transitions, and render lists."""

import pytest
from eager_core.types import BLACK, Vec2

from eager_graphics.compositor import StageCompositor


def test_compositor_background_instant_and_crossfade() -> None:
    comp = StageCompositor(1920, 1080)
    # Instant background
    comp.set_background("bg/courtyard", transition="cut")
    items = comp.render_list()
    assert len(items) == 1
    assert items[0].asset_id == "bg/courtyard"
    assert items[0].opacity == 1.0
    assert items[0].layer == "background"

    # Crossfade background transition over 1.0s
    comp.set_background("bg/hall", transition="crossfade", duration=1.0)
    # Advance slightly into crossfade
    comp.update(0.1)
    items_mid = comp.render_list()
    assert len(items_mid) == 2  # courtyard fading out, hall fading in

    # Step to half second total (0.1 + 0.4 = 0.5)
    comp.update(0.4)
    items_half = comp.render_list()
    assert len(items_half) == 2
    # Check that opacity is progressing
    hall_item = next(it for it in items_half if it.asset_id == "bg/hall")
    assert hall_item.opacity == pytest.approx(0.5, abs=0.1)

    # Step to completion
    comp.update(0.6)
    items_done = comp.render_list()
    assert len(items_done) == 1
    assert items_done[0].asset_id == "bg/hall"
    assert items_done[0].opacity == 1.0


def test_compositor_character_show_hide_move() -> None:
    comp = StageCompositor(1920, 1080, ground_y=1000.0)

    # Show Alice at left with fade
    comp.show_character("alice", "happy", position="left", transition="fade", duration=0.4)
    # Initial opacity is 0.0, so render list won't yield invisible item until opacity > 0
    comp.update(0.2)
    items = comp.render_list()
    assert len(items) == 1
    assert items[0].asset_id == "alice/happy"
    assert items[0].x == pytest.approx(480.0)
    assert items[0].y == pytest.approx(1000.0)
    assert items[0].opacity == pytest.approx(0.5, abs=0.1)

    # Complete fade
    comp.update(0.3)
    items = comp.render_list()
    assert items[0].opacity == 1.0

    # Expression change
    success = comp.set_expression("alice", "angry")
    assert success is True
    assert comp.render_list()[0].asset_id == "alice/angry"

    # Move Alice to right over 0.5s
    comp.move_character("alice", "right", duration=0.5)
    comp.update(0.25)
    item_moving = comp.render_list()[0]
    assert 480.0 < item_moving.x < 1440.0

    comp.update(0.3)
    item_arrived = comp.render_list()[0]
    assert item_arrived.x == pytest.approx(1440.0)

    # Hide Alice
    comp.hide_character("alice", transition="fade", duration=0.2)
    comp.update(0.3)
    assert len(comp.render_list()) == 0


def test_compositor_camera_shake_exemption() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/space", transition="cut")
    comp.show_character("bob", "normal", position="center", transition="cut")
    comp.show_element("ui", "dialogue_box", "ui/box", position=Vec2(960.0, 900.0))

    # Trigger camera shake
    comp.shake(intensity=2.0, duration=0.5)
    comp.update(0.05)  # advance into shake

    assert comp.shake_offset != Vec2(0.0, 0.0)

    items = {it.layer: it for it in comp.render_list()}
    # Background and Character layers should be offset by camera shake
    assert items["background"].x == pytest.approx(comp.shake_offset.x)
    assert items["characters"].x == pytest.approx(960.0 + comp.shake_offset.x)

    # UI layer must be exempt from shake
    assert items["ui"].x == pytest.approx(960.0)
    assert items["ui"].y == pytest.approx(900.0)

    # Update past shake duration -> shake returns to 0
    comp.update(0.6)
    assert comp.shake_offset == Vec2(0.0, 0.0)


def test_compositor_fade_and_flash() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/night", transition="cut")

    # Fade out to black over 1.0s
    comp.fade_out(duration=1.0)
    comp.update(0.5)
    items = comp.render_list()
    overlay_item = next(it for it in items if it.layer == "overlay")
    assert overlay_item.tint == BLACK
    assert overlay_item.opacity == pytest.approx(0.5, abs=0.1)

    comp.update(0.6)
    items_done = comp.render_list()
    overlay_full = next(it for it in items_done if it.layer == "overlay")
    assert overlay_full.opacity == pytest.approx(1.0)


def test_compositor_save_and_load_state() -> None:
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/garden", transition="cut")
    comp.show_character("alice", "smile", position="left", transition="cut")
    comp.show_character("bob", "thinking", position="right", transition="cut")

    snapshot = comp.save_state()
    assert "stage" in snapshot
    assert snapshot["virtual_width"] == 1920

    # Wipe stage
    comp.clear()
    assert len(comp.render_list()) == 0

    # Restore stage
    comp.load_state(snapshot)
    items = comp.render_list()
    assert len(items) == 3
    asset_ids = {it.asset_id for it in items}
    assert asset_ids == {"bg/garden", "alice/smile", "bob/thinking"}


def test_compositor_background_slide_transitions() -> None:
    """Verify slide transitions on set_background move position with full opacity."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/garden", transition="cut")

    # Slide left transition (incoming enters from right, old slides to left)
    comp.set_background("bg/hall", transition="slide_left", duration=0.5)
    items_start = comp.render_list()
    assert len(items_start) == 2
    incoming = next(it for it in items_start if it.asset_id == "bg/hall")
    old = next(it for it in items_start if it.asset_id == "bg/garden")
    assert incoming.opacity == 1.0
    assert old.opacity == 1.0
    assert incoming.x == pytest.approx(1920.0)
    assert old.x == pytest.approx(0.0)

    # Halfway through slide
    comp.update(0.25)
    items_mid = comp.render_list()
    incoming_mid = next(it for it in items_mid if it.asset_id == "bg/hall")
    old_mid = next(it for it in items_mid if it.asset_id == "bg/garden")
    assert incoming_mid.x < 1920.0 and incoming_mid.x > 0.0
    assert old_mid.x < 0.0

    # Finish transition
    comp.update(0.3)
    items_end = comp.render_list()
    assert len(items_end) == 1
    assert items_end[0].asset_id == "bg/hall"
    assert items_end[0].x == pytest.approx(0.0)
    assert items_end[0].opacity == 1.0

    # Slide right transition
    comp.set_background("bg/shrine", transition="slide_right", duration=0.4)
    items_right = comp.render_list()
    incoming_right = next(it for it in items_right if it.asset_id == "bg/shrine")
    assert incoming_right.x == pytest.approx(-1920.0)
    assert incoming_right.opacity == 1.0

    comp.update(0.5)
    assert len(comp.render_list()) == 1
    assert comp.render_list()[0].asset_id == "bg/shrine"

    # Slide up transition
    comp.set_background("bg/sky", transition="slide_up", duration=0.4)
    incoming_up = next(it for it in comp.render_list() if it.asset_id == "bg/sky")
    assert incoming_up.y == pytest.approx(1080.0)

    comp.update(0.5)
    assert len(comp.render_list()) == 1
    assert comp.render_list()[0].asset_id == "bg/sky"

    # Slide down transition
    comp.set_background("bg/basement", transition="slide_down", duration=0.4)
    incoming_down = next(it for it in comp.render_list() if it.asset_id == "bg/basement")
    assert incoming_down.y == pytest.approx(-1080.0)

    comp.update(0.5)
    assert len(comp.render_list()) == 1
    assert comp.render_list()[0].asset_id == "bg/basement"


def test_compositor_character_reshow_with_slide() -> None:
    """Verify re-showing an existing character honors slide transitions."""
    comp = StageCompositor(1920, 1080, ground_y=1000.0)
    comp.show_character("alice", "happy", position="center", transition="cut")
    initial_items = comp.render_list()
    assert len(initial_items) == 1
    assert initial_items[0].x == pytest.approx(960.0)

    # Re-show alice with slide_right to right position
    # target_pos for right is x=1440.0. slide_right starts at target_pos - (300, 0) = 1140.0
    comp.show_character("alice", "sad", position="right", transition="slide_right", duration=0.5)
    comp.update(0.01)
    items = comp.render_list()
    alice = next(it for it in items if "alice" in it.asset_id)
    assert alice.asset_id == "alice/sad"
    # Should be sliding towards 1440.0 from 1140.0
    assert 1140.0 <= alice.x < 1440.0

    # Complete transition
    comp.update(0.6)
    items_done = comp.render_list()
    alice_done = next(it for it in items_done if "alice" in it.asset_id)
    assert alice_done.x == pytest.approx(1440.0)
    assert alice_done.opacity == 1.0

    # Re-show with slide_left
    # target_pos for left is x=480.0. slide_left starts at target_pos + (300, 0) = 780.0
    comp.show_character("alice", "surprised", position="left", transition="slide_left", duration=0.5)
    comp.update(0.01)
    items_left = comp.render_list()
    alice_left = next(it for it in items_left if "alice" in it.asset_id)
    assert alice_left.asset_id == "alice/surprised"
    assert 480.0 < alice_left.x <= 780.0

    comp.update(0.6)
    items_left_done = comp.render_list()
    alice_left_done = next(it for it in items_left_done if "alice" in it.asset_id)
    assert alice_left_done.x == pytest.approx(480.0)


def test_compositor_save_state_flushes_active_fade_and_crossfade() -> None:
    """Verify save_state snaps active tweens so checkpoints do not store opacity 0.0 or pending transitions."""
    comp = StageCompositor(1920, 1080)
    comp.set_background("bg/garden", transition="cut")

    # Start a fade-in show_character with duration 0.5 without ticking update()
    comp.show_character("alice", "happy", position="center", transition="fade", duration=0.5)

    # Crossfade background to bg/hall without ticking update()
    comp.set_background("bg/hall", transition="dissolve", duration=0.5)

    assert comp.timeline.active_count > 0

    # save_state() snapshots settled state while preserving live active animations
    snapshot = comp.save_state()
    assert comp.timeline.active_count > 0

    # Clear and restore snapshot
    comp.clear()
    assert len(comp.render_list()) == 0

    comp.load_state(snapshot)
    items = comp.render_list()
    asset_ids = {it.asset_id for it in items}
    assert "alice/happy" in asset_ids
    assert "bg/hall" in asset_ids
    assert "bg/garden" not in asset_ids  # old background was cleaned up

    alice_item = next(it for it in items if it.asset_id == "alice/happy")
    assert alice_item.opacity == pytest.approx(1.0)

    # finish_animations flushes active tweens on the live compositor
    comp.fade_out(duration=0.5)
    assert comp.timeline.active_count > 0
    comp.finish_animations()
    assert comp.timeline.active_count == 0

