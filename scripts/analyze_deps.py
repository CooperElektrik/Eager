#!/usr/bin/env python3
"""Report per-module dependencies across a Python source tree.

For every module (a ``.py`` file) the report prints one line describing what the
module *contains* (the classes and functions it defines) and what it *uses*
(the symbols it imports), with the used symbols grouped by their source module.
For example, the line for ``eager_graphics.director`` looks roughly like::

    [eager_graphics.director]: contains [CharacterConfig, StageDirector],
    using [from eager_core.events: [AppendEvent, DialogueEvent],
    from eager_script: [HookArgs, parse_hook_args]]

Module identity is the dotted import path derived from the ``src/`` layout used
by this workspace (``packages/eager-graphics/src/eager_graphics/director.py`` ->
``eager_graphics.director``).  Import discovery is static (AST based): it does
not execute the code, and it finds imports nested inside functions and
``if TYPE_CHECKING:`` blocks.

Usage::

    python scripts/analyze_deps.py                       # scan ./packages
    python scripts/analyze_deps.py packages/eager-graphics
    python scripts/analyze_deps.py --internal-only --methods
    python scripts/analyze_deps.py --json > deps.json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = frozenset({
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    ".ruff_cache",
    ".pytest_cache",
})


@dataclass
class ModuleReport:
    """What a single module defines and what it imports."""

    module: str
    path: str
    contains: set[str] = field(default_factory=set)
    uses: dict[str, set[str]] = field(default_factory=dict)
    type_uses: dict[str, set[str]] = field(default_factory=dict)


def _is_type_checking(test: ast.expr) -> bool:
    """Return ``True`` for a ``TYPE_CHECKING`` / ``typing.TYPE_CHECKING`` guard."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


class _Analyzer(ast.NodeVisitor):
    """Collect definitions and imports from a single module AST."""

    def __init__(self, module: str, *, is_package: bool, collect_methods: bool) -> None:
        self.module = module
        self.is_package = is_package
        self.collect_methods = collect_methods
        self.contains: set[str] = set()
        self.uses: dict[str, set[str]] = {}
        self.type_uses: dict[str, set[str]] = {}
        self._type_depth = 0
        self._class_depth = 0
        self._func_depth = 0

    # -- imports ---------------------------------------------------------
    def _record(self, source: str, name: str) -> None:
        if source == "__future__":  # ``from __future__ import annotations`` is noise here
            return
        table = self.type_uses if self._type_depth else self.uses
        table.setdefault(source, set()).add(name)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record(alias.name, alias.asname or alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        source = self._resolve_from(node)
        if not source:
            return
        for alias in node.names:
            if alias.name == "*":
                self._record(source, "*")
            elif alias.asname:
                self._record(source, f"{alias.name} as {alias.asname}")
            else:
                self._record(source, alias.name)

    def _resolve_from(self, node: ast.ImportFrom) -> str:
        if node.level == 0:
            return node.module or ""
        # Relative import: resolve against this module's package.
        parts = self.module.split(".")
        package = parts if self.is_package else parts[:-1]
        up = node.level - 1
        if up:
            package = package[: len(package) - up] if up <= len(package) else []
        if node.module:
            package = [*package, *node.module.split(".")]
        return ".".join(package)

    # -- definitions -----------------------------------------------------
    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking(node.test):
            self._type_depth += 1
            for stmt in node.body:
                self.visit(stmt)
            self._type_depth -= 1
            for stmt in node.orelse:
                self.visit(stmt)
            return
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._func_depth == 0:
            self.contains.add(node.name)
            if self.collect_methods:
                for stmt in node.body:
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.contains.add(f"{node.name}.{stmt.name}")
        self._class_depth += 1
        self.generic_visit(node)
        self._class_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._func_depth == 0 and self._class_depth == 0:
            self.contains.add(node.name)
        self._func_depth += 1
        self.generic_visit(node)
        self._func_depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef


def module_name_for(path: Path, root: Path) -> tuple[str, bool]:
    """Derive ``(dotted.module, is_package)`` for *path* relative to *root*.

    The ``src/`` anchor is stripped when present so ``src/pkg/mod.py`` becomes
    ``pkg.mod`` rather than ``src.pkg.mod``.
    """
    parts = list(path.resolve().with_suffix("").parts)
    if "src" not in parts:
        # No ``src/`` anchor (e.g. a bare single-file scan): fall back to
        # path-relative-to-root so the name is still stable and unique.
        try:
            parts = list(path.resolve().relative_to(root.resolve()).with_suffix("").parts)
        except ValueError:
            parts = list(path.with_suffix("").parts)
    is_package = bool(parts) and parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    if "src" in parts:
        idx = len(parts) - 1 - parts[::-1].index("src")
        parts = parts[idx + 1 :]
    module = ".".join(parts) or path.stem
    return module, is_package


def _is_test(path: Path) -> bool:
    parts = path.parts
    if "tests" in parts or "test" in parts:
        return True
    return path.name.startswith("test_") or path.name == "conftest.py"


def build_reports(paths: list[str], *, collect_methods: bool, include_tests: bool) -> list[ModuleReport]:
    reports: list[ModuleReport] = []
    seen: set[tuple[str, str]] = set()
    for raw_root in paths:
        root = Path(raw_root)
        if not root.exists():
            print(f"warning: path does not exist: {raw_root}", file=sys.stderr)
            continue
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in files:
            if path.suffix != ".py":
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if not include_tests and _is_test(path):
                continue
            module, is_package = module_name_for(path, root if root.is_dir() else root.parent)
            key = (module, str(path))
            if key in seen:
                continue
            seen.add(key)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError) as exc:
                print(f"warning: skipped {path}: {exc}", file=sys.stderr)
                continue
            analyzer = _Analyzer(module, is_package=is_package, collect_methods=collect_methods)
            analyzer.visit(tree)
            reports.append(
                ModuleReport(
                    module=module,
                    path=str(path),
                    contains=analyzer.contains,
                    uses=analyzer.uses,
                    type_uses=analyzer.type_uses,
                )
            )
    reports.sort(key=lambda report: report.module)
    return reports


def _internal_roots(reports: list[ModuleReport]) -> set[str]:
    return {report.module.split(".")[0] for report in reports}


def _filter(table: dict[str, set[str]], internal: set[str] | None) -> dict[str, list[str]]:
    return {
        source: sorted(names)
        for source, names in sorted(table.items())
        if internal is None or source.split(".")[0] in internal
    }


def format_report(report: ModuleReport, internal: set[str] | None) -> str:
    contains = ", ".join(sorted(report.contains))
    groups = [f"from {src}: [{', '.join(names)}]" for src, names in _filter(report.uses, internal).items()]
    groups += [
        f"from {src} (type-checking): [{', '.join(names)}]"
        for src, names in _filter(report.type_uses, internal).items()
    ]
    return f"[{report.module}]: contains [{contains}], using [{', '.join(groups)}]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", default=["packages"], help="files or directories to scan (default: packages)")
    parser.add_argument("--methods", action="store_true", help="also list class methods as 'Class.method' in 'contains'")
    parser.add_argument("--include-tests", action="store_true", help="include test modules (excluded by default)")
    parser.add_argument("--internal-only", action="store_true", help="show only imports of workspace packages (drop stdlib/third-party)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the one-line report format")
    args = parser.parse_args(argv)

    reports = build_reports(args.paths, collect_methods=args.methods, include_tests=args.include_tests)
    internal = _internal_roots(reports) if args.internal_only else None

    if args.json:
        payload = [
            {
                "module": report.module,
                "path": report.path,
                "contains": sorted(report.contains),
                "uses": _filter(report.uses, internal),
                "type_uses": _filter(report.type_uses, internal),
            }
            for report in reports
        ]
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    for report in reports:
        print(format_report(report, internal))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
