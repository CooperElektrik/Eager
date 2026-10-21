"""Tests for the screenplay hook argument parser."""

from eager_script import (
    HookArgs,
    InputHookArgs,
    is_input_hook,
    parse_hook_args,
    parse_input_args,
    parse_input_hook,
)


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


def test_is_input_hook() -> None:
    assert is_input_hook("input") is True
    assert is_input_hook("input hero_name") is True
    assert is_input_hook("  input   player_name 'Prompt'  ") is True
    assert is_input_hook("input_mode") is False
    assert is_input_hook("inputting") is False
    assert is_input_hook("scene bg_room") is False
    assert is_input_hook("") is False


def test_parse_input_args_variants() -> None:
    # 1. Empty / fallback
    res = parse_input_args("")
    assert res == InputHookArgs(var_name="player_input", prompt="Enter input:", default="")

    # 2. Variable only
    res = parse_input_args("player_name")
    assert res == InputHookArgs(var_name="player_name", prompt="Enter input:", default="")

    # 3. Variable + Quoted prompt
    res = parse_input_args('hero_name "What is your name?"')
    assert res == InputHookArgs(var_name="hero_name", prompt="What is your name?", default="")

    # 4. Variable + Quoted prompt + Quoted default
    res = parse_input_args('hero_name "Enter name:" "Traveler"')
    assert res == InputHookArgs(var_name="hero_name", prompt="Enter name:", default="Traveler")

    # 5. Variable + Unquoted multi-word prompt
    res = parse_input_args("hero_name Enter your name:")
    assert res == InputHookArgs(var_name="hero_name", prompt="Enter your name:", default="")

    # 6. Keyword prompt & default
    res = parse_input_args('player_name prompt="Who are you?" default="Explorer"')
    assert res == InputHookArgs(var_name="player_name", prompt="Who are you?", default="Explorer")

    # 7. Keyword default + Positional quoted prompt
    res = parse_input_args('player_name default="Valiant" "Enter your title:"')
    assert res == InputHookArgs(var_name="player_name", prompt="Enter your title:", default="Valiant")

    # 8. Keyword default + Positional unquoted multi-word prompt
    res = parse_input_args("player_name default=Valiant What is your title?")
    assert res == InputHookArgs(var_name="player_name", prompt="What is your title?", default="Valiant")


def test_parse_input_hook() -> None:
    assert parse_input_hook("scene bg_room") is None
    assert parse_input_hook("input_mode off") is None

    res = parse_input_hook('input hero_name "Enter name:" "Traveler"')
    assert res == InputHookArgs(var_name="hero_name", prompt="Enter name:", default="Traveler")

