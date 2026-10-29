#!/usr/bin/env python3
"""Concatenate all .py files in the repository into a single labelled file."""
import argparse
import sys
from pathlib import Path

EXCLUDED = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", 
    ".mypy_cache", ".poolside", ".freebuff", "node_modules", "build", "dist", "egg-info"
}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", nargs="?", default="concat_output.txt", help="Output file path, or '-' for stdout")
    p.add_argument("--root", default=".", type=Path, help="Directory to scan")
    p.add_argument("--include-tests", action="store_true", help="Include test modules")
    p.add_argument("--exclude-tests", dest="include_tests", action="store_false", help=argparse.SUPPRESS)
    p.add_argument("-f", "--force", action="store_true", help="Allow overwriting an existing output file")
    args = p.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        p.error(f"root is not a directory: {root}")

    out = None if args.output == "-" else Path(args.output).resolve()
    if out:
        if out.suffix == ".py" and out.is_relative_to(root):
            p.error(f"refusing to overwrite Python source inside the tree: {out}")
        if out.exists() and not args.force:
            p.error(f"output already exists (use --force): {out}")

    files = []
    for path in root.rglob("*.py"):
        if not path.is_file(): continue
        parts = path.relative_to(root).parts
        if EXCLUDED.intersection(parts) or any(pt.endswith(".egg-info") for pt in parts):
            continue
        is_test = {"test", "tests"}.intersection(parts) or path.name.startswith("test_") or path.name.endswith("_test.py") or path.name == "conftest.py"
        if args.include_tests or not is_test:
            files.append(path)
    
    files.sort()
    out_parts = [f"# Concatenated Python sources from {root}\n# {len(files)} files\n\n"]
    
    for i, path in enumerate(files, 1):
        txt = path.read_text("utf-8", "replace")
        lines = txt.count("\n") + (0 if txt.endswith("\n") or not txt else 1)
        trailer = "\n" if txt and not txt.endswith("\n") else ""
        out_parts.append(f"{'='*78}\n[{i}/{len(files)}] {path.relative_to(root).as_posix()}\n{lines} lines\n{'='*78}\n{txt}{trailer}")

    text = "".join(out_parts)
    if out:
        out.write_text(text, "utf-8")
        print(f"Wrote {len(files)} files to {out}", file=sys.stderr)
    else:
        sys.stdout.write(text)

if __name__ == "__main__":
    raise SystemExit(main())