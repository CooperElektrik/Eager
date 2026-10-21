"""Unified game session controller and checkpoint manager for Eager visual novels."""

from __future__ import annotations

import collections
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    InputPromptEvent,
    NarrationEvent,
    StoryEvent,
)
from eager_core.input import InputAction, Keymap
from eager_core.protocols import (
    ScreenManagerProtocol,
    StageProtocol,
    UIProtocol,
)
from eager_core.storage import get_default_save_dir
from eager_script import parse_graph

from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.headless import (
    HeadlessUIState,
    NullCompositor,
    NullScreenManager,
    NullStage,
    NullUI,
)
from eager_runtime.persistent import PersistentData
from eager_runtime.preferences import Preferences
from eager_runtime.runtime import StoryVM
from eager_runtime.saves import SaveManager
from eager_runtime.state import StorySnapshot


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
    """Bounded history stack for interactive story checkpoints with redo support."""

    def __init__(self, max_history: int = 100) -> None:
        self.max_history = max_history
        self._history: collections.deque[Checkpoint] = collections.deque(maxlen=max_history)
        self._redo_stack: list[Checkpoint] = []

    def push(self, checkpoint: Checkpoint) -> None:
        """Add a checkpoint to the history and clear redo stack."""
        self._history.append(checkpoint)
        self._redo_stack.clear()

    def pop(self) -> Checkpoint | None:
        """Remove and return the most recent checkpoint, preserving it on redo stack."""
        if not self._history:
            return None
        cp = self._history.pop()
        self._redo_stack.append(cp)
        return cp

    def roll_forward(self) -> Checkpoint | None:
        """Pop a checkpoint from redo stack and push it back to history."""
        if not self._redo_stack:
            return None
        cp = self._redo_stack.pop()
        self._history.append(cp)
        return cp

    def clear(self) -> None:
        """Clear all stored checkpoints and redo stack."""
        self._history.clear()
        self._redo_stack.clear()

    def clear_redo(self) -> None:
        """Clear only the redo stack."""
        self._redo_stack.clear()

    @property
    def can_rollback(self) -> bool:
        """True if there is at least one previous checkpoint to restore."""
        return len(self._history) > 1

    @property
    def can_roll_forward(self) -> bool:
        """True if there is at least one popped checkpoint that can be restored forward."""
        return len(self._redo_stack) > 0

    @property
    def depth(self) -> int:
        """Number of checkpoints stored in history."""
        return len(self._history)

    def get_latest(self) -> Checkpoint | None:
        """Inspect the top checkpoint without popping."""
        return self._history[-1] if self._history else None


def _create_default_stage(
    virtual_width: int,
    virtual_height: int,
    audio: Any,
    skip_mode_cb: Any,
) -> StageProtocol:
    try:
        from eager_graphics.compositor import StageCompositor
        from eager_graphics.director import StageDirector

        compositor = StageCompositor(
            virtual_width=virtual_width,
            virtual_height=virtual_height,
        )
        return StageDirector(compositor, audio=audio, skip_mode_cb=skip_mode_cb)
    except ImportError:
        return NullStage(virtual_width=virtual_width, virtual_height=virtual_height)


def _create_default_ui(width: int = 1280, height: int = 720) -> UIProtocol:
    try:
        from eager_graphics.ui_components import UIOverlay

        return UIOverlay(width=width, height=height)
    except ImportError:
        return NullUI(width=width, height=height)


def _create_default_screens(config: Any, session: Any) -> ScreenManagerProtocol:
    try:
        from eager_graphics.screens import (
            HistoryScreen,
            PreferencesScreen,
            SaveLoadScreen,
            ScreenManager,
            TitleScreen,
        )

        w = getattr(getattr(session, "overlay", None), "width", 1280) or 1280
        h = getattr(getattr(session, "overlay", None), "height", 720) or 720
        mgr = ScreenManager(viewport_width=w, viewport_height=h)
        mgr.register(TitleScreen(title=getattr(config, "title", "Eager Visual Novel"), viewport_width=w, viewport_height=h))
        mgr.register(SaveLoadScreen("save", viewport_width=w, viewport_height=h))
        mgr.register(SaveLoadScreen("load", viewport_width=w, viewport_height=h))
        mgr.register(PreferencesScreen(viewport_width=w, viewport_height=h))
        mgr.register(HistoryScreen(viewport_width=w, viewport_height=h))
        return mgr
    except ImportError:
        return NullScreenManager()


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
        rollback_limit: int = 100,
        config: Any = None,
        auto_reload: bool = False,
        watch: bool = False,
        save_dir: str | Path | None = None,
        stage: StageProtocol | None = None,
        ui: UIProtocol | None = None,
        screens: ScreenManagerProtocol | None = None,
    ) -> None:
        self.script_path = Path(project_or_script) if isinstance(project_or_script, (str, Path)) else None
        self.backend = backend
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self._custom_save_dir = Path(save_dir) if save_dir is not None else None
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height
        self.auto_reload = auto_reload or watch
        self._ui_dirty: bool = True

        # Parse scene graph
        if self.script_path is not None:
            text = self.script_path.read_text(encoding="utf-8")
            self.graph: Any = parse_graph(text)
        elif hasattr(project_or_script, "graph"):
            self.graph = project_or_script.graph
        else:
            self.graph = project_or_script

        from eager_core.audio import AudioMixer
        from eager_core.i18n import TranslationManager

        self.translation_manager = TranslationManager()
        locales_dir: Path | None = None
        if self.script_path is not None:
            candidate = self.script_path.resolve().parent / "locales"
            if candidate.is_dir():
                locales_dir = candidate
        if locales_dir is not None:
            self.translation_manager.load_directory(locales_dir)

        if isinstance(project_or_script, StoryVM):
            self.vm = project_or_script
            self.vm.disable_history()
        else:
            self.vm = StoryVM(
                self.graph,
                translation_manager=self.translation_manager,
                enable_history=False,
            )
        self.dispatcher = EventDispatcher()
        self.audio = AudioMixer(backend=audio_backend, asset_dir=self.asset_dir)

        if stage is not None:
            self.stage: StageProtocol = stage
        else:
            self.stage = _create_default_stage(
                virtual_width=virtual_width,
                virtual_height=virtual_height,
                audio=self.audio,
                skip_mode_cb=lambda: self.skip_mode,
            )
        self.director: Any = self.stage
        self.compositor: Any = getattr(self.stage, "compositor", None)
        if self.compositor is None:
            self.compositor = NullCompositor(virtual_width=virtual_width, virtual_height=virtual_height)
        if hasattr(self.stage, "bind"):
            self.stage.bind(self.dispatcher)

        if (
            hasattr(self.graph, "characters")
            and isinstance(self.graph.characters, dict)
            and hasattr(self.director, "register_character")
            and callable(self.director.register_character)
        ):
            for cid, cinfo in self.graph.characters.items():
                attrs = cinfo.get("attrs", {}) if isinstance(cinfo, dict) else {}
                name = cinfo.get("name") if isinstance(cinfo, dict) else None
                self.director.register_character(
                    cid,
                    name=name,
                    asset_prefix=attrs.get("asset_prefix"),
                    default_expression=attrs.get("default_expression", "default"),
                    default_position=attrs.get("default_position", "center"),
                    side_image=attrs.get("side_image"),
                    color=attrs.get("color"),
                )

        self.checkpoints = CheckpointHistory(max_history=rollback_limit)
        self.keymap = Keymap()
        self.ui: UIProtocol = ui if ui is not None else _create_default_ui(width=1280, height=720)
        self.overlay: Any = self.ui

        # Persistent state, preferences, and saves
        save_dir = (
            self._custom_save_dir
            if self._custom_save_dir is not None
            else get_default_save_dir(self.script_path.stem if self.script_path else "default")
        )
        self.persistent = PersistentData(save_dir / "persistent.json")
        self.preferences = Preferences.load(save_dir / "preferences.json")
        self.apply_preferences()
        self.save_manager = SaveManager(save_dir)

        # Share persistent with VM
        self.vm.set_variable("persistent", self.persistent)

        # Screens and Theme
        self.screens: ScreenManagerProtocol = (
            screens if screens is not None else _create_default_screens(config, self)
        )

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
        self.input_text: str = ""
        self.text_reveal: Any | None = None

        self._last_event: StoryEvent | None = None
        self._current_beat_previously_seen: bool = False
        if self.script_path is not None:
            from eager_runtime.watcher import FileWatcher

            self.watcher: FileWatcher | None = FileWatcher(self.script_path)
        else:
            self.watcher = None

    def apply_preferences(self) -> None:
        """Apply current preferences to audio mixer, translation locale, and subsystems."""
        if hasattr(self, "audio") and self.audio is not None:
            self.audio.set_master_volume(self.preferences.master_volume)
            self.audio.set_channel_volume("music", self.preferences.music_volume)
            self.audio.set_channel_volume("sound", self.preferences.sfx_volume)
            self.audio.set_channel_volume("voice", self.preferences.voice_volume)
        if hasattr(self, "vm") and self.vm is not None:
            self.vm.set_locale(self.preferences.language)

    def set_language(self, locale: str) -> None:
        """Switch active language locale, updating VM and persisting preferences."""
        self.preferences.language = locale
        self.apply_preferences()
        self.preferences.save(self.save_manager.save_dir / "preferences.json")

    def play_voice(self, voice_path: str) -> None:
        """Replay a voice clip on the voice channel."""
        if hasattr(self, "audio") and self.audio is not None:
            self.audio.play("voice", str(voice_path), loop=False)

    def _capture_checkpoint(self) -> Checkpoint:
        """Generate a unified checkpoint of the current session state."""
        input_data = (
            self.active_input_prompt.to_dict()
            if self.active_input_prompt is not None and hasattr(self.active_input_prompt, "to_dict")
            else (copy.deepcopy(self.active_input_prompt) if self.active_input_prompt is not None else None)
        )
        visual_state = (
            self.director.save_visual_state()
            if hasattr(self.director, "save_visual_state")
            else {}
        )
        if hasattr(self.director, "save_ui_state"):
            ui_state_dict = self.director.save_ui_state()
        elif hasattr(self.director, "ui_state") and hasattr(self.director.ui_state, "to_dict"):
            ui_state_dict = self.director.ui_state.to_dict()
        else:
            ui_state_dict = {}

        return Checkpoint(
            story=self.vm.save().to_dict(),
            visual=visual_state,
            audio=self.audio.save_state(),
            backlog_len=len(self.backlog),
            ui=ui_state_dict,
            active_input_prompt=input_data,
        )

    def _restore_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Restore full session state from a checkpoint."""
        snap = StorySnapshot.from_dict(checkpoint.story)
        self.vm.load(snap)
        if hasattr(self.director, "load_visual_state"):
            self.director.load_visual_state(checkpoint.visual)
        self.audio.load_state(checkpoint.audio)

        if hasattr(self.director, "restore_ui_state"):
            self.director.restore_ui_state(checkpoint.ui)
        elif hasattr(self.director, "ui_state") and hasattr(self.director.ui_state, "from_dict"):
            self.director.ui_state = self.director.ui_state.from_dict(checkpoint.ui)
        else:
            try:
                from eager_graphics.ui_state import UIState

                self.director.ui_state = UIState.from_dict(checkpoint.ui)
            except ImportError:
                self.director.ui_state = HeadlessUIState.from_dict(checkpoint.ui)

        if hasattr(self.director, "ui_state"):
            self.director.ui_state.visible_chars = None
        self.text_reveal = None
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

        if self.active_input_prompt is not None:
            self.input_text = getattr(self.active_input_prompt, "default", "")
        else:
            self.input_text = ""

        self.is_finished = self.vm.is_ended
        self.mode = "ended" if self.is_finished else "game"

    def _setup_text_reveal(self, text: str, initial_visible_chars: int = 0) -> None:
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
        self.text_reveal = TextReveal(fmt, chars_per_second=cps, initial_visible_chars=initial_visible_chars)
        if self.text_reveal.is_complete:
            self.director.ui_state.visible_chars = None
        else:
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

        self.auto_timer = 0.0

        while not self.vm.is_ended:
            event = self.vm.step()
            if event is None:
                self.is_finished = True
                self.mode = "ended"
                break

            prev_text = self.director.ui_state.text if event.type == "append" else None

            self.dispatcher.dispatch(event)
            self._last_event = event

            # Record beat_id into persistent seen_beats
            beat_id = getattr(event, "beat_id", None)
            if beat_id:
                seen_beats = self.persistent.get("seen_beats")
                if not isinstance(seen_beats, list):
                    seen_beats = []
                    self.persistent["seen_beats"] = seen_beats
                self._current_beat_previously_seen = (beat_id in seen_beats)
                if not self._current_beat_previously_seen:
                    seen_beats.append(beat_id)
                    self.persistent.save()
            else:
                self._current_beat_previously_seen = False

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
                    initial_chars = 0
                    if prev_text:
                        from eager_core.text import parse_text_tags

                        initial_chars = len(parse_text_tags(prev_text).plain_text)
                    self._setup_text_reveal(self.director.ui_state.text, initial_visible_chars=initial_chars)
                elif event.type in ("choice_prompt", "input_prompt", "story_end"):
                    self.text_reveal = None
                    self.director.ui_state.visible_chars = None

                if event.type == "choice_prompt":
                    self.active_choice_prompt = event
                    if hasattr(self, "overlay") and getattr(self.overlay, "choice_menu", None) is not None:
                        self.overlay.choice_menu.set_options(event.options)
                elif event.type == "input_prompt":
                    self.active_input_prompt = event
                    self.input_text = getattr(event, "default", "")
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
        self.input_text = ""
        return self.advance()

    def choose(self, choice: int | str) -> StoryEvent | None:
        """Make a branching choice and advance to the next interactive point."""
        if self.active_choice_prompt is None:
            return None

        # Verify choice is enabled before advancing
        if isinstance(choice, int):
            if 0 <= choice < len(self.active_choice_prompt.options) and not getattr(
                self.active_choice_prompt.options[choice], "enabled", True
            ):
                return None
        else:
            for opt in self.active_choice_prompt.options:
                if (opt.target == choice or opt.text == choice) and not getattr(opt, "enabled", True):
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

    @property
    def can_rollback(self) -> bool:
        """True if there is at least one previous checkpoint to restore."""
        return self.checkpoints.can_rollback

    @property
    def can_roll_forward(self) -> bool:
        """True if there is at least one popped checkpoint that can be restored forward."""
        return self.checkpoints.can_roll_forward

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

    def roll_forward(self) -> bool:
        """Step forward through the redo stack to restore previously rolled-back checkpoints."""
        if not self.checkpoints.can_roll_forward:
            return False

        next_cp = self.checkpoints.roll_forward()
        if next_cp is None:
            return False

        self._restore_checkpoint(next_cp)
        self.text_reveal = None
        self.director.ui_state.visible_chars = None
        return True

    def is_current_beat_read(self) -> bool:
        """Return True if the current beat was already seen in a previous playthrough."""
        if self._last_event is None:
            return False
        beat_id = getattr(self._last_event, "beat_id", None)
        if not beat_id:
            return False
        seen_beats = self.persistent.get("seen_beats")
        if isinstance(seen_beats, (list, set, tuple)):
            return beat_id in seen_beats
        return False

    def update(self, dt: float) -> None:
        """Update animation timelines, compositor, audio, typewriter reveal, and timers."""
        if hasattr(self.director, "step"):
            self.director.step(dt)
        elif self.compositor is not None and hasattr(self.compositor, "step"):
            self.compositor.step(dt)
        self.audio.update(dt)

        # Automatic hot-reload via file-watcher
        if self.auto_reload and self.watcher is not None and self.watcher.check_modified():
            self.hot_reload()

        # Update typewriter text reveal
        if self.text_reveal is not None and not self.text_reveal.is_complete:
            self.text_reveal.update(dt)
            if self.text_reveal.is_complete:
                if hasattr(self.director, "ui_state"):
                    self.director.ui_state.visible_chars = None
            else:
                if hasattr(self.director, "ui_state"):
                    self.director.ui_state.visible_chars = int(self.text_reveal.visible_chars)

        # Update input box cursor if input prompt is active
        if self.active_input_prompt is not None and hasattr(self, "overlay") and hasattr(self.overlay, "input_box") and self.overlay.input_box is not None:
            self.overlay.input_box.update(dt)

        # Skip mode advances immediately until player choices, input prompt, or story ends
        if self.skip_mode and not self.is_finished:
            if self.text_reveal is not None:
                self.text_reveal.complete_immediately()
                if hasattr(self.director, "ui_state"):
                    self.director.ui_state.visible_chars = None
            while (
                self.skip_mode
                and not self.is_finished
                and self.active_choice_prompt is None
                and self.active_input_prompt is None
            ):
                # If skip_unseen is False, check whether the current line was seen before advancing further
                if not getattr(self.preferences, "skip_unseen", False) and not self._current_beat_previously_seen:
                    self.skip_mode = False
                    break

                self.advance()
                if not getattr(self.preferences, "skip_unseen", False) and not self._current_beat_previously_seen:
                    self.skip_mode = False
                    break
        elif self.auto_mode and not self.is_finished and self.active_choice_prompt is None and self.active_input_prompt is None:
            reveal_done = (self.text_reveal is None or self.text_reveal.is_complete)
            voice_playing = hasattr(self, "audio") and self.audio is not None and self.audio.is_playing("voice")
            if reveal_done and not voice_playing:
                self.auto_timer += dt
                base_time = float(getattr(self.preferences, "auto_forward_time", 3.0))
                # Scale wait time slightly by character count (0.02s per char capped at 2.0s)
                # so long unvoiced paragraphs have sufficient reading time
                cur_text = getattr(getattr(self.director, "ui_state", None), "text", "") or ""
                extra_pause = min(2.0, len(cur_text) * 0.02)
                threshold = base_time + extra_pause
                if self.auto_timer >= threshold:
                    self.auto_timer = 0.0
                    if self.text_reveal is not None:
                        self.text_reveal.complete_immediately()
                        if hasattr(self.director, "ui_state"):
                            self.director.ui_state.visible_chars = None
                    self.advance()

    def draw(self, ui_backend: Any, width: int, height: int) -> None:
        """Draw the stage compositor and UI chrome through the given renderer / backend."""
        if self.compositor is not None and hasattr(ui_backend, "render_compositor"):
            ui_backend.render_compositor(self.compositor, width, height)

        status_badge: str | None = None
        if self.skip_mode:
            status_badge = "SKIP >>"
        elif self.auto_mode:
            status_badge = "AUTO >"

        if not self.ui_hidden and hasattr(self, "overlay") and self.overlay is not None:
            is_read = self.is_current_beat_read()
            if hasattr(self.overlay, "set_viewport"):
                self.overlay.set_viewport(width, height)
            if hasattr(self.overlay, "draw"):
                self.overlay.draw(
                    ui_backend,
                    getattr(self.director, "ui_state", None),
                    self.active_choice_prompt,
                    self.active_input_prompt,
                    input_text=self.input_text,
                    is_finished=self.is_finished,
                    show_quick_menu=True,
                    status_badge=status_badge,
                    is_read=is_read,
                )

        # Draw active screen on top
        if hasattr(self, "screens") and self.screens.active_screen:
            if hasattr(self.screens, "set_viewport"):
                self.screens.set_viewport(width, height)
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
                changed = self.screens.handle_mouse_move(x, y)
                return bool(changed)
            return None

        # 2. In-game interactions:
        # Choice menu keyboard navigation
        if (
            self.active_choice_prompt is not None
            and self.active_choice_prompt.options
            and getattr(self.overlay, "choice_menu", None) is not None
        ):
            opts = self.active_choice_prompt.options
            opts_count = len(opts)
            enabled_indices = [i for i, opt in enumerate(opts) if getattr(opt, "enabled", True)]
            if action == InputAction.NAV_UP and enabled_indices:
                cur = self.overlay.choice_menu.selected_index
                if cur in enabled_indices:
                    pos = enabled_indices.index(cur)
                    self.overlay.choice_menu.selected_index = enabled_indices[(pos - 1) % len(enabled_indices)]
                else:
                    self.overlay.choice_menu.selected_index = enabled_indices[-1]
                return True
            elif action == InputAction.NAV_DOWN and enabled_indices:
                cur = self.overlay.choice_menu.selected_index
                if cur in enabled_indices:
                    pos = enabled_indices.index(cur)
                    self.overlay.choice_menu.selected_index = enabled_indices[(pos + 1) % len(enabled_indices)]
                else:
                    self.overlay.choice_menu.selected_index = enabled_indices[0]
                return True
            elif action in (InputAction.ADVANCE, InputAction.CONFIRM):
                if self.overlay.choice_menu.selected_index is not None:
                    idx = self.overlay.choice_menu.selected_index
                    self.overlay.choice_menu.selected_index = None
                    if 0 <= idx < opts_count and getattr(opts[idx], "enabled", True):
                        return self.choose(idx)
                    return False

        # Active input prompt modal handling
        if self.active_input_prompt is not None:
            if action == InputAction.TEXT_CHAR:
                ch = payload.get("char", "")
                if ch:
                    self.input_text += ch
                    if getattr(self.overlay, "input_box", None) is not None:
                        self.overlay.input_box.text_buffer = self.input_text
                    self._ui_dirty = True
                    return True
            elif action == InputAction.TEXT_BACKSPACE:
                if self.input_text:
                    self.input_text = self.input_text[:-1]
                    if getattr(self.overlay, "input_box", None) is not None:
                        self.overlay.input_box.text_buffer = self.input_text
                    self._ui_dirty = True
                    return True
            elif action == InputAction.CONFIRM:
                val = self.input_text
                return self.submit_input(val)
            # If an input prompt is active, intercept other inputs so we don't accidentally advance or rollback
            if action in (InputAction.ADVANCE, InputAction.ROLLBACK, InputAction.ROLL_FORWARD):
                return None

        # Advance / Typewriter completion
        if action in (InputAction.ADVANCE, InputAction.CONFIRM):
            if self.text_reveal is not None and not self.text_reveal.is_complete:
                self.text_reveal.complete_immediately()
                if hasattr(self.director, "ui_state"):
                    self.director.ui_state.visible_chars = None
                if getattr(self.overlay, "dialogue_box", None) is not None:
                    self.overlay.dialogue_box.visible_chars = None
                    self.overlay.dialogue_box.show_advance_arrow = (self.active_choice_prompt is None)
                return True
            if self.active_choice_prompt is None and self.active_input_prompt is None:
                return self.advance()
        elif action == InputAction.ROLLBACK:
            return self.rollback()
        elif action == InputAction.ROLL_FORWARD:
            return self.roll_forward()
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
        elif action == InputAction.RELOAD:
            return self.hot_reload()
        elif action == InputAction.POINTER_CLICK:
            x = payload.get("x", 0.0)
            y = payload.get("y", 0.0)
            # Check quick action bar in UIOverlay
            if not self.ui_hidden and hasattr(self.overlay, "hit_test_quick_action"):
                qa = self.overlay.hit_test_quick_action(x, y)
                if qa:
                    return self._handle_quick_action(qa)
            # Check choices
            if self.active_choice_prompt is not None and hasattr(self.overlay, "hit_test_choice"):
                idx = self.overlay.hit_test_choice(x, y)
                if idx is not None:
                    return self.choose(idx)
                return None
            # Check typewriter reveal completion
            if self.text_reveal is not None and not self.text_reveal.is_complete:
                self.text_reveal.complete_immediately()
                if hasattr(self.director, "ui_state"):
                    self.director.ui_state.visible_chars = None
                if getattr(self.overlay, "dialogue_box", None) is not None:
                    self.overlay.dialogue_box.visible_chars = None
                    self.overlay.dialogue_box.show_advance_arrow = (self.active_choice_prompt is None)
                return True
            # Otherwise advance
            if self.active_choice_prompt is None and self.active_input_prompt is None:
                return self.advance()
        elif action == InputAction.POINTER_MOVE:
            x = payload.get("x", 0.0)
            y = payload.get("y", 0.0)
            hover_changed = False
            if hasattr(self, "overlay") and self.overlay is not None:
                # Choice menu hover update
                if self.active_choice_prompt is not None and getattr(self.overlay, "choice_menu", None) is not None:
                    idx = self.overlay.hit_test_choice(x, y)
                    if self.overlay.choice_menu.selected_index != idx:
                        self.overlay.choice_menu.selected_index = idx
                        hover_changed = True
                # Quick menu hover update
                if not self.ui_hidden and getattr(self.overlay, "quick_menu", None) is not None:
                    qa = self.overlay.hit_test_quick_action(x, y)
                    if getattr(self.overlay.quick_menu, "hovered_action", None) != qa:
                        self.overlay.quick_menu.hovered_action = qa
                        hover_changed = True
            return hover_changed
        return None

    def _set_error_overlay(self, msg: str) -> None:
        """Set error overlay and clear active choices/prompts."""
        if hasattr(self, "overlay") and self.overlay is not None:
            self.overlay.error_overlay = msg
        if hasattr(self, "director") and self.director is not None and hasattr(self.director, "ui_state"):
            self.director.ui_state.speaker = "Error"
            self.director.ui_state.text = msg
            if hasattr(self.director.ui_state, "clear_choices"):
                self.director.ui_state.clear_choices()
        self.active_choice_prompt = None

    def _clear_error_overlay(self) -> None:
        """Clear the error overlay from the UI."""
        if hasattr(self, "overlay") and self.overlay is not None:
            self.overlay.error_overlay = None

    def _refresh_presentation_after_reload(self, new_scene: Any, display_idx: int) -> None:
        """Update active dialogue/choice display to reflect the reloaded scene body."""
        if not new_scene.body:
            return
        if 0 <= display_idx < len(new_scene.body):
            from eager_script import ParsedChoiceSet, ParsedDialogue, ParsedNarration

            item = new_scene.body[display_idx]
            if isinstance(item, ParsedDialogue):
                self.director.ui_state.speaker = item.speaker
                self.director.ui_state.text = self.vm.interpolate(item.text)
                self.director.ui_state.emotion = item.emotion
                self.director.ui_state.visible_chars = None
                self.text_reveal = None
            elif isinstance(item, ParsedNarration):
                self.director.ui_state.speaker = None
                self.director.ui_state.text = self.vm.interpolate(item.text)
                self.director.ui_state.emotion = None
                self.director.ui_state.visible_chars = None
                self.text_reveal = None
            elif isinstance(item, ParsedChoiceSet):
                if self.active_choice_prompt is not None or self.vm.pending_choice is not None:
                    prompt = self.vm._build_choice_prompt(item)
                    self.active_choice_prompt = prompt
                    self.vm._pending_choice = prompt

    def hot_reload(self, script_path: str | Path | None = None) -> bool:
        """Hot-reload the screenplay from disk, hot-swapping the VM and reconciling state.

        1. Capture current state: vm.current_scene_id, vm.beat_index, vm.variables.
        2. Re-parse script: read .es file and generate fresh SceneGraph.
        3. Hot-swap VM: swap vm.graph reference.
        4. Reconcile state:
           - If current_scene_id still exists, cap beat_index to len(new_scene.body) - 1.
           - If scene was deleted, gracefully jump to entry node or display a safe
             "Scene not found" error overlay.
        5. Force a redraw: set self._ui_dirty = True and trigger a re-render.
        """
        target_path = Path(script_path) if script_path else self.script_path
        if target_path is None or not target_path.exists():
            self._set_error_overlay("Hot-reload error: script file not found.")
            self._ui_dirty = True
            return False

        # 1. Capture current state
        cur_scene_id = self.vm.current_scene_id
        b_idx = self.vm.beat_index
        _variables = self.vm.variables

        # 2. Re-parse the script
        try:
            text = target_path.read_text(encoding="utf-8")
            new_graph = parse_graph(text)
        except Exception as exc:  # noqa: BLE001
            self._set_error_overlay(f"Hot-reload parse error: {exc}")
            self._ui_dirty = True
            return False

        # 3. Hot-swap the VM
        self.graph = new_graph
        self.vm.graph = new_graph

        # 4. Reconcile State
        if cur_scene_id is not None and cur_scene_id in new_graph.nodes:
            new_scene = new_graph.nodes[cur_scene_id]
            if new_scene.body:
                self.vm.beat_index = max(0, min(b_idx, len(new_scene.body) - 1))
                active_idx = min(max(0, b_idx - 1) if b_idx > 0 else 0, len(new_scene.body) - 1)
            else:
                self.vm.beat_index = 0
                active_idx = 0
            self._clear_error_overlay()
            self._refresh_presentation_after_reload(new_scene, active_idx)
        else:
            # Scene was deleted
            if new_graph.entry and new_graph.entry in new_graph.nodes:
                self._clear_error_overlay()
                self.vm.jump(new_graph.entry)
                self.advance()
            else:
                self._set_error_overlay(f"Scene not found: '{cur_scene_id}'")

        # 5. Force a redraw
        self._ui_dirty = True
        if hasattr(self, "overlay") and self.overlay is not None and hasattr(self.overlay, "sync"):
            self.overlay.sync(
                self.director.ui_state,
                self.active_choice_prompt,
                self.active_input_prompt,
                input_text=self.input_text,
                is_read=self.is_current_beat_read(),
            )

        return True
