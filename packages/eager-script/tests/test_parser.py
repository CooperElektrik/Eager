"""Tests for standalone Eager-Script parser, validator, and CLI."""

import ast
import json
import tempfile
import unittest
from pathlib import Path

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
from eager_script.cli import build_parser, main

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


class TestScreenplayParser(unittest.TestCase):
    """Test suite for ScreenplayParser."""

    def test_parser_extracts_all_ast_nodes(self) -> None:
        """Verify parser extracts all node types in correct sequential order."""
        items = parse(SAMPLE_SCRIPT)
        self.assertEqual(len(items), 16)

        # 1. ParsedLabel with explicit id
        assert isinstance(items[0], ParsedLabel)
        self.assertEqual(items[0].type, "label")
        self.assertEqual(items[0].display_name, "The Clearing")
        self.assertEqual(items[0].name, "clearing_label")

        # 2. ParsedDialogue with voice tag
        assert isinstance(items[1], ParsedDialogue)
        self.assertEqual(items[1].type, "dialogue")
        self.assertEqual(items[1].speaker, "Alice")
        self.assertEqual(items[1].voice, "alice_01.ogg")
        self.assertEqual(items[1].text, "Welcome to the ancient ruins!")
        self.assertIsNone(items[1].emotion)

        # 3. ParsedAppend
        assert isinstance(items[2], ParsedAppend)
        self.assertEqual(items[2].type, "append")
        self.assertEqual(items[2].text, "Look at those carved pillars.")

        # 4. ParsedFreshBox
        assert isinstance(items[3], ParsedFreshBox)
        self.assertEqual(items[3].type, "fresh_box")
        self.assertEqual(items[3].text, "Be careful where you step.")

        # 5. Grouped ParsedNarration
        assert isinstance(items[4], ParsedNarration)
        self.assertEqual(items[4].type, "narration")
        self.assertEqual(
            items[4].text,
            "The wind howls through the stone. A cold chill runs down your spine.",
        )

        # 6. ParsedHook
        assert isinstance(items[5], ParsedHook)
        self.assertEqual(items[5].type, "hook")
        self.assertEqual(items[5].hook_name, "inspect_pillars")

        # 7. ParsedChoiceSet with multiple options
        assert isinstance(items[6], ParsedChoiceSet)
        self.assertEqual(items[6].type, "choice_set")
        self.assertEqual(len(items[6].options), 2)
        self.assertEqual(items[6].options[0].type, "choice_option")
        self.assertEqual(items[6].options[0].text, "Examine the glowing runes")
        self.assertEqual(items[6].options[0].target, "runes")
        self.assertEqual(items[6].options[1].text, "Turn back towards town")
        self.assertEqual(items[6].options[1].target, "exit")

        # 8. ParsedLabel
        assert isinstance(items[7], ParsedLabel)
        self.assertEqual(items[7].name, "runes")

        # 9. ParsedNarration
        assert isinstance(items[8], ParsedNarration)
        self.assertEqual(items[8].text, "The runes shimmer with blue light.")

        # 10. ParsedCall
        assert isinstance(items[9], ParsedCall)
        self.assertEqual(items[9].type, "call")
        self.assertEqual(items[9].target, "secret_subroutine")

        # 11. ParsedJump
        assert isinstance(items[10], ParsedJump)
        self.assertEqual(items[10].type, "jump")
        self.assertEqual(items[10].target, "clearing_label")

        # 12. ParsedLabel
        assert isinstance(items[11], ParsedLabel)
        self.assertEqual(items[11].name, "secret_subroutine")

        # 13. ParsedDialogue without voice tag
        assert isinstance(items[12], ParsedDialogue)
        self.assertEqual(items[12].speaker, "Alice")
        self.assertIsNone(items[12].voice)
        self.assertEqual(items[12].text, "A hidden compartment opened!")

        # 14. ParsedReturn
        assert isinstance(items[13], ParsedReturn)
        self.assertEqual(items[13].type, "return")

        # 15. ParsedLabel
        assert isinstance(items[14], ParsedLabel)
        self.assertEqual(items[14].name, "exit")

        # 16. ParsedNarration
        assert isinstance(items[15], ParsedNarration)
        self.assertEqual(items[15].text, "You head back to town.")

    def test_parser_python_310_syntax_compatibility(self) -> None:
        """Verify module does not use PEP 695 type keyword (incompatible with Python 3.10/3.11)."""
        src_path = Path(__file__).resolve().parent.parent / "src" / "eager_script" / "__init__.py"
        code = src_path.read_text(encoding="utf-8")
        # ast.parse with feature_version=(3, 10) will fail if PEP 695 is used
        parsed = ast.parse(code, feature_version=(3, 10))
        self.assertIsNotNone(parsed)

    def test_parser_label_auto_slug(self) -> None:
        """Verify label without explicit id is automatically slugified."""
        items = parse("## Mysterious Cavern Entrance")
        self.assertEqual(len(items), 1)
        assert isinstance(items[0], ParsedLabel)
        self.assertEqual(items[0].display_name, "Mysterious Cavern Entrance")
        self.assertEqual(items[0].name, "mysterious_cavern_entrance")

    def test_parser_empty_label_errors(self) -> None:
        """Verify parser raises error on empty label definition or missing name/id."""
        with self.assertRaises(ParseError) as ctx:
            parse("##    ")
        self.assertIn("Empty label definition", str(ctx.exception))

        with self.assertRaises(ParseError) as ctx:
            parse("## Scene ---   ")
        self.assertIn("Empty label identifier", str(ctx.exception))

        with self.assertRaises(ParseError) as ctx:
            parse("##    --- scene_id")
        self.assertIn("Empty label display name", str(ctx.exception))

    def test_parser_empty_targets_raise_errors(self) -> None:
        """Verify jump, call, hook, and choice validate empty targets."""
        with self.assertRaises(ParseError) as ctx:
            parse(">   ")
        self.assertIn("Empty jump target", str(ctx.exception))

        with self.assertRaises(ParseError) as ctx:
            parse(">>   ")
        self.assertIn("Empty call target", str(ctx.exception))

        with self.assertRaises(ParseError) as ctx:
            parse("~   ")
        self.assertIn("Empty hook name", str(ctx.exception))

    def test_parser_invalid_choice_syntax(self) -> None:
        """Verify parser raises ParseError on malformed choice syntax."""
        with self.assertRaises(ParseError) as ctx:
            parse("? This choice is missing a target")
        self.assertIn("Invalid choice syntax", str(ctx.exception))

    def test_parser_choice_with_parentheses_in_text(self) -> None:
        """Verify choice text can contain parentheses and details."""
        items = parse("? Take (small) potion (take_potion)")
        self.assertEqual(len(items), 1)
        assert isinstance(items[0], ParsedChoiceSet)
        opt = items[0].options[0]
        self.assertEqual(opt.text, "Take (small) potion")
        self.assertEqual(opt.target, "take_potion")

    def test_parser_comment_and_hash_handling(self) -> None:
        """Verify inline and standalone comments are stripped without breaking # in dialogue."""
        script = """
        # Standalone comment
        Alice: Hello! # Inline comment
        Bob: Take item #1 and color #ff0000 please.
        Charlie: I code in C# every day.
        """
        items = parse(script)
        self.assertEqual(len(items), 3)
        d0, d1, d2 = items[0], items[1], items[2]
        assert isinstance(d0, ParsedDialogue)
        assert isinstance(d1, ParsedDialogue)
        assert isinstance(d2, ParsedDialogue)
        self.assertEqual(d0.text, "Hello!")
        self.assertEqual(d1.text, "Take item #1 and color #ff0000 please.")
        self.assertEqual(d2.speaker, "Charlie")
        self.assertEqual(d2.text, "I code in C# every day.")

    def test_parser_escaping(self) -> None:
        """Verify backslash escaping works for reserved symbols."""
        script = r"""
        Alice: Here is a number \#1 and a colon\: not a speaker.
        \- Not an append beat, but narration starting with hyphen.
        \? Not a choice option.
        \> Not a jump.
        """
        items = parse(script)
        self.assertEqual(len(items), 2)
        e0, e1 = items[0], items[1]
        assert isinstance(e0, ParsedDialogue)
        assert isinstance(e1, ParsedNarration)
        self.assertEqual(e0.text, "Here is a number #1 and a colon: not a speaker.")
        self.assertEqual(
            e1.text,
            "- Not an append beat, but narration starting with hyphen. "
            "? Not a choice option. > Not a jump.",
        )

    def test_parser_dialogue_emotion(self) -> None:
        """Verify character dialogue can have optional emotion tag."""
        items = parse("Alice (happy): Good morning, traveler!")
        self.assertEqual(len(items), 1)
        assert isinstance(items[0], ParsedDialogue)
        self.assertEqual(items[0].speaker, "Alice")
        self.assertEqual(items[0].emotion, "happy")
        self.assertEqual(items[0].text, "Good morning, traveler!")

    def test_parser_non_dialogue_colons(self) -> None:
        """Verify lines with colons in timestamps or URLs are not treated as character dialogue."""
        script = """
        10:30 PM: the lights went out suddenly.
        Check http://example.com for more info.
        """
        items = parse(script)
        self.assertEqual(len(items), 1)
        assert isinstance(items[0], ParsedNarration)

    def test_parser_lines_starting_with_single_angle_bracket(self) -> None:
        """Verify lines starting with single < are not silently dropped."""
        items = parse("<tag> text </tag>")
        self.assertEqual(len(items), 1)
        assert isinstance(items[0], ParsedNarration)
        self.assertEqual(items[0].text, "<tag> text </tag>")

    def test_parse_iter_equivalence(self) -> None:
        """Verify parse_iter yields exactly identical AST items as parse."""
        parsed_list = parse(SAMPLE_SCRIPT)
        iter_list = list(parse_iter(SAMPLE_SCRIPT))
        self.assertEqual(to_dict(parsed_list), to_dict(iter_list))

    def test_character_quoted_attributes_with_spaces(self) -> None:
        script = '@character hero "Hero" title="The Great Magician" color="#ff0000" role="Protagonist and Leader"'
        items = list(parse_iter(script))
        self.assertEqual(len(items), 1)
        char = items[0]
        assert isinstance(char, ParsedCharacter)
        self.assertEqual(char.id, "hero")
        self.assertEqual(char.name, "Hero")
        attr_dict = dict(char.attrs)
        self.assertEqual(attr_dict.get("title"), "The Great Magician")
        self.assertEqual(attr_dict.get("color"), "#ff0000")
        self.assertEqual(attr_dict.get("role"), "Protagonist and Leader")




class TestSerialization(unittest.TestCase):
    """Test AST dictionary and JSON serialization."""

    def test_to_dict_and_to_json(self) -> None:
        script = """
        ## Start --- start_label
        Alice: Hello!
        > start_label
        """
        items = parse(script)
        dicts = to_dict(items)
        self.assertEqual(len(dicts), 3)
        self.assertEqual(dicts[0]["type"], "label")
        self.assertEqual(dicts[0]["name"], "start_label")
        self.assertEqual(dicts[1]["type"], "dialogue")
        self.assertEqual(dicts[1]["speaker"], "Alice")
        self.assertEqual(dicts[2]["type"], "jump")
        self.assertEqual(dicts[2]["target"], "start_label")

        json_str = to_json(items)
        loaded = json.loads(json_str)
        self.assertEqual(loaded, dicts)


class TestValidator(unittest.TestCase):
    """Test script link and structure validation."""

    def test_valid_script_passes_validation(self) -> None:
        items = parse(SAMPLE_SCRIPT)
        result = validate(items)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)

    def test_duplicate_label_error(self) -> None:
        script = """
        ## Scene One --- scene1
        Alice: Hello
        ## Scene One Again --- scene1
        Alice: Bye
        """
        items = parse(script)
        result = validate(items)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Duplicate label" in err.message for err in result.errors))

    def test_undefined_target_error(self) -> None:
        script = """
        ## Start --- start
        > nonexistent_target
        ? Option (missing_label)
        """
        items = parse(script)
        result = validate(items)
        self.assertFalse(result.is_valid)
        self.assertEqual(len(result.errors), 2)
        self.assertTrue(any("nonexistent_target" in err.message for err in result.errors))
        self.assertTrue(any("missing_label" in err.message for err in result.errors))

    def test_unreturned_call_warning(self) -> None:
        script = """
        ## Start --- start
        >> my_subroutine
        ## Sub --- my_subroutine
        Alice: Done.
        """
        items = parse(script)
        result = validate(items)
        self.assertTrue(result.is_valid)  # Warnings do not invalidate
        self.assertEqual(len(result.warnings), 1)
        self.assertIn("Subroutine call", result.warnings[0].message)

    def test_cyclical_traversal_warning(self) -> None:
        # 2-node unconditional loop
        script = """
        ## Intro --- intro
        Alice: Hello
        > tiny_slug

        ## Tiny Slug --- tiny_slug
        Alice: World
        > intro
        """
        items = parse(script)
        result = validate(items)
        self.assertTrue(result.is_valid)
        cycle_warnings = [w for w in result.warnings if "Cyclical traversal detected" in w.message]
        self.assertEqual(len(cycle_warnings), 1)
        self.assertIn("intro -> tiny_slug -> intro", cycle_warnings[0].message)
        self.assertEqual(cycle_warnings[0].level, "warning")

        # Self-loop
        script_self = """
        ## Intro --- intro
        Alice: Hello
        > intro
        """
        items_self = parse(script_self)
        result_self = validate(items_self)
        cycle_self = [w for w in result_self.warnings if "Cyclical traversal detected" in w.message]
        self.assertEqual(len(cycle_self), 1)
        self.assertIn("intro -> intro", cycle_self[0].message)

    def test_branching_loop_with_choices_not_flagged(self) -> None:
        # Game hub looping back via player choices should not be flagged as unconditional cycle
        script = """
        ## Town Square --- town
        Alice: What do you want to do?
        ? Enter tavern (tavern)
        ? Depart town (leave)

        ## Tavern --- tavern
        Bartender: Welcome to the tavern!
        > town

        ## Departure --- leave
        You walk away into the sunset.
        """
        items = parse(script)
        result = validate(items)
        self.assertTrue(result.is_valid)
        cycle_warnings = [w for w in result.warnings if "Cyclical traversal detected" in w.message]
        self.assertEqual(len(cycle_warnings), 0)

    def test_unreachable_statements_within_scene(self) -> None:
        # Code after jump
        script_jump = """
        ## Start --- start
        Alice: Hello
        > finish
        Bob: This is unreachable!

        ## Finish --- finish
        Alice: Done.
        """
        result = validate(parse(script_jump))
        unreachable = [
            w for w in result.warnings if "Unreachable code: statement after jump" in w.message
        ]
        self.assertEqual(len(unreachable), 1)

        # Code after return
        script_ret = """
        ## Sub --- sub
        Alice: Inside subroutine
        <<
        Bob: This is unreachable after return!
        """
        result_ret = validate(parse(script_ret))
        unreachable_ret = [
            w
            for w in result_ret.warnings
            if "Unreachable code: statement after return" in w.message
        ]
        self.assertEqual(len(unreachable_ret), 1)

        # Code after choice menu
        script_choice = """
        ## Choices --- choices
        ? Option 1 (finish)
        ? Option 2 (finish)
        Alice: This is unreachable after choice menu!

        ## Finish --- finish
        """
        result_choice = validate(parse(script_choice))
        unreachable_choice = [
            w
            for w in result_choice.warnings
            if "Unreachable code: statement after choice menu" in w.message
        ]
        self.assertEqual(len(unreachable_choice), 1)

    def test_unreachable_scene_cluster(self) -> None:
        # Scenes referencing each other but disconnected from script entry point
        script = """
        ## Main --- main
        Alice: Welcome to main story
        > finish

        ## Finish --- finish
        Alice: Goodbye

        ## Island A --- island_a
        Alice: Secret island A
        > island_b

        ## Island B --- island_b
        Alice: Secret island B
        > island_a
        """
        result = validate(parse(script))
        unreachable_scenes = [
            w for w in result.warnings if "unreachable from the script entry point" in w.message
        ]
        self.assertEqual(len(unreachable_scenes), 2)
        warned_labels = {w.message for w in unreachable_scenes}
        self.assertTrue(any("island_a" in msg for msg in warned_labels))
        self.assertTrue(any("island_b" in msg for msg in warned_labels))


class TestCLI(unittest.TestCase):
    """Test CLI argument parsing and execution."""

    def test_cli_version(self) -> None:
        parser = build_parser()
        self.assertIsNotNone(parser)

    def test_cli_check_and_parse(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".es", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(SAMPLE_SCRIPT)
            tmp_path = tmp.name

        try:
            # Test check
            exit_code = main(["check", tmp_path])
            self.assertEqual(exit_code, 0)

            # Test parse to file
            out_file = tmp_path + ".json"
            exit_code = main(["parse", tmp_path, "-o", out_file])
            self.assertEqual(exit_code, 0)
            data = json.loads(Path(out_file).read_text(encoding="utf-8"))
            self.assertEqual(len(data), 16)
            Path(out_file).unlink(missing_ok=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)





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


class TestInlineChoiceBlocks(unittest.TestCase):
    """Test suite for inline choice blocks that lower into anonymous scenes."""

    def test_parser_attaches_indented_block_to_option(self) -> None:
        items = parse(INLINE_CHOICE_SCRIPT)
        self.assertEqual([item.type for item in items], ["label", "dialogue", "choice_set", "dialogue"])

        choice_set = items[2]
        assert isinstance(choice_set, ParsedChoiceSet)
        self.assertEqual(len(choice_set.options), 2)

        first = choice_set.options[0]
        self.assertEqual(first.text, "Order an ale")
        self.assertIsNone(first.target)
        self.assertTrue(first.is_inline)
        self.assertEqual(len(first.body), 2)
        assert isinstance(first.body[0], ParsedSet)
        self.assertEqual(first.body[0].target, "gold")
        assert isinstance(first.body[1], ParsedDialogue)
        self.assertEqual(first.body[1].text, "Coming right up.")

        second = choice_set.options[1]
        self.assertIsNone(second.target)
        self.assertEqual(len(second.body), 1)
        assert isinstance(second.body[0], ParsedDialogue)

    def test_parser_preserves_source_line_numbers(self) -> None:
        items = parse(INLINE_CHOICE_SCRIPT)
        choice_set = items[2]
        assert isinstance(choice_set, ParsedChoiceSet)
        first = choice_set.options[0]
        self.assertEqual(first.line_number, 4)
        self.assertEqual(first.body[0].line_number, 5)
        self.assertEqual(first.body[1].line_number, 6)
        self.assertEqual(choice_set.options[1].line_number, 7)

    def test_parser_nested_inline_blocks(self) -> None:
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
        self.assertEqual([item.type for item in outer.body], ["dialogue", "choice_set", "dialogue"])
        nested_cs = outer.body[1]
        assert isinstance(nested_cs, ParsedChoiceSet)
        nested_option = nested_cs.options[0]
        self.assertEqual(nested_option.text, "Nested")
        self.assertIsNone(nested_option.target)
        self.assertEqual([item.type for item in nested_option.body], ["dialogue"])
        nested_d = nested_option.body[0]
        assert isinstance(nested_d, ParsedDialogue)
        self.assertEqual(nested_d.text, "deep")

    def test_inline_option_with_condition(self) -> None:
        items = parse("""## S --- s
? Sneak in if has_key
    Narrator: You slip inside.
""")
        cs = items[1]
        assert isinstance(cs, ParsedChoiceSet)
        opt = cs.options[0]
        self.assertEqual(opt.text, "Sneak in")
        self.assertEqual(opt.condition, "has_key")
        self.assertEqual(len(opt.body), 1)

    def test_target_and_block_combination_rejected(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse("## A --- a\n? Go (somewhere)\n    Alice: hi\n")
        self.assertIn("cannot combine", str(ctx.exception))

    def test_targetless_option_without_block_rejected(self) -> None:
        with self.assertRaises(ParseError) as ctx:
            parse("## A --- a\n? Just some text\n")
        self.assertIn("Invalid choice syntax", str(ctx.exception))

    def test_parse_iter_matches_parse_for_inline_blocks(self) -> None:
        self.assertEqual(
            to_dict(parse(INLINE_CHOICE_SCRIPT)),
            to_dict(list(parse_iter(INLINE_CHOICE_SCRIPT))),
        )

    def test_to_dict_serializes_inline_body(self) -> None:
        dicts = to_dict(parse(INLINE_CHOICE_SCRIPT))
        choice_set = next(d for d in dicts if d["type"] == "choice_set")
        first = choice_set["options"][0]
        self.assertIsNone(first["target"])
        self.assertEqual(first["body"][0]["type"], "set")
        self.assertEqual(choice_set["options"][1]["body"][0]["type"], "dialogue")
        # Round-trips through JSON
        self.assertEqual(json.loads(to_json(parse(INLINE_CHOICE_SCRIPT))), dicts)

    def test_validator_accepts_inline_blocks_and_reachable_continuation(self) -> None:
        result = validate(parse(INLINE_CHOICE_SCRIPT))
        self.assertTrue(result.is_valid)
        unreachable = [w for w in result.warnings if "Unreachable" in w.message]
        self.assertEqual(unreachable, [])

    def test_validator_checks_targets_inside_inline_blocks(self) -> None:
        result = validate(parse("## A --- a\n? Go\n    > nowhere\n"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("nowhere" in err.message for err in result.errors))

    def test_validator_rejects_invalid_expression_inside_block(self) -> None:
        result = validate(parse("## A --- a\n? Go\n    $ x = 1 +\n"))
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Invalid expression" in err.message for err in result.errors))

    def test_inline_block_with_comments_and_blank_lines(self) -> None:
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
        self.assertEqual(len(choice_set.options), 2)
        first = choice_set.options[0]
        self.assertEqual(len(first.body), 2)
        self.assertEqual(first.body[0].type, "set")
        self.assertEqual(first.body[1].type, "dialogue")

    def test_inline_block_with_tabs_and_spaces(self) -> None:
        script = "## A --- a\n? Choice\n    $ a = 1\n\t$ b = 2\n"
        items = parse(script)
        cs = items[1]
        assert isinstance(cs, ParsedChoiceSet)
        opt = cs.options[0]
        self.assertEqual(len(opt.body), 2)
        b0, b1 = opt.body[0], opt.body[1]
        assert isinstance(b0, ParsedSet)
        self.assertEqual(b0.target, "a")
        assert isinstance(b1, ParsedSet)
        self.assertEqual(b1.target, "b")


    def test_validator_rejects_unclosed_if_in_inline_block(self) -> None:
        items = parse("## A --- a\n? Go\n    @if cond\n        Alice: hi\n")
        result = validate(items)
        self.assertFalse(result.is_valid)
        self.assertTrue(any("Unclosed @if block" in err.message for err in result.errors))

    def test_deeply_nested_inline_choices(self) -> None:
        """Parser and scene lowering must cleanly handle deeply nested choice trees (up to depth 50)."""
        depth = 50
        lines = ["## start"]
        for d in range(depth):
            indent = "    " * d
            lines.append(f"{indent}? Option depth {d}")
            lines.append(f"{indent}    Alice: Dialogue at level {d}")

        script = "\n".join(lines)
        items = parse(script)
        self.assertEqual(len(items), 2)  # ParsedLabel + ParsedChoiceSet
        self.assertIsInstance(items[1], ParsedChoiceSet)

        graph = to_graph(items)
        self.assertEqual(len(graph.anonymous_scenes()), depth)
        self.assertEqual(graph.entry, "start")



class TestParserScreenplayBoundaries(unittest.TestCase):
    """Test suite covering empty lines, unmatched braces, edge case jumps, and unicode."""

    # 1. Empty Screenplay Lines
    def test_parser_empty_string(self) -> None:
        """Parsing empty string produces empty AST list."""
        self.assertEqual(parse(""), [])

    def test_parser_whitespace_lines_only(self) -> None:
        """Parsing lines with spaces, tabs, and newlines produces empty list."""
        self.assertEqual(parse("   \n\n\t  \n   \r\n"), [])

    def test_parser_consecutive_blank_lines_flush_properly(self) -> None:
        """Multiple consecutive empty lines between statements flush narration properly."""
        script = """
        Line 1 narration.


        Line 2 narration.



        Alice: Hello!
        """
        items = parse(script)
        self.assertEqual(len(items), 3)

        assert isinstance(items[0], ParsedNarration)
        self.assertEqual(items[0].text, "Line 1 narration.")

        assert isinstance(items[1], ParsedNarration)
        self.assertEqual(items[1].text, "Line 2 narration.")

        assert isinstance(items[2], ParsedDialogue)
        self.assertEqual(items[2].speaker, "Alice")
        self.assertEqual(items[2].text, "Hello!")

    # 2. Unmatched Braces
    def test_parser_unclosed_voice_tag_handled_gracefully(self) -> None:
        """Unclosed {voice: tag does not crash parser; treated as regular text."""
        script = "Alice: {voice:alice_01 Unclosed voice tag line"
        items = parse(script)
        self.assertEqual(len(items), 1)

        assert isinstance(items[0], ParsedDialogue)
        self.assertEqual(items[0].speaker, "Alice")
        self.assertIsNone(items[0].voice)
        self.assertEqual(items[0].text, "{voice:alice_01 Unclosed voice tag line")

    def test_parser_unclosed_inline_markup_tags(self) -> None:
        """Unclosed formatting braces in dialogue and narration parse without error."""
        script = """
        Alice: Hello {b bold without closing brace
        Bob: Another {color=#ff0000 unclosed color
        A chill {size=20 runs down the spine.
        """
        items = parse(script)
        self.assertEqual(len(items), 3)

        assert isinstance(items[0], ParsedDialogue)
        self.assertEqual(items[0].text, "Hello {b bold without closing brace")

        assert isinstance(items[1], ParsedDialogue)
        self.assertEqual(items[1].text, "Another {color=#ff0000 unclosed color")

        assert isinstance(items[2], ParsedNarration)
        self.assertEqual(items[2].text, "A chill {size=20 runs down the spine.")

    def test_parser_lone_closing_braces_in_dialogue(self) -> None:
        """Dialogue with lone closing braces parses verbatim."""
        script = "Alice: Closing brace } without open { or matched {}"
        items = parse(script)
        self.assertEqual(len(items), 1)

        assert isinstance(items[0], ParsedDialogue)
        self.assertEqual(items[0].text, "Closing brace } without open { or matched {}")

    # 3. Edge Case Jump Tags
    def test_parser_bare_jump_raises_parse_error(self) -> None:
        """Bare '>' without target raises ParseError."""
        with self.assertRaises(ParseError) as ctx:
            parse(">")
        self.assertIn("Empty jump target", str(ctx.exception))

        with self.assertRaises(ParseError) as ctx:
            parse(">\n")
        self.assertIn("Empty jump target", str(ctx.exception))

    def test_parser_bare_call_raises_parse_error(self) -> None:
        """Bare '>>' without target raises ParseError."""
        with self.assertRaises(ParseError) as ctx:
            parse(">>")
        self.assertIn("Empty call target", str(ctx.exception))

    def test_parser_bare_hook_raises_parse_error(self) -> None:
        """Bare '~' without hook name raises ParseError."""
        with self.assertRaises(ParseError) as ctx:
            parse("~")
        self.assertIn("Empty hook name", str(ctx.exception))

    def test_parser_jump_with_special_characters_and_numbers(self) -> None:
        """Jump targets with hyphens, underscores, dots, and numbers parse cleanly."""
        script = """
        > scene-part-2
        > 100_intro_scene
        > chapter.1.sub
        """
        items = parse(script)
        self.assertEqual(len(items), 3)

        assert isinstance(items[0], ParsedJump)
        self.assertEqual(items[0].target, "scene-part-2")

        assert isinstance(items[1], ParsedJump)
        self.assertEqual(items[1].target, "100_intro_scene")

        assert isinstance(items[2], ParsedJump)
        self.assertEqual(items[2].target, "chapter.1.sub")

    def test_parser_jump_with_inline_comment(self) -> None:
        """Jump statement followed by inline comment strips comment cleanly."""
        script = "> target_scene # jump to target scene"
        items = parse(script)
        self.assertEqual(len(items), 1)

        assert isinstance(items[0], ParsedJump)
        self.assertEqual(items[0].target, "target_scene")

    def test_parser_return_statement(self) -> None:
        """'<<' parses as ParsedReturn node."""
        script = "<<"
        items = parse(script)
        self.assertEqual(len(items), 1)

        assert isinstance(items[0], ParsedReturn)

    # 4. Unicode Screenplay Characters
    def test_parser_unicode_cjk_characters(self) -> None:
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
        self.assertEqual(len(items), 8)

        # Label
        assert isinstance(items[0], ParsedLabel)
        self.assertEqual(items[0].display_name, "第一章")
        self.assertEqual(items[0].name, "chapter_1")

        # Dialogue
        assert isinstance(items[1], ParsedDialogue)
        self.assertEqual(items[1].speaker, "Alice")
        self.assertEqual(items[1].text, "こんにちは、旅人さん。")

        # Dialogue with emotion
        assert isinstance(items[2], ParsedDialogue)
        self.assertEqual(items[2].speaker, "Bob")
        self.assertEqual(items[2].emotion, "smile")
        self.assertEqual(items[2].text, "やあ！")

        # Narration
        assert isinstance(items[3], ParsedNarration)
        self.assertEqual(items[3].text, "桜の花びらが静かに風に舞っている。")

        # Append & FreshBox
        assert isinstance(items[4], ParsedAppend)
        self.assertEqual(items[4].text, "そして、夜が明けた。")
        assert isinstance(items[5], ParsedFreshBox)
        self.assertEqual(items[5].text, "新しい一日が始まる。")

        # Hook
        assert isinstance(items[6], ParsedHook)
        self.assertEqual(items[6].hook_name, '背景 "神社"')

        # ChoiceSet
        assert isinstance(items[7], ParsedChoiceSet)
        self.assertEqual(len(items[7].options), 2)
        self.assertEqual(items[7].options[0].text, "探索する")
        self.assertEqual(items[7].options[0].target, "explore")
        self.assertEqual(items[7].options[1].text, "立ち去る")
        self.assertEqual(items[7].options[1].target, "leave")

    def test_parser_unicode_european_accents(self) -> None:
        """Accented European characters parse accurately in dialogue and narration."""
        script = """
        Eleonore (tres_emu): C'est magnifique, mon cher ami!
        Muller (frohlich): Wunderbar!
        El niño corrió hacia la cabaña.
        """
        items = parse(script)
        self.assertEqual(len(items), 3)

        assert isinstance(items[0], ParsedDialogue)
        self.assertEqual(items[0].speaker, "Eleonore")
        self.assertEqual(items[0].emotion, "tres_emu")
        self.assertEqual(items[0].text, "C'est magnifique, mon cher ami!")

        assert isinstance(items[1], ParsedDialogue)
        self.assertEqual(items[1].speaker, "Muller")
        self.assertEqual(items[1].emotion, "frohlich")
        self.assertEqual(items[1].text, "Wunderbar!")

        assert isinstance(items[2], ParsedNarration)
        self.assertEqual(items[2].text, "El niño corrió hacia la cabaña.")

    def test_parser_unicode_cyrillic(self) -> None:
        """Cyrillic screenplay text parses accurately."""
        script = "Tatyana (joy): Здравствуйте, добро пожаловать!"
        items = parse(script)
        self.assertEqual(len(items), 1)

        assert isinstance(items[0], ParsedDialogue)
        self.assertEqual(items[0].speaker, "Tatyana")
        self.assertEqual(items[0].emotion, "joy")
        self.assertEqual(items[0].text, "Здравствуйте, добро пожаловать!")

    def test_parser_unicode_emoji_and_symbols(self) -> None:
        """Emoji and unicode symbols in dialogue, choices, and narration."""
        script = """
        A gentle breeze 🍃 whispers through the grove ✨.
        ? Attack with sword ⚔️ (attack)
        ? Defend with shield 🛡️ (defend)
        """
        items = parse(script)
        self.assertEqual(len(items), 2)

        assert isinstance(items[0], ParsedNarration)
        self.assertIn("🍃", items[0].text)
        self.assertIn("✨", items[0].text)

        assert isinstance(items[1], ParsedChoiceSet)
        self.assertIn("⚔️", items[1].options[0].text)
        self.assertIn("🛡️", items[1].options[1].text)

    def test_parser_unicode_to_dict_to_json_roundtrip(self) -> None:
        """to_dict and to_json preserve unicode strings without escape corruption."""
        script = "Alice: こんにちは！ 🌸"
        items = parse(script)
        dict_data = to_dict(items)
        self.assertEqual(dict_data[0]["speaker"], "Alice")
        self.assertEqual(dict_data[0]["text"], "こんにちは！ 🌸")

        json_str = to_json(items)
        decoded = json.loads(json_str)
        self.assertEqual(decoded[0]["speaker"], "Alice")
        self.assertEqual(decoded[0]["text"], "こんにちは！ 🌸")


if __name__ == "__main__":
    unittest.main()
