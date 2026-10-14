"""Tests for standalone Eager-Script parser, validator, and CLI."""

import ast
import json
import tempfile
import unittest
from pathlib import Path

from eager_script import (
    ParsedAppend,
    ParsedCall,
    ParsedChoiceSet,
    ParsedDialogue,
    ParsedFreshBox,
    ParsedHook,
    ParsedJump,
    ParsedLabel,
    ParsedNarration,
    ParsedReturn,
    ParseError,
    parse,
    parse_iter,
    to_dict,
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
        self.assertIsInstance(items[0], ParsedLabel)
        self.assertEqual(items[0].type, "label")
        self.assertEqual(items[0].display_name, "The Clearing")
        self.assertEqual(items[0].name, "clearing_label")

        # 2. ParsedDialogue with voice tag
        self.assertIsInstance(items[1], ParsedDialogue)
        self.assertEqual(items[1].type, "dialogue")
        self.assertEqual(items[1].speaker, "Alice")
        self.assertEqual(items[1].voice, "alice_01.ogg")
        self.assertEqual(items[1].text, "Welcome to the ancient ruins!")
        self.assertIsNone(items[1].emotion)

        # 3. ParsedAppend
        self.assertIsInstance(items[2], ParsedAppend)
        self.assertEqual(items[2].type, "append")
        self.assertEqual(items[2].text, "Look at those carved pillars.")

        # 4. ParsedFreshBox
        self.assertIsInstance(items[3], ParsedFreshBox)
        self.assertEqual(items[3].type, "fresh_box")
        self.assertEqual(items[3].text, "Be careful where you step.")

        # 5. Grouped ParsedNarration
        self.assertIsInstance(items[4], ParsedNarration)
        self.assertEqual(items[4].type, "narration")
        self.assertEqual(
            items[4].text,
            "The wind howls through the stone. A cold chill runs down your spine.",
        )

        # 6. ParsedHook
        self.assertIsInstance(items[5], ParsedHook)
        self.assertEqual(items[5].type, "hook")
        self.assertEqual(items[5].hook_name, "inspect_pillars")

        # 7. ParsedChoiceSet with multiple options
        self.assertIsInstance(items[6], ParsedChoiceSet)
        self.assertEqual(items[6].type, "choice_set")
        self.assertEqual(len(items[6].options), 2)
        self.assertEqual(items[6].options[0].type, "choice_option")
        self.assertEqual(items[6].options[0].text, "Examine the glowing runes")
        self.assertEqual(items[6].options[0].target, "runes")
        self.assertEqual(items[6].options[1].text, "Turn back towards town")
        self.assertEqual(items[6].options[1].target, "exit")

        # 8. ParsedLabel
        self.assertIsInstance(items[7], ParsedLabel)
        self.assertEqual(items[7].name, "runes")

        # 9. ParsedNarration
        self.assertIsInstance(items[8], ParsedNarration)
        self.assertEqual(items[8].text, "The runes shimmer with blue light.")

        # 10. ParsedCall
        self.assertIsInstance(items[9], ParsedCall)
        self.assertEqual(items[9].type, "call")
        self.assertEqual(items[9].target, "secret_subroutine")

        # 11. ParsedJump
        self.assertIsInstance(items[10], ParsedJump)
        self.assertEqual(items[10].type, "jump")
        self.assertEqual(items[10].target, "clearing_label")

        # 12. ParsedLabel
        self.assertIsInstance(items[11], ParsedLabel)
        self.assertEqual(items[11].name, "secret_subroutine")

        # 13. ParsedDialogue without voice tag
        self.assertIsInstance(items[12], ParsedDialogue)
        self.assertEqual(items[12].speaker, "Alice")
        self.assertIsNone(items[12].voice)
        self.assertEqual(items[12].text, "A hidden compartment opened!")

        # 14. ParsedReturn
        self.assertIsInstance(items[13], ParsedReturn)
        self.assertEqual(items[13].type, "return")

        # 15. ParsedLabel
        self.assertIsInstance(items[14], ParsedLabel)
        self.assertEqual(items[14].name, "exit")

        # 16. ParsedNarration
        self.assertIsInstance(items[15], ParsedNarration)
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
        self.assertIsInstance(items[0], ParsedLabel)
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
        self.assertIsInstance(items[0], ParsedChoiceSet)
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
        self.assertEqual(items[0].text, "Hello!")
        self.assertEqual(items[1].text, "Take item #1 and color #ff0000 please.")
        self.assertEqual(items[2].speaker, "Charlie")
        self.assertEqual(items[2].text, "I code in C# every day.")

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
        self.assertEqual(items[0].text, "Here is a number #1 and a colon: not a speaker.")
        self.assertEqual(
            items[1].text,
            "- Not an append beat, but narration starting with hyphen. "
            "? Not a choice option. > Not a jump.",
        )

    def test_parser_dialogue_emotion(self) -> None:
        """Verify character dialogue can have optional emotion tag."""
        items = parse("Alice (happy): Good morning, traveler!")
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], ParsedDialogue)
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
        self.assertIsInstance(items[0], ParsedNarration)

    def test_parser_lines_starting_with_single_angle_bracket(self) -> None:
        """Verify lines starting with single < are not silently dropped."""
        items = parse("<tag> text </tag>")
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], ParsedNarration)
        self.assertEqual(items[0].text, "<tag> text </tag>")

    def test_parse_iter_equivalence(self) -> None:
        """Verify parse_iter yields exactly identical AST items as parse."""
        parsed_list = parse(SAMPLE_SCRIPT)
        iter_list = list(parse_iter(SAMPLE_SCRIPT))
        self.assertEqual(to_dict(parsed_list), to_dict(iter_list))

    def test_parse_iter_plain_mode(self) -> None:
        """Verify parse_iter works equivalently in Eager-SP plain mode."""
        plain_script = "## Chapter One\nAlice: Hello world\n> chapter_two"
        parsed_list = parse(plain_script, plain=True)
        iter_list = list(parse_iter(plain_script, plain=True))
        self.assertEqual(to_dict(parsed_list), to_dict(iter_list))


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


class TestEagerSP(unittest.TestCase):
    """Test suite for Eager-SP (--plain) parsing, validation, and CLI behavior."""

    PLAIN_SCRIPT = """
    ## The Ancient Courtyard

    Alice: Look at this place.
    It has been abandoned for centuries.

    A cold wind blows through the crumbling archway.
    The leaves dance across the stone pavers.

    ? Enter the grand hall (The Grand Hall)
    ? Walk down into the crypt (The Crypt)

    ## The Grand Hall
    Alice (whispering): Stay close.
    The shadows seem alive in here.
    > The Crypt

    ## The Crypt
    The air here is damp and thick with dust.
    """

    def test_eager_sp_parsing_and_continuation(self) -> None:
        """Verify Eager-SP parses natural titles, dialogue continuation, and auto-slug targets."""
        items = parse(self.PLAIN_SCRIPT, plain=True)

        # 1. Label
        self.assertIsInstance(items[0], ParsedLabel)
        self.assertEqual(items[0].name, "the_ancient_courtyard")
        self.assertEqual(items[0].display_name, "The Ancient Courtyard")

        # 2. Multi-line dialogue continuation without '-'
        self.assertIsInstance(items[1], ParsedDialogue)
        self.assertEqual(items[1].speaker, "Alice")
        self.assertEqual(items[1].text, "Look at this place. It has been abandoned for centuries.")
        self.assertIsNone(items[1].voice)

        # 3. Narration paragraph
        self.assertIsInstance(items[2], ParsedNarration)
        self.assertEqual(
            items[2].text,
            "A cold wind blows through the crumbling archway. The leaves dance across the stone pavers.",
        )

        # 4. Choice set with slugified natural titles
        self.assertIsInstance(items[3], ParsedChoiceSet)
        self.assertEqual(len(items[3].options), 2)
        self.assertEqual(items[3].options[0].text, "Enter the grand hall")
        self.assertEqual(items[3].options[0].target, "the_grand_hall")
        self.assertEqual(items[3].options[1].text, "Walk down into the crypt")
        self.assertEqual(items[3].options[1].target, "the_crypt")

        # 5. Label
        self.assertIsInstance(items[4], ParsedLabel)
        self.assertEqual(items[4].name, "the_grand_hall")

        # 6. Dialogue with emotion and continuation
        self.assertIsInstance(items[5], ParsedDialogue)
        self.assertEqual(items[5].speaker, "Alice")
        self.assertEqual(items[5].emotion, "whispering")
        self.assertEqual(items[5].text, "Stay close. The shadows seem alive in here.")

        # 7. Jump with natural title
        self.assertIsInstance(items[6], ParsedJump)
        self.assertEqual(items[6].target, "the_crypt")

        # 8. Label
        self.assertIsInstance(items[7], ParsedLabel)
        self.assertEqual(items[7].name, "the_crypt")

        # 9. Narration
        self.assertIsInstance(items[8], ParsedNarration)
        self.assertEqual(items[8].text, "The air here is damp and thick with dust.")

        # Validation passes cleanly
        result = validate(items, plain=True)
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.errors), 0)

    def test_plain_disallowed_syntax_raises_parse_error(self) -> None:
        """Verify engine constructs raise ParseError in Eager-SP mode."""
        # Explicit label IDs
        with self.assertRaises(ParseError) as ctx:
            parse("## Scene --- scene_id", plain=True)
        self.assertIn("Explicit label identifiers ('---') are not allowed", str(ctx.exception))

        # Append beats
        with self.assertRaises(ParseError) as ctx:
            parse("- Appended beat", plain=True)
        self.assertIn("Append beats ('-') are not supported", str(ctx.exception))

        # Fresh box beats
        with self.assertRaises(ParseError) as ctx:
            parse("/ Fresh box beat", plain=True)
        self.assertIn("Fresh box beats ('/') are not supported", str(ctx.exception))

        # Engine hooks
        with self.assertRaises(ParseError) as ctx:
            parse("~ screen_shake", plain=True)
        self.assertIn("Engine hooks ('~') are not supported", str(ctx.exception))

        # Subroutine calls
        with self.assertRaises(ParseError) as ctx:
            parse(">> sub_label", plain=True)
        self.assertIn("Subroutine calls ('>>') are not supported", str(ctx.exception))

        # Subroutine returns
        with self.assertRaises(ParseError) as ctx:
            parse("<<", plain=True)
        self.assertIn("Subroutine returns ('<<') are not supported", str(ctx.exception))

        # Voice clips
        with self.assertRaises(ParseError) as ctx:
            parse("Alice: {voice:clip.ogg} Hello", plain=True)
        self.assertIn("Voice tags ('{voice:...}') are not supported", str(ctx.exception))

    def test_plain_validator_catches_disallowed_nodes(self) -> None:
        """Verify validator flags non-plain nodes when plain=True."""
        standard_items = parse(
            "## Scene --- custom_id\nAlice: {voice:a.ogg} Hi\n~ hook", plain=False
        )
        result = validate(standard_items, plain=True)
        self.assertFalse(result.is_valid)
        error_msgs = [e.message for e in result.errors]
        self.assertTrue(any("Explicit label identifier" in m for m in error_msgs))
        self.assertTrue(any("Voice tags" in m for m in error_msgs))
        self.assertTrue(any("Engine hooks" in m for m in error_msgs))

    def test_plain_cli_check_and_parse(self) -> None:
        """Verify CLI check and parse commands with --plain flag."""
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".es", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(self.PLAIN_SCRIPT)
            tmp_path = tmp.name

        try:
            # Check with --plain
            exit_code = main(["check", "--plain", tmp_path])
            self.assertEqual(exit_code, 0)

            # Parse with --plain
            out_file = tmp_path + ".json"
            exit_code = main(["parse", "--plain", tmp_path, "-o", out_file])
            self.assertEqual(exit_code, 0)
            data = json.loads(Path(out_file).read_text(encoding="utf-8"))
            self.assertEqual(len(data), 9)
            Path(out_file).unlink(missing_ok=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        # Disallowed syntax in check --plain should fail
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".es", delete=False, encoding="utf-8"
        ) as tmp_err:
            tmp_err.write("## Start --- start_id\n~ hook\n")
            tmp_err_path = tmp_err.name

        try:
            exit_code = main(["check", "--plain", tmp_err_path])
            self.assertEqual(exit_code, 1)
        finally:
            Path(tmp_err_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
