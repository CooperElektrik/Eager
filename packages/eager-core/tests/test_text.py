from eager_core.text import (
    TextReveal,
    parse_text_tags,
)
from eager_core.types import Color


def test_parse_text_tags():
    raw = "Hello {b}brave{/b} {i}new{/i} {color=#ff0000}world{/color}!{w=0.5}"
    fmt = parse_text_tags(raw)

    assert fmt.plain_text == "Hello brave new world!"
    assert len(fmt.pauses) == 1
    assert fmt.pauses[0].char_index == len(fmt.plain_text)
    assert fmt.pauses[0].duration == 0.5

    # Check segments
    assert fmt.segments[0].text == "Hello "
    assert not fmt.segments[0].bold
    assert fmt.segments[1].text == "brave"
    assert fmt.segments[1].bold
    assert fmt.segments[2].text == " "
    assert fmt.segments[3].text == "new"
    assert fmt.segments[3].italic
    assert fmt.segments[5].text == "world"
    assert fmt.segments[5].color == Color(1.0, 0.0, 0.0, 1.0)


def test_text_reveal_instant():
    fmt = parse_text_tags("Instant text")
    reveal = TextReveal(fmt, chars_per_second=0)
    assert reveal.is_complete
    assert reveal.current_visible_plain_text == "Instant text"


def test_text_reveal_typewriter():
    fmt = parse_text_tags("1234567890")
    reveal = TextReveal(fmt, chars_per_second=10.0)
    assert reveal.visible_chars == 0
    assert not reveal.is_complete

    reveal.update(0.5)
    assert reveal.current_visible_plain_text == "12345"

    reveal.complete_immediately()
    assert reveal.is_complete
    assert reveal.current_visible_plain_text == "1234567890"


def test_text_reveal_initial_visible_chars():
    fmt = parse_text_tags("Hello world!")
    reveal = TextReveal(fmt, chars_per_second=10.0, initial_visible_chars=5)
    assert reveal.visible_chars == 5.0
    assert not reveal.is_complete
    assert reveal.current_visible_plain_text == "Hello"

    reveal.update(0.3)
    assert reveal.visible_chars == 8.0
    assert reveal.current_visible_plain_text == "Hello wo"

    reveal.update(0.5)
    assert reveal.is_complete
    assert reveal.current_visible_plain_text == "Hello world!"


def test_text_reveal_with_pauses():
    fmt = parse_text_tags("Part 1.{w=0.5} Part 2.")
    assert len(fmt.pauses) == 1
    assert fmt.pauses[0].char_index == 7

    reveal = TextReveal(fmt, chars_per_second=10.0, initial_visible_chars=0)
    # 0.7s at 10 cps = 7 chars, hits pause at char_index 7
    reveal.update(0.8)
    assert reveal.visible_chars == 7.0
    assert reveal.current_visible_plain_text == "Part 1."

    # While pause timer is active, visible chars do not advance
    reveal.update(0.2)
    assert reveal.visible_chars == 7.0

    # Once pause timer elapses (total 0.5s pause), reveal continues
    reveal.update(0.4)  # 0.3s remaining pause + 0.1s reveal = 1 char
    assert reveal.visible_chars == 8.0
    assert reveal.current_visible_plain_text == "Part 1. "


def test_fast_tag_parsing():
    raw = "Previously displayed text.{fast} Newly typed text."
    fmt = parse_text_tags(raw)
    assert fmt.plain_text == "Previously displayed text. Newly typed text."
    assert fmt.fast_index == len("Previously displayed text.")


def test_text_reveal_fast_tag_skips_prior_text():
    raw = "Old line.{fast}New line."
    fmt = parse_text_tags(raw)
    reveal = TextReveal(fmt, chars_per_second=10.0)

    # Visible text starts immediately at fast_index
    assert reveal.visible_chars == float(len("Old line."))
    assert reveal.current_visible_plain_text == "Old line."
    assert not reveal.is_complete

    # Advances from fast_index onwards
    reveal.update(0.3)
    assert reveal.current_visible_plain_text == "Old line.New"


def test_text_reveal_fast_tag_bypasses_prior_pauses():
    raw = "Wait here{w=1.0}.{fast} Immediate next."
    fmt = parse_text_tags(raw)
    reveal = TextReveal(fmt, chars_per_second=10.0)

    # Prior pause point is skipped because fast_index > pause.char_index
    assert reveal.visible_chars == float(len("Wait here."))
    assert reveal._pause_timer == 0.0

    reveal.update(0.5)
    assert reveal.current_visible_plain_text == "Wait here. Imme"


def test_fast_tag_at_start():
    fmt = parse_text_tags("{fast}Starts immediately.")
    assert fmt.plain_text == "Starts immediately."
    assert fmt.fast_index == 0


def test_fast_tag_at_end():
    fmt = parse_text_tags("All text already shown.{fast}")
    assert fmt.plain_text == "All text already shown."
    assert fmt.fast_index == len("All text already shown.")
    reveal = TextReveal(fmt, chars_per_second=10.0)
    assert reveal.is_complete
    assert reveal.current_visible_plain_text == "All text already shown."


def test_size_tag_multipliers_and_nesting():
    raw = "Base {size=1.5}Larger {size=2.0}Huge{/size} Back to Large{/size} Normal"
    fmt = parse_text_tags(raw)
    assert fmt.plain_text == "Base Larger Huge Back to Large Normal"

    seg_map = {s.text: s.size_mult for s in fmt.segments}
    assert seg_map["Base "] == 1.0
    assert seg_map["Larger "] == 1.5
    assert seg_map["Huge"] == 2.0
    assert seg_map[" Back to Large"] == 1.5
    assert seg_map[" Normal"] == 1.0


def test_size_tag_malformed_ignored_gracefully():
    raw = "Normal {size=invalid}Still Normal{/size} Done"
    fmt = parse_text_tags(raw)
    assert fmt.plain_text == "Normal Still Normal Done"
    for s in fmt.segments:
        assert s.size_mult == 1.0


def test_paragraph_pause_tags():
    raw = "Para 1.{p} Para 2.{p=2.5} Para 3."
    fmt = parse_text_tags(raw)

    assert fmt.plain_text == "Para 1. Para 2. Para 3."
    assert len(fmt.pauses) == 2

    assert fmt.pauses[0].char_index == 7
    assert fmt.pauses[0].duration == 1.0

    assert fmt.pauses[1].char_index == 15
    assert fmt.pauses[1].duration == 2.5


def test_paragraph_pause_typewriter_update():
    fmt = parse_text_tags("A.{p}B")
    reveal = TextReveal(fmt, chars_per_second=10.0)

    reveal.update(0.3)
    assert reveal.visible_chars == 2.0
    assert reveal.current_visible_plain_text == "A."

    reveal.update(0.5)
    assert reveal.visible_chars == 2.0

    reveal.update(0.6)
    assert reveal.visible_chars == 3.0
    assert reveal.current_visible_plain_text == "A.B"
    assert reveal.is_complete


def test_unrecognized_tags_preserved_in_text():
    raw = "Hello {unknown_tag} world and {slot:1} item."
    fmt = parse_text_tags(raw)
    assert "{unknown_tag}" in fmt.plain_text
    assert "{slot:1}" in fmt.plain_text
    assert fmt.plain_text == "Hello {unknown_tag} world and {slot:1} item."

