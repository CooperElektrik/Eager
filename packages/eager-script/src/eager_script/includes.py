"""Include resolution for multi-file Eager-Script screenplays."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from eager_script.ast import ParsedInclude, ParsedItem
from eager_script.parser import parse

__all__ = [
    "IncludeError",
    "parse_file",
    "resolve_includes",
]


class IncludeError(Exception):
    """Raised when an include cannot be resolved, is circular, or violates bounds."""


def resolve_includes(
    items: Sequence[ParsedItem],
    base_dir: Path | str,
    *,
    visited: set[Path] | None = None,
) -> list[ParsedItem]:
    """Recursively resolve ParsedInclude items by parsing target files and inlining their AST items."""
    base_path = Path(base_dir).resolve()
    if visited is None:
        visited = set()

    resolved: list[ParsedItem] = []
    for item in items:
        if isinstance(item, ParsedInclude):
            inc_target = (base_path / item.path).resolve()
            if not inc_target.is_file():
                msg = f"Line {item.line_number}: Included file not found: '{item.path}' (looked at {inc_target})"
                raise IncludeError(msg)
            if inc_target in visited:
                msg = f"Line {item.line_number}: Circular include detected for '{item.path}'"
                raise IncludeError(msg)

            sub_visited = set(visited)
            sub_visited.add(inc_target)
            content = inc_target.read_text(encoding="utf-8")
            sub_items = parse(content)
            inlined = resolve_includes(sub_items, inc_target.parent, visited=sub_visited)
            resolved.extend(inlined)
        else:
            resolved.append(item)
    return resolved


def parse_file(
    file_path: Path | str,
    *,
    resolve_includes_flag: bool = True,
) -> list[ParsedItem]:
    """Parse an .es screenplay file from disk, optionally expanding @include directives."""
    p = Path(file_path).resolve()
    if not p.is_file():
        msg = f"File not found: {p}"
        raise FileNotFoundError(msg)
    content = p.read_text(encoding="utf-8")
    items = parse(content)
    if resolve_includes_flag:
        return resolve_includes(items, p.parent, visited={p})
    return items
