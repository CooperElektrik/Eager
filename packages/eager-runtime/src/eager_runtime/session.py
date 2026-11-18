"""Unified game session controller and checkpoint manager for Eager visual novels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eager_core.dispatcher import EventDispatcher
from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    InputPromptEvent,
    NarrationEvent,
    StoryEndEvent,
    StoryEvent,
)
from eager_core.headless import NullCompositor, NullScreenManager, NullStage, NullUI
from eager_core.input import InputAction, Keymap
from eager_core.persistent import PersistentData
from eager_core.preferences import Preferences
from eager_core.protocols import (
    HostLifecycleListener,
    ProviderRegistry,
    ScreenManagerProtocol,
    StageProtocol,
    UIProtocol,
    get_default_registry,
    load_providers,  # noqa: F401 - re-exported for test patching
)
from eager_core.saves import SaveManager
from eager_core.state import Checkpoint, CheckpointHistory
from eager_core.storage import get_default_save_dir

from eager_runtime._session_bootstrap import (
    create_default_screens,
    create_default_stage,
    create_default_ui,
    discover_locales_dir,
    register_graph_characters,
    register_scene_backgrounds,
    resolve_theme,
)
from eager_runtime._session_input import handle_input as _route_input
from eager_runtime._session_input import handle_quick_action as _route_quick_action
from eager_runtime._session_reload import (
    clear_error_overlay,
    refresh_presentation_after_reload,
    set_error_overlay,
)
from eager_runtime._session_reload import (
    hot_reload as _perform_hot_reload,
)
from eager_runtime._session_saves import (
    capture_checkpoint,
    restore_checkpoint,
)
from eager_runtime._session_saves import (
    load_game as _load_game,
)
from eager_runtime._session_saves import (
    quickload as _quickload,
)
from eager_runtime._session_saves import (
    quicksave as _quicksave,
)
from eager_runtime._session_saves import (
    roll_forward as _roll_forward,
)
from eager_runtime._session_saves import (
    rollback as _rollback,
)
from eager_runtime._session_saves import (
    save_game as _save_game,
)
from eager_runtime._session_saves import (
    take_screenshot as _take_screenshot,
)
from eager_runtime._session_warp import finalize_warp
from eager_runtime._session_warp import warp as _perform_warp
from eager_runtime.project import load_project_graph, resolve_project_scripts
from eager_runtime.runtime import StoryVM

__all__ = [
    "GameSession",
]


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
        registry: ProviderRegistry | None = None,
    ) -> None:
        self.registry: ProviderRegistry = registry or get_default_registry()
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
        locales_dir = discover_locales_dir(self.script_path)
        if locales_dir is not None:
            self.translation_manager.load_directory(locales_dir)

        # Persistent state, preferences, and saves
        resolved_save_dir = (
            self._custom_save_dir
            if self._custom_save_dir is not None
            else get_default_save_dir(self.script_path.stem if self.script_path else "default")
        )
        self.persistent = PersistentData(resolved_save_dir / "persistent.json")
        self.preferences = Preferences.load(resolved_save_dir / "preferences.json")
        self.save_manager = SaveManager(resolved_save_dir)

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

        stage_kwargs: dict[str, Any] = {}
        if config is not None:
            for k in ("auto_highlight_speaker", "dim_color", "highlight_duration", "pop_scale", "pop_hop"):
                if hasattr(config, k) and getattr(config, k) is not None:
                    stage_kwargs[k] = getattr(config, k)

        if stage is not None:
            self.stage: Any = stage
        elif headless:
            self.stage = NullStage(virtual_width=virtual_width, virtual_height=virtual_height)
        else:
            self.stage = create_default_stage(
                virtual_width=virtual_width,
                virtual_height=virtual_height,
                audio=self.audio,
                skip_mode_cb=lambda: self.skip_mode,
                registry=self.registry,
                **stage_kwargs,
            )
        self.director: Any = self.stage
        self.compositor: Any = getattr(self.stage, "compositor", None)
        if self.compositor is None:
            self.compositor = NullCompositor(virtual_width=virtual_width, virtual_height=virtual_height)
        self.stage.bind(self.dispatcher)

        register_scene_backgrounds(self.director, config)
        register_graph_characters(self.director, self.graph)

        self.checkpoints = CheckpointHistory(max_history=rollback_limit)
        self.keymap = Keymap()
        resolved_theme = resolve_theme(config, registry=self.registry) if config is not None else None
        if ui is not None:
            self.ui: Any = ui
        elif headless:
            self.ui = NullUI(width=1280, height=720)
        else:
            self.ui = create_default_ui(width=1280, height=720, theme=resolved_theme, registry=self.registry)
        self.overlay: Any = self.ui

        # Screens and Theme
        if screens is not None:
            self.screens: Any = screens
        elif headless:
            self.screens = NullScreenManager()
        else:
            self.screens = create_default_screens(config, self, registry=self.registry)

        from eager_core.backlog import Backlog

        self.backlog = Backlog(max_entries=200)

        # State flags
        self.mode: str = "game"  # "title", "game", "menu", "ended"
        self._cli_args: Any = None
        self.skip_mode: bool = False
        self._skip_timer: float = 0.0
        self.skip_interval: float = 0.03
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
            from eager_core.watcher import FileWatcher

            self.watcher: FileWatcher | None = FileWatcher(getattr(self, "_project_scripts", [self.script_path]))
        else:
            self.watcher = None
        self._lifecycle_listeners: list[HostLifecycleListener] = []

    def add_lifecycle_listener(self, listener: HostLifecycleListener) -> None:
        """Register a host environment listener for lifecycle requests (fullscreen, quit)."""
        if listener not in self._lifecycle_listeners:
            self._lifecycle_listeners.append(listener)

    def remove_lifecycle_listener(self, listener: HostLifecycleListener) -> None:
        """Unregister a host environment lifecycle listener."""
        if listener in self._lifecycle_listeners:
            self._lifecycle_listeners.remove(listener)

    def request_fullscreen(self) -> None:
        """Notify registered host listeners to toggle fullscreen."""
        prev_fs = bool(getattr(self.preferences, "fullscreen", False))
        for listener in list(self._lifecycle_listeners):
            listener.on_request_fullscreen()
        if hasattr(self.renderer, "toggle_fullscreen"):
            self.renderer.toggle_fullscreen()
        # Only flip preference here if no host listener/renderer already toggled it
        if bool(getattr(self.preferences, "fullscreen", False)) == prev_fs:
            self.preferences.fullscreen = not prev_fs
            self.save_preferences()

    def request_quit(self) -> bool:
        """Notify registered host listeners to terminate the application."""
        if not self._lifecycle_listeners:
            return False
        for listener in list(self._lifecycle_listeners):
            listener.on_request_quit()
        return True

    @property
    def _player(self) -> Any:
        return self._lifecycle_listeners[0] if self._lifecycle_listeners else None

    @_player.setter
    def _player(self, player: Any) -> None:
        if player is not None:
            self.add_lifecycle_listener(player)

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
        self.audio.set_channel_volume("ambient", getattr(self.preferences, "ambient_volume", 0.8))
        self.vm.set_locale(self.preferences.language)
        scale = getattr(self.preferences, "resolution_scale", 1.0)
        for listener in list(getattr(self, "_lifecycle_listeners", ())):
            set_scale = getattr(listener, "set_resolution_scale", None)
            if callable(set_scale):
                set_scale(scale)

    def save_preferences(self) -> None:
        """Persist current preferences to preferences.json in save directory."""
        self.preferences.save(self.save_manager.save_dir / "preferences.json")

    def set_language(self, locale: str) -> None:
        """Switch active language locale, updating VM and persisting preferences."""
        self.preferences.language = locale
        self.apply_preferences()
        self.save_preferences()

    def play_voice(self, voice_path: str) -> None:
        """Replay a voice clip on the voice channel."""
        self.audio.play("voice", str(voice_path), loop=False)

    def play_audio(self, channel: str, track: str) -> None:
        """Play an audio track on a specified channel."""
        self.audio.play(channel, track)

    def queue_audio(self, channel: str, track: str) -> None:
        """Queue an audio track to play after current playback completes."""
        self.audio.queue(channel, track)

    def pause_audio(self, channel: str | None = None) -> None:
        """Pause playback on a specific channel, or all channels if channel is None."""
        if channel is None:
            if hasattr(self.audio, "pause_all"):
                self.audio.pause_all()
            else:
                for c in list(self.audio.channels):
                    self.audio.pause(c)
        else:
            self.audio.pause(channel)

    def resume_audio(self, channel: str | None = None) -> None:
        """Resume playback on a specific channel, or all channels if channel is None."""
        if channel is None:
            if hasattr(self.audio, "resume_all"):
                self.audio.resume_all()
            else:
                for c in list(self.audio.channels):
                    self.audio.resume(c)
        else:
            self.audio.resume(channel)

    def _capture_checkpoint(self) -> Checkpoint:
        """Generate a unified checkpoint of the current session state."""
        return capture_checkpoint(self)

    def _restore_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Restore full session state from a checkpoint."""
        restore_checkpoint(self, checkpoint)

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

    def _record_backlog_event(self, event: StoryEvent) -> None:
        """Append dialogue, narration, or append events to the session backlog."""
        if isinstance(event, DialogueEvent):
            self.backlog.add(event.speaker, event.text, voice=event.voice, emotion=event.emotion)
        elif isinstance(event, (NarrationEvent, FreshBoxEvent)):
            self.backlog.add(None, event.text)
        elif isinstance(event, AppendEvent):
            self.backlog.append_to_last(event.text)

    def advance(self) -> StoryEvent | None:
        """Step the VM forward until the next interactive event, dispatching all
        intermediate events, and record a checkpoint at the new interaction point.
        """
        if self.is_finished or self.vm.is_ended:
            self.is_finished = True
            self.mode = "ended"
            return None

        if self.active_choice_prompt is not None:
            return self.active_choice_prompt

        if self.active_input_prompt is not None:
            return self.active_input_prompt

        if hasattr(self.stage, "finish_animations"):
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
                self._current_beat_previously_seen = beat_id in seen_beats
                if not self._current_beat_previously_seen:
                    seen_beats.append(beat_id)
                    self.persistent.save()
            else:
                self._current_beat_previously_seen = False

            self._record_backlog_event(event)

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
                elif isinstance(event, InputPromptEvent):
                    self.active_input_prompt = event
                    self.input_text = event.default
                elif isinstance(event, StoryEndEvent):
                    self.is_finished = True
                    self.mode = "ended"

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

        if isinstance(choice, int):
            if (
                0 <= choice < len(self.active_choice_prompt.options)
                and not self.active_choice_prompt.options[choice].enabled
            ):
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
        """Fast-forward / jump directly to target_scene, reconstructing stage and story state."""
        return _perform_warp(self, target_scene, simulate=simulate, max_steps=max_steps)

    def _finalize_warp(self, prev_skip: bool = False) -> bool:
        return finalize_warp(self, prev_skip=prev_skip)

    def save_game(self, slot_name: str) -> Any:
        """Save current checkpoint to named slot, capturing a thumbnail screenshot."""
        return _save_game(self, slot_name)

    def load_game(self, slot_name: str) -> bool:
        """Load game from named slot."""
        return _load_game(self, slot_name)

    def delete_save_slot(self, slot_name: str) -> bool:
        """Delete saved game in named slot."""
        return self.save_manager.delete_slot(slot_name)

    def quicksave(self) -> Any:
        """Quicksave current checkpoint."""
        return _quicksave(self)

    def quickload(self) -> bool:
        """Quickload from quicksave slot."""
        return _quickload(self)

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
        return _rollback(self)

    def roll_forward(self) -> bool:
        """Step forward through the redo stack to restore previously rolled-back checkpoints."""
        return _roll_forward(self)

    def restart_story(self) -> StoryEvent | None:
        """Reset the session to the beginning of the screenplay and advance the initial beat."""
        self.vm = StoryVM(
            self.graph,
            translation_manager=self.translation_manager,
            persistent=self.persistent,
        )
        if hasattr(self.stage, "clear_stage"):
            self.stage.clear_stage()
        self.audio.stop_all()

        self.checkpoints.clear()
        self.backlog.clear()
        self.is_finished = False
        self.mode = "game"
        self.skip_mode = False
        self._skip_timer = 0.0
        self.auto_mode = False
        self.auto_timer = 0.0
        self.active_choice_prompt = None
        self.active_input_prompt = None
        self.input_text = ""
        self.text_reveal = None
        self._last_event = None
        self._current_beat_previously_seen = False
        self._ui_dirty = True

        if hasattr(self.screens, "hide"):
            self.screens.hide(self)

        return self.advance()

    def return_to_title(self) -> bool:
        """Halt story execution and return to the main TitleScreen."""
        self.audio.stop_all()
        self.skip_mode = False
        self._skip_timer = 0.0
        self.auto_mode = False
        self.mode = "title"
        self._ui_dirty = True
        if hasattr(self.screens, "show"):
            return bool(self.screens.show("title", self))
        return False

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

        if self.auto_reload and self.watcher is not None and self.watcher.check_modified():
            self.hot_reload()

        if self.text_reveal is not None and not self.text_reveal.is_complete:
            self.text_reveal.update(dt)
            if self.text_reveal.is_complete:
                self.director.ui_state.visible_chars = None
            else:
                self.director.ui_state.visible_chars = int(self.text_reveal.visible_chars)

        if hasattr(self.overlay, "update_toast"):
            self.overlay.update_toast(dt)

        if self.active_input_prompt is not None:
            if hasattr(self.overlay, "update_input"):
                self.overlay.update_input(dt)
            elif getattr(self.overlay, "input_box", None) is not None:
                self.overlay.input_box.update(dt)

        if self.skip_mode and not self.is_finished:
            if self.text_reveal is not None:
                self.text_reveal.complete_immediately()
                self.director.ui_state.visible_chars = None
            if self.active_choice_prompt is not None or self.active_input_prompt is not None:
                self.skip_mode = False
            else:
                self._skip_timer += dt
                step_interval = getattr(self, "skip_interval", 0.03)
                if step_interval <= 0.0:
                    step_interval = 0.001
                while (
                    self.skip_mode
                    and not self.is_finished
                    and self.active_choice_prompt is None
                    and self.active_input_prompt is None
                    and self._skip_timer >= step_interval
                ):
                    self._skip_timer -= step_interval
                    if not getattr(self.preferences, "skip_unseen", False) and not self._current_beat_previously_seen:
                        self.skip_mode = False
                        break

                    self.advance()
                    if not getattr(self.preferences, "skip_unseen", False) and not self._current_beat_previously_seen:
                        self.skip_mode = False
                        break
        elif (
            self.auto_mode
            and not self.is_finished
            and self.active_choice_prompt is None
            and self.active_input_prompt is None
        ):
            reveal_done = self.text_reveal is None or self.text_reveal.is_complete
            voice_playing = self.audio.is_playing("voice")
            if reveal_done and not voice_playing:
                self.auto_timer += dt
                base_time = float(getattr(self.preferences, "auto_forward_time", 3.0))
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
        return _take_screenshot(self, target_path=target_path, renderer=renderer, **kwargs)

    def _handle_quick_action(self, action_name: str) -> Any:
        return _route_quick_action(self, action_name)

    def handle_input(self, action: InputAction, **payload: Any) -> Any:
        """Process semantic InputAction events."""
        return _route_input(self, action, **payload)

    def _set_error_overlay(self, msg: str) -> None:
        set_error_overlay(self, msg)

    def _clear_error_overlay(self) -> None:
        clear_error_overlay(self)

    def _refresh_presentation_after_reload(self, new_scene: Any, display_idx: int) -> None:
        refresh_presentation_after_reload(self, new_scene, display_idx)

    def hot_reload(self, script_path: str | Path | None = None) -> bool:
        """Hot-reload the screenplay from disk, hot-swapping the VM and reconciling state."""
        return _perform_hot_reload(self, script_path=script_path)
