"""Main application loop and UI renderer for the Eager-Script terminal text editor."""

from __future__ import annotations

import contextlib
import sys
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

try:
    import termios
    import tty
except ImportError:
    termios = None  # type: ignore[assignment]
    tty = None  # type: ignore[assignment]

HAS_TERMIOS: bool = termios is not None and tty is not None

try:
    from blessed import Terminal
except ImportError:
    Terminal = None  # type: ignore[misc,assignment]

from eager_script.editor.buffer import TextBuffer
from eager_script.editor.highlighter import EagerSHighlighter
from eager_script.editor.outline import extract_outline
from eager_script.editor.ui import confirm_dialog, help_dialog, outline_dialog, prompt_input
from eager_script.editor.validator_cache import ValidatorCache


@contextlib.contextmanager
def editor_input_mode(term: Any) -> Generator[None, None, None]:
    """Context manager configuring terminal for interactive editing.

    Disables ICANON and ECHO (cbreak), and crucially disables IXON (software
    flow control: Ctrl+S/Ctrl+Q) and ISIG (signal generation: Ctrl+Z/Ctrl+C)
    so control keys are received as keystrokes by inkey() rather than being
    intercepted by the OS terminal driver. Keeps OPOST enabled for standard
    output carriage return handling.
    """
    fd = getattr(term, "_keyboard_fd", None)
    if termios is None or tty is None or not isinstance(fd, int) or not sys.stdin.isatty():
        cbreak_cm = getattr(term, "cbreak", None)
        if callable(cbreak_cm):
            with term.cbreak():
                yield
        else:
            yield
        return

    try:
        old_mode = termios.tcgetattr(fd)
    except (termios.error, OSError):
        cbreak_cm = getattr(term, "cbreak", None)
        if callable(cbreak_cm):
            with term.cbreak():
                yield
        else:
            yield
        return

    try:
        new_mode = list(old_mode)
        tty.cfmakecbreak(new_mode)
        # Disable IXON and IXOFF so ^S and ^Q reach the application
        new_mode[0] &= ~(termios.IXON | getattr(termios, "IXOFF", 0))
        # Disable ISIG so ^Z (suspend) and ^C (interrupt) are delivered as keys
        new_mode[3] &= ~termios.ISIG
        # Keep OPOST enabled for standard newline carriage-return output
        new_mode[1] |= termios.OPOST
        new_mode[6][termios.VMIN] = 1
        new_mode[6][termios.VTIME] = 0

        termios.tcsetattr(fd, termios.TCSANOW, new_mode)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_mode)


class Editor:
    """Eager-Script interactive terminal screenplay text editor."""

    def __init__(
        self,
        filepath: str | Path | None = None,
        *,
        read_only: bool = False,
        term: Any = None,
        plain: bool = False,
    ) -> None:
        if term is None:
            if Terminal is None:
                raise ImportError(
                    "The Eager-Script terminal editor requires 'blessed'. "
                    'Install it with: pip install "eager-script[editor]"'
                )
            self.term = Terminal()
        else:
            self.term = term
        self.plain = plain
        self.buffer = TextBuffer(filepath=filepath, read_only=read_only)
        self.highlighter = EagerSHighlighter(self.term)
        self.validator = ValidatorCache(plain=plain)

        if filepath:
            path = Path(filepath)
            if path.exists():
                self.buffer.load_file(path)

        self.scroll_row: int = 0
        self.scroll_col: int = 0
        self.status_message: str = ""
        self.status_message_time: float = 0.0
        self.last_search_query: str = ""
        self.running: bool = True

        # Initial validation
        self.validator.update(self.buffer.get_text())

    def set_status(self, message: str) -> None:
        self.status_message = message
        self.status_message_time = time.time()

    def run(self) -> int:
        """Run main editor loop in alternate screen buffer with raw/cbreak keyboard input."""
        with self.term.fullscreen(), editor_input_mode(self.term):
            # Initial full render
            self.render_all()

            while self.running:
                key = self.term.inkey(timeout=0.1)
                if not key:
                    continue

                self.handle_key(key)
                self.render_all()

        return 0

    def handle_key(self, key: Any) -> None:
        """Process a single keystroke."""
        name = getattr(key, "name", "") or ""
        k_str = str(key) if key is not None else ""

        # 1. Editor shortcuts
        # Save: Ctrl+S
        if k_str == "\x13" or name in ("KEY_CTRL_S", "KEY_S_CTRL"):
            self.action_save()
            return

        # Quit: Ctrl+Q, Ctrl+X, or Ctrl+C
        if k_str in ("\x11", "\x18", "\x03") or name in (
            "KEY_CTRL_Q",
            "KEY_CTRL_X",
            "KEY_CTRL_C",
            "KEY_Q_CTRL",
            "KEY_X_CTRL",
            "KEY_C_CTRL",
        ):
            self.action_quit()
            return

        # Scene Outline: Ctrl+O
        if k_str == "\x0f" or name in ("KEY_CTRL_O", "KEY_O_CTRL"):
            self.action_outline()
            return

        # Find: Ctrl+F or Ctrl+W
        if k_str in ("\x06", "\x17") or name in (
            "KEY_CTRL_F",
            "KEY_CTRL_W",
            "KEY_F_CTRL",
            "KEY_W_CTRL",
        ):
            self.action_find()
            return

        # Go to line: Ctrl+G
        if k_str == "\x07" or name in ("KEY_CTRL_G", "KEY_G_CTRL"):
            self.action_goto_line()
            return

        # Undo: Ctrl+Z
        if k_str in ("\x1a", "\x1f") or name in ("KEY_CTRL_Z", "KEY_Z_CTRL"):
            if self.buffer.undo():
                self.set_status("Undo")
                self.validator.update(self.buffer.get_text())
            return

        # Redo: Ctrl+Y or Ctrl+R
        if k_str in ("\x19", "\x12") or name in (
            "KEY_CTRL_Y",
            "KEY_CTRL_R",
            "KEY_Y_CTRL",
            "KEY_R_CTRL",
        ):
            if self.buffer.redo():
                self.set_status("Redo")
                self.validator.update(self.buffer.get_text())
            return

        # Delete line: Ctrl+K or Ctrl+D
        if k_str in ("\x0b", "\x04") or name in (
            "KEY_CTRL_K",
            "KEY_CTRL_D",
            "KEY_K_CTRL",
            "KEY_D_CTRL",
        ):
            self.buffer.delete_line()
            self.validator.update(self.buffer.get_text())
            return

        # Help: F1
        if name in ("KEY_F1", "KEY_F(1)") or k_str in ("\x1b[OP", "\x1bOP", "\x1b[11~", "\x1b[[A"):
            help_dialog(self.term)
            return

        # 2. Navigation
        if name == "KEY_UP":
            self.buffer.move_up()
        elif name == "KEY_DOWN":
            self.buffer.move_down()
        elif name == "KEY_LEFT":
            self.buffer.move_left()
        elif name == "KEY_RIGHT":
            self.buffer.move_right()
        elif name == "KEY_HOME":
            self.buffer.move_to_line_start()
        elif name == "KEY_END":
            self.buffer.move_to_line_end()
        elif name == "KEY_PGUP":
            view_h = max(1, self.term.height - 3)
            self.buffer.move_up(view_h)
        elif name == "KEY_PGDOWN":
            view_h = max(1, self.term.height - 3)
            self.buffer.move_down(view_h)

        # 3. Editing
        elif name in ("KEY_ENTER", "KEY_CTRL_M", "KEY_CTRL_J") or k_str in ("\r", "\n"):
            self.buffer.insert_newline()
            self.validator.update(self.buffer.get_text())
        elif name in ("KEY_BACKSPACE", "KEY_DELETE", "KEY_CTRL_H") or k_str in ("\x7f", "\x08"):
            if name == "KEY_DELETE" or k_str == "\x1b[3~":
                self.buffer.delete_forward()
            else:
                self.buffer.delete_backspace()
            self.validator.update(self.buffer.get_text())
        elif name in ("KEY_TAB", "KEY_CTRL_I") or k_str == "\t":
            self.buffer.insert_tab(4)
            self.validator.update(self.buffer.get_text())
        elif not getattr(key, "is_sequence", False) and k_str and k_str >= " ":
            self.buffer.insert_char(k_str)
            self.validator.update(self.buffer.get_text())

    # ================= Actions =================

    def action_save(self) -> None:
        if self.buffer.read_only:
            self.set_status("Cannot save: Buffer is read-only")
            return

        if not self.buffer.filepath:
            new_path = prompt_input(self.term, "Save Screenplay", "File path: ")
            if not new_path:
                self.set_status("Save canceled")
                return
            self.buffer.filepath = Path(new_path)

        try:
            saved_to = self.buffer.save_file()
            self.set_status(f"Saved to {saved_to.name}")
        except (OSError, ValueError) as exc:
            self.set_status(f"Error saving: {exc}")

    def action_quit(self) -> None:
        if self.buffer.dirty:
            res = confirm_dialog(self.term, "Save unsaved changes before exiting?")
            if res == "cancel":
                return
            elif res == "y":
                self.action_save()
                if self.buffer.dirty:
                    # Save failed or was canceled
                    return
        self.running = False

    def action_outline(self) -> None:
        scenes = extract_outline(self.buffer.lines)
        picked = outline_dialog(self.term, scenes)
        if picked:
            self.buffer.move_to_line(picked.line_index)
            self.set_status(f"Jumped to: {picked.display_name}")

    def action_find(self) -> None:
        query = prompt_input(
            self.term,
            "Find Text",
            "Search: ",
            default=self.last_search_query,
        )
        if query is None:
            return
        if not query:
            self.set_status("Empty search string")
            return

        self.last_search_query = query
        match = self.buffer.find_next(query)
        if match:
            row, col = match
            self.buffer.move_to_line(row, col)
            self.set_status(f"Found match at line {row + 1}, col {col + 1}")
        else:
            self.set_status(f"Pattern not found: {query!r}")

    def action_goto_line(self) -> None:
        raw_val = prompt_input(
            self.term,
            "Go to Line",
            f"Line (1-{self.buffer.line_count}): ",
        )
        if not raw_val:
            return
        try:
            target = int(raw_val.strip())
            self.buffer.move_to_line(target - 1)
            self.set_status(f"Jumped to line {target}")
        except ValueError:
            self.set_status("Invalid line number")

    # ================= Rendering =================

    def adjust_viewport(self, view_height: int, view_width: int) -> None:
        """Keep cursor visible inside the scrollable viewport."""
        # Vertical scrolling
        if self.buffer.cursor_row < self.scroll_row:
            self.scroll_row = self.buffer.cursor_row
        elif self.buffer.cursor_row >= self.scroll_row + view_height:
            self.scroll_row = self.buffer.cursor_row - view_height + 1

        # Horizontal scrolling
        if self.buffer.cursor_col < self.scroll_col:
            self.scroll_col = self.buffer.cursor_col
        elif self.buffer.cursor_col >= self.scroll_col + view_width:
            self.scroll_col = self.buffer.cursor_col - view_width + 1

    def render_all(self) -> None:
        """Render complete editor UI to terminal."""
        t = self.term
        w = t.width
        h = t.height

        if h < 5 or w < 20:
            print(t.move_xy(0, 0) + "Window too small!", end="", flush=True)
            return

        view_height = h - 3  # Header (1), Status (1), Help (1)
        gutter_digits = max(3, len(str(self.buffer.line_count)))
        gutter_width = gutter_digits + 4  # e.g., '  12 │ '
        view_width = max(10, w - gutter_width)

        self.adjust_viewport(view_height, view_width)

        output_chunks: list[str] = []

        # 1. Header Bar
        fname = self.buffer.filepath.name if self.buffer.filepath else "[Untitled]"
        dirty_flag = " [+]" if self.buffer.dirty else ""
        ro_flag = " [RO]" if self.buffer.read_only else ""
        left_header = f" Eager-Script Editor │ {fname}{dirty_flag}{ro_flag}"
        right_header = (
            f"Ln {self.buffer.cursor_row + 1}, Col {self.buffer.cursor_col + 1} │ F1: Help "
        )
        spaces = max(0, w - len(left_header) - len(right_header))
        header_text = left_header + (" " * spaces) + right_header
        output_chunks.append(t.move_xy(0, 0) + t.bold_black_on_cyan(header_text[:w]))

        # 2. Main Editing Viewport
        for row_idx in range(view_height):
            screen_y = 1 + row_idx
            file_line_idx = self.scroll_row + row_idx

            if file_line_idx < len(self.buffer.lines):
                line_no = file_line_idx + 1
                raw_line = self.buffer.lines[file_line_idx]

                # Diagnostic indicator in gutter
                errors, warnings = self.validator.get_line_status(line_no)
                if errors:
                    marker = t.bold_red("!")
                elif warnings:
                    marker = t.bold_yellow("W")
                else:
                    marker = " "

                # Gutter
                gutter_str = f"{marker}{line_no:>{gutter_digits}} │ "
                styled_gutter = t.bright_black(gutter_str)

                # Content slicing for horizontal scroll
                if self.scroll_col < len(raw_line):
                    visible_slice = raw_line[self.scroll_col :]
                else:
                    visible_slice = ""

                highlighted_text = self.highlighter.highlight_line(visible_slice)
                # Ensure width does not wrap
                line_out = styled_gutter + highlighted_text
            else:
                # Beyond end of file
                styled_gutter = t.bright_black("~".rjust(gutter_digits + 2) + " │ ")
                line_out = styled_gutter

            output_chunks.append(t.move_xy(0, screen_y) + line_out + t.clear_eol)

        # 3. Status Bar
        status_y = h - 2
        # If current line has diagnostic, display it with priority
        curr_line_no = self.buffer.cursor_row + 1
        curr_errors, curr_warnings = self.validator.get_line_status(curr_line_no)

        if curr_errors:
            diag_str = f" ✗ Line {curr_line_no}: {curr_errors[0]} "
            left_status = t.bold_white_on_red(diag_str)
            raw_len = len(diag_str)
        elif curr_warnings:
            diag_str = f" ⚠ Line {curr_line_no}: {curr_warnings[0]} "
            left_status = t.bold_black_on_yellow(diag_str)
            raw_len = len(diag_str)
        elif self.status_message and (time.time() - self.status_message_time < 5.0):
            left_status = t.bold_white_on_blue(f" {self.status_message} ")
            raw_len = len(self.status_message) + 2
        else:
            val_summary = self.validator.summary()
            left_status = t.bright_black(f" {val_summary} ")
            raw_len = len(val_summary) + 2

        status_pad = max(0, w - raw_len)
        output_chunks.append(
            t.move_xy(0, status_y) + left_status + t.on_black(" " * status_pad) + t.clear_eol
        )

        # 4. Shortcut Help Bar
        help_y = h - 1
        shortcuts = " ^S Save │ ^Q/^X Quit │ ^O Outline │ ^F Find │ ^G GoTo │ ^Z Undo │ F1 Help"
        styled_help = t.bold_black_on_white(shortcuts.ljust(w)[:w])
        output_chunks.append(t.move_xy(0, help_y) + styled_help)

        # 5. Position cursor
        cursor_screen_x = gutter_width + (self.buffer.cursor_col - self.scroll_col)
        cursor_screen_y = 1 + (self.buffer.cursor_row - self.scroll_row)

        cursor_screen_x = max(gutter_width, min(cursor_screen_x, w - 1))
        cursor_screen_y = max(1, min(cursor_screen_y, h - 3))

        output_chunks.append(t.move_xy(cursor_screen_x, cursor_screen_y))

        # Flush everything to terminal in one write to prevent flickering
        sys.stdout.write("".join(output_chunks))
        sys.stdout.flush()
