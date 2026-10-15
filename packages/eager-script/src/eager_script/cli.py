"""Command line interface for eager-script parser."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import eager_script


def _cmd_parse(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        content = path.read_text(encoding="utf-8")
        items = eager_script.parse(content, plain=args.plain)
        json_output = eager_script.to_json(items, indent=args.indent)
        if args.output:
            out_path = Path(args.output)
            out_path.write_text(json_output, encoding="utf-8")
        else:
            sys.stdout.write(json_output + "\n")
        return 0
    except eager_script.ParseError as exc:
        sys.stderr.write(f"Parse error: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Error: {exc}\n")
        return 1


def _cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        content = path.read_text(encoding="utf-8")
        items = eager_script.parse(content, plain=args.plain)
        result = eager_script.validate(items, plain=args.plain)

        for warning in result.warnings:
            sys.stderr.write(f"WARNING: Line {warning.line_number}: {warning.message}\n")

        for error in result.errors:
            sys.stderr.write(f"ERROR: Line {error.line_number}: {error.message}\n")

        if not result.is_valid:
            sys.stderr.write(f"Validation failed with {len(result.errors)} error(s).\n")
            return 1

        sys.stdout.write(
            f"✓ Script '{path.name}' is valid ({len(items)} AST items, {len(result.warnings)} warning(s)).\n"
        )
        return 0
    except eager_script.ParseError as exc:
        sys.stderr.write(f"Syntax error: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Error: {exc}\n")
        return 1


def _cmd_graph(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        content = path.read_text(encoding="utf-8")
        graph = eager_script.parse_graph(content, plain=args.plain)

        if args.format == "dot":
            output_text = graph.to_dot()
        elif args.format == "mermaid":
            output_text = graph.to_mermaid()
        else:  # json
            include_body = not args.no_body
            output_text = graph.to_json(include_body=include_body, indent=args.indent)

        if args.output:
            out_path = Path(args.output)
            out_path.write_text(output_text + "\n", encoding="utf-8")
        else:
            sys.stdout.write(output_text + "\n")
        return 0
    except eager_script.ParseError as exc:
        sys.stderr.write(f"Parse error: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Error: {exc}\n")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eager-script",
        description="Fast screenplay DSL parser and tool for visual novels and interactive fiction.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"eager-script {eager_script.__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # parse subcommand
    parse_cmd = subparsers.add_parser("parse", help="Parse screenplay into JSON AST")
    parse_cmd.add_argument("file", help="Path to .es screenplay file")
    parse_cmd.add_argument(
        "-o",
        "--output",
        help="Path to write JSON output (default: stdout)",
    )
    parse_cmd.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation spaces (default: 2)",
    )
    parse_cmd.add_argument(
        "--plain",
        action="store_true",
        help="Enable Eager-SP mode (strict conventions, natural scene titles)",
    )

    # graph subcommand
    graph_cmd = subparsers.add_parser("graph", help="Export screenplay as a directed scene graph")
    graph_cmd.add_argument("file", help="Path to .es screenplay file")
    graph_cmd.add_argument(
        "-o",
        "--output",
        help="Path to write graph output (default: stdout)",
    )
    graph_cmd.add_argument(
        "--format",
        choices=["json", "dot", "mermaid"],
        default="json",
        help="Graph output format: json, dot, or mermaid (default: json)",
    )
    graph_cmd.add_argument(
        "--no-body",
        action="store_true",
        help="Exclude AST body items from JSON output",
    )
    graph_cmd.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation spaces (default: 2)",
    )
    graph_cmd.add_argument(
        "--plain",
        action="store_true",
        help="Enable Eager-SP mode",
    )

    # check subcommand
    check_cmd = subparsers.add_parser("check", help="Validate screenplay syntax and links")
    check_cmd.add_argument("file", help="Path to .es screenplay file")
    check_cmd.add_argument(
        "--plain",
        action="store_true",
        help="Enable Eager-SP validation mode",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "parse":
        return _cmd_parse(args)
    elif args.command == "graph":
        return _cmd_graph(args)
    elif args.command == "check":
        return _cmd_check(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
