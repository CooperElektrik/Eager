"""Command-line interface for the Eager-Script Language Server."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from eager_script_lsp import __version__
from eager_script_lsp.server import create_server

__all__ = [
    "add_arguments",
    "build_parser",
    "main",
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


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for eager-script-lsp."""
    parser = argparse.ArgumentParser(
        prog="eager-script-lsp",
        description="Language Server Protocol (LSP) server for Eager-Script screenplays.",
    )
    add_arguments(parser)
    return parser


def run_cli(_args: argparse.Namespace) -> int:
    """Execute LSP server over stdio."""
    server = create_server()
    server.start_io()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entry point for eager-script-lsp."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
