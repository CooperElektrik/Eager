"""Text buffer model for the Eager-Script editor."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BufferSnapshot:
    """Snapshot of buffer state for undo/redo."""

    lines: tuple[str, ...]
    cursor_row: int
    cursor_col: int


class TextBuffer:
    """Manages line storage, cursor tracking, editing operations, and history."""

    def __init__(
        self,
        lines: Sequence[str] | None = None,
        filepath: str | Path | None = None,
        *,
        read_only: bool = False,
    ) -> None:
        self.lines: list[str] = list(lines) if lines else [""]
        if not self.lines:
            self.lines = [""]
        self.cursor_row: int = 0
        self.cursor_col: int = 0
        self.preferred_col: int = 0
        self.filepath: Path | None = Path(filepath) if filepath else None
        self.read_only: bool = read_only
        self.dirty: bool = False

        self._undo_stack: list[BufferSnapshot] = []
        self._redo_stack: list[BufferSnapshot] = []
        self._max_undo: int = 200

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def current_line(self) -> str:
        if 0 <= self.cursor_row < len(self.lines):
            return self.lines[self.cursor_row]
        return ""

    def get_text(self) -> str:
        return "\n".join(self.lines)

    def set_text(self, text: str) -> None:
        self._record_undo()
        raw_lines = text.splitlines()
        self.lines = raw_lines if raw_lines else [""]
        self.cursor_row = min(self.cursor_row, len(self.lines) - 1)
        self.cursor_col = min(self.cursor_col, len(self.current_line))
        self.preferred_col = self.cursor_col
        self.dirty = True

    def load_file(self, filepath: str | Path) -> None:
        path = Path(filepath)
        content = path.read_text(encoding="utf-8")
        raw_lines = content.splitlines()
        self.lines = raw_lines if raw_lines else [""]
        self.filepath = path
        self.cursor_row = 0
        self.cursor_col = 0
        self.preferred_col = 0
        self.dirty = False
        self._undo_stack.clear()
        self._redo_stack.clear()

    def save_file(self, filepath: str | Path | None = None) -> Path:
        target = Path(filepath) if filepath else self.filepath
        if not target:
            raise ValueError("Cannot save buffer: no filepath specified.")
        content = self.get_text() + "\n"
        target.write_text(content, encoding="utf-8")
        self.filepath = target
        self.dirty = False
        return target

    # ================= Cursor Movement =================

    def clamp_cursor(self) -> None:
        if not self.lines:
            self.lines = [""]
        self.cursor_row = max(0, min(self.cursor_row, len(self.lines) - 1))
        curr_len = len(self.lines[self.cursor_row])
        self.cursor_col = max(0, min(self.cursor_col, curr_len))

    def move_left(self) -> None:
        if self.cursor_col > 0:
            self.cursor_col -= 1
        elif self.cursor_row > 0:
            self.cursor_row -= 1
            self.cursor_col = len(self.lines[self.cursor_row])
        self.preferred_col = self.cursor_col

    def move_right(self) -> None:
        curr_len = len(self.current_line)
        if self.cursor_col < curr_len:
            self.cursor_col += 1
        elif self.cursor_row < len(self.lines) - 1:
            self.cursor_row += 1
            self.cursor_col = 0
        self.preferred_col = self.cursor_col

    def move_up(self, n: int = 1) -> None:
        if self.cursor_row > 0:
            self.cursor_row = max(0, self.cursor_row - n)
            curr_len = len(self.lines[self.cursor_row])
            self.cursor_col = min(self.preferred_col, curr_len)

    def move_down(self, n: int = 1) -> None:
        if self.cursor_row < len(self.lines) - 1:
            self.cursor_row = min(len(self.lines) - 1, self.cursor_row + n)
            curr_len = len(self.lines[self.cursor_row])
            self.cursor_col = min(self.preferred_col, curr_len)

    def move_to_line_start(self) -> None:
        self.cursor_col = 0
        self.preferred_col = 0

    def move_to_line_end(self) -> None:
        self.cursor_col = len(self.current_line)
        self.preferred_col = self.cursor_col

    def move_to_file_start(self) -> None:
        self.cursor_row = 0
        self.cursor_col = 0
        self.preferred_col = 0

    def move_to_file_end(self) -> None:
        self.cursor_row = len(self.lines) - 1
        self.cursor_col = len(self.lines[self.cursor_row])
        self.preferred_col = self.cursor_col

    def move_to_line(self, row: int, col: int = 0) -> None:
        self.cursor_row = max(0, min(row, len(self.lines) - 1))
        self.cursor_col = max(0, min(col, len(self.lines[self.cursor_row])))
        self.preferred_col = self.cursor_col

    # ================= Undo / Redo =================

    def _record_undo(self) -> None:
        if self.read_only:
            return
        snapshot = BufferSnapshot(
            lines=tuple(self.lines),
            cursor_row=self.cursor_row,
            cursor_col=self.cursor_col,
        )
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack or self.read_only:
            return False
        current_snapshot = BufferSnapshot(
            lines=tuple(self.lines),
            cursor_row=self.cursor_row,
            cursor_col=self.cursor_col,
        )
        self._redo_stack.append(current_snapshot)

        last = self._undo_stack.pop()
        self.lines = list(last.lines)
        self.cursor_row = last.cursor_row
        self.cursor_col = last.cursor_col
        self.preferred_col = self.cursor_col
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo_stack or self.read_only:
            return False
        current_snapshot = BufferSnapshot(
            lines=tuple(self.lines),
            cursor_row=self.cursor_row,
            cursor_col=self.cursor_col,
        )
        self._undo_stack.append(current_snapshot)

        nxt = self._redo_stack.pop()
        self.lines = list(nxt.lines)
        self.cursor_row = nxt.cursor_row
        self.cursor_col = nxt.cursor_col
        self.preferred_col = self.cursor_col
        self.dirty = True
        return True

    # ================= Text Edits =================

    def insert_char(self, ch: str) -> None:
        if self.read_only:
            return
        self._record_undo()
        line = self.current_line
        self.lines[self.cursor_row] = line[: self.cursor_col] + ch + line[self.cursor_col :]
        self.cursor_col += len(ch)
        self.preferred_col = self.cursor_col
        self.dirty = True

    def insert_tab(self, spaces: int = 4) -> None:
        self.insert_char(" " * spaces)

    def insert_newline(self) -> None:
        if self.read_only:
            return
        self._record_undo()
        line = self.current_line
        before = line[: self.cursor_col]
        after = line[self.cursor_col :]

        self.lines[self.cursor_row] = before
        self.lines.insert(self.cursor_row + 1, after)
        self.cursor_row += 1
        self.cursor_col = 0
        self.preferred_col = 0
        self.dirty = True

    def delete_backspace(self) -> None:
        if self.read_only:
            return
        if self.cursor_col > 0:
            self._record_undo()
            line = self.current_line
            self.lines[self.cursor_row] = line[: self.cursor_col - 1] + line[self.cursor_col :]
            self.cursor_col -= 1
            self.preferred_col = self.cursor_col
            self.dirty = True
        elif self.cursor_row > 0:
            self._record_undo()
            prev_line = self.lines[self.cursor_row - 1]
            curr_line = self.lines[self.cursor_row]
            new_col = len(prev_line)
            self.lines[self.cursor_row - 1] = prev_line + curr_line
            del self.lines[self.cursor_row]
            self.cursor_row -= 1
            self.cursor_col = new_col
            self.preferred_col = self.cursor_col
            self.dirty = True

    def delete_forward(self) -> None:
        if self.read_only:
            return
        curr_len = len(self.current_line)
        if self.cursor_col < curr_len:
            self._record_undo()
            line = self.current_line
            self.lines[self.cursor_row] = line[: self.cursor_col] + line[self.cursor_col + 1 :]
            self.dirty = True
        elif self.cursor_row < len(self.lines) - 1:
            self._record_undo()
            curr_line = self.lines[self.cursor_row]
            next_line = self.lines[self.cursor_row + 1]
            self.lines[self.cursor_row] = curr_line + next_line
            del self.lines[self.cursor_row + 1]
            self.dirty = True

    def delete_line(self) -> None:
        if self.read_only:
            return
        self._record_undo()
        if len(self.lines) > 1:
            del self.lines[self.cursor_row]
            if self.cursor_row >= len(self.lines):
                self.cursor_row = len(self.lines) - 1
        else:
            self.lines[0] = ""
        self.cursor_col = min(self.cursor_col, len(self.current_line))
        self.preferred_col = self.cursor_col
        self.dirty = True

    # ================= Search / Find =================

    def find_next(
        self,
        query: str,
        *,
        case_sensitive: bool = False,
        start_from_cursor: bool = True,
    ) -> tuple[int, int] | None:
        """Search forward for query, wrapping around. Returns (row, col) or None."""
        if not query or not self.lines:
            return None

        q = query if case_sensitive else query.lower()
        start_row = self.cursor_row if start_from_cursor else 0
        start_col = (self.cursor_col + 1) if start_from_cursor else 0

        total_lines = len(self.lines)
        for offset in range(total_lines):
            row = (start_row + offset) % total_lines
            line = self.lines[row]
            search_line = line if case_sensitive else line.lower()

            col_search_start = start_col if offset == 0 else 0
            idx = search_line.find(q, col_search_start)
            if idx != -1:
                return (row, idx)

        return None
