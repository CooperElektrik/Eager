"""Tests for Phase 8 tooling: eager check, build, warp, and all-paths test-run."""

import zipfile
from pathlib import Path

import pytest

from eager_runtime.cli import main


def test_cli_check_valid_script(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    script = """## Start --- start
Narrator: All good.
> end
## End --- end
Narrator: Done.
"""
    sf = tmp_path / "valid.es"
    sf.write_text(script, encoding="utf-8")

    code = main(["check", str(sf)])
    assert code == 0
    captured = capsys.readouterr()
    assert "PASSED" in captured.out


def test_cli_check_invalid_script(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    script = """## Start
Narrator: Broken jump.
> nonexistent_target
"""
    sf = tmp_path / "invalid.es"
    sf.write_text(script, encoding="utf-8")

    code = main(["check", str(sf)])
    assert code == 1
    captured = capsys.readouterr()
    assert "FAILED" in captured.out
    assert "nonexistent_target" in captured.out


def test_cli_build_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    proj_dir = tmp_path / "my_game"
    proj_dir.mkdir()
    (proj_dir / "game.toml").write_text('[game]\ntitle = "Game"\nentry_script = "main.es"\n', encoding="utf-8")
    (proj_dir / "main.es").write_text("## Start\nNarrator: Hello\n", encoding="utf-8")
    (proj_dir / "assets").mkdir()
    (proj_dir / "assets" / "test.png").write_bytes(b"dummy")

    zip_out = tmp_path / "dist.zip"
    code = main(["build", str(proj_dir), "-o", str(zip_out)])
    assert code == 0
    assert zip_out.exists()

    with zipfile.ZipFile(zip_out, "r") as zf:
        names = zf.namelist()
        assert "game.toml" in names
        assert "main.es" in names
        assert "assets/test.png" in names


def test_cli_test_run_all_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    script = """## Start
Narrator: Choose a door.
? Door 1 (door1)
? Door 2 (door2)

## Door 1 --- door1
Narrator: Entered door 1.
? Left (left)
? Right (right)

## Door 2 --- door2
Narrator: Entered door 2.

## Left --- left
Narrator: Left ending.

## Right --- right
Narrator: Right ending.
"""
    sf = tmp_path / "branching.es"
    sf.write_text(script, encoding="utf-8")

    code = main(["test-run", str(sf), "--all-paths"])
    assert code == 0
    captured = capsys.readouterr()
    assert "All-paths exploration completed" in captured.out
    # There are 3 leaves: (Door 1 -> Left), (Door 1 -> Right), (Door 2)
    assert "3 paths explored" in captured.out
