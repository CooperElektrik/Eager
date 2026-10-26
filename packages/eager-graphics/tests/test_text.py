"""Tests for Phase 5 text presentation, markup parsing, typewriter reveal, backlog, and skip/auto modes."""

import tempfile
import unittest
from pathlib import Path

from eager_core.text import TextReveal, parse_text_tags
from eager_runtime.backlog import Backlog
from eager_runtime.session import GameSession

SAMPLE_SCRIPT = """
## Start --- start
Alice: Hello {b}brave{/b} warrior!
Alice: Take your time.{w=0.5} Are you ready?
- Let us go.

## End --- end
Alice: Done!
"""


class TestTextPresentation(unittest.TestCase):
    def test_text_tag_parsing(self):
        raw = "Hello {b}world{/b}! This is {color=#ff0000}red{/color} and {i}italic{/i}.{w=0.5}"
        fmt = parse_text_tags(raw)
        self.assertEqual(fmt.plain_text, "Hello world! This is red and italic.")
        self.assertEqual(len(fmt.pauses), 1)
        self.assertEqual(fmt.pauses[0].duration, 0.5)

        # Check bold segment
        bold_segs = [s for s in fmt.segments if s.bold]
        self.assertEqual(len(bold_segs), 1)
        self.assertEqual(bold_segs[0].text, "world")

    def test_text_reveal_typewriter(self):
        fmt = parse_text_tags("One two three")
        reveal = TextReveal(fmt, chars_per_second=10.0)
        self.assertFalse(reveal.is_complete)
        self.assertEqual(reveal.visible_chars, 0)

        reveal.update(0.5)  # 5 characters
        self.assertAlmostEqual(reveal.visible_chars, 5.0)
        self.assertEqual(reveal.current_visible_plain_text, "One t")

        reveal.complete_immediately()
        self.assertTrue(reveal.is_complete)
        self.assertEqual(reveal.current_visible_plain_text, "One two three")

    def test_backlog(self):
        b = Backlog(max_entries=5)
        b.add("Alice", "Hello!")
        b.add(None, "The sun sets.")
        b.append_to_last("The moon rises.")

        self.assertEqual(len(b), 2)
        self.assertEqual(b.entries[0].speaker, "Alice")
        self.assertEqual(b.entries[0].text, "Hello!")
        self.assertEqual(b.entries[1].text, "The sun sets. The moon rises.")

    def test_session_skip_and_auto_modes(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".es", delete=False) as f:
            f.write(SAMPLE_SCRIPT)
            script_path = Path(f.name)

        try:
            session = GameSession(script_path)
            session.preferences.auto_forward_time = 0.5

            # Initial state
            ev = session.advance()
            assert ev is not None
            self.assertEqual(ev.type, "dialogue")
            self.assertEqual(len(session.backlog), 1)

            # Test auto mode
            session.auto_mode = True
            # First updates allow typewriter reveal to complete
            session.update(0.4)
            self.assertEqual(session.vm.beat_index, 1)
            # Post-reveal auto forward timer advances after auto_forward_time + char scaling
            session.update(0.7)
            self.assertGreater(session.vm.beat_index, 1)

            # Test skip mode
            session.preferences.skip_unseen = True
            session.skip_mode = True
            session.update(0.01)
            self.assertTrue(session.is_finished)
        finally:
            script_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
