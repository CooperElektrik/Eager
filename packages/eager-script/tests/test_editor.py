"""Unit tests for Eager-Script terminal text editor components."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from eager_script.cli import build_parser, main
from eager_script.editor import is_editor_available
from eager_script.editor.buffer import TextBuffer
from eager_script.editor.highlighter import EagerSHighlighter
from eager_script.editor.outline import SceneEntry, extract_outline
from eager_script.editor.validator_cache import ValidatorCache

SAMPLE_ES = """## Intro --- scene_intro
Narrator: The story begins.
? Enter cave (cave)
? Walk away (forest)

## The Cave --- cave
Alice (nervous): {voice:cave.ogg} It is dark in here.
- Can you see anything?
/ Suddenly, a torch lights up.
~ play_torch_sfx
> scene_intro

## Forest --- forest
<<
"""


class DummyTerm:
    """Mock Terminal providing Blessed styling methods for headless test execution."""

    width = 80
    height = 24

    def __getattr__(self, name: str):
        def style_fn(s: str) -> str:
            return f"<{name}>{s}</{name}>"

        return style_fn

    def length(self, s: str) -> int:
        return len(s)

    def move_xy(self, x: int, y: int) -> str:
        return f"\033[{y};{x}H"

    @property
    def clear_eol(self) -> str:
        return "\033[K"

    import contextlib

    @contextlib.contextmanager
    def cbreak(self):
        yield

    @contextlib.contextmanager
    def raw(self):
        yield

    @contextlib.contextmanager
    def fullscreen(self):
        yield


class TestTextBuffer(unittest.TestCase):
    """Test editing buffer operations, cursor tracking, history, and search."""

    def test_buffer_initialization(self) -> None:
        buf = TextBuffer()
        self.assertEqual(buf.line_count, 1)
        self.assertEqual(buf.lines, [""])
        self.assertEqual(buf.cursor_row, 0)
        self.assertEqual(buf.cursor_col, 0)
        self.assertFalse(buf.dirty)

    def test_insert_char_and_movement(self) -> None:
        buf = TextBuffer()
        buf.insert_char("H")
        buf.insert_char("i")
        self.assertEqual(buf.current_line, "Hi")
        self.assertEqual(buf.cursor_col, 2)
        self.assertTrue(buf.dirty)

        buf.move_left()
        self.assertEqual(buf.cursor_col, 1)
        buf.move_right()
        self.assertEqual(buf.cursor_col, 2)
        buf.move_to_line_start()
        self.assertEqual(buf.cursor_col, 0)
        buf.move_to_line_end()
        self.assertEqual(buf.cursor_col, 2)

    def test_insert_newline_and_backspace(self) -> None:
        buf = TextBuffer()
        buf.insert_char("Hello World")
        buf.cursor_col = 5
        buf.insert_newline()

        self.assertEqual(buf.line_count, 2)
        self.assertEqual(buf.lines[0], "Hello")
        self.assertEqual(buf.lines[1], " World")
        self.assertEqual(buf.cursor_row, 1)
        self.assertEqual(buf.cursor_col, 0)

        # Backspace at start of line joins with previous line
        buf.delete_backspace()
        self.assertEqual(buf.line_count, 1)
        self.assertEqual(buf.lines[0], "Hello World")
        self.assertEqual(buf.cursor_row, 0)
        self.assertEqual(buf.cursor_col, 5)

        # Backspace within line
        buf.delete_backspace()
        self.assertEqual(buf.lines[0], "Hell World")
        self.assertEqual(buf.cursor_col, 4)

    def test_delete_forward(self) -> None:
        buf = TextBuffer(lines=["Line 1", "Line 2"])
        buf.cursor_row = 0
        buf.cursor_col = 0
        buf.delete_forward()
        self.assertEqual(buf.lines[0], "ine 1")

        # Delete at end of line joins lines
        buf.cursor_col = len(buf.lines[0])
        buf.delete_forward()
        self.assertEqual(buf.line_count, 1)
        self.assertEqual(buf.lines[0], "ine 1Line 2")

    def test_delete_line(self) -> None:
        buf = TextBuffer(lines=["First", "Second", "Third"])
        buf.cursor_row = 1
        buf.delete_line()
        self.assertEqual(buf.line_count, 2)
        self.assertEqual(buf.lines, ["First", "Third"])

    def test_insert_tab(self) -> None:
        buf = TextBuffer()
        buf.insert_tab(4)
        self.assertEqual(buf.current_line, "    ")
        self.assertEqual(buf.cursor_col, 4)

    def test_undo_and_redo(self) -> None:
        buf = TextBuffer()
        buf.insert_char("A")
        buf.insert_char("B")
        self.assertEqual(buf.current_line, "AB")

        self.assertTrue(buf.undo())
        self.assertEqual(buf.current_line, "A")

        self.assertTrue(buf.undo())
        self.assertEqual(buf.current_line, "")

        self.assertFalse(buf.undo())

        self.assertTrue(buf.redo())
        self.assertEqual(buf.current_line, "A")

        self.assertTrue(buf.redo())
        self.assertEqual(buf.current_line, "AB")

    def test_find_next(self) -> None:
        buf = TextBuffer(lines=["Apple Banana", "Cherry Date", "Banana Fig"])
        buf.cursor_row = 0
        buf.cursor_col = 0

        # Find "Banana" starting from cursor
        match = buf.find_next("Banana")
        self.assertEqual(match, (0, 6))
        assert match is not None

        # Move past first match and find next
        buf.cursor_row, buf.cursor_col = match
        match2 = buf.find_next("Banana")
        self.assertEqual(match2, (2, 0))
        assert match2 is not None

        # Wrap around
        buf.cursor_row, buf.cursor_col = match2
        match3 = buf.find_next("Banana")
        self.assertEqual(match3, (0, 6))

        # Not found
        self.assertIsNone(buf.find_next("Nonexistent"))

    def test_save_and_load(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w+", suffix=".es", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(SAMPLE_ES)
            tmp_path = Path(tmp.name)

        try:
            buf = TextBuffer()
            buf.load_file(tmp_path)
            self.assertEqual(buf.line_count, len(SAMPLE_ES.splitlines()))
            self.assertFalse(buf.dirty)

            buf.cursor_row = 0
            buf.insert_char("# Edit\n")
            self.assertTrue(buf.dirty)

            buf.save_file()
            self.assertFalse(buf.dirty)

            content = tmp_path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("# Edit"))
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_read_only_protection(self) -> None:
        buf = TextBuffer(lines=["Hello"], read_only=True)
        buf.insert_char("X")
        buf.insert_newline()
        buf.delete_backspace()
        buf.delete_forward()
        self.assertEqual(buf.lines, ["Hello"])
        self.assertFalse(buf.dirty)


class TestHighlighter(unittest.TestCase):
    """Test syntax highlighting for all Eager-Script DSL constructs."""

    def setUp(self) -> None:
        self.highlighter = EagerSHighlighter(DummyTerm())

    def test_highlight_label(self) -> None:
        out1 = self.highlighter.highlight_line("## Courtyard --- court")
        self.assertIn("<bold_magenta>##</bold_magenta>", out1)
        self.assertIn("<bold_white>Courtyard</bold_white>", out1)
        self.assertIn("<bold_cyan>court</bold_cyan>", out1)

        out2 = self.highlighter.highlight_line("## Great Hall")
        self.assertIn("<bold_magenta>##</bold_magenta>", out2)
        self.assertIn("<bold_white>Great Hall</bold_white>", out2)

    def test_highlight_dialogue(self) -> None:
        out = self.highlighter.highlight_line("Alice: Hello!")
        self.assertIn("<bold_yellow>Alice</bold_yellow>", out)
        self.assertIn("<white>Hello!</white>", out)

    def test_highlight_dialogue_with_emotion_and_voice(self) -> None:
        out = self.highlighter.highlight_line("Alice (happy): {voice:greet.ogg} Hello!")
        self.assertIn("<cyan>happy</cyan>", out)
        self.assertIn("<magenta>{voice:greet.ogg}</magenta>", out)
        self.assertIn("<white>Hello!</white>", out)

    def test_highlight_append_and_fresh_box(self) -> None:
        out_append = self.highlighter.highlight_line("- Continued text")
        self.assertIn("<bold_green>-</bold_green>", out_append)

        out_fresh = self.highlighter.highlight_line("/ New box text")
        self.assertIn("<bold_cyan>/</bold_cyan>", out_fresh)

    def test_highlight_choice(self) -> None:
        out = self.highlighter.highlight_line("? Take key (key_pickup)")
        self.assertIn("<bold_green>?</bold_green>", out)
        self.assertIn("<green>Take key</green>", out)
        self.assertIn("<bold_cyan>key_pickup</bold_cyan>", out)

    def test_highlight_jump_call_return_hook(self) -> None:
        out_jump = self.highlighter.highlight_line("> target_id")
        self.assertIn("<bold_red>></bold_red>", out_jump)

        out_call = self.highlighter.highlight_line(">> sub_label")
        self.assertIn("<bold_blue>>></bold_blue>", out_call)

        out_ret = self.highlighter.highlight_line("<<")
        self.assertIn("<bold_blue><<</bold_blue>", out_ret)

        out_hook = self.highlighter.highlight_line("~ shake_camera")
        self.assertIn("<bold_magenta>~</bold_magenta>", out_hook)

    def test_highlight_comment(self) -> None:
        out = self.highlighter.highlight_line("# This is a comment")
        self.assertIn("<bright_black># This is a comment</bright_black>", out)

        out_inline = self.highlighter.highlight_line("Alice: Hi # greeting")
        self.assertIn("<bright_black> # greeting</bright_black>", out_inline)


class TestValidatorCache(unittest.TestCase):
    """Test live buffer validation cache."""

    def test_valid_script_cache(self) -> None:
        cache = ValidatorCache()
        cache.update(SAMPLE_ES)
        self.assertTrue(cache.is_valid)
        self.assertIsNone(cache.parse_error)
        self.assertIn("Valid", cache.summary())

    def test_syntax_error_cache(self) -> None:
        cache = ValidatorCache()
        cache.update("? Bad choice without target")
        self.assertFalse(cache.is_valid)
        self.assertIsNotNone(cache.parse_error)
        self.assertIn("Parse error", cache.summary())
        errs, _ = cache.get_line_status(1)
        self.assertTrue(len(errs) > 0)

    def test_undefined_target_cache(self) -> None:
        cache = ValidatorCache()
        cache.update("## Start\n> nonexistent")
        self.assertFalse(cache.is_valid)
        self.assertIn("error(s)", cache.summary())
        errs, _ = cache.get_line_status(2)
        self.assertTrue(any("nonexistent" in e for e in errs))


class TestOutline(unittest.TestCase):
    """Test scene outline extraction."""

    def test_extract_outline(self) -> None:
        lines = SAMPLE_ES.splitlines()
        scenes = extract_outline(lines)
        self.assertEqual(len(scenes), 3)

        self.assertEqual(scenes[0].display_name, "Intro")
        self.assertEqual(scenes[0].label_id, "scene_intro")
        self.assertEqual(scenes[0].line_number, 1)

        self.assertEqual(scenes[1].display_name, "The Cave")
        self.assertEqual(scenes[1].label_id, "cave")

        self.assertEqual(scenes[2].display_name, "Forest")
        self.assertEqual(scenes[2].label_id, "forest")


class TestCLIEditSubcommand(unittest.TestCase):
    """Test CLI argument parsing for the edit subcommand."""

    def test_edit_argparse(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["edit", "story.es", "--read-only"])
        self.assertEqual(args.command, "edit")
        self.assertEqual(args.file, "story.es")
        self.assertTrue(args.read_only)

    def test_edit_argparse_default_file(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["edit"])
        self.assertEqual(args.command, "edit")
        self.assertIsNone(args.file)
        self.assertFalse(args.read_only)

    @patch("eager_script.editor.is_editor_available", return_value=False)
    def test_edit_fails_helpfully_when_blessed_missing(self, mock_avail) -> None:
        import io

        with patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            exit_code = main(["edit", "test.es"])
            self.assertEqual(exit_code, 1)
            err = mock_stderr.getvalue()
            self.assertIn("The Eager-Script terminal editor requires 'blessed'", err)
            self.assertIn('pip install "eager-script[editor]"', err)

    @patch("eager_script.editor.is_editor_available", return_value=True)
    @patch("eager_script.editor.run_editor", return_value=0)
    def test_edit_launches_when_blessed_available(self, mock_run, mock_avail) -> None:
        exit_code = main(["edit", "test.es"])
        self.assertEqual(exit_code, 0)
        mock_run.assert_called_once_with(filepath="test.es", read_only=False, plain=False)

        mock_run.reset_mock()
        exit_code_plain = main(["edit", "test.es", "--plain"])
        self.assertEqual(exit_code_plain, 0)
        mock_run.assert_called_once_with(filepath="test.es", read_only=False, plain=True)


class DummyKey(str):
    """Mock Keystroke object mimicking blessed.keyboard.Keystroke."""

    name: str | None
    is_sequence: bool

    def __new__(cls, val: str, name: str | None = None, is_sequence: bool = False):
        obj = str.__new__(cls, val)
        obj.name = name
        obj.is_sequence = is_sequence
        return obj


class TestEditorApp(unittest.TestCase):
    """Test Editor event handling, rendering, and action dispatching."""

    def setUp(self) -> None:
        from eager_script.editor.app import Editor

        self.term = DummyTerm()
        self.editor = Editor(term=self.term)

    def test_editor_typing_and_navigation(self) -> None:
        # Type 'Hello'
        for ch in "Hello":
            self.editor.handle_key(DummyKey(ch))
        self.assertEqual(self.editor.buffer.current_line, "Hello")

        # Newline
        self.editor.handle_key(DummyKey("", name="KEY_ENTER", is_sequence=True))
        self.assertEqual(self.editor.buffer.line_count, 2)
        self.assertEqual(self.editor.buffer.cursor_row, 1)

        # Type 'World' on line 2
        for ch in "World":
            self.editor.handle_key(DummyKey(ch))
        self.assertEqual(self.editor.buffer.current_line, "World")

        # Arrow navigation
        self.editor.handle_key(DummyKey("", name="KEY_UP", is_sequence=True))
        self.assertEqual(self.editor.buffer.cursor_row, 0)
        self.editor.handle_key(DummyKey("", name="KEY_DOWN", is_sequence=True))
        self.assertEqual(self.editor.buffer.cursor_row, 1)
        self.editor.handle_key(DummyKey("", name="KEY_HOME", is_sequence=True))
        self.assertEqual(self.editor.buffer.cursor_col, 0)
        self.editor.handle_key(DummyKey("", name="KEY_END", is_sequence=True))
        self.assertEqual(self.editor.buffer.cursor_col, 5)

        # Backspace at start of line
        self.editor.handle_key(DummyKey("", name="KEY_HOME", is_sequence=True))
        self.editor.handle_key(DummyKey("", name="KEY_BACKSPACE", is_sequence=True))
        self.assertEqual(self.editor.buffer.line_count, 1)
        self.assertEqual(self.editor.buffer.current_line, "HelloWorld")

    def test_editor_enter_variations(self) -> None:
        # Enter as \n (KEY_CTRL_J) and \r (KEY_CTRL_M) must insert newline and not open outline
        with patch.object(self.editor, "action_outline") as mock_outline:
            self.editor.handle_key(DummyKey("\n", name="KEY_CTRL_J"))
            self.editor.handle_key(DummyKey("\r", name="KEY_CTRL_M"))
            self.editor.handle_key(DummyKey("", name="KEY_ENTER", is_sequence=True))
            mock_outline.assert_not_called()
            self.assertEqual(self.editor.buffer.line_count, 4)

        # Space key inserts space character
        self.editor.handle_key(DummyKey(" "))
        self.assertEqual(self.editor.buffer.current_line, " ")

    def test_editor_undo_redo_shortcuts(self) -> None:
        self.editor.handle_key(DummyKey("A"))
        self.assertEqual(self.editor.buffer.current_line, "A")

        # Ctrl+Z (Undo)
        self.editor.handle_key(DummyKey("\x1a"))
        self.assertEqual(self.editor.buffer.current_line, "")

        # Ctrl+Y (Redo)
        self.editor.handle_key(DummyKey("\x19"))
        self.assertEqual(self.editor.buffer.current_line, "A")

    def test_editor_delete_line(self) -> None:
        self.editor.handle_key(DummyKey("Line 1"))
        self.editor.handle_key(DummyKey("", name="KEY_ENTER", is_sequence=True))
        self.editor.handle_key(DummyKey("Line 2"))

        # Ctrl+K on Line 2
        self.editor.handle_key(DummyKey("\x0b"))
        self.assertEqual(self.editor.buffer.line_count, 1)
        self.assertEqual(self.editor.buffer.current_line, "Line 1")

    def test_editor_render_all(self) -> None:
        # Verify render_all runs without raising exceptions
        import io

        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            self.editor.render_all()
            output = mock_out.getvalue()
            self.assertTrue(len(output) > 0)

    @patch("eager_script.editor.app.prompt_input", return_value="1")
    def test_action_goto_line(self, mock_prompt) -> None:
        self.editor.buffer.lines = ["Line 1", "Line 2", "Line 3"]
        self.editor.action_goto_line()
        self.assertEqual(self.editor.buffer.cursor_row, 0)

    @patch("eager_script.editor.app.prompt_input", return_value="World")
    def test_action_find(self, mock_prompt) -> None:
        self.editor.buffer.lines = ["Hello", "World"]
        self.editor.action_find()
        self.assertEqual(self.editor.buffer.cursor_row, 1)
        self.assertEqual(self.editor.buffer.cursor_col, 0)

    @patch("eager_script.editor.app.outline_dialog")
    def test_action_outline(self, mock_dialog) -> None:

        mock_dialog.return_value = SceneEntry(
            line_index=2, line_number=3, display_name="Scene 3", label_id="scene_3"
        )
        self.editor.buffer.lines = ["## Scene 1", "Narration", "## Scene 3"]
        self.editor.action_outline()
        self.assertEqual(self.editor.buffer.cursor_row, 2)

    def test_editor_control_key_names(self) -> None:
        # Test KEY_CTRL_S triggers action_save
        with patch.object(self.editor, "action_save") as mock_save:
            self.editor.handle_key(DummyKey("", name="KEY_CTRL_S"))
            mock_save.assert_called_once()

        # Test KEY_CTRL_Q and KEY_CTRL_X trigger action_quit
        with patch.object(self.editor, "action_quit") as mock_quit:
            self.editor.handle_key(DummyKey("", name="KEY_CTRL_Q"))
            self.editor.handle_key(DummyKey("", name="KEY_CTRL_X"))
            self.editor.handle_key(DummyKey("", name="KEY_CTRL_C"))
            self.assertEqual(mock_quit.call_count, 3)

        # Test KEY_CTRL_O triggers action_outline
        with patch.object(self.editor, "action_outline") as mock_outline:
            self.editor.handle_key(DummyKey("", name="KEY_CTRL_O"))
            mock_outline.assert_called_once()

        # Test KEY_CTRL_F triggers action_find
        with patch.object(self.editor, "action_find") as mock_find:
            self.editor.handle_key(DummyKey("", name="KEY_CTRL_F"))
            mock_find.assert_called_once()

        # Test KEY_CTRL_G triggers action_goto_line
        with patch.object(self.editor, "action_goto_line") as mock_goto:
            self.editor.handle_key(DummyKey("", name="KEY_CTRL_G"))
            mock_goto.assert_called_once()

    def test_editor_input_mode_fallback(self) -> None:
        from eager_script.editor.app import editor_input_mode

        # Test that editor_input_mode works cleanly without error on non-tty / DummyTerm
        with editor_input_mode(self.term):
            pass


class TestEditorModule(unittest.TestCase):
    """Test top-level eager_script.editor helpers and fallback behaviors."""

    def test_is_editor_available_returns_bool(self) -> None:
        res = is_editor_available()
        self.assertIsInstance(res, bool)

    def test_getattr_raises_attribute_error(self) -> None:
        import eager_script.editor

        with self.assertRaises(AttributeError):
            _ = eager_script.editor.nonexistent_attribute

    @patch("eager_script.editor.is_editor_available", return_value=False)
    def test_getattr_editor_raises_when_blessed_missing(self, mock_avail) -> None:
        import eager_script.editor

        with self.assertRaises(ImportError) as ctx:
            _ = eager_script.editor.Editor
        self.assertIn("The Eager-Script terminal editor requires 'blessed'", str(ctx.exception))

    @patch("eager_script.editor.is_editor_available", return_value=False)
    def test_run_editor_returns_1_when_missing(self, mock_avail) -> None:
        import io

        import eager_script.editor

        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            exit_code = eager_script.editor.run_editor()
            self.assertEqual(exit_code, 1)
            self.assertIn("The Eager-Script terminal editor requires 'blessed'", mock_err.getvalue())

    def test_editor_python_310_compatibility(self) -> None:
        import ast

        editor_dir = Path(__file__).resolve().parent.parent / "src" / "eager_script" / "editor"
        for py_file in editor_dir.glob("*.py"):
            code = py_file.read_text(encoding="utf-8")
            parsed = ast.parse(code, feature_version=(3, 10))
            self.assertIsNotNone(parsed)


if __name__ == "__main__":
    unittest.main()
