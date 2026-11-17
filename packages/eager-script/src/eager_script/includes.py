"""Include resolution for multi-file Eager-Script screenplays."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from eager_script.ast import ParsedChoiceSet, ParsedInclude, ParsedItem
from eager_script.parser import parse

__all__ = [
    "IncludeError",
    "discover_includes",
    "parse_file",
    "resolve_includes",
]


class IncludeError(Exception):
    """Raised when an include cannot be resolved, is circular, or violates bounds."""


def _resolve_include_target(
    inc: ParsedInclude,
    base_path: Path,
    root_path: Path,
    visited: set[Path],
    *,
    missing_ok: bool = False,
) -> Path | None:
    """Resolve and validate a single ParsedInclude target path."""
    inc_target = (base_path / inc.path).resolve()
    if not inc_target.is_relative_to(root_path):
        msg = (
            f"Line {inc.line_number}: Path traversal detected: "
            f"@include '{inc.path}' resolves outside root '{root_path}'"
        )
        raise IncludeError(msg)
    if not inc_target.is_file():
        if missing_ok:
            return None
        msg = f"Line {inc.line_number}: Included file not found: '{inc.path}' (looked at {inc_target})"
        raise IncludeError(msg)
    if inc_target in visited:
        msg = f"Line {inc.line_number}: Circular include detected for '{inc.path}'"
        raise IncludeError(msg)
    return inc_target


def resolve_includes(
    items: Sequence[ParsedItem],
    base_dir: Path | str,
    *,
    visited: set[Path] | None = None,
    root_dir: Path | str | None = None,
    included_paths: set[Path] | None = None,
    read_file: Callable[[Path], str] | None = None,
) -> list[ParsedItem]:
    """Recursively resolve ParsedInclude items by parsing target files and inlining their AST items."""
    base_path = Path(base_dir).resolve()
    root_path = Path(root_dir).resolve() if root_dir is not None else base_path
    if visited is None:
        visited = set()

    reader = read_file or (lambda p: p.read_text(encoding="utf-8"))
    resolved: list[ParsedItem] = []

    for item in items:
        if isinstance(item, ParsedInclude):
            inc_target = _resolve_include_target(item, base_path, root_path, visited)
            assert inc_target is not None
            if included_paths is not None:
                included_paths.add(inc_target)

            sub_visited = set(visited)
            sub_visited.add(inc_target)
            content = reader(inc_target)
            sub_items = parse(content)
            inlined = resolve_includes(
                sub_items,
                inc_target.parent,
                visited=sub_visited,
                root_dir=root_path,
                included_paths=included_paths,
                read_file=reader,
            )
            resolved.extend(inlined)
        elif isinstance(item, ParsedChoiceSet):
            new_options = []
            changed = False
            for opt in item.options:
                if opt.body:
                    new_body = tuple(
                        resolve_includes(
                            opt.body,
                            base_path,
                            visited=visited,
                            root_dir=root_path,
                            included_paths=included_paths,
                            read_file=reader,
                        )
                    )
                    if new_body != opt.body:
                        changed = True
                        new_options.append(replace(opt, body=new_body))
                        continue
                new_options.append(opt)
            resolved.append(replace(item, options=tuple(new_options)) if changed else item)
        else:
            resolved.append(item)
    return resolved


def _iter_ast_includes(items: Sequence[ParsedItem]) -> list[ParsedInclude]:
    """Collect all ParsedInclude nodes in source order, including inside choice blocks."""
    found: list[ParsedInclude] = []
    for item in items:
        if isinstance(item, ParsedInclude):
            found.append(item)
        elif isinstance(item, ParsedChoiceSet):
            for opt in item.options:
                if opt.body:
                    found.extend(_iter_ast_includes(opt.body))
    return found


def discover_includes(
    file_path: Path | str,
    *,
    root_dir: Path | str | None = None,
    missing_ok: bool = False,
) -> list[Path]:
    """Return the entry file followed by all transitively @included files in AST order."""
    entry = Path(file_path).resolve()
    if not entry.is_file():
        return []

    root_path = Path(root_dir).resolve() if root_dir is not None else entry.parent
    discovered: list[Path] = []
    visited: set[Path] = set()

    def walk(current: Path, active_stack: set[Path]) -> None:
        if current in visited or not current.is_file():
            return
        visited.add(current)
        discovered.append(current)

        content = current.read_text(encoding="utf-8")
        items = parse(content, recovery=True)
        for inc in _iter_ast_includes(items):
            inc_target = _resolve_include_target(
                inc,
                current.parent,
                root_path,
                active_stack,
                missing_ok=missing_ok,
            )
            if inc_target is None:
                continue
            next_stack = set(active_stack)
            next_stack.add(inc_target)
            walk(inc_target, next_stack)

    walk(entry, {entry})
    return discovered


def parse_file(
    file_path: Path | str,
    *,
    resolve_includes_flag: bool = True,
    root_dir: Path | str | None = None,
    included_paths: set[Path] | None = None,
) -> list[ParsedItem]:
    """Parse an .es screenplay file from disk, optionally expanding @include directives."""
    p = Path(file_path).resolve()
    if not p.is_file():
        msg = f"File not found: {p}"
        raise FileNotFoundError(msg)
    content = p.read_text(encoding="utf-8")
    items = parse(content)
    if resolve_includes_flag:
        return resolve_includes(
            items,
            p.parent,
            visited={p},
            root_dir=root_dir,
            included_paths=included_paths,
        )
    return items
