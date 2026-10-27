"""Tests for graphics-specific types (Anchor, TransitionKind)."""

from eager_graphics.types import Anchor, TransitionKind


def test_anchor_offsets_and_parsing() -> None:
    assert Anchor.TOP_LEFT.get_offset_factor() == (0.0, 0.0)
    assert Anchor.CENTER.get_offset_factor() == (0.5, 0.5)
    assert Anchor.BOTTOM_CENTER.get_offset_factor() == (0.5, 1.0)

    assert Anchor.from_str("bottom_center") == Anchor.BOTTOM_CENTER
    assert Anchor.from_str("top") == Anchor.TOP_CENTER
    assert Anchor.from_str("left") == Anchor.CENTER_LEFT
    assert Anchor.from_str("middle") == Anchor.CENTER


def test_transition_kind_parsing() -> None:
    assert TransitionKind.from_str("crossfade") == TransitionKind.CROSSFADE
    assert TransitionKind.from_str("fade") == TransitionKind.FADE
    assert TransitionKind.from_str("slide-left") == TransitionKind.SLIDE_LEFT
    assert TransitionKind.from_str("unknown_xyz") == TransitionKind.CUT
