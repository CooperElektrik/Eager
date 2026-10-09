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
