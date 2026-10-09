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
