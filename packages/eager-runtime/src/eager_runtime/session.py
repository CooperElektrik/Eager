"""Unified game session controller and checkpoint manager for Eager visual novels."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    InputPromptEvent,
    NarrationEvent,
    SceneEnterEvent,
    StoryEndEvent,
    StoryEvent,
)
from eager_core.input import InputAction, Keymap
from eager_core.protocols import (
    ScreenManagerProtocol,
    StageProtocol,
    UIProtocol,
    get_screen_manager_factory,
    get_stage_factory,
    get_theme_factory,
    get_ui_factory,
    load_providers,
)
from eager_core.storage import get_default_save_dir

from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.headless import (
    NullCompositor,
    NullScreenManager,
    NullStage,
    NullUI,
)
from eager_runtime.persistent import PersistentData
from eager_runtime.preferences import Preferences
from eager_runtime.project import load_project_graph, resolve_project_scripts
from eager_runtime.runtime import StoryVM
from eager_runtime.saves import SaveManager
from eager_runtime.state import Checkpoint, CheckpointHistory, StorySnapshot

__all__ = [
    "GameSession",
]


def _create_default_stage(
    virtual_width: int,
    virtual_height: int,
    audio: Any,
    skip_mode_cb: Any,
) -> Any:
    load_providers()
    factory = get_stage_factory()
    if factory is not None:
        return factory(
            virtual_width=virtual_width,
            virtual_height=virtual_height,
            audio=audio,
            skip_mode_cb=skip_mode_cb,
        )
    return NullStage(virtual_width=virtual_width, virtual_height=virtual_height)


def _resolve_theme(config: Any) -> Any:
    """Instantiate a Theme object or options dict from ProjectConfig."""
    if config is None:
        return None
    theme_name = getattr(config, "theme", None)
    theme_overrides = getattr(config, "theme_overrides", {}) or {}
    if not theme_name and not theme_overrides:
        return None
    load_providers()
    factory = get_theme_factory()
    kwargs: dict[str, Any] = {}
    if theme_name:
        kwargs["name"] = theme_name
    kwargs.update(theme_overrides)
    if factory is not None:
        try:
            return factory(**kwargs)
        except (TypeError, ValueError, AttributeError):
            return None
    return kwargs


def _create_default_ui(width: int = 1280, height: int = 720, theme: Any = None) -> Any:
    load_providers()
    factory = get_ui_factory()
    if factory is not None:
        try:
            return factory(width=width, height=height, theme=theme)
        except TypeError:
            return factory(width=width, height=height)
    return NullUI(width=width, height=height)


def _create_default_screens(config: Any, session: Any) -> Any:
    load_providers()
    factory = get_screen_manager_factory()
    if factory is not None:
        return factory(config=config, session=session)
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
        headless: bool = False,
        renderer: Any = None,
    ) -> None:
        self.script_path = Path(project_or_script) if isinstance(project_or_script, (str, Path)) else None
        self.backend = backend
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self._custom_save_dir = Path(save_dir) if save_dir is not None else None
        if config is not None:
            if virtual_width == 1920 and hasattr(config, "virtual_width") and config.virtual_width:
                virtual_width = config.virtual_width
            if virtual_height == 1080 and hasattr(config, "virtual_height") and config.virtual_height:
                virtual_height = config.virtual_height
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height
        self.auto_reload = auto_reload or watch
        self._ui_dirty: bool = True
        self.config: Any = config
        self.renderer: Any = renderer
        self._last_renderer: Any = None
        self._playtime: float = 0.0

        # Parse scene graph
        if isinstance(project_or_script, (str, Path)):
            self.script_path = Path(project_or_script)
            self.graph: Any = load_project_graph(self.script_path)
            self._project_scripts = resolve_project_scripts(self.script_path)
        elif hasattr(project_or_script, "graph"):
            self.graph = project_or_script.graph
        else:
            self.graph = project_or_script

        from eager_core.audio import AudioMixer
        from eager_core.i18n import TranslationManager

        self.translation_manager = TranslationManager()
        locales_dir: Path | None = None
        if self.script_path is not None:
            base_dir = (
                self.script_path.resolve()
                if self.script_path.is_dir()
                else self.script_path.resolve().parent
            )
            candidate = base_dir / "locales"
            if candidate.is_dir():
                locales_dir = candidate
        if locales_dir is not None:
            self.translation_manager.load_directory(locales_dir)

        # Persistent state, preferences, and saves
        save_dir = (
            self._custom_save_dir
            if self._custom_save_dir is not None
            else get_default_save_dir(self.script_path.stem if self.script_path else "default")
        )
        self.persistent = PersistentData(save_dir / "persistent.json")
        self.preferences = Preferences.load(save_dir / "preferences.json")
        self.save_manager = SaveManager(save_dir)

        if isinstance(project_or_script, StoryVM):
            self.vm = project_or_script
            self.vm.set_variable("persistent", self.persistent)
        else:
            self.vm = StoryVM(
                self.graph,
                translation_manager=self.translation_manager,
                persistent=self.persistent,
            )
        self.dispatcher = EventDispatcher()
        self.audio = AudioMixer(backend=audio_backend, asset_dir=self.asset_dir)
        self.apply_preferences()

        if stage is not None:
            self.stage: Any = stage
        elif headless:
            self.stage = NullStage(virtual_width=virtual_width, virtual_height=virtual_height)
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
        self.stage.bind(self.dispatcher)

        if self.graph.characters:
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
        resolved_theme = _resolve_theme(config) if config is not None else None
        if ui is not None:
            self.ui: Any = ui
        elif headless:
            self.ui = NullUI(width=1280, height=720)
        else:
            self.ui = _create_default_ui(width=1280, height=720, theme=resolved_theme)
        self.overlay: Any = self.ui

        # Screens and Theme
        if screens is not None:
            self.screens: Any = screens
        elif headless:
            self.screens = NullScreenManager()
        else:
            self.screens = _create_default_screens(config, self)

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

            self.watcher: FileWatcher | None = FileWatcher(getattr(self, "_project_scripts", [self.script_path]))
        else:
            self.watcher = None

    @property
    def playtime(self) -> float:
        """Accumulated session playtime in seconds."""
        return self._playtime

    def apply_preferences(self) -> None:
        """Apply current preferences to audio mixer, translation locale, and subsystems."""
        self.audio.set_master_volume(self.preferences.master_volume)
        self.audio.set_channel_volume("music", self.preferences.music_volume)
        self.audio.set_channel_volume("sound", self.preferences.sfx_volume)
        self.audio.set_channel_volume("voice", self.preferences.voice_volume)
        self.vm.set_locale(self.preferences.language)

    def set_language(self, locale: str) -> None:
        """Switch active language locale, updating VM and persisting preferences."""
        self.preferences.language = locale
        self.apply_preferences()
        self.preferences.save(self.save_manager.save_dir / "preferences.json")

    def play_voice(self, voice_path: str) -> None:
        """Replay a voice clip on the voice channel."""
        self.audio.play("voice", str(voice_path), loop=False)

    def _capture_checkpoint(self) -> Checkpoint:
        """Generate a unified checkpoint of the current session state."""
        input_data = (
            self.active_input_prompt.to_dict()
            if self.active_input_prompt is not None
            else None
        )
        visual_state = self.director.save_visual_state()
        ui_state_dict = self.director.save_ui_state()

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
        self.director.load_visual_state(checkpoint.visual)
        self.audio.load_state(checkpoint.audio)
        self.director.restore_ui_state(checkpoint.ui)
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

        if hasattr(self.director, "finish_animations"):
            self.director.finish_animations()
        elif hasattr(self.stage, "finish_animations"):
            self.stage.finish_animations()

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

                if isinstance(event, ChoicePromptEvent):
                    self.active_choice_prompt = event
                    if hasattr(self.overlay, "set_choice_options"):
                        self.overlay.set_choice_options(event.options)
                    elif getattr(self.overlay, "choice_menu", None) is not None:
                        self.overlay.choice_menu.set_options(event.options)
                elif isinstance(event, InputPromptEvent):
                    self.active_input_prompt = event
                    self.input_text = event.default
                elif isinstance(event, StoryEndEvent):
                    self.is_finished = True
                    self.mode = "ended"

                # Push checkpoint after reaching interaction
                cp = self._capture_checkpoint()
                self.checkpoints.push(cp)
                if getattr(self.preferences, "autosave_enabled", True) and not self.skip_mode:
                    self.save_manager.autosave(cp, playtime_seconds=self._playtime)
                return event

        if self.vm.is_ended:
            self.is_finished = True
            self.mode = "ended"
            cp = self._capture_checkpoint()
            self.checkpoints.push(cp)
            if getattr(self.preferences, "autosave_enabled", True) and not self.skip_mode:
                self.save_manager.autosave(cp, playtime_seconds=self._playtime)

        return None

    def submit_input(self, value: str) -> StoryEvent | None:
        """Submit user text input for active input prompt and advance."""
        if self.active_input_prompt is None:
            return None
        var_name = self.active_input_prompt.var_name
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
            if 0 <= choice < len(self.active_choice_prompt.options) and not self.active_choice_prompt.options[choice].enabled:
                return None
        else:
            for opt in self.active_choice_prompt.options:
                if (opt.target == choice or opt.text == choice) and not opt.enabled:
                    return None

        self.vm.choose(choice)
        self.active_choice_prompt = None
        return self.advance()

    def warp(
        self,
        target_scene: str,
        *,
        simulate: bool = True,
        max_steps: int = 10000,
    ) -> bool:
        """Fast-forward / jump directly to target_scene, reconstructing stage and story state.

        If *simulate* is True and a path from story entry (or a root ancestor)
        to *target_scene* exists in the scene graph, simulates preceding scenes
        headlessly. Stage directives, character placements, expressions, variables,
        and continuous audio are reconstructed, while one-shot audio effects
        are suppressed and dialogue is added to the backlog.
        """
        if target_scene not in self.vm.graph.nodes:
            return False

        if not simulate:
            self.vm.jump(target_scene)
            return self._finalize_warp(prev_skip=self.skip_mode)

        if self.vm.current_scene_id == target_scene and not self.vm.is_ended:
            return True

        entry = self.vm.graph.entry
        path = self.vm.graph.find_path(entry, target_scene) if entry else None
        if path is None:
            root = self.vm.graph.find_root_ancestor(target_scene)
            if root:
                path = self.vm.graph.find_path(root, target_scene)

        if path is None or len(path) <= 1:
            self.vm.jump(target_scene)
            return self._finalize_warp(prev_skip=self.skip_mode)

        self.vm.jump(path[0])
        prev_skip = self.skip_mode
        self.skip_mode = True
        step_count = 0

        while not self.vm.is_ended and step_count < max_steps:
            step_count += 1
            event = self.vm.step()
            if event is None:
                break

            if isinstance(event, SceneEnterEvent) and event.scene_id == target_scene:
                self.dispatcher.dispatch(event)
                break

            self.dispatcher.dispatch(event)
            self._last_event = event

            beat_id = getattr(event, "beat_id", None)
            if beat_id:
                seen_beats = self.persistent.get("seen_beats")
                if not isinstance(seen_beats, list):
                    seen_beats = []
                    self.persistent["seen_beats"] = seen_beats
                if beat_id not in seen_beats:
                    seen_beats.append(beat_id)
                    self.persistent.save()

            if isinstance(event, DialogueEvent):
                self.backlog.add(event.speaker, event.text, voice=event.voice, emotion=event.emotion)
            elif isinstance(event, NarrationEvent):
                self.backlog.add(None, event.text)
            elif isinstance(event, AppendEvent):
                self.backlog.append_to_last(event.text)

            if hasattr(self.director, "finish_animations"):
                self.director.finish_animations()
            elif hasattr(self.stage, "finish_animations"):
                self.stage.finish_animations()

            if isinstance(event, ChoicePromptEvent):
                chosen_idx = 0
                curr_scene = self.vm.current_scene_id
                if curr_scene in path:
                    curr_idx = path.index(curr_scene)
                    remaining_targets = set(path[curr_idx + 1 :])
                    for idx, opt in enumerate(event.options):
                        if opt.target and opt.target in remaining_targets and opt.enabled:
                            chosen_idx = idx
                            break
                    else:
                        for idx, opt in enumerate(event.options):
                            if (
                                opt.target
                                and opt.enabled
                                and target_scene in self.vm.graph.reachable_from(opt.target)
                            ):
                                chosen_idx = idx
                                break
                else:
                    for idx, opt in enumerate(event.options):
                        if (
                            opt.target
                            and opt.enabled
                            and target_scene in self.vm.graph.reachable_from(opt.target)
                        ):
                            chosen_idx = idx
                            break
                self.vm.choose(chosen_idx)
            elif isinstance(event, InputPromptEvent):
                val = event.default or "Player"
                self.vm.set_variable(event.var_name, val)
                self.vm._pending_input = None

        if self.vm.current_scene_id != target_scene:
            self.vm.jump(target_scene)

        return self._finalize_warp(prev_skip=prev_skip)

    def _finalize_warp(self, prev_skip: bool = False) -> bool:
        if hasattr(self.director, "finish_animations"):
            self.director.finish_animations()
        elif hasattr(self.stage, "finish_animations"):
            self.stage.finish_animations()

        if hasattr(self.director, "ui_state"):
            self.director.ui_state.clear_dialogue()
            self.director.ui_state.clear_choices()
            self.director.ui_state.is_finished = False

        self.is_finished = False
        self.mode = "game"
        self.text_reveal = None
        self.active_choice_prompt = None
        self.active_input_prompt = None
        self.skip_mode = prev_skip

        self.checkpoints.clear()
        self.checkpoints.push(self._capture_checkpoint())
        return True


    def save_game(self, slot_name: str) -> Any:
        """Save current checkpoint to named slot, capturing a thumbnail screenshot."""
        cp = self.checkpoints.get_latest() or self._capture_checkpoint()
        thumb_path: Path | None = None
        try:
            thumb_dir = self.save_manager.save_dir / "screenshots" / "thumbs"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = self.take_screenshot(
                target_path=thumb_dir / f"thumb_{slot_name}.png"
            )
        except Exception:  # noqa: BLE001
            # A missing renderer or screenshot failure must never break saving.
            thumb_path = None
        return self.save_manager.save_slot(
            slot_name,
            cp,
            metadata_extra={
                "playtime_seconds": self._playtime,
                "thumbnail_path": str(thumb_path) if thumb_path else None,
            },
        )

    def load_game(self, slot_name: str) -> bool:
        """Load game from named slot."""
        meta = self.save_manager.get_slot_metadata(slot_name)
        cp = self.save_manager.load_slot(slot_name)
        if cp is None:
            return False
        if meta is not None:
            self._playtime = meta.playtime_seconds
        self._restore_checkpoint(cp)
        self.checkpoints.clear()
        self.checkpoints.push(cp)
        return True

    def quicksave(self) -> Any:
        """Quicksave current checkpoint."""
        cp = self.checkpoints.get_latest() or self._capture_checkpoint()
        result = self.save_manager.quicksave(cp, playtime_seconds=self._playtime)
        if hasattr(self.overlay, "show_toast"):
            self.overlay.show_toast("Saved to quickslot", 2.0)
        return result

    def quickload(self) -> bool:
        """Quickload from quicksave slot."""
        slot = self.save_manager._latest_rotated_slot("quick", self.save_manager.max_quicksaves)
        if slot is not None:
            meta = self.save_manager.get_slot_metadata(slot)
            if meta is not None:
                self._playtime = meta.playtime_seconds
        cp = self.save_manager.quickload()
        if cp is None:
            return False
        self._restore_checkpoint(cp)
        self.checkpoints.clear()
        self.checkpoints.push(cp)
        if hasattr(self.overlay, "show_toast"):
            self.overlay.show_toast("Loaded quickslot", 2.0)
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
        """Update animation timelines, compositor, audio, typewriter reveal, timers, and playtime."""
        if dt > 0.0:
            self._playtime += dt

        self.director.step(dt)
        self.audio.update(dt)

        # Automatic hot-reload via file-watcher
        if self.auto_reload and self.watcher is not None and self.watcher.check_modified():
            self.hot_reload()

        # Update typewriter text reveal
        if self.text_reveal is not None and not self.text_reveal.is_complete:
            self.text_reveal.update(dt)
            if self.text_reveal.is_complete:
                self.director.ui_state.visible_chars = None
            else:
                self.director.ui_state.visible_chars = int(self.text_reveal.visible_chars)

        # Update transient toast timer (quicksave/quickload feedback)
        if hasattr(self.overlay, "update_toast"):
            self.overlay.update_toast(dt)

        # Update input box cursor if input prompt is active
        if self.active_input_prompt is not None:
            if hasattr(self.overlay, "update_input"):
                self.overlay.update_input(dt)
            elif getattr(self.overlay, "input_box", None) is not None:
                self.overlay.input_box.update(dt)

        # Skip mode advances immediately until player choices, input prompt, or story ends
        if self.skip_mode and not self.is_finished:
            if self.text_reveal is not None:
                self.text_reveal.complete_immediately()
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
            voice_playing = self.audio.is_playing("voice")
            if reveal_done and not voice_playing:
                self.auto_timer += dt
                base_time = float(getattr(self.preferences, "auto_forward_time", 3.0))
                # Scale wait time slightly by character count (0.02s per char capped at 2.0s)
                # so long unvoiced paragraphs have sufficient reading time
                cur_text = self.director.ui_state.text or ""
                extra_pause = min(2.0, len(cur_text) * 0.02)
                threshold = base_time + extra_pause
                if self.auto_timer >= threshold:
                    self.auto_timer = 0.0
                    if self.text_reveal is not None:
                        self.text_reveal.complete_immediately()
                        self.director.ui_state.visible_chars = None
                    self.advance()

    def draw(self, ui_backend: Any, width: int, height: int) -> None:
        """Draw the stage compositor and UI chrome through the given renderer / backend."""
        self._last_renderer = ui_backend
        if self.renderer is None:
            self.renderer = ui_backend

        if self.compositor is not None and hasattr(ui_backend, "render_compositor"):
            ui_backend.render_compositor(self.compositor, width, height)

        status_badge: str | None = None
        if self.skip_mode:
            status_badge = "SKIP >>"
        elif self.auto_mode:
            status_badge = "AUTO >"

        if not self.ui_hidden:
            is_read = self.is_current_beat_read()
            self.overlay.set_viewport(width, height)
            self.overlay.draw(
                ui_backend,
                self.director.ui_state,
                self.active_choice_prompt,
                self.active_input_prompt,
                input_text=self.input_text,
                is_finished=self.is_finished,
                show_quick_menu=True,
                status_badge=status_badge,
                is_read=is_read,
            )

        # Draw active screen on top
        if self.screens.active_screen:
            self.screens.set_viewport(width, height)
            self.screens.draw(ui_backend, width, height)

    def take_screenshot(
        self,
        target_path: str | Path | None = None,
        renderer: Any = None,
        **kwargs: Any,
    ) -> Path:
        """Capture the current frame and save a timestamped PNG to save_dir / 'screenshots'."""
        r = renderer or self.renderer or self._last_renderer
        screenshot_dir = self.save_manager.save_dir / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        if target_path is None:
            now = datetime.datetime.now(datetime.UTC)
            now_str = now.strftime("%Y%m%d_%H%M%S")
            candidate = screenshot_dir / f"screenshot_{now_str}.png"
            if candidate.exists():
                now_str = now.strftime("%Y%m%d_%H%M%S_%f")
                candidate = screenshot_dir / f"screenshot_{now_str}.png"
            target_path = candidate
        else:
            target_path = Path(target_path)

        if r is not None and hasattr(r, "save_frame"):
            r.save_frame(target_path, **kwargs)
        else:
            # Headless fallback: minimal 1x1 valid PNG
            target_path.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
                b"\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
            )
        return target_path

    def _handle_quick_action(self, action_name: str) -> Any:
        """Handle clicks on the in-game quick menu buttons."""
        if action_name == "log":
            return self.screens.show("history", self)
        elif action_name == "skip":
            self.skip_mode = not self.skip_mode
            return self.skip_mode
        elif action_name == "auto":
            self.auto_mode = not self.auto_mode
            return self.auto_mode
        elif action_name == "save":
            return self.screens.show("save", self)
        elif action_name == "load":
            return self.screens.show("load", self)
        elif action_name == "quicksave":
            return self.quicksave()
        elif action_name == "quickload":
            return self.quickload()
        elif action_name == "prefs":
            return self.screens.show("preferences", self)
        return None

    def handle_input(self, action: InputAction, **payload: Any) -> Any:
        """Process semantic InputAction events."""
        # 1. Screen active intercepts:
        if self.screens.is_active:
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
            if action == InputAction.SCREENSHOT:
                return self.take_screenshot(**payload)
            return None

        # 2. In-game interactions:
        # Choice menu keyboard navigation
        if (
            self.active_choice_prompt is not None
            and self.active_choice_prompt.options
            and (hasattr(self.overlay, "get_selected_choice") or getattr(self.overlay, "choice_menu", None) is not None)
        ):
            opts = self.active_choice_prompt.options
            opts_count = len(opts)
            enabled_indices = [i for i, opt in enumerate(opts) if opt.enabled]
            if action == InputAction.NAV_UP and enabled_indices:
                cur = self.overlay.get_selected_choice() if hasattr(self.overlay, "get_selected_choice") else self.overlay.choice_menu.selected_index
                if cur in enabled_indices:
                    pos = enabled_indices.index(cur)
                    new_idx = enabled_indices[(pos - 1) % len(enabled_indices)]
                else:
                    new_idx = enabled_indices[-1]
                if hasattr(self.overlay, "set_selected_choice"):
                    self.overlay.set_selected_choice(new_idx)
                else:
                    self.overlay.choice_menu.selected_index = new_idx
                return True
            elif action == InputAction.NAV_DOWN and enabled_indices:
                cur = self.overlay.get_selected_choice() if hasattr(self.overlay, "get_selected_choice") else self.overlay.choice_menu.selected_index
                if cur in enabled_indices:
                    pos = enabled_indices.index(cur)
                    new_idx = enabled_indices[(pos + 1) % len(enabled_indices)]
                else:
                    new_idx = enabled_indices[0]
                if hasattr(self.overlay, "set_selected_choice"):
                    self.overlay.set_selected_choice(new_idx)
                else:
                    self.overlay.choice_menu.selected_index = new_idx
                return True
            elif action in (InputAction.ADVANCE, InputAction.CONFIRM):
                idx = self.overlay.get_selected_choice() if hasattr(self.overlay, "get_selected_choice") else self.overlay.choice_menu.selected_index
                if idx is not None:
                    if hasattr(self.overlay, "set_selected_choice"):
                        self.overlay.set_selected_choice(None)
                    else:
                        self.overlay.choice_menu.selected_index = None
                    if 0 <= idx < opts_count and opts[idx].enabled:
                        return self.choose(idx)
                    return False

        # Active input prompt modal handling
        if self.active_input_prompt is not None:
            if action == InputAction.TEXT_CHAR:
                ch = payload.get("char", "")
                if ch:
                    self.input_text += ch
                    if hasattr(self.overlay, "set_input_text"):
                        self.overlay.set_input_text(self.input_text)
                    elif getattr(self.overlay, "input_box", None) is not None:
                        self.overlay.input_box.text_buffer = self.input_text
                    self._ui_dirty = True
                    return True
            elif action == InputAction.TEXT_BACKSPACE:
                if self.input_text:
                    self.input_text = self.input_text[:-1]
                    if hasattr(self.overlay, "set_input_text"):
                        self.overlay.set_input_text(self.input_text)
                    elif getattr(self.overlay, "input_box", None) is not None:
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
                self.director.ui_state.visible_chars = None
                if hasattr(self.overlay, "complete_dialogue_reveal"):
                    self.overlay.complete_dialogue_reveal(show_arrow=(self.active_choice_prompt is None))
                elif getattr(self.overlay, "dialogue_box", None) is not None:
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
            return self.screens.show("save", self)
        elif action == InputAction.HISTORY:
            return self.screens.show("history", self)
        elif action == InputAction.FULLSCREEN:
            player: Any = getattr(self, "_player", None)
            if player is not None and hasattr(player, "toggle_fullscreen"):
                player.toggle_fullscreen()
            elif hasattr(self.renderer, "toggle_fullscreen"):
                self.renderer.toggle_fullscreen()
            return True
        elif action == InputAction.RELOAD:
            return self.hot_reload()
        elif action == InputAction.SCREENSHOT:
            return self.take_screenshot(**payload)
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
                if hasattr(self.overlay, "complete_dialogue_reveal"):
                    self.overlay.complete_dialogue_reveal(show_arrow=(self.active_choice_prompt is None))
                elif getattr(self.overlay, "dialogue_box", None) is not None:
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
            # Choice menu hover update
            if self.active_choice_prompt is not None:
                idx = self.overlay.hit_test_choice(x, y)
                cur_idx = self.overlay.get_selected_choice() if hasattr(self.overlay, "get_selected_choice") else getattr(self.overlay.choice_menu, "selected_index", None)
                if cur_idx != idx:
                    if hasattr(self.overlay, "set_selected_choice"):
                        self.overlay.set_selected_choice(idx)
                    else:
                        self.overlay.choice_menu.selected_index = idx
                    hover_changed = True
            # Quick menu hover update
            if not self.ui_hidden:
                qa = self.overlay.hit_test_quick_action(x, y)
                cur_qa = self.overlay.get_hovered_quick_action() if hasattr(self.overlay, "get_hovered_quick_action") else getattr(self.overlay.quick_menu, "hovered_action", None)
                if cur_qa != qa:
                    if hasattr(self.overlay, "set_hovered_quick_action"):
                        self.overlay.set_hovered_quick_action(qa)
                    else:
                        self.overlay.quick_menu.hovered_action = qa
                    hover_changed = True
            return hover_changed
        return None

    def _set_error_overlay(self, msg: str) -> None:
        """Set error overlay and clear active choices/prompts."""
        self.overlay.error_overlay = msg
        self.director.ui_state.speaker = "Error"
        self.director.ui_state.text = msg
        self.director.ui_state.clear_choices()
        self.active_choice_prompt = None

    def _clear_error_overlay(self) -> None:
        """Clear the error overlay from the UI."""
        self.overlay.error_overlay = None

    def _refresh_presentation_after_reload(self, new_scene: Any, display_idx: int) -> None:
        """Update active dialogue/choice display to reflect the reloaded scene body."""
        if not new_scene.body:
            return
        if 0 <= display_idx < len(new_scene.body):
            from eager_script import ParsedChoiceSet, ParsedDialogue, ParsedNarration

            from eager_runtime.i18n import compute_beat_id, get_beat_occurrence

            item = new_scene.body[display_idx]
            occ = get_beat_occurrence(new_scene.body, display_idx)
            cid = compute_beat_id(self.vm.current_scene_id or "", item, occurrence=occ)

            if isinstance(item, ParsedDialogue):
                raw_speaker = self.vm._interpolate(item.speaker)
                display_speaker = raw_speaker
                if self.vm._graph.characters:
                    cid_match = raw_speaker if raw_speaker in self.vm._graph.characters else raw_speaker.lower()
                    if cid_match in self.vm._graph.characters:
                        display_speaker = self.vm._graph.characters[cid_match].get("name", raw_speaker)
                interp_speaker = self.vm._translate_speaker(display_speaker)
                if interp_speaker == display_speaker and raw_speaker != display_speaker:
                    translated_raw = self.vm._translate_speaker(raw_speaker)
                    if translated_raw != raw_speaker:
                        interp_speaker = translated_raw

                raw_text, _ = self.vm._translate_beat(cid, item.text)
                final_text = self.vm._interpolate(raw_text)

                char_cfg = getattr(self.director, "_find_character_config", lambda s: None)(interp_speaker)
                if char_cfg is None and raw_speaker != interp_speaker:
                    char_cfg = getattr(self.director, "_find_character_config", lambda s: None)(raw_speaker)
                if char_cfg is None and display_speaker != interp_speaker:
                    char_cfg = getattr(self.director, "_find_character_config", lambda s: None)(display_speaker)

                char_color = (
                    getattr(char_cfg, "color", None)
                    if not isinstance(char_cfg, dict)
                    else (char_cfg.get("color") if isinstance(char_cfg, dict) else None)
                )

                self.director.ui_state.speaker = interp_speaker
                self.director.ui_state.text = final_text
                self.director.ui_state.emotion = item.emotion
                if hasattr(self.director, "_resolve_side_image"):
                    side = self.director._resolve_side_image(interp_speaker, item.emotion)
                    if not side and raw_speaker != interp_speaker:
                        side = self.director._resolve_side_image(raw_speaker, item.emotion)
                    self.director.ui_state.side_image = side
                elif isinstance(char_cfg, dict):
                    self.director.ui_state.side_image = char_cfg.get("side_image")
                self.director.ui_state.speaker_color = char_color

                if getattr(self.director.ui_state, "nvl_mode", False) and getattr(self.director.ui_state, "nvl_entries", None):
                    self.director.ui_state.nvl_entries[-1].speaker = interp_speaker
                    self.director.ui_state.nvl_entries[-1].text = final_text
                    self.director.ui_state.nvl_entries[-1].emotion = item.emotion

                self.director.ui_state.visible_chars = None
                self.text_reveal = None
            elif isinstance(item, ParsedNarration):
                raw_text, _ = self.vm._translate_beat(cid, item.text)
                final_text = self.vm._interpolate(raw_text)
                self.director.ui_state.speaker = None
                self.director.ui_state.text = final_text
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
            new_graph = load_project_graph(target_path, raise_parse_error=True)
            self._project_scripts = resolve_project_scripts(target_path)
            if self.watcher is not None:
                self.watcher.target_paths = self._project_scripts
        except Exception as exc:  # noqa: BLE001
            self._set_error_overlay(f"Hot-reload parse error: {exc}")
            self._ui_dirty = True
            return False

        # 3. Hot-swap the VM and sync characters and defaults
        self.graph = new_graph
        self.vm.graph = new_graph

        if self.translation_manager is not None:
            proj_dir = target_path if target_path.is_dir() else target_path.parent
            locales_dir = proj_dir / "locales"
            if locales_dir.is_dir():
                self.translation_manager.load_directory(locales_dir)

        if hasattr(self.director, "register_character") and new_graph.characters:
            for cid, cinfo in new_graph.characters.items():
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

        if hasattr(self.vm, "_apply_graph_defaults"):
            self.vm._apply_graph_defaults()

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
        self.overlay.sync(
                self.director.ui_state,
                self.active_choice_prompt,
                self.active_input_prompt,
                input_text=self.input_text,
                is_read=self.is_current_beat_read(),
            )

        return True
