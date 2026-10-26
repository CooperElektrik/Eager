"""Command-line interface for the Eager-Script Language Server."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from lsprotocol.types import DiagnosticSeverity

from eager_script_lsp import __version__
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.server import create_server
from eager_script_lsp.workspace import WorkspaceIndex, path_to_uri, uri_to_path

__all__ = [
    "add_arguments",
    "build_parser",
    "main",
    "run_check",
    "run_cli",
]


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Register LSP command line flags on an argument parser."""
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        default=True,
        help="Run language server over standard I/O (default).",
    )
    parser.add_argument(
        "--tcp",
        action="store_true",
        help="Run language server over TCP socket.",
    )
    parser.add_argument(
        "--ws",
        action="store_true",
        help="Run language server over WebSocket.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="TCP/WebSocket host to bind (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2087,
        help="TCP/WebSocket port to bind (default: 2087).",
    )
    parser.add_argument(
        "--check",
        metavar="PATH",
        help="Headlessly validate script or workspace path and print diagnostics.",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for eager-script-lsp."""
    parser = argparse.ArgumentParser(
        prog="eager-script-lsp",
        description="Full-featured Language Server Protocol (LSP) server for Eager-Script screenplays.",
    )
    add_arguments(parser)
    return parser


def run_check(target_path_str: str) -> int:
    """Run full headless diagnostics on a script or workspace path."""
    target_path = Path(target_path_str).resolve()
    if not target_path.exists():
        sys.stderr.write(f"Error: Path '{target_path}' not found.\n")
        return 1

    if target_path.is_file() and target_path.suffix != ".es":
        sys.stderr.write(f"Error: Target path '{target_path.name}' is not an .es screenplay file.\n")
        return 1

    root = target_path if target_path.is_dir() else target_path.parent
    index = WorkspaceIndex(root)
    index.initialize()

    docs_to_check = []
    if target_path.is_file():
        target_uri = path_to_uri(target_path)
        doc = index.get_document(target_uri)
        if doc is None:
            text = target_path.read_text(encoding="utf-8")
            doc = index.update_document(target_uri, text)
        docs_to_check.append(doc)
    else:
        docs_to_check = list(index.documents.values())

    has_errors = False
    total_diags = 0

    print(f"Checking {len(docs_to_check)} document(s) in '{root}'...")

    for doc in docs_to_check:
        diags = compute_diagnostics(doc, index)
        if not diags:
            continue

        total_diags += len(diags)
        file_path = str(uri_to_path(doc.uri))
        print(f"\n{file_path}:")
        for d in diags:
            line_1 = d.range.start.line + 1
            col_1 = d.range.start.character + 1
            sev_name = "ERROR" if d.severity == DiagnosticSeverity.Error else "WARNING"
            if d.severity == DiagnosticSeverity.Error:
                has_errors = True
            print(f"  Line {line_1}:{col_1} [{sev_name}] ({d.source}): {d.message}")

    if has_errors:
        print(f"\nCheck FAILED with errors ({total_diags} total diagnostic issue(s)).")
        return 1

    print(f"\nCheck PASSED (0 errors, {total_diags} warning(s)/info).")
    return 0


def run_cli(args: argparse.Namespace) -> int:
    """Execute LSP server or checker based on parsed arguments."""
    if args.check:
        return run_check(args.check)

    server = create_server()
    if args.tcp:
        server.start_tcp(args.host, args.port)
    elif args.ws:
        server.start_ws(args.host, args.port)
    else:
        server.start_io()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point for eager-script-lsp."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
