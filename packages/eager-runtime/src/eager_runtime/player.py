"""Interactive terminal runner for playing Eager-S screenplays."""

from __future__ import annotations

import sys
from typing import IO

from eager_runtime.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    HookEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)
from eager_runtime.runtime import StoryVM
from eager_runtime.state import StorySnapshot


class TerminalPlayer:
    """Renders narrative story progression to a text terminal with interactive choice prompts."""

    def __init__(
        self,
        vm: StoryVM,
        *,
        input_stream: IO[str] | None = None,
        output_stream: IO[str] | None = None,
        use_colors: bool = True,
    ) -> None:
        self.vm = vm
        self.input_stream = input_stream or sys.stdin
        self.output_stream = output_stream or sys.stdout
        self.use_colors = use_colors and self.output_stream.isatty()
        self._saved_slot: StorySnapshot | None = None

    def _print(self, text: str = "") -> None:
        print(text, file=self.output_stream, flush=True)

    def _color(self, text: str, code: str) -> str:
        if not self.use_colors:
            return text
        return f"\033[{code}m{text}\033[0m"

    def play(self) -> None:
        """Run the interactive playthrough loop until completion or user quit."""
        self._print(self._color("--- EAGER NARRATIVE RUNNER ---", "1;36"))
        self._print(self._color("Commands: :undo (rewind), :save, :load, :vars, :q (quit)\n", "90"))

        while not self.vm.is_ended:
            event = self.vm.step()
            if event is None:
                break

            if isinstance(event, SceneEnterEvent):
                self._print(
                    self._color(f"\n[Scene: {event.display_name} ({event.scene_id})]", "1;34")
                )

            elif isinstance(event, DialogueEvent):
                emotion_part = f" ({event.emotion})" if event.emotion else ""
                speaker_str = self._color(f"{event.speaker}{emotion_part}", "1;32")
                voice_str = f" {self._color(f'[{event.voice}]', '35')}" if event.voice else ""
                self._print(f"{speaker_str}{voice_str}: {event.text}")

            elif isinstance(event, NarrationEvent):
                self._print(f"  {event.text}")

            elif isinstance(event, AppendEvent):
                self._print(f"  - {event.text}")

            elif isinstance(event, FreshBoxEvent):
                self._print(f"\n  / {event.text}")

            elif isinstance(event, HookEvent):
                args_str = f" {event.args}" if event.args else ""
                self._print(self._color(f"  [~ {event.hook_name}{args_str}]", "90"))

            elif isinstance(event, SceneExitEvent):
                pass

            elif isinstance(event, ChoicePromptEvent):
                self._print(self._color("\nChoices:", "1;33"))
                for opt in event.options:
                    self._print(f"  [{opt.index + 1}] {opt.text}")

                self._handle_choice_input(event)

            elif isinstance(event, StoryEndEvent):
                self._print(self._color(f"\n[The End: {event.reason}]", "1;32"))
                break

    def _handle_choice_input(self, prompt: ChoicePromptEvent) -> None:
        """Prompt user for choice selection or player commands."""
        while True:
            self.output_stream.write(self._color("Select option or command: ", "1;33"))
            self.output_stream.flush()

            try:
                line = self.input_stream.readline()
                if not line:
                    # End of input
                    self.vm.choose(0)
                    return
                cmd = line.strip()
            except (EOFError, KeyboardInterrupt):
                self._print("\nInterrupted.")
                self.vm.jump(prompt.options[0].target)
                return

            if not cmd:
                continue

            # Check built-in commands
            if cmd == ":q" or cmd == ":quit":
                self._print("Quitting story.")
                self.vm.choose(0)
                sys.exit(0)

            if cmd == ":save":
                self._saved_slot = self.vm.save()
                self._print(self._color("Game state saved to memory slot.", "32"))
                continue

            if cmd == ":load":
                if self._saved_slot is not None:
                    self.vm.load(self._saved_slot)
                    self._print(self._color("Loaded state from memory slot.", "32"))
                    return
                self._print(self._color("No saved state in slot.", "31"))
                continue

            if cmd == ":undo" or cmd == ":rollback":
                if self.vm.can_rollback:
                    self.vm.rollback()
                    self._print(self._color("Rewound state to previous beat.", "33"))
                    return
                self._print(self._color("Cannot rollback further.", "31"))
                continue

            if cmd == ":vars":
                self._print(self._color(f"Variables: {self.vm.variables}", "36"))
                continue

            # Attempt numeric choice
            if cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(prompt.options):
                    self.vm.choose(idx)
                    return
                self._print(self._color(f"Please select between 1 and {len(prompt.options)}.", "31"))
                continue

            # Attempt textual match
            found = False
            for opt in prompt.options:
                if cmd.lower() in opt.text.lower() or cmd.lower() == opt.target.lower():
                    self.vm.choose(opt.index)
                    found = True
                    return

            if not found:
                self._print(self._color("Invalid choice or command. Type 1, 2, ... or :q to quit.", "31"))
