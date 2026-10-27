"""Tests for standalone Eager-Script screenplay parser and AST serialization."""

import ast
import json
from pathlib import Path

import pytest

from eager_script import (
    ParsedAppend,
    ParsedCall,
    ParsedCharacter,
    ParsedChoiceSet,
    ParsedDialogue,
    ParsedFreshBox,
    ParsedHook,
    ParsedJump,
    ParsedLabel,
    ParsedNarration,
    ParsedReturn,
    ParsedSet,
    ParseError,
    parse,
    parse_iter,
    to_dict,
    to_graph,
    to_json,
    validate,
)

SAMPLE_SCRIPT = """
## The Clearing --- clearing_label

# This is an ambient comment
Alice: {voice:alice_01.ogg} Welcome to the ancient ruins!
- Look at those carved pillars.
/ Be careful where you step.

The wind howls through the stone.
A cold chill runs down your spine.

~ inspect_pillars

? Examine the glowing runes (runes)
? Turn back towards town (exit)

## Ancient Runes --- runes
The runes shimmer with blue light.
>> secret_subroutine
> clearing_label

## Subroutine --- secret_subroutine
Alice: A hidden compartment opened!
<<

## Town Exit --- exit
You head back to town.
"""


def test_parser_extracts_all_ast_nodes() -> None:
    """Verify parser extracts all node types in correct sequential order."""
    items = parse(SAMPLE_SCRIPT)
    assert len(items) == 16

    # 1. ParsedLabel with explicit id
    assert isinstance(items[0], ParsedLabel)
    assert items[0].type == "label"
    assert items[0].display_name == "The Clearing"
    assert items[0].name == "clearing_label"

    # 2. ParsedDialogue with voice tag
    assert isinstance(items[1], ParsedDialogue)
    assert items[1].type == "dialogue"
    assert items[1].speaker == "Alice"
    assert items[1].voice == "alice_01.ogg"
    assert items[1].text == "Welcome to the ancient ruins!"
    assert items[1].emotion is None

    # 3. ParsedAppend
    assert isinstance(items[2], ParsedAppend)
    assert items[2].type == "append"
    assert items[2].text == "Look at those carved pillars."

    # 4. ParsedFreshBox
    assert isinstance(items[3], ParsedFreshBox)
    assert items[3].type == "fresh_box"
    assert items[3].text == "Be careful where you step."

    # 5. Grouped ParsedNarration
    assert isinstance(items[4], ParsedNarration)
    assert items[4].type == "narration"
    assert (
        items[4].text
        == "The wind howls through the stone. A cold chill runs down your spine."
    )

    # 6. ParsedHook
    assert isinstance(items[5], ParsedHook)
    assert items[5].type == "hook"
    assert items[5].hook_name == "inspect_pillars"

    # 7. ParsedChoiceSet with multiple options
    assert isinstance(items[6], ParsedChoiceSet)
    assert items[6].type == "choice_set"
    assert len(items[6].options) == 2
    assert items[6].options[0].type == "choice_option"
    assert items[6].options[0].text == "Examine the glowing runes"
    assert items[6].options[0].target == "runes"
    assert items[6].options[1].text == "Turn back towards town"
    assert items[6].options[1].target == "exit"

    # 8. ParsedLabel
    assert isinstance(items[7], ParsedLabel)
    assert items[7].name == "runes"

    # 9. ParsedNarration
    assert isinstance(items[8], ParsedNarration)
    assert items[8].text == "The runes shimmer with blue light."

    # 10. ParsedCall
    assert isinstance(items[9], ParsedCall)
    assert items[9].type == "call"
    assert items[9].target == "secret_subroutine"

    # 11. ParsedJump
    assert isinstance(items[10], ParsedJump)
    assert items[10].type == "jump"
    assert items[10].target == "clearing_label"

    # 12. ParsedLabel
    assert isinstance(items[11], ParsedLabel)
    assert items[11].name == "secret_subroutine"

    # 13. ParsedDialogue without voice tag
    assert isinstance(items[12], ParsedDialogue)
    assert items[12].speaker == "Alice"
    assert items[12].voice is None
    assert items[12].text == "A hidden compartment opened!"

    # 14. ParsedReturn
    assert isinstance(items[13], ParsedReturn)
    assert items[13].type == "return"

    # 15. ParsedLabel
    assert isinstance(items[14], ParsedLabel)
    assert items[14].name == "exit"

    # 16. ParsedNarration
    assert isinstance(items[15], ParsedNarration)
    assert items[15].text == "You head back to town."


def test_parser_python_310_syntax_compatibility() -> None:
    """Verify module does not use PEP 695 type keyword (incompatible with Python 3.10/3.11)."""
    src_path = Path(__file__).resolve().parent.parent / "src" / "eager_script" / "__init__.py"
    code = src_path.read_text(encoding="utf-8")
    parsed = ast.parse(code, feature_version=(3, 10))
    assert parsed is not None


def test_parser_label_auto_slug() -> None:
    """Verify label without explicit id is automatically slugified."""
    items = parse("## Mysterious Cavern Entrance")
    assert len(items) == 1
    assert isinstance(items[0], ParsedLabel)
    assert items[0].display_name == "Mysterious Cavern Entrance"
    assert items[0].name == "mysterious_cavern_entrance"


def test_parser_empty_label_errors() -> None:
    """Verify parser raises error on empty label definition or missing name/id."""
    with pytest.raises(ParseError) as ctx:
        parse("##    ")
    assert "Empty label definition" in str(ctx.value)

    with pytest.raises(ParseError) as ctx:
        parse("## Scene ---   ")
    assert "Empty label identifier" in str(ctx.value)

    with pytest.raises(ParseError) as ctx:
        parse("##    --- scene_id")
    assert "Empty label display name" in str(ctx.value)


def test_parser_empty_targets_raise_errors() -> None:
    """Verify jump, call, hook, and choice validate empty targets."""
    with pytest.raises(ParseError) as ctx:
        parse(">   ")
    assert "Empty jump target" in str(ctx.value)

    with pytest.raises(ParseError) as ctx:
        parse(">>   ")
    assert "Empty call target" in str(ctx.value)

    with pytest.raises(ParseError) as ctx:
        parse("~   ")
    assert "Empty hook name" in str(ctx.value)


def test_parser_invalid_choice_syntax() -> None:
    """Verify parser raises ParseError on malformed choice syntax."""
    with pytest.raises(ParseError) as ctx:
        parse("? This choice is missing a target")
    assert "Invalid choice syntax" in str(ctx.value)


def test_parser_choice_with_parentheses_in_text() -> None:
    """Verify choice text can contain parentheses and details."""
    items = parse("? Take (small) potion (take_potion)")
    assert len(items) == 1
    assert isinstance(items[0], ParsedChoiceSet)
    opt = items[0].options[0]
    assert opt.text == "Take (small) potion"
    assert opt.target == "take_potion"


def test_parser_comment_and_hash_handling() -> None:
    """Verify inline and standalone comments are stripped without breaking # in dialogue."""
    script = """
    # Standalone comment
    Alice: Hello! # Inline comment
    Bob: Take item #1 and color #ff0000 please.
    Charlie: I code in C# every day.
    """
    items = parse(script)
    assert len(items) == 3
    d0, d1, d2 = items[0], items[1], items[2]
    assert isinstance(d0, ParsedDialogue)
    assert isinstance(d1, ParsedDialogue)
    assert isinstance(d2, ParsedDialogue)
    assert d0.text == "Hello!"
    assert d1.text == "Take item #1 and color #ff0000 please."
    assert d2.speaker == "Charlie"
    assert d2.text == "I code in C# every day."


def test_parser_escaping() -> None:
    """Verify backslash escaping works for reserved symbols."""
    script = r"""
    Alice: Here is a number \#1 and a colon\: not a speaker.
    \- Not an append beat, but narration starting with hyphen.
    \? Not a choice option.
    \> Not a jump.
    """
    items = parse(script)
    assert len(items) == 2
    e0, e1 = items[0], items[1]
    assert isinstance(e0, ParsedDialogue)
    assert isinstance(e1, ParsedNarration)
    assert e0.text == "Here is a number #1 and a colon: not a speaker."
    assert (
        e1.text
        == "- Not an append beat, but narration starting with hyphen. "
        "? Not a choice option. > Not a jump."
    )


def test_parser_dialogue_emotion() -> None:
    """Verify character dialogue can have optional emotion tag."""
    items = parse("Alice (happy): Good morning, traveler!")
    assert len(items) == 1
    assert isinstance(items[0], ParsedDialogue)
    assert items[0].speaker == "Alice"
    assert items[0].emotion == "happy"
    assert items[0].text == "Good morning, traveler!"


def test_parser_non_dialogue_colons() -> None:
    """Verify lines with colons in timestamps or URLs are not treated as character dialogue."""
    script = """
    10:30 PM: the lights went out suddenly.
    Check http://example.com for more info.
    """
    items = parse(script)
    assert len(items) == 1
    assert isinstance(items[0], ParsedNarration)


def test_parser_lines_starting_with_single_angle_bracket() -> None:
    """Verify lines starting with single < are not silently dropped."""
    items = parse("<tag> text </tag>")
    assert len(items) == 1
    assert isinstance(items[0], ParsedNarration)
    assert items[0].text == "<tag> text </tag>"


def test_parse_iter_equivalence() -> None:
    """Verify parse_iter yields exactly identical AST items as parse."""
    parsed_list = parse(SAMPLE_SCRIPT)
    iter_list = list(parse_iter(SAMPLE_SCRIPT))
    assert to_dict(parsed_list) == to_dict(iter_list)


def test_character_quoted_attributes_with_spaces() -> None:
    script = '@character hero "Hero" title="The Great Magician" color="#ff0000" role="Protagonist and Leader"'
    items = list(parse_iter(script))
    assert len(items) == 1
    char = items[0]
    assert isinstance(char, ParsedCharacter)
    assert char.id == "hero"
    assert char.name == "Hero"
    attr_dict = dict(char.attrs)
    assert attr_dict.get("title") == "The Great Magician"
    assert attr_dict.get("color") == "#ff0000"
    assert attr_dict.get("role") == "Protagonist and Leader"


def test_to_dict_and_to_json() -> None:
    script = """
    ## Start --- start_label
    Alice: Hello!
    > start_label
    """
    items = parse(script)
    dicts = to_dict(items)
    assert len(dicts) == 3
    assert dicts[0]["type"] == "label"
    assert dicts[0]["name"] == "start_label"
    assert dicts[1]["type"] == "dialogue"
    assert dicts[1]["speaker"] == "Alice"
    assert dicts[2]["type"] == "jump"
    assert dicts[2]["target"] == "start_label"

    json_str = to_json(items)
    loaded = json.loads(json_str)
    assert loaded == dicts


INLINE_CHOICE_SCRIPT = """\
## Tavern --- tavern
Bartender: What will it be?

? Order an ale
    $ gold -= 3
    Bartender: Coming right up.
? Ask for water
    Bartender: Suit yourself.

Narrator: You settle by the fire.
"""


def test_parser_attaches_indented_block_to_option() -> None:
    items = parse(INLINE_CHOICE_SCRIPT)
    assert [item.type for item in items] == ["label", "dialogue", "choice_set", "dialogue"]

    choice_set = items[2]
    assert isinstance(choice_set, ParsedChoiceSet)
    assert len(choice_set.options) == 2

    first = choice_set.options[0]
    assert first.text == "Order an ale"
    assert first.target is None
    assert first.is_inline
    assert len(first.body) == 2
    assert isinstance(first.body[0], ParsedSet)
    assert first.body[0].target == "gold"
    assert isinstance(first.body[1], ParsedDialogue)
    assert first.body[1].text == "Coming right up."

    second = choice_set.options[1]
    assert second.target is None
    assert len(second.body) == 1
    assert isinstance(second.body[0], ParsedDialogue)


def test_parser_preserves_source_line_numbers() -> None:
    items = parse(INLINE_CHOICE_SCRIPT)
    choice_set = items[2]
    assert isinstance(choice_set, ParsedChoiceSet)
    first = choice_set.options[0]
    assert first.line_number == 4
    assert first.body[0].line_number == 5
    assert first.body[1].line_number == 6
    assert choice_set.options[1].line_number == 7


def test_parser_nested_inline_blocks() -> None:
    script = """## Outer --- outer
? Reaction
    Alice: first
    ? Nested
        Bob: deep
    Alice: back
"""
    items = parse(script)
    cs1 = items[1]
    assert isinstance(cs1, ParsedChoiceSet)
    outer = cs1.options[0]
    assert [item.type for item in outer.body] == ["dialogue", "choice_set", "dialogue"]
    nested_cs = outer.body[1]
    assert isinstance(nested_cs, ParsedChoiceSet)
    nested_option = nested_cs.options[0]
    assert nested_option.text == "Nested"
    assert nested_option.target is None
    assert [item.type for item in nested_option.body] == ["dialogue"]
    nested_d = nested_option.body[0]
    assert isinstance(nested_d, ParsedDialogue)
    assert nested_d.text == "deep"


def test_inline_option_with_condition() -> None:
    items = parse("""## S --- s
? Sneak in if has_key
    Narrator: You slip inside.
""")
    cs = items[1]
    assert isinstance(cs, ParsedChoiceSet)
    opt = cs.options[0]
    assert opt.text == "Sneak in"
    assert opt.condition == "has_key"
    assert len(opt.body) == 1


def test_target_and_block_combination_rejected() -> None:
    with pytest.raises(ParseError) as ctx:
        parse("## A --- a\n? Go (somewhere)\n    Alice: hi\n")
    assert "cannot combine" in str(ctx.value)


def test_targetless_option_without_block_rejected() -> None:
    with pytest.raises(ParseError) as ctx:
        parse("## A --- a\n? Just some text\n")
    assert "Invalid choice syntax" in str(ctx.value)


def test_parse_iter_matches_parse_for_inline_blocks() -> None:
    assert to_dict(parse(INLINE_CHOICE_SCRIPT)) == to_dict(list(parse_iter(INLINE_CHOICE_SCRIPT)))


def test_to_dict_serializes_inline_body() -> None:
    dicts = to_dict(parse(INLINE_CHOICE_SCRIPT))
    choice_set = next(d for d in dicts if d["type"] == "choice_set")
    first = choice_set["options"][0]
    assert first["target"] is None
    assert first["body"][0]["type"] == "set"
    assert choice_set["options"][1]["body"][0]["type"] == "dialogue"
    # Round-trips through JSON
    assert json.loads(to_json(parse(INLINE_CHOICE_SCRIPT))) == dicts


def test_validator_accepts_inline_blocks_and_reachable_continuation() -> None:
    result = validate(parse(INLINE_CHOICE_SCRIPT))
    assert result.is_valid
    unreachable = [w for w in result.warnings if "Unreachable" in w.message]
    assert unreachable == []


def test_validator_checks_targets_inside_inline_blocks() -> None:
    result = validate(parse("## A --- a\n? Go\n    > nowhere\n"))
    assert not result.is_valid
    assert any("nowhere" in err.message for err in result.errors)


def test_validator_rejects_invalid_expression_inside_block() -> None:
    result = validate(parse("## A --- a\n? Go\n    $ x = 1 +\n"))
    assert not result.is_valid
    assert any("Invalid expression" in err.message for err in result.errors)


def test_inline_block_with_comments_and_blank_lines() -> None:
    script = """\
## Tavern --- tavern
? Order
    # first comment
    $ gold -= 3

    # second comment
    Bartender: Coming up.
? Leave
    > nowhere
"""
    items = parse(script)
    choice_set = items[1]
    assert isinstance(choice_set, ParsedChoiceSet)
    assert len(choice_set.options) == 2
    first = choice_set.options[0]
    assert len(first.body) == 2
    assert first.body[0].type == "set"
    assert first.body[1].type == "dialogue"


def test_inline_block_with_tabs_and_spaces() -> None:
    script = "## A --- a\n? Choice\n    $ a = 1\n\t$ b = 2\n"
    items = parse(script)
    cs = items[1]
    assert isinstance(cs, ParsedChoiceSet)
    opt = cs.options[0]
    assert len(opt.body) == 2
    b0, b1 = opt.body[0], opt.body[1]
    assert isinstance(b0, ParsedSet)
    assert b0.target == "a"
    assert isinstance(b1, ParsedSet)
    assert b1.target == "b"


def test_validator_rejects_unclosed_if_in_inline_block() -> None:
    items = parse("## A --- a\n? Go\n    @if cond\n        Alice: hi\n")
    result = validate(items)
    assert not result.is_valid
    assert any("Unclosed @if block" in err.message for err in result.errors)


def test_deeply_nested_inline_choices() -> None:
    """Parser and scene lowering must cleanly handle deeply nested choice trees (up to depth 50)."""
    depth = 50
    lines = ["## start"]
    for d in range(depth):
        indent = "    " * d
        lines.append(f"{indent}? Option depth {d}")
        lines.append(f"{indent}    Alice: Dialogue at level {d}")

    script = "\n".join(lines)
    items = parse(script)
    assert len(items) == 2  # ParsedLabel + ParsedChoiceSet
    assert isinstance(items[1], ParsedChoiceSet)

    graph = to_graph(items)
    assert len(graph.anonymous_scenes()) == depth
    assert graph.entry == "start"


# Empty Screenplay Lines
def test_parser_empty_string() -> None:
    """Parsing empty string produces empty AST list."""
    assert parse("") == []


def test_parser_whitespace_lines_only() -> None:
    """Parsing lines with spaces, tabs, and newlines produces empty list."""
    assert parse("   \n\n\t  \n   \r\n") == []


def test_parser_consecutive_blank_lines_flush_properly() -> None:
    """Multiple consecutive empty lines between statements flush narration properly."""
    script = """
    Line 1 narration.


    Line 2 narration.



    Alice: Hello!
    """
    items = parse(script)
    assert len(items) == 3

    assert isinstance(items[0], ParsedNarration)
    assert items[0].text == "Line 1 narration."

    assert isinstance(items[1], ParsedNarration)
    assert items[1].text == "Line 2 narration."

    assert isinstance(items[2], ParsedDialogue)
    assert items[2].speaker == "Alice"
    assert items[2].text == "Hello!"


# Unmatched Braces
def test_parser_unclosed_voice_tag_handled_gracefully() -> None:
    """Unclosed {voice: tag does not crash parser; treated as regular text."""
    script = "Alice: {voice:alice_01 Unclosed voice tag line"
    items = parse(script)
    assert len(items) == 1

    assert isinstance(items[0], ParsedDialogue)
    assert items[0].speaker == "Alice"
    assert items[0].voice is None
    assert items[0].text == "{voice:alice_01 Unclosed voice tag line"


def test_parser_unclosed_inline_markup_tags() -> None:
    """Unclosed formatting braces in dialogue and narration parse without error."""
    script = """
    Alice: Hello {b bold without closing brace
    Bob: Another {color=#ff0000 unclosed color
    A chill {size=20 runs down the spine.
    """
    items = parse(script)
    assert len(items) == 3

    assert isinstance(items[0], ParsedDialogue)
    assert items[0].text == "Hello {b bold without closing brace"

    assert isinstance(items[1], ParsedDialogue)
    assert items[1].text == "Another {color=#ff0000 unclosed color"

    assert isinstance(items[2], ParsedNarration)
    assert items[2].text == "A chill {size=20 runs down the spine."


def test_parser_lone_closing_braces_in_dialogue() -> None:
    """Dialogue with lone closing braces parses verbatim."""
    script = "Alice: Closing brace } without open { or matched {}"
    items = parse(script)
    assert len(items) == 1

    assert isinstance(items[0], ParsedDialogue)
    assert items[0].text == "Closing brace } without open { or matched {}"


# Edge Case Jump Tags
def test_parser_bare_jump_raises_parse_error() -> None:
    """Bare '>' without target raises ParseError."""
    with pytest.raises(ParseError) as ctx:
        parse(">")
    assert "Empty jump target" in str(ctx.value)

    with pytest.raises(ParseError) as ctx:
        parse(">\n")
    assert "Empty jump target" in str(ctx.value)


def test_parser_bare_call_raises_parse_error() -> None:
    """Bare '>>' without target raises ParseError."""
    with pytest.raises(ParseError) as ctx:
        parse(">>")
    assert "Empty call target" in str(ctx.value)


def test_parser_bare_hook_raises_parse_error() -> None:
    """Bare '~' without hook name raises ParseError."""
    with pytest.raises(ParseError) as ctx:
        parse("~")
    assert "Empty hook name" in str(ctx.value)


def test_parser_jump_with_special_characters_and_numbers() -> None:
    """Jump targets with hyphens, underscores, dots, and numbers parse cleanly."""
    script = """
    > scene-part-2
    > 100_intro_scene
    > chapter.1.sub
    """
    items = parse(script)
    assert len(items) == 3

    assert isinstance(items[0], ParsedJump)
    assert items[0].target == "scene-part-2"

    assert isinstance(items[1], ParsedJump)
    assert items[1].target == "100_intro_scene"

    assert isinstance(items[2], ParsedJump)
    assert items[2].target == "chapter.1.sub"


def test_parser_jump_with_inline_comment() -> None:
    """Jump statement followed by inline comment strips comment cleanly."""
    script = "> target_scene # jump to target scene"
    items = parse(script)
    assert len(items) == 1

    assert isinstance(items[0], ParsedJump)
    assert items[0].target == "target_scene"


def test_parser_return_statement() -> None:
    """'<<' parses as ParsedReturn node."""
    script = "<<"
    items = parse(script)
    assert len(items) == 1

    assert isinstance(items[0], ParsedReturn)


# Unicode Screenplay Characters
def test_parser_unicode_cjk_characters() -> None:
    """Parser fully supports Japanese/CJK characters across all screenplay constructs."""
    script = """
    ## 第一章 --- chapter_1
    Alice: こんにちは、旅人さん。
    Bob (smile): やあ！
    桜の花びらが静かに風に舞っている。
    - そして、夜が明けた。
    / 新しい一日が始まる。
    ~ 背景 "神社"
    ? 探索する (explore)
    ? 立ち去る (leave)
    """
    items = parse(script)
    assert len(items) == 8

    # Label
    assert isinstance(items[0], ParsedLabel)
    assert items[0].display_name == "第一章"
    assert items[0].name == "chapter_1"

    # Dialogue
    assert isinstance(items[1], ParsedDialogue)
    assert items[1].speaker == "Alice"
    assert items[1].text == "こんにちは、旅人さん。"

    # Dialogue with emotion
    assert isinstance(items[2], ParsedDialogue)
    assert items[2].speaker == "Bob"
    assert items[2].emotion == "smile"
    assert items[2].text == "やあ！"

    # Narration
    assert isinstance(items[3], ParsedNarration)
    assert items[3].text == "桜の花びらが静かに風に舞っている。"

    # Append & FreshBox
    assert isinstance(items[4], ParsedAppend)
    assert items[4].text == "そして、夜が明けた。"
    assert isinstance(items[5], ParsedFreshBox)
    assert items[5].text == "新しい一日が始まる。"

    # Hook
    assert isinstance(items[6], ParsedHook)
    assert items[6].hook_name == '背景 "神社"'

    # ChoiceSet
    assert isinstance(items[7], ParsedChoiceSet)
    assert len(items[7].options) == 2
    assert items[7].options[0].text == "探索する"
    assert items[7].options[0].target == "explore"
    assert items[7].options[1].text == "立ち去る"
    assert items[7].options[1].target == "leave"


def test_parser_unicode_european_accents() -> None:
    """Accented European characters parse accurately in dialogue and narration."""
    script = """
    Eleonore (tres_emu): C'est magnifique, mon cher ami!
    Muller (frohlich): Wunderbar!
    El niño corrió hacia la cabaña.
    """
    items = parse(script)
    assert len(items) == 3

    assert isinstance(items[0], ParsedDialogue)
    assert items[0].speaker == "Eleonore"
    assert items[0].emotion == "tres_emu"
    assert items[0].text == "C'est magnifique, mon cher ami!"

    assert isinstance(items[1], ParsedDialogue)
    assert items[1].speaker == "Muller"
    assert items[1].emotion == "frohlich"
    assert items[1].text == "Wunderbar!"

    assert isinstance(items[2], ParsedNarration)
    assert items[2].text == "El niño corrió hacia la cabaña."


def test_parser_unicode_cyrillic() -> None:
    """Cyrillic screenplay text parses accurately."""
    script = "Tatyana (joy): Здравствуйте, добро пожаловать!"
    items = parse(script)
    assert len(items) == 1

    assert isinstance(items[0], ParsedDialogue)
    assert items[0].speaker == "Tatyana"
    assert items[0].emotion == "joy"
    assert items[0].text == "Здравствуйте, добро пожаловать!"


def test_parser_unicode_emoji_and_symbols() -> None:
    """Emoji and unicode symbols in dialogue, choices, and narration."""
    script = """
    A gentle breeze 🍃 whispers through the grove ✨.
    ? Attack with sword ⚔️ (attack)
    ? Defend with shield 🛡️ (defend)
    """
    items = parse(script)
    assert len(items) == 2

    assert isinstance(items[0], ParsedNarration)
    assert "🍃" in items[0].text
    assert "✨" in items[0].text

    assert isinstance(items[1], ParsedChoiceSet)
    assert "⚔️" in items[1].options[0].text
    assert "🛡️" in items[1].options[1].text


def test_parser_unicode_to_dict_to_json_roundtrip() -> None:
    """to_dict and to_json preserve unicode strings without escape corruption."""
    script = "Alice: こんにちは！ 🌸"
    items = parse(script)
    dict_data = to_dict(items)
    assert dict_data[0]["speaker"] == "Alice"
    assert dict_data[0]["text"] == "こんにちは！ 🌸"

    json_str = to_json(items)
    decoded = json.loads(json_str)
    assert decoded[0]["speaker"] == "Alice"
    assert decoded[0]["text"] == "こんにちは！ 🌸"
