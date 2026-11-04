"""Unit tests for eager_core.hooks."""

from eager_core.hooks import (
    HookArgs,
    InputHookArgs,
    is_input_hook,
    parse_hook_args,
    parse_input_args,
    parse_input_hook,
)
from eager_core.types import BLACK, WHITE, Color


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


def test_get_color() -> None:
    args = parse_hook_args("duration=0.5 color=#ff0000 invalid_color=foobar")
    assert args.get_color("color", BLACK) == Color(1.0, 0.0, 0.0, 1.0)
    assert args.get_color("nonexistent", WHITE) == WHITE
    assert args.get_color("invalid_color", WHITE) == WHITE


def test_input_hooks() -> None:
    assert is_input_hook("input player_name")
    assert not is_input_hook("play_music track1")

    res = parse_input_hook("input player_name prompt=\"What's your name?\" default=\"Hero\"")
    assert isinstance(res, InputHookArgs)
    assert res.var_name == "player_name"
    assert res.prompt == "What's your name?"
    assert res.default == "Hero"

    res2 = parse_input_args("player_name \"Enter name:\"")
    assert res2.var_name == "player_name"
    assert res2.prompt == "Enter name:"
