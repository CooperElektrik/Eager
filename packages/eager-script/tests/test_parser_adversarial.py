"""Adversarial stress suite probing screenplay parser edge cases and domain exceptions."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from eager_core.exceptions import (
    AudioError,
    ColorParseError,
    EagerCoreError,
    I18nError,
    StorageError,
)
from eager_core.storage import atomic_write_json
from eager_core.text import parse_text_tags
from eager_core.types import Color

from eager_script import (
    ParsedChoiceSet,
    ParsedDialogue,
    ParseError,
    parse,
    parse_iter,
    to_dict,
    to_graph,
    to_json,
    validate,
)


class TestDomainExceptionCatchingHierarchy:
    """Stress test domain exception catching and inheritance hierarchy."""

    def test_audio_error_caught_by_value_error_and_core_error(self) -> None:
        """AudioError must be caught by both ValueError and EagerCoreError."""
        caught_value_error = False
        caught_core_error = False

        try:
            raise AudioError("Path traversal", track="bgm.ogg", code=403)
        except ValueError as exc:
            caught_value_error = True
            assert isinstance(exc, EagerCoreError)
            assert getattr(exc, "track") == "bgm.ogg"  # noqa: B009
            assert getattr(exc, "code") == 403  # noqa: B009

        try:
            raise AudioError("Asset missing")
        except EagerCoreError:
            caught_core_error = True

        assert caught_value_error
        assert caught_core_error
        assert issubclass(AudioError, ValueError)
        assert issubclass(AudioError, EagerCoreError)
        assert not issubclass(AudioError, OSError)

    def test_color_parse_error_caught_by_value_error_and_core_error(self) -> None:
        """ColorParseError must be caught by both ValueError and EagerCoreError."""
        caught_value_error = False
        caught_core_error = False

        try:
            Color.from_hex("INVALID_HEX_STRING")
        except ValueError as exc:
            caught_value_error = True
            assert isinstance(exc, ColorParseError)
            assert isinstance(exc, EagerCoreError)

        try:
            Color.from_hex("#ZZZZZZ")
        except EagerCoreError:
            caught_core_error = True

        assert caught_value_error
        assert caught_core_error
        assert issubclass(ColorParseError, ValueError)
        assert issubclass(ColorParseError, EagerCoreError)
        assert not issubclass(ColorParseError, OSError)

    def test_storage_error_caught_by_os_error_and_core_error(self) -> None:
        """StorageError must be caught by both OSError and EagerCoreError."""
        caught_os_error = False
        caught_core_error = False

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.json"
            # Non-serializable payload triggers StorageError
            try:
                atomic_write_json(file_path, {"unsupported": object()})
            except OSError as exc:
                caught_os_error = True
                assert isinstance(exc, StorageError)
                assert isinstance(exc, EagerCoreError)

            try:
                atomic_write_json(file_path, {"unsupported": object()})
            except EagerCoreError:
                caught_core_error = True

        assert caught_os_error
        assert caught_core_error
        assert issubclass(StorageError, OSError)
        assert issubclass(StorageError, EagerCoreError)
        assert not issubclass(StorageError, ValueError)

    def test_i18n_error_caught_by_value_error(self) -> None:
        """I18nError must inherit from ValueError and EagerCoreError."""
        assert issubclass(I18nError, ValueError)
        assert issubclass(I18nError, EagerCoreError)
        assert not issubclass(I18nError, OSError)

    def test_exception_disjoint_separation(self) -> None:
        """Cross-checking: ValueError handlers must never catch StorageError; OSError must never catch AudioError."""
        storage_escaped = False
        try:
            try:
                raise StorageError("Disk write failed")
            except ValueError:
                pytest.fail("ValueError caught StorageError!")
        except StorageError:
            storage_escaped = True
        assert storage_escaped

        audio_escaped = False
        try:
            try:
                raise AudioError("Bad audio")
            except OSError:
                pytest.fail("OSError caught AudioError!")
        except AudioError:
            audio_escaped = True
        assert audio_escaped


class TestAdversarialScreenplayParser:
    """Stress tests on screenplay parser edge cases and adversarial inputs."""

    def test_thousands_of_empty_lines_and_line_numbering(self) -> None:
        """Parser must handle 20,000 blank lines with linear performance and exact line tracking."""
        lines = [""] * 10_000 + ["Alice: Dialogue after 10k blanks"] + [""] * 10_000 + ["Bob: Dialogue after 20k blanks"]
        script = "\n".join(lines)

        items = parse(script)
        assert len(items) == 2
        assert isinstance(items[0], ParsedDialogue)
        assert items[0].speaker == "Alice"
        assert items[0].line_number == 10_001

        assert isinstance(items[1], ParsedDialogue)
        assert items[1].speaker == "Bob"
        assert items[1].line_number == 20_002

    def test_massive_comments_and_inline_stripping(self) -> None:
        """Parser must withstand multi-megabyte comment lines and massive inline comments."""
        huge_comment = "# " + ("A" * 100_000)
        inline_comment = "Alice: Speech # " + ("B" * 100_000)

        script = f"{huge_comment}\n{inline_comment}\n"
        items = parse(script)

        assert len(items) == 1
        assert isinstance(items[0], ParsedDialogue)
        assert items[0].speaker == "Alice"
        assert items[0].text == "Speech"
        assert items[0].line_number == 2

    def test_unmatched_braces_and_malformed_tags(self) -> None:
        """Screenplay parser and text tag engine must be resilient to unmatched braces."""
        script = """
Alice: Unclosed {brace in dialogue
Narrator with lone } closing brace
Alice: {voice:unclosed_voice Hello world
Alice: {voice:} Empty voice tag
Alice: {{double}} curly braces
Alice: {color=#123456}Colored {fast}instant {size=2.0}sized {p=1.0}paused
"""
        items = parse(script)
        assert len(items) == 6

        # Check eager_core.text.parse_text_tags resilience
        fmt1 = parse_text_tags("Unclosed {bracket in string")
        assert fmt1.plain_text == "Unclosed {bracket in string"

        fmt2 = parse_text_tags("Lone } bracket in string")
        assert fmt2.plain_text == "Lone } bracket in string"

        fmt3 = parse_text_tags("Multiple {fast} {fast} tags")
        assert fmt3.fast_index == 10

        fmt4 = parse_text_tags("{size=invalid} malformed size")
        assert fmt4.plain_text == " malformed size"

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
        assert len(items) == 2  # ParsedLabel + ParsedChoiceSet
        assert isinstance(items[1], ParsedChoiceSet)

        graph = to_graph(items)
        assert len(graph.anonymous_scenes()) == depth
        assert graph.entry == "start"

    def test_unicode_identifiers_and_characters(self) -> None:
        """Screenplay DSL must support Unicode labels, choice prompts, hooks, and @character display names."""
        script = """
@character tanaka "田中 太郎" role="Sensei"
@default player_exp = 100

## 序章 --- intro_scene
tanaka: ようこそ！ (Welcome!)
? 鍛冶屋へ向かう (blacksmith)
? 街を散策する (stroll)

## 鍛冶屋 --- blacksmith
tanaka: ここは鍛冶屋だ。
~ 特殊効果(エフェクト="火花")
<<

## 散策 --- stroll
tanaka: 平和な一日だ。
<<
"""
        items = parse(script)
        assert len(items) == 12

        val_res = validate(items)
        assert val_res.is_valid

        graph = to_graph(items)
        assert "tanaka" in graph.characters
        assert graph.characters["tanaka"]["name"] == "田中 太郎"
        assert "intro_scene" in graph.nodes
        assert "blacksmith" in graph.nodes
        assert "stroll" in graph.nodes

        # Non-ASCII variable identifiers in @default and $ must raise ParseError
        with pytest.raises(ParseError, match="Invalid @default syntax"):
            parse("@default 経験値 = 100")

        with pytest.raises(ParseError, match="Invalid set statement syntax"):
            parse("$ 経験値 += 10")

    def test_exotic_jump_and_call_targets(self) -> None:
        """Jumps and subroutine calls must support spaces, numbers, and symbols."""
        script = """
## start
> target with spaces
>> subroutine 99
> 42_scene

## Explicit Label --- target with spaces
Alice: In target with spaces
<<

## Subroutine --- subroutine 99
Alice: In sub 99
<<

## 42_scene
Alice: In 42_scene
<<
"""
        items = parse(script)
        graph = to_graph(items)
        assert "target with spaces" in graph.nodes
        assert "subroutine 99" in graph.nodes
        assert "42_scene" in graph.nodes
        assert graph.is_reachable("target with spaces")
        assert graph.is_reachable("subroutine 99")
        assert graph.is_reachable("42_scene")

        val_res = validate(items)
        assert val_res.is_valid

        # Implicit labels without '---' slugify spaces to underscores
        implicit_script = """
## start
> my_scene

## My Scene
Alice: Hello
<<
"""
        imp_items = parse(implicit_script)
        imp_graph = to_graph(imp_items)
        assert "my_scene" in imp_graph.nodes
        assert imp_graph.nodes["my_scene"].display_name == "My Scene"
        assert validate(imp_items).is_valid

    def test_malformed_syntax_error_reporting(self) -> None:
        """Invalid screenplay syntax must raise descriptive ParseError exceptions with line numbers."""
        bad_cases = [
            ("##", "Empty label definition"),
            ("## ---", "Empty label display name"),
            ("## Disp ---", "Empty label identifier"),
            ("## !!!", "cannot be converted to a valid identifier"),
            (">", "Empty jump target"),
            (">>", "Empty call target"),
            ("~", "Empty hook name"),
            ("$", "Invalid set statement syntax"),
            ("$ target", "Invalid set statement syntax"),
            ("@", "Unknown directive '@'"),
            ("@invalid_directive", "Unknown directive '@invalid_directive'"),
            ("@if", "Invalid @if syntax"),
            ("@elif", "Invalid @elif syntax"),
            ("@else extra", "Invalid @else syntax"),
            ("@end extra", "Invalid @end syntax"),
            ("? Option (   )", "Empty choice target"),
            ("? Inline without block", "needs a '(target)' or an indented block"),
            ("? Both (target)\n    Alice: Body not allowed with target", "cannot combine a '(target)' with an indented block"),
            ("? Choice\n    ## Label inside choice", "Scene labels and preamble directives are not allowed"),
        ]

        for code, expected_msg in bad_cases:
            with pytest.raises(ParseError) as exc_info:
                parse(code)
            assert expected_msg in str(exc_info.value), f"Expected '{expected_msg}' in '{exc_info.value}'"
            assert exc_info.value.line_number >= 1

    def test_streaming_and_serialization_equivalence(self) -> None:
        """Streaming parse_iter and batch parse must produce identical JSON representations."""
        script = """
## test_scene
Alice: Line 1
Bob: Line 2
? Option 1 (test_scene)
? Option 2 (test_scene)
"""
        items_batch = parse(script)
        items_iter = list(parse_iter(script))

        dict_batch = to_dict(items_batch)
        dict_iter = to_dict(items_iter)
        assert dict_batch == dict_iter

        json_str = to_json(items_batch)
        loaded = json.loads(json_str)
        assert loaded == dict_batch
