"""Unit tests for TerminalPlayer runner."""

import io
import sys
from unittest.mock import patch

import eager_script

from eager_runtime import StoryVM, TerminalPlayer

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


def test_terminal_player_scripted_run() -> None:
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
    assert "Guard: State your business." in out
    assert "Guard: Welcome traveler." in out
    assert "[The End: terminal]" in out


def test_terminal_player_commands_save_and_undo() -> None:
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
    assert "Game state saved to memory slot." in out
    assert "Guard: En garde!" in out


def test_terminal_player_input_prompt_stream() -> None:
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
    assert "Guard: Who goes there?" in out
    assert "Guard: Welcome, Sir Robin!" in out
    assert vm.get_variable("traveler_name") == "Sir Robin"


def test_terminal_player_input_prompt_default_fallback() -> None:
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
    assert "Guard: Welcome, Traveler!" in out
    assert vm.get_variable("traveler_name") == "Traveler"


def test_terminal_player_input_prompt_eof_fallback() -> None:
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

    assert vm.get_variable("traveler_name") == "Traveler"


def test_terminal_player_choice_input_closed_stream() -> None:
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
    assert "Interrupted." in out
    assert "Guard: Welcome traveler." in out


def test_terminal_player_choice_input_os_error_stream() -> None:
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
    assert "Interrupted." in out
    assert "Guard: Welcome traveler." in out


def test_terminal_player_text_input_closed_stream() -> None:
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

    assert vm.get_variable("traveler_name") == "Traveler"


def test_terminal_player_text_input_os_error_stream() -> None:
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

    assert vm.get_variable("traveler_name") == "Traveler"


def test_terminal_player_text_input_stdin_value_error() -> None:
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

    assert vm.get_variable("traveler_name") == "Traveler"
