"""Live parser and validator feedback cache for the Eager-S editor."""

from __future__ import annotations

from collections import defaultdict

import eager_script
from eager_script import ParsedItem, ParseError, ValidationResult


class ValidatorCache:
    """Caches parse & validation results to provide real-time line diagnostics."""

    plain: bool

    def __init__(self, *, plain: bool = False) -> None:
        self.plain = plain
        self.items: list[ParsedItem] = []
        self.errors_by_line: dict[int, list[str]] = defaultdict(list)
        self.warnings_by_line: dict[int, list[str]] = defaultdict(list)
        self.is_valid: bool = True
        self.parse_error: ParseError | None = None
        self._last_text: str | None = None

    def update(self, text: str) -> None:
        """Re-parse and re-validate if text has changed."""
        if text == self._last_text:
            return

        self._last_text = text
        self.items.clear()
        self.errors_by_line.clear()
        self.warnings_by_line.clear()
        self.parse_error = None

        try:
            self.items = eager_script.parse(text, plain=self.plain)
            val_result: ValidationResult = eager_script.validate(self.items, plain=self.plain)
            self.is_valid = val_result.is_valid

            for err in val_result.errors:
                self.errors_by_line[err.line_number].append(err.message)

            for warn in val_result.warnings:
                self.warnings_by_line[warn.line_number].append(warn.message)

        except ParseError as exc:
            self.is_valid = False
            self.parse_error = exc
            self.errors_by_line[exc.line_number].append(str(exc))

    def get_line_status(self, line_number: int) -> tuple[list[str], list[str]]:
        """Return (errors, warnings) for a 1-indexed line."""
        return (
            self.errors_by_line.get(line_number, []),
            self.warnings_by_line.get(line_number, []),
        )

    def summary(self) -> str:
        """Format a short summary for the editor status bar."""
        if self.parse_error:
            return f"✗ Parse error (line {self.parse_error.line_number})"

        total_errs = sum(len(v) for v in self.errors_by_line.values())
        total_warns = sum(len(v) for v in self.warnings_by_line.values())

        if total_errs == 0 and total_warns == 0:
            return f"✓ Valid ({len(self.items)} nodes)"
        elif total_errs > 0:
            return f"✗ {total_errs} error(s), {total_warns} warning(s)"
        else:
            return f"⚠ {total_warns} warning(s) ({len(self.items)} nodes)"
