"""Tests for the screenplay hook argument parser."""

from eager_script import HookArgs, parse_hook_args


def test_parse_empty_hooks() -> None:
    assert parse_hook_args("") == HookArgs()
    assert parse_hook_args("   ") == HookArgs()


def test_parse_positional_and_keywords() -> None:
    args = parse_hook_args("alice happy at left with dissolve duration=0.8 flip_h=true z=5")
    assert args.positional == ("alice", "happy")
    assert args.at == "left"
    assert args.with_ == "dissolve"
    assert args.to is None
    assert args.get_float("duration") == 0.8
    assert args.get_bool("flip_h") is True
    assert args.get_int("z") == 5


def test_parse_destination_and_easing() -> None:
    args = parse_hook_args("bob to right duration=1.5 easing=ease_out_back")
    assert args.positional == ("bob",)
    assert args.to == "right"
    assert args.get_float("duration") == 1.5
    assert args.get_str("easing") == "ease_out_back"


def test_parse_color_kwarg_raw_string() -> None:
    # The parser stays rendering-agnostic: colours are returned as raw strings
    # and decoded by the caller (e.g. the graphics director via Color.from_hex).
    args = parse_hook_args("duration=0.5 color=#ff0000")
    assert args.get_str("color") == "#ff0000"
    assert args.get_str("nonexistent") is None


def test_parse_quoted_strings() -> None:
    args = parse_hook_args('"grand castle gate" with "smooth crossfade" duration=2.0')
    assert args.positional == ("grand castle gate",)
    assert args.with_ == "smooth crossfade"
    assert args.get_float("duration") == 2.0


def test_hook_args_serialization() -> None:
    args = parse_hook_args("alice at right duration=0.5")
    d = args.to_dict()
    assert d["positional"] == ["alice"]
    assert d["at"] == "right"
    assert d["kwargs"]["duration"] == "0.5"
