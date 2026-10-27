"""Tests for eager_script CLI argument parsing and execution commands."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from eager_script.cli import build_parser, main

SAMPLE_SCRIPT = """
## The Clearing --- courtyard

# Ambient comment
Alice: Welcome to the ancient ruins!
? Examine the glowing runes (runes)
? Turn back towards town (exit)

## Ancient Runes --- runes
The runes shimmer with blue light.
> courtyard

## Town Exit --- exit
You head back to town.
"""


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "eager_script", *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_version() -> None:
    parser = build_parser()
    assert parser is not None


def test_cli_check_and_parse() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".es", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(SAMPLE_SCRIPT)
        tmp_path = tmp.name

    try:
        # Test check
        exit_code = main(["check", tmp_path])
        assert exit_code == 0

        # Test parse to file
        out_file = tmp_path + ".json"
        exit_code = main(["parse", tmp_path, "-o", out_file])
        assert exit_code == 0
        data = json.loads(Path(out_file).read_text(encoding="utf-8"))
        assert len(data) == 8
        Path(out_file).unlink(missing_ok=True)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def test_cli_graph_json_stdout() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
        f.write(SAMPLE_SCRIPT)
        f_path = f.name

    try:
        res = _run_cli("graph", f_path)
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert data["entry"] == "courtyard"
        assert "nodes" in data
        assert "edges" in data
        assert "body" in data["nodes"]["courtyard"]
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_cli_graph_no_body() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
        f.write(SAMPLE_SCRIPT)
        f_path = f.name

    try:
        res = _run_cli("graph", f_path, "--no-body")
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert "body" not in data["nodes"]["courtyard"]
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_cli_graph_dot_and_mermaid() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
        f.write(SAMPLE_SCRIPT)
        f_path = f.name

    try:
        # DOT format
        res_dot = _run_cli("graph", f_path, "--format", "dot")
        assert res_dot.returncode == 0
        assert "digraph SceneGraph {" in res_dot.stdout

        # Mermaid format
        res_mmd = _run_cli("graph", f_path, "--format", "mermaid")
        assert res_mmd.returncode == 0
        assert "flowchart TD" in res_mmd.stdout
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_cli_graph_output_file() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
        f.write(SAMPLE_SCRIPT)
        src_path = f.name

    out_path = Path(src_path + ".out.json")
    try:
        res = _run_cli("graph", src_path, "-o", str(out_path))
        assert res.returncode == 0
        assert out_path.exists()
        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["entry"] == "courtyard"
    finally:
        Path(src_path).unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)


def test_cli_graph_file_not_found() -> None:
    res = _run_cli("graph", "non_existent_file_12345.es")
    assert res.returncode == 1
    assert "File not found" in res.stderr
