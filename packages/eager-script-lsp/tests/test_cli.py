"""Unit tests for eager-script-lsp command-line interface and headless checker."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from eager_script_lsp import __version__
from eager_script_lsp.cli import build_parser, main


def test_cli_check_valid_script_exit_0():
    """Verify --check on a valid standalone script exits with code 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        script = root / "valid.es"
        script.write_text("## Scene 1 --- s1\nNarrator: Hello world\n> s1\n", encoding="utf-8")

        exit_code = main(["--check", str(script)])
        assert exit_code == 0


def test_cli_check_invalid_script_exit_1(capsys: pytest.CaptureFixture[str]):
    """Verify --check on a script with unresolved jump targets exits with code 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        script = root / "invalid.es"
        script.write_text("## Scene 1 --- s1\n> non_existent_label\n", encoding="utf-8")

        exit_code = main(["--check", str(script)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "non_existent_label" in captured.out
        assert "Check FAILED with errors" in captured.out


def test_cli_check_workspace_dir_valid_exit_0():
    """Verify --check on a multi-file workspace with cross-file links exits 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "ch1.es").write_text("## Chapter 1 --- ch1\n> ch2\n", encoding="utf-8")
        (root / "ch2.es").write_text("## Chapter 2 --- ch2\nNarrator: In chapter 2\n", encoding="utf-8")

        exit_code = main(["--check", str(root)])
        assert exit_code == 0


def test_cli_check_workspace_dir_duplicate_labels_exit_1(capsys: pytest.CaptureFixture[str]):
    """Verify --check on a directory containing duplicate scene IDs exits 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.es").write_text("## Scene A --- same_id\nNarrator: In A\n", encoding="utf-8")
        (root / "b.es").write_text("## Scene B --- same_id\nNarrator: In B\n", encoding="utf-8")

        exit_code = main(["--check", str(root)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "Duplicate scene label 'same_id'" in captured.out


def test_cli_check_nonexistent_path_exit_1(capsys: pytest.CaptureFixture[str]):
    """Verify --check on a missing path prints error to stderr and exits 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        missing_path = Path(tmpdir) / "does_not_exist.es"
        exit_code = main(["--check", str(missing_path)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err


def test_cli_check_non_es_path_exit_1(capsys: pytest.CaptureFixture[str]):
    """Verify --check on a non-.es file prints error to stderr and exits 1."""
    with tempfile.TemporaryDirectory() as tmpdir:
        txt_file = Path(tmpdir) / "story.txt"
        txt_file.write_text("Not an .es file", encoding="utf-8")
        exit_code = main(["--check", str(txt_file)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "is not an .es screenplay file" in captured.err


def test_cli_build_parser_options():
    """Verify CLI parser registers all server protocols and flags."""
    parser = build_parser()
    args_check = parser.parse_args(["--check", "scene.es"])
    assert args_check.check == "scene.es"

    args_tcp = parser.parse_args(["--tcp", "--host", "0.0.0.0", "--port", "5000"])
    assert args_tcp.tcp is True
    assert args_tcp.host == "0.0.0.0"
    assert args_tcp.port == 5000

    args_ws = parser.parse_args(["--ws"])
    assert args_ws.ws is True

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
    assert "--check" in captured.out

