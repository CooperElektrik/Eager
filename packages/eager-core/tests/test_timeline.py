"""Unit tests for eager_core.timeline."""

from eager_core.easing import ease_out_quad
from eager_core.timeline import Timeline
from eager_core.types import Vec2


def test_timeline_add_and_update() -> None:
    tl = Timeline()
    target = {"x": 0.0}
    tl.add_tween(target, "x", 100.0, 1.0, easing=ease_out_quad)
    assert tl.active_count == 1

    tl.update(0.5)
    assert target["x"] > 50.0  # Ease out should be past halfway
    assert tl.active_count == 1

    tl.update(0.6)
    assert target["x"] == 100.0
    assert tl.active_count == 0


def test_timeline_vec2_lerp() -> None:
    tl = Timeline()
    target = {"pos": Vec2(0.0, 0.0)}
    tl.add_tween(target, "pos", Vec2(10.0, 20.0), 1.0)
    tl.update(0.5)
    assert target["pos"] == Vec2(5.0, 10.0)
    tl.finish_all()
    assert target["pos"] == Vec2(10.0, 20.0)
