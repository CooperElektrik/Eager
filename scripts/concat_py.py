#!/usr/bin/env python3
"""Concatenate all .py files in the repository into a single labelled file.

Read-only with respect to the source tree: the script never modifies or
deletes any existing file. It refuses to write to a path that is itself
a Python source file in the tree, and refuses to overwrite an existing
file unless --force is given.

Usage:
    python scripts/concat_py.py                      # writes concat_output.txt
    python scripts/concat_py.py report.txt           # custom output path
    python scripts/concat_py.py --root packages      # limit to a subdirectory
    python scripts/concat_py.py -                    # write to stdout
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Directories skipped when walking the tree.
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".poolside",
    ".freebuff",
    "node_modules",
    "build",
    "dist",
    "egg-info",
}

SEPARATOR = "=" * 78


def should_skip(path: Path) -> bool:
    """Return True if any parent directory of *path* is excluded."""
    return any(
        part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in path.parts
    )


def collect_files(root: Path) -> list[Path]:
    """Return sorted .py files under *root*, excluding generated dirs."""
    files = [
        p
        for p in root.rglob("*.py")
        if p.is_file() and not should_skip(p.relative_to(root))
    ]
    return sorted(files)


def format_file(path: Path, root: Path, index: int, total: int) -> str:
    """Render one file's contents with a path/line-count header."""
    rel = path.relative_to(root)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8", errors="replace")
    line_count = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    header = (
        f"{SEPARATOR}\n"
        f"[{index}/{total}] {rel.as_posix()}\n"
        f"{line_count} lines\n"
        f"{SEPARATOR}\n"
    )
    if text and not text.endswith("\n"):
        text += "\n"
    return header + text


def concatenate(root: Path) -> tuple[str, int]:
    """Return (combined output text, number of files included)."""
    files = collect_files(root)
    header = (
        f"# Concatenated Python sources from {root.resolve()}\n# {len(files)} files\n\n"
    )
    parts = [header]
    for i, path in enumerate(files, start=1):
        parts.append(format_file(path, root, i, len(files)))
    return "".join(parts), len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "output",
        nargs="?",
        default="concat_output.txt",
        help="Output file path, or '-' for stdout (default: concat_output.txt)",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Allow overwriting an existing output file",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error(f"root is not a directory: {root}")

    if args.output != "-":
        out = Path(args.output).resolve()
        if out.suffix == ".py" and out.is_relative_to(root):
            parser.error(f"refusing to overwrite Python source inside the tree: {out}")
        if out.exists() and not args.force:
            parser.error(f"output already exists (use --force): {out}")

    text, count = concatenate(root)

    if args.output == "-":
        sys.stdout.write(text)
    else:
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {count} files to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
