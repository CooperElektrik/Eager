"""Unit tests for Eager CLI commands and TerminalPlayer runner."""

import argparse
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import eager_script
import pytest

from eager_runtime import StoryVM, TerminalPlayer
from eager_runtime.cli import _cmd_build, main

TEST_SCRIPT = """
## Courtyard --- courtyard
Guard: State your business.
? Enter peacefully (peace)
? Draw sword (fight)

## Peace --- peace
Guard: Welcome traveler.

## Fight --- fight
Guard: En garde!
"""

INPUT_TEST_SCRIPT = """
## Welcome --- welcome
Guard: Who goes there?
~ input traveler_name "State your name:" default="Traveler"
Guard: Welcome, [traveler_name]!
"""


class TestCLIAndPlayer(unittest.TestCase):
    def test_terminal_player_scripted_run(self) -> None:
        graph = eager_script.parse_graph(TEST_SCRIPT)
        vm = StoryVM(graph)

        # Simulate user typing "1" for the choice
        fake_input = io.StringIO("1\n")
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=fake_input,
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        out = fake_output.getvalue()
        self.assertIn("Guard: State your business.", out)
        self.assertIn("Guard: Welcome traveler.", out)
        self.assertIn("[The End: terminal]", out)

    def test_terminal_player_commands_save_and_undo(self) -> None:
        graph = eager_script.parse_graph(TEST_SCRIPT)
        vm = StoryVM(graph)

        # Simulate user saving state, undoing, then picking choice 2
        fake_input = io.StringIO(":save\n:undo\n2\n")
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=fake_input,
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        out = fake_output.getvalue()
        self.assertIn("Game state saved to memory slot.", out)
        self.assertIn("Guard: En garde!", out)

    def test_terminal_player_input_prompt_stream(self) -> None:
        graph = eager_script.parse_graph(INPUT_TEST_SCRIPT)
        vm = StoryVM(graph)

        fake_input = io.StringIO("Sir Robin\n")
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=fake_input,
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        out = fake_output.getvalue()
        self.assertIn("Guard: Who goes there?", out)
        self.assertIn("Guard: Welcome, Sir Robin!", out)
        self.assertEqual(vm.get_variable("traveler_name"), "Sir Robin")

    def test_terminal_player_input_prompt_default_fallback(self) -> None:
        graph = eager_script.parse_graph(INPUT_TEST_SCRIPT)
        vm = StoryVM(graph)

        # Empty line should trigger fallback to default "Traveler"
        fake_input = io.StringIO("\n")
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=fake_input,
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        out = fake_output.getvalue()
        self.assertIn("Guard: Welcome, Traveler!", out)
        self.assertEqual(vm.get_variable("traveler_name"), "Traveler")

    def test_terminal_player_input_prompt_eof_fallback(self) -> None:
        graph = eager_script.parse_graph(INPUT_TEST_SCRIPT)
        vm = StoryVM(graph)

        # EOF (empty stream) triggers fallback to default
        fake_input = io.StringIO("")
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=fake_input,
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        self.assertEqual(vm.get_variable("traveler_name"), "Traveler")

    def test_cli_inspect_command(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".es", delete=False) as f:
            f.write(TEST_SCRIPT)
            path = f.name

        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["inspect", path])
                self.assertEqual(code, 0)
                output = mock_out.getvalue()
                self.assertIn("Entry Scene: courtyard", output)
                self.assertIn("Total Scenes: 3", output)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_cli_test_run_command(self) -> None:
        with tempfile.NamedTemporaryFile("w+", suffix=".es", delete=False) as f:
            f.write(TEST_SCRIPT)
            path = f.name

        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["test-run", path])
                self.assertEqual(code, 0)
                output = mock_out.getvalue()
                self.assertIn("Test run completed", output)
                self.assertIn("ended: True", output)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_cli_file_not_found(self) -> None:
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            code = main(["inspect", "non_existent_file.es"])
            self.assertEqual(code, 1)
            self.assertIn("not found", mock_err.getvalue())

    def test_cli_new_default_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            proj_path = Path(tmp_dir) / "test_novel"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["new", str(proj_path)])
                self.assertEqual(code, 0)
                out = mock_out.getvalue()
                self.assertIn("Created new Eager project", out)

            self.assertTrue((proj_path / "game.toml").is_file())
            self.assertTrue((proj_path / "main.es").is_file())
            self.assertTrue((proj_path / "assets" / "bg" / "classroom.jpg").is_file())
            self.assertTrue((proj_path / "assets" / "characters" / "guide" / "default.png").is_file())

            # Validate that the generated project passes validation with 0 errors
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                check_code = main(["check", str(proj_path), "--assets"])
                self.assertEqual(check_code, 0)
                check_out = mock_out.getvalue()
                self.assertIn("validation PASSED", check_out)
                self.assertIn("All referenced assets resolved successfully", check_out)

    def test_cli_new_demo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            proj_path = Path(tmp_dir) / "test_demo"
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                code = main(["new", str(proj_path), "--demo"])
                self.assertEqual(code, 0)
                out = mock_out.getvalue()
                self.assertIn("demo showcase project", out)

            self.assertTrue((proj_path / "game.toml").is_file())
            self.assertTrue((proj_path / "main.es").is_file())
            self.assertTrue((proj_path / "assets" / "hoshiko" / "default.png").is_file())

    def test_cli_new_existing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            proj_path = Path(tmp_dir) / "existing"
            proj_path.mkdir()
            with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
                code = main(["new", str(proj_path)])
                self.assertEqual(code, 1)
                self.assertIn("already exists", mock_err.getvalue())

    def test_cmd_run_passes_config_with_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            proj_path = Path(tmp_dir) / "themed_proj"
            proj_path.mkdir()
            (proj_path / "game.toml").write_text(
                """[game]
title = "Themed Story"
theme = "slate"
entry_script = "story.es"

[theme]
accent_color = "#ff8800"
""",
                encoding="utf-8",
            )
            (proj_path / "story.es").write_text(
                "## Start --- start\nNarrator: Hello\n",
                encoding="utf-8",
            )
            with patch("eager_runtime.session.GameSession") as mock_session_cls, patch(
                "eager_runtime.cli._run_interactive_player"
            ):
                code = main(["run", str(proj_path)])
                self.assertEqual(code, 0)
                mock_session_cls.assert_called_once()
                call_kwargs = mock_session_cls.call_args.kwargs
                self.assertIn("config", call_kwargs)
                cfg = call_kwargs["config"]
                self.assertEqual(cfg.title, "Themed Story")
                self.assertEqual(cfg.theme, "slate")
                self.assertIn("accent_color", cfg.theme_overrides)

    def test_terminal_player_choice_input_closed_stream(self) -> None:
        graph = eager_script.parse_graph(TEST_SCRIPT)
        vm = StoryVM(graph)

        closed_input = io.StringIO("1\n")
        closed_input.close()
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=closed_input,
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        out = fake_output.getvalue()
        self.assertIn("Interrupted.", out)
        self.assertIn("Guard: Welcome traveler.", out)

    def test_terminal_player_choice_input_os_error_stream(self) -> None:
        class ErrorStream(io.StringIO):
            def readline(self, size: int = -1, /) -> str:
                raise OSError("Stream I/O error")

        graph = eager_script.parse_graph(TEST_SCRIPT)
        vm = StoryVM(graph)
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=ErrorStream(),
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        out = fake_output.getvalue()
        self.assertIn("Interrupted.", out)
        self.assertIn("Guard: Welcome traveler.", out)

    def test_terminal_player_text_input_closed_stream(self) -> None:
        graph = eager_script.parse_graph(INPUT_TEST_SCRIPT)
        vm = StoryVM(graph)

        closed_input = io.StringIO("Sir Gawain\n")
        closed_input.close()
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=closed_input,
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        self.assertEqual(vm.get_variable("traveler_name"), "Traveler")

    def test_terminal_player_text_input_os_error_stream(self) -> None:
        class ErrorStream(io.StringIO):
            def readline(self, size: int = -1, /) -> str:
                raise OSError("Custom pipe broken")

        graph = eager_script.parse_graph(INPUT_TEST_SCRIPT)
        vm = StoryVM(graph)
        fake_output = io.StringIO()

        player = TerminalPlayer(
            vm,
            input_stream=ErrorStream(),
            output_stream=fake_output,
            use_colors=False,
        )
        player.play()

        self.assertEqual(vm.get_variable("traveler_name"), "Traveler")

    def test_terminal_player_text_input_stdin_value_error(self) -> None:
        graph = eager_script.parse_graph(INPUT_TEST_SCRIPT)
        vm = StoryVM(graph)

        player = TerminalPlayer(
            vm,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
            use_colors=False,
        )
        with patch("builtins.input", side_effect=ValueError("I/O operation on closed file")):
            player.play()

        self.assertEqual(vm.get_variable("traveler_name"), "Traveler")


def test_cli_check_valid_script(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_cli_check_invalid_script(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_cli_build_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_cli_test_run_all_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_cli_play_warp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    script = """## Start --- start
Narrator: Hello.
> next_scene

## Next Scene --- next_scene
Narrator: At next scene.
"""
    sf = tmp_path / "warp.es"
    sf.write_text(script, encoding="utf-8")

    import eager_runtime.cli

    monkeypatch.setattr(eager_runtime.cli, "_run_interactive_player", lambda session, backend: None)

    code = main(["play", str(sf), "--warp", "next_scene", "--backend", "pil"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Warped directly to scene 'next_scene'" in captured.err


def test_cmd_build_excludes_output_zip(tmp_path: Path) -> None:
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    (proj_dir / "game.toml").write_text('[game]\ntitle = "Test"\n', encoding="utf-8")
    (proj_dir / "main.es").write_text("## Start --- start\nNarrator: Test.\n", encoding="utf-8")

    out_zip = proj_dir / "dist.zip"
    args = argparse.Namespace(project_dir=str(proj_dir), output=str(out_zip))
    res = _cmd_build(args)
    assert res == 0
    assert out_zip.exists()

    with zipfile.ZipFile(out_zip, "r") as zf:
        names = zf.namelist()
        assert "dist.zip" not in names
        assert "main.es" in names
        assert "game.toml" in names


