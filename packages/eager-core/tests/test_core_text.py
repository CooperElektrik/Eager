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

