"""Unified game session controller and checkpoint manager for Eager visual novels."""

from __future__ import annotations

import collections
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eager_script import parse_graph

try:
    from eager_graphics.compositor import StageCompositor
    from eager_graphics.director import StageDirector
    from eager_graphics.renderers.null import NullRenderer
    from eager_graphics.ui_components import UIOverlay
    from eager_graphics.ui_state import UIState
except ImportError:
    StageCompositor = None  # type: ignore[assignment, misc]
    StageDirector = None  # type: ignore[assignment, misc]
    NullRenderer = None  # type: ignore[assignment, misc]
    UIOverlay = None  # type: ignore[assignment, misc]
    UIState = None  # type: ignore[assignment, misc]

from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    InputPromptEvent,
    NarrationEvent,
    StoryEvent,
)
from eager_runtime.input import InputAction, Keymap
from eager_runtime.persistent import PersistentData
from eager_runtime.preferences import Preferences
from eager_runtime.runtime import StoryVM
from eager_runtime.saves import SaveManager
from eager_runtime.state import StorySnapshot
from eager_runtime.storage import get_default_save_dir


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Unified state snapshot captured at an interactive point in the story."""

    story: dict[str, Any]
    visual: dict[str, Any]
    audio: dict[str, Any]
    backlog_len: int
    ui: dict[str, Any]
    active_input_prompt: dict[str, Any] | None = None


class CheckpointHistory:
    """Bounded history stack for interactive story checkpoints."""

    def __init__(self, max_history: int = 100) -> None:
        self._history: collections.deque[Checkpoint] = collections.deque(maxlen=max_history)

    def push(self, checkpoint: Checkpoint) -> None:
        """Add a checkpoint to the history."""
        self._history.append(checkpoint)

    def pop(self) -> Checkpoint | None:
        """Remove and return the most recent checkpoint."""
        if not self._history:
            return None
        return self._history.pop()

    def clear(self) -> None:
        """Clear all stored checkpoints."""
        self._history.clear()

    @property
    def can_rollback(self) -> bool:
        """True if there is at least one previous checkpoint to restore."""
        return len(self._history) > 1

    @property
    def depth(self) -> int:
        """Number of checkpoints stored."""
        return len(self._history)

    def get_latest(self) -> Checkpoint | None:
        """Inspect the top checkpoint without popping."""
        return self._history[-1] if self._history else None


class GameSession:
    """Backend-agnostic controller that coordinates narrative execution, compositor,
    director, audio, input handling, and checkpoints.
    """

    INTERACTION_TYPES = frozenset({
        "dialogue",
        "narration",
        "append",
        "fresh_box",
        "choice_prompt",
        "story_end",
        "input_prompt",
    })


    def __init__(
        self,
        project_or_script: str | Path | Any,
        *,
        backend: str = "null",
        audio_backend: Any = None,
        asset_dir: str | Path | None = None,
        virtual_width: int = 1920,
        virtual_height: int = 1080,
        plain: bool = False,
        rollback_limit: int = 100,
        config: Any = None,
    ) -> None:
        self.script_path = Path(project_or_script) if isinstance(project_or_script, (str, Path)) else None
        self.backend = backend
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self.plain = plain
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height

        # Parse scene graph
        if self.script_path is not None:
            text = self.script_path.read_text(encoding="utf-8")
            self.graph = parse_graph(text, plain=plain)
        elif hasattr(project_or_script, "graph"):
            self.graph = project_or_script.graph
        else:
            self.graph = project_or_script

        from eager_core.audio import AudioMixer

        if StageCompositor is None or StageDirector is None:
            raise ImportError(
                "eager_graphics is required for GameSession. "
                "Install eager-runtime[graphics] or eager-graphics."
            )

        self.vm = StoryVM(self.graph)
        self.dispatcher = EventDispatcher()
        self.compositor = StageCompositor(
            virtual_width=virtual_width,
            virtual_height=virtual_height,
        )
        self.audio = AudioMixer(backend=audio_backend, asset_dir=self.asset_dir)
        self.director = StageDirector(
            self.compositor,
            audio=self.audio,
            skip_mode_cb=lambda: self.skip_mode,
        )
        self.director.bind(self.dispatcher)

        self.checkpoints = CheckpointHistory(max_history=rollback_limit)
        self.keymap = Keymap()
        self.overlay = UIOverlay(width=1280, height=720)

        # Persistent state, preferences, and saves
        save_dir = get_default_save_dir(self.script_path.stem if self.script_path else "default")
        self.persistent = PersistentData(save_dir / "persistent.json")
        self.preferences = Preferences.load(save_dir / "preferences.json")
        self.apply_preferences()
        self.save_manager = SaveManager(save_dir)

        # Share persistent with VM
        self.vm.set_variable("persistent", self.persistent)

        # Screens and Theme
        from eager_graphics.screens import (
            HistoryScreen,
            PreferencesScreen,
            SaveLoadScreen,
            ScreenManager,
            TitleScreen,
        )

        self.screens = ScreenManager()
        self.screens.register(TitleScreen(title=getattr(config, "title", "Eager Visual Novel")))
        self.screens.register(SaveLoadScreen("save"))
        self.screens.register(SaveLoadScreen("load"))
        self.screens.register(PreferencesScreen())
        self.screens.register(HistoryScreen())

        from eager_runtime.backlog import Backlog

        self.backlog = Backlog(max_entries=200)

        # State flags
        self.mode: str = "game"  # "title", "game", "menu", "ended"
        self.skip_mode: bool = False
        self.skip_timer: float = 0.0
        self.auto_mode: bool = False
        self.auto_timer: float = 0.0
        self.ui_hidden: bool = False
        self.is_finished: bool = False
        self.active_choice_prompt: ChoicePromptEvent | None = None
        self.active_input_prompt: Any | None = None
        self.text_reveal: Any | None = None

        self._last_event: StoryEvent | None = None

    def apply_preferences(self) -> None:
        """Apply current preferences to audio mixer and other subsystems."""
        if hasattr(self, "audio") and self.audio is not None:
            self.audio.set_master_volume(self.preferences.master_volume)
            self.audio.set_channel_volume("music", self.preferences.music_volume)
            self.audio.set_channel_volume("sound", self.preferences.sfx_volume)
            self.audio.set_channel_volume("voice", self.preferences.voice_volume)

    def _capture_checkpoint(self) -> Checkpoint:
        """Generate a unified checkpoint of the current session state."""
        input_data = (
            self.active_input_prompt.to_dict()
            if self.active_input_prompt is not None and hasattr(self.active_input_prompt, "to_dict")
            else (copy.deepcopy(self.active_input_prompt) if self.active_input_prompt is not None else None)
        )
        return Checkpoint(
            story=self.vm.save().to_dict(),
            visual=self.director.save_visual_state(),
            audio=self.audio.save_state(),
            backlog_len=len(self.backlog),
            ui=self.director.ui_state.to_dict(),
            active_input_prompt=input_data,
        )

    def _restore_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Restore full session state from a checkpoint."""
        snap = StorySnapshot.from_dict(checkpoint.story)
        self.vm.load(snap)
        self.director.load_visual_state(checkpoint.visual)
        self.audio.load_state(checkpoint.audio)
        self.director.ui_state = UIState.from_dict(checkpoint.ui)
        if len(self.backlog.entries) > checkpoint.backlog_len:
            self.backlog.entries = self.backlog.entries[: checkpoint.backlog_len]

        self.active_choice_prompt = self.vm.pending_choice
        if self.vm.pending_input is not None:
            self.active_input_prompt = self.vm.pending_input
        elif checkpoint.active_input_prompt is not None:
            inp = checkpoint.active_input_prompt
            if isinstance(inp, dict):
                self.active_input_prompt = InputPromptEvent(
                    var_name=inp.get("var_name", "player_input"),
                    prompt=inp.get("prompt", "Enter input:"),
                    default=inp.get("default", ""),
                    line_number=inp.get("line_number", 0),
                )
            else:
                self.active_input_prompt = inp
        else:
            self.active_input_prompt = None

        self.is_finished = self.vm.is_ended
        self.mode = "ended" if self.is_finished else "game"

    def _setup_text_reveal(self, text: str) -> None:
        """Initialize typewriter text reveal based on user preferences."""
        if self.skip_mode or not text:
            self.text_reveal = None
            self.director.ui_state.visible_chars = None
            return

        cps = float(getattr(self.preferences, "text_speed", 50.0))
        if cps <= 0.0:
            self.text_reveal = None
            self.director.ui_state.visible_chars = None
            return

        from eager_core.text import TextReveal, parse_text_tags

        fmt = parse_text_tags(text)
        self.text_reveal = TextReveal(fmt, chars_per_second=cps)
        self.director.ui_state.visible_chars = int(self.text_reveal.visible_chars)

    def advance(self) -> StoryEvent | None:
        """Step the VM forward until the next interactive event, dispatching all
        intermediate events, and record a checkpoint at the new interaction point.
        """
        if self.is_finished or self.vm.is_ended:
            self.is_finished = True
            self.mode = "ended"
            return None

        if self.active_choice_prompt is not None:
            # Cannot advance while awaiting choice selection
            return self.active_choice_prompt

        if self.active_input_prompt is not None:
            # Cannot advance while awaiting text input
            return self.active_input_prompt

        while not self.vm.is_ended:
            event = self.vm.step()
            if event is None:
                self.is_finished = True
                self.mode = "ended"
                break

            self.dispatcher.dispatch(event)
            self._last_event = event

            # Record into backlog
            if isinstance(event, DialogueEvent):
                self.backlog.add(event.speaker, event.text, voice=event.voice, emotion=event.emotion)
            elif isinstance(event, NarrationEvent):
                self.backlog.add(None, event.text)
            elif isinstance(event, AppendEvent):
                self.backlog.append_to_last(event.text)

            if event.type in self.INTERACTION_TYPES:
                if event.type in ("dialogue", "narration", "fresh_box"):
                    self._setup_text_reveal(getattr(event, "text", ""))
                elif event.type == "append":
                    self._setup_text_reveal(self.director.ui_state.text)
                elif event.type in ("choice_prompt", "input_prompt", "story_end"):
                    self.text_reveal = None
                    self.director.ui_state.visible_chars = None

                if event.type == "choice_prompt":
                    self.active_choice_prompt = event
                elif event.type == "input_prompt":
                    self.active_input_prompt = event
                elif event.type == "story_end":
                    self.is_finished = True
                    self.mode = "ended"

                # Push checkpoint after reaching interaction
                self.checkpoints.push(self._capture_checkpoint())
                return event

        if self.vm.is_ended:
            self.is_finished = True
            self.mode = "ended"
            self.checkpoints.push(self._capture_checkpoint())

        return None

    def submit_input(self, value: str) -> StoryEvent | None:
        """Submit user text input for active input prompt and advance."""
        if self.active_input_prompt is None:
            return None
        var_name = getattr(self.active_input_prompt, "var_name", "player_input")
        self.vm.set_variable(var_name, value)
        self.active_input_prompt = None
        return self.advance()

    def choose(self, choice: int | str) -> StoryEvent | None:
        """Make a branching choice and advance to the next interactive point."""
        if self.active_choice_prompt is None:
            return None

        self.vm.choose(choice)
        self.active_choice_prompt = None
        return self.advance()


    def save_game(self, slot_name: str) -> Any:
        """Save current checkpoint to named slot."""
        cp = self.checkpoints.get_latest() or self._capture_checkpoint()
        return self.save_manager.save_slot(slot_name, cp)

    def load_game(self, slot_name: str) -> bool:
        """Load game from named slot."""
        cp = self.save_manager.load_slot(slot_name)
        if cp is None:
            return False
        self._restore_checkpoint(cp)
        self.checkpoints.clear()
        self.checkpoints.push(cp)
        return True

    def quicksave(self) -> Any:
        """Quicksave current checkpoint."""
        cp = self.checkpoints.get_latest() or self._capture_checkpoint()
        return self.save_manager.quicksave(cp)

    def quickload(self) -> bool:
        """Quickload from quicksave slot."""
        cp = self.save_manager.quickload()
        if cp is None:
            return False
        self._restore_checkpoint(cp)
        self.checkpoints.clear()
        self.checkpoints.push(cp)
        return True

    def rollback(self) -> bool:
        """Roll back to the previous interactive checkpoint."""
        if not self.checkpoints.can_rollback:
            return False

        # Pop current checkpoint
        self.checkpoints.pop()
        prev = self.checkpoints.get_latest()
        if prev is None:
            return False

        self._restore_checkpoint(prev)
        self.text_reveal = None
        self.director.ui_state.visible_chars = None
        return True

    def update(self, dt: float) -> None:
        """Update animation timelines, compositor, audio, typewriter reveal, and timers."""
        self.compositor.step(dt)
        self.audio.update(dt)

        # Update typewriter text reveal
        if self.text_reveal is not None and not self.text_reveal.is_complete:
            self.text_reveal.update(dt)
            if self.text_reveal.is_complete:
                self.director.ui_state.visible_chars = None
            else:
                self.director.ui_state.visible_chars = int(self.text_reveal.visible_chars)

        # Skip mode advances immediately until player choices or story ends
        if self.skip_mode and not self.is_finished:
            if self.text_reveal is not None:
                self.text_reveal.complete_immediately()
                self.director.ui_state.visible_chars = None
            while self.skip_mode and not self.is_finished and self.active_choice_prompt is None:
                self.advance()
        elif self.auto_mode and not self.is_finished and self.active_choice_prompt is None:
            self.auto_timer += dt
            threshold = getattr(self.preferences, "auto_forward_time", 3.0)
            if self.auto_timer >= threshold:
                self.auto_timer = 0.0
                if self.text_reveal is not None:
                    self.text_reveal.complete_immediately()
                    self.director.ui_state.visible_chars = None
                self.advance()

    def draw(self, ui_backend: Any, width: int, height: int) -> None:
        """Draw the stage compositor and UI chrome through the given renderer / backend."""
        if hasattr(ui_backend, "render_compositor"):
            ui_backend.render_compositor(self.compositor, width, height)

        status_badge: str | None = None
        if self.skip_mode:
            status_badge = "SKIP >>"
        elif self.auto_mode:
            status_badge = "AUTO >"

        if not self.ui_hidden:
            self.overlay.set_viewport(width, height)
            self.overlay.draw(
                ui_backend,
                self.director.ui_state,
                self.active_choice_prompt,
                is_finished=self.is_finished,
                show_quick_menu=True,
                status_badge=status_badge,
            )

        # Draw active screen on top
        if hasattr(self, "screens") and self.screens.active_screen:
            self.screens.draw(ui_backend, width, height)

    def _handle_quick_action(self, action_name: str) -> Any:
        """Handle clicks on the in-game quick menu buttons."""
        if action_name == "log":
            if hasattr(self, "screens"):
                return self.screens.show("history", self)
        elif action_name == "skip":
            self.skip_mode = not self.skip_mode
            return self.skip_mode
        elif action_name == "auto":
            self.auto_mode = not self.auto_mode
            return self.auto_mode
        elif action_name == "save":
            if hasattr(self, "screens"):
                return self.screens.show("save", self)
        elif action_name == "load":
            if hasattr(self, "screens"):
                return self.screens.show("load", self)
        elif action_name == "quicksave":
            return self.quicksave()
        elif action_name == "quickload":
            return self.quickload()
        elif action_name == "prefs" and hasattr(self, "screens"):
            return self.screens.show("preferences", self)
        return None

    def handle_input(self, action: InputAction, **payload: Any) -> Any:
        """Process semantic InputAction events."""
        # 1. Screen active intercepts:
        if hasattr(self, "screens") and self.screens.is_active:
            if action in (InputAction.GAME_MENU, InputAction.CANCEL):
                self.screens.hide(self)
                return True
            if action in (InputAction.ROLLBACK, InputAction.NAV_UP):
                active = self.screens.active_screen
                if hasattr(active, "scroll_up"):
                    active.scroll_up()
                    return True
            if action in (InputAction.ROLL_FORWARD, InputAction.NAV_DOWN):
                active = self.screens.active_screen
                if hasattr(active, "scroll_down"):
                    active.scroll_down()
                    return True
            if action == InputAction.POINTER_CLICK:
                x = payload.get("x", 0.0)
                y = payload.get("y", 0.0)
                return self.screens.handle_mouse_click(x, y)
            if action == InputAction.POINTER_MOVE:
                x = payload.get("x", 0.0)
                y = payload.get("y", 0.0)
                self.screens.handle_mouse_move(x, y)
                return True
            return None

        # 2. In-game interactions:
        # Choice menu keyboard navigation
        if self.active_choice_prompt is not None and self.active_choice_prompt.options:
            opts_count = len(self.active_choice_prompt.options)
            if action == InputAction.NAV_UP:
                cur = self.overlay.choice_menu.selected_index
                self.overlay.choice_menu.selected_index = (
                    opts_count - 1 if cur is None else (cur - 1) % opts_count
                )
                return True
            elif action == InputAction.NAV_DOWN:
                cur = self.overlay.choice_menu.selected_index
                self.overlay.choice_menu.selected_index = (
                    0 if cur is None else (cur + 1) % opts_count
                )
                return True
            elif action in (InputAction.ADVANCE, InputAction.CONFIRM):
                if self.overlay.choice_menu.selected_index is not None:
                    idx = self.overlay.choice_menu.selected_index
                    self.overlay.choice_menu.selected_index = None
                    return self.choose(idx)

        # Advance / Typewriter completion
        if action in (InputAction.ADVANCE, InputAction.CONFIRM):
            if self.text_reveal is not None and not self.text_reveal.is_complete:
                self.text_reveal.complete_immediately()
                self.director.ui_state.visible_chars = None
                self.overlay.dialogue_box.visible_chars = None
                self.overlay.dialogue_box.show_advance_arrow = (self.active_choice_prompt is None)
                return True
            if self.active_choice_prompt is None and self.active_input_prompt is None:
                return self.advance()
        elif action == InputAction.ROLLBACK:
            return self.rollback()
        elif action == InputAction.CHOOSE:
            idx = payload.get("index")
            if idx is not None:
                return self.choose(idx)
        elif action == InputAction.HIDE_UI:
            self.ui_hidden = not self.ui_hidden
            return self.ui_hidden
        elif action == InputAction.SKIP_TOGGLE:
            self.skip_mode = not self.skip_mode
            return self.skip_mode
        elif action == InputAction.SKIP_HOLD:
            self.skip_mode = True
            return True
        elif action == InputAction.SKIP_RELEASE:
            self.skip_mode = False
            return True
        elif action == InputAction.AUTO_TOGGLE:
            self.auto_mode = not self.auto_mode
            return self.auto_mode
        elif action == InputAction.QUICK_SAVE:
            return self.quicksave()
        elif action == InputAction.QUICK_LOAD:
            return self.quickload()
        elif action == InputAction.GAME_MENU:
            if hasattr(self, "screens"):
                return self.screens.show("save", self)
        elif action == InputAction.HISTORY:
            if hasattr(self, "screens"):
                return self.screens.show("history", self)
        elif action == InputAction.POINTER_CLICK:
            x = payload.get("x", 0.0)
            y = payload.get("y", 0.0)
            # Check quick action bar in UIOverlay
            if not self.ui_hidden:
                qa = self.overlay.hit_test_quick_action(x, y)
                if qa:
                    return self._handle_quick_action(qa)
            # Check choices
            if self.active_choice_prompt is not None:
                idx = self.overlay.hit_test_choice(x, y)
                if idx is not None:
                    return self.choose(idx)
                return None
            # Check typewriter reveal completion
            if self.text_reveal is not None and not self.text_reveal.is_complete:
                self.text_reveal.complete_immediately()
                self.director.ui_state.visible_chars = None
                self.overlay.dialogue_box.visible_chars = None
                self.overlay.dialogue_box.show_advance_arrow = (self.active_choice_prompt is None)
                return True
            # Otherwise advance
            if self.active_choice_prompt is None and self.active_input_prompt is None:
                return self.advance()
        elif action == InputAction.POINTER_MOVE:
            return None
        return None
