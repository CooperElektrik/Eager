"""Unit tests for the eager-script-lsp CLI."""

from __future__ import annotations

import pytest

from eager_script_lsp import __version__
from eager_script_lsp.cli import build_parser, main


def test_cli_build_parser_options():
    """Verify CLI parser registers --stdio."""
    parser = build_parser()
    args_stdio = parser.parse_args(["--stdio"])
    assert args_stdio.stdio is True


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]):
    """Verify --version flag outputs the package version and exits."""
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_cli_main_help(capsys: pytest.CaptureFixture[str]):
    """Verify --help flag prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "usage:" in captured.out
    assert "--stdio" in captured.out
