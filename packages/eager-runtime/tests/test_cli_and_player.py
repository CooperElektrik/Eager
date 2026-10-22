"""Unit tests for Eager CLI commands and TerminalPlayer runner."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import eager_script

from eager_runtime import StoryVM, TerminalPlayer
from eager_runtime.cli import main

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
