"""Interactive terminal text editor for Eager-Script screenplay DSL scripts."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager_script.editor.app import Editor


def is_editor_available() -> bool:
    """Check if optional dependencies (blessed) are installed."""
    try:
        import blessed  # noqa: F401

        return True
    except ImportError:
        return False


def run_editor(
    filepath: str | Path | None = None,
    *,
    read_only: bool = False,
    plain: bool = False,
) -> int:
    """Launch the Eager-Script terminal text editor.

    Returns exit code (0 on normal exit, non-zero on error).
    """
    if not is_editor_available():
        sys.stderr.write(
            "Error: The Eager-Script terminal editor requires 'blessed'.\n"
            'Install it with: pip install "eager-script[editor]"\n'
        )
        return 1

    from eager_script.editor.app import Editor

    editor = Editor(filepath=filepath, read_only=read_only, plain=plain)
    return editor.run()


def __getattr__(name: str) -> Any:
    if name == "Editor":
        if not is_editor_available():
            raise ImportError(
                "The Eager-Script terminal editor requires 'blessed'. "
                'Install it with: pip install "eager-script[editor]"'
            )
        from eager_script.editor.app import Editor

        return Editor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Editor",
    "is_editor_available",
    "run_editor",
]
