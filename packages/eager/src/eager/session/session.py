"""Unified game session controller and checkpoint manager for Eager visual novels."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from eager.core.dispatcher import EventDispatcher
from eager.core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
    StoryEvent,
)
from eager.core.input import InputAction, Keymap
from eager.core.persistent import PersistentData
from eager.core.preferences import Preferences
from eager.core.saves import SaveManager
from eager.core.state import Checkpoint, CheckpointHistory
from eager.core.storage import get_default_save_dir

if TYPE_CHECKING:
    from eager.script.graph import SceneGraph
    from eager.stage.compositor import StageCompositor
    from eager.stage.director import StageDirector
    from eager.ui.components import UIOverlay
    from eager.ui.screens.screen import ScreenManager

from eager.script.graph import to_graph
from eager.script.includes import resolve_includes
from eager.script.parser import parse, slugify
from eager.session._session_bootstrap import (
    create_default_screens,
    create_default_stage,
    create_default_ui,
    register_graph_characters,
    register_scene_backgrounds,
)
from eager.session._session_input import handle_input as _route_input
from eager.session._session_input import handle_quick_action as _route_quick_action
from eager.session._session_saves import (
    capture_checkpoint,
    restore_checkpoint,
)
from eager.session._session_saves import (
    load_game as _load_game,
)
from eager.session._session_saves import (
    quickload as _quickload,
)
from eager.session._session_saves import (
    quicksave as _quicksave,
)
from eager.session._session_saves import (
    rollback as _rollback,
)
from eager.session._session_saves import (
    save_game as _save_game,
)
from eager.session._session_saves import (
    take_screenshot as _take_screenshot,
)
from eager.vm.runtime import StoryVM

logger = logging.getLogger(__name__)

__all__ = [
    "GameSession",
]


def _resolve_save_game_id(config: Any, script_path: Path | None) -> str:
    """Derive a per-project save folder name from config title or project directory."""
    title = getattr(config, "title", None)
    if isinstance(title, str) and title.strip():
        slug = slugify(title)
        if slug:
            return slug
    if script_path is not None:
        entry_script = getattr(config, "entry_script", None)
        if script_path.name == "main.es" or entry_script == "main.es":
            parent_slug = slugify(script_path.parent.resolve().name)
            if parent_slug:
                return parent_slug
        return slugify(script_path.stem) or "default"
    return "default"


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
        save_dir: str | Path | None = None,
        stage: StageDirector | Any | None = None,
        ui: UIOverlay | Any | None = None,
        screens: ScreenManager | Any | None = None,
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
        self.config: Any = config
        if renderer is None and (headless or backend == "null"):
            from eager.backends.renderers.null import NullRenderBackend

            renderer = NullRenderBackend()
        self.renderer: Any = renderer
        self._last_renderer: Any = None
        self._playtime: float = 0.0

        # Parse scene graph via @include from entry script
        if isinstance(project_or_script, (str, Path)):
            target = Path(project_or_script)
            if target.is_dir():
                entry_name = getattr(config, "entry_script", None) or "main.es"
                project_root = target.resolve()
                target = (project_root / entry_name).resolve()
                if not target.is_relative_to(project_root):
                    raise ValueError(f"Path traversal detected in entry_script: {entry_name!r}")
            self.script_path = target
            items = parse(target.read_text(encoding="utf-8"))
            self.graph: SceneGraph = to_graph(
                resolve_includes(items, base_dir=target.parent, visited={target.resolve()})
            )
        elif hasattr(project_or_script, "graph"):
            self.graph = cast("SceneGraph", project_or_script.graph)
        else:
            self.graph = cast("SceneGraph", project_or_script)

        from eager.core.audio import AudioMixer

        # Persistent state, preferences, and saves
        resolved_save_dir = (
            self._custom_save_dir
            if self._custom_save_dir is not None
            else get_default_save_dir(_resolve_save_game_id(config, self.script_path))
        )
        self.persistent = PersistentData(resolved_save_dir / "persistent.json")
        raw_seen = self.persistent.get("seen_beats")
        self._seen_beats_set: set[str] = (
            {str(item) for item in raw_seen} if isinstance(raw_seen, (list, set, tuple)) else set()
        )
        self._persistent_dirty: bool = False
        self.preferences = Preferences.load(resolved_save_dir / "preferences.json")
        self.save_manager = SaveManager(resolved_save_dir)
        logger.debug(
            "Initialized GameSession (backend=%r, save_dir=%s, asset_dir=%s)",
            self.backend,
            resolved_save_dir,
            self.asset_dir,
        )

        if isinstance(project_or_script, StoryVM):
            self.vm = project_or_script
            self.vm.set_variable("persistent", self.persistent)
        else:
            self.vm = StoryVM(
                self.graph,
                persistent=self.persistent,
            )
        self.dispatcher = EventDispatcher()
        if audio_backend is None and (headless or backend == "null"):
            from eager.core.audio import NullAudioBackend

            audio_backend = NullAudioBackend()
        self.audio = AudioMixer(backend=audio_backend, asset_dir=self.asset_dir)
        self.apply_preferences()

        if stage is not None:
            self.stage: StageDirector | Any = stage
        else:
            self.stage = create_default_stage(
                virtual_width=virtual_width,
                virtual_height=virtual_height,
                audio=self.audio,
                skip_mode_cb=lambda: self.skip_mode,
            )
        self.director: StageDirector | Any = self.stage
        self.compositor: StageCompositor | Any = getattr(self.stage, "compositor", None)
        self.stage.bind(self.dispatcher)

        register_scene_backgrounds(self.director, config)
        register_graph_characters(self.director, self.graph)

        self.checkpoints = CheckpointHistory(max_history=rollback_limit)
        self.keymap = Keymap()
        if ui is not None:
            self.ui: UIOverlay | Any = ui
        else:
            self.ui = create_default_ui(width=1280, height=720)
        self.overlay: UIOverlay | Any = self.ui

        # Screens
        if screens is not None:
            self.screens: ScreenManager | Any = screens
        else:
            self.screens = create_default_screens(config, self)

        from eager.core.backlog import Backlog

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
        self.text_reveal: Any | None = None

        self._last_event: StoryEvent | None = None
        self._last_beat_key: str | None = None
        self._current_beat_previously_seen: bool = False
        self._lifecycle_listeners: list[Any] = []

    def add_lifecycle_listener(self, listener: Any) -> None:
        """Register a host environment listener for lifecycle requests (fullscreen, quit)."""
        if listener not in self._lifecycle_listeners:
            self._lifecycle_listeners.append(listener)

    def remove_lifecycle_listener(self, listener: Any) -> None:
        """Unregister a host environment lifecycle listener."""
        if listener in self._lifecycle_listeners:
            self._lifecycle_listeners.remove(listener)

    def request_fullscreen(self) -> None:
        """Notify registered host listeners to toggle fullscreen."""
        prev_fs = bool(getattr(self.preferences, "fullscreen", False))
        listeners = list(self._lifecycle_listeners)
        for listener in listeners:
            listener.on_request_fullscreen()
        if not listeners and hasattr(self.renderer, "toggle_fullscreen"):
            self.renderer.toggle_fullscreen()
        # Only flip preference here if no host listener/renderer already toggled it
        if bool(getattr(self.preferences, "fullscreen", False)) == prev_fs:
            self.preferences.fullscreen = not prev_fs
            self.save_preferences()

    def _flush_persistent(self) -> None:
        """Persist dirty persistent data (e.g. seen_beats) to disk."""
        if self._persistent_dirty:
            self.persistent.save()
            self._persistent_dirty = False

    def request_quit(self) -> bool:
        """Autosave if enabled and notify registered host listeners to terminate."""
        self._flush_persistent()
        if getattr(self.preferences, "autosave_enabled", True) and self.has_started:
            cp = self.checkpoints.get_latest() or self._capture_checkpoint()
            self.save_manager.autosave(cp, playtime_seconds=self._playtime)
        if not self._lifecycle_listeners:
            return False
        for listener in list(self._lifecycle_listeners):
            listener.on_request_quit()
        return True

    def notify_state_restored(self) -> None:
        """Notify registered host listeners that session state was restored."""
        for listener in list(self._lifecycle_listeners):
            if hasattr(listener, "on_state_restored"):
                listener.on_state_restored()

    @property
    def has_started(self) -> bool:
        """True if at least one story event has been dispatched in this session."""
        return self._last_event is not None

    @property
    def playtime(self) -> float:
        """Accumulated session playtime in seconds."""
        return self._playtime

    def apply_preferences(self) -> None:
        """Apply current preferences to audio mixer."""
        self.audio.set_master_volume(self.preferences.master_volume)
        self.audio.set_channel_volume("music", self.preferences.music_volume)
        self.audio.set_channel_volume("sound", self.preferences.sfx_volume)
        self.audio.set_channel_volume("voice", self.preferences.voice_volume)
        self.audio.set_channel_volume("ambient", getattr(self.preferences, "ambient_volume", 0.8))

    def save_preferences(self) -> None:
        """Persist current preferences to preferences.json in save directory."""
        self.preferences.save(self.save_manager.save_dir / "preferences.json")

    def play_voice(self, voice_path: str) -> None:
        """Replay a voice clip on the voice channel."""
        self.audio.play("voice", str(voice_path), loop=False)

    def play_audio(self, channel: str, track: str) -> None:
        """Play an audio track on a specified channel."""
        self.audio.play(channel, track)

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

        from eager.core.text import TextReveal, parse_text_tags

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

        if hasattr(self.stage, "finish_animations"):
            self.stage.finish_animations()

        self.auto_timer = 0.0
        entered_new_scene = False

        while not self.vm.is_ended:
            event = self.vm.step()
            if event is None:
                self.is_finished = True
                self.mode = "ended"
                break

            if isinstance(event, SceneEnterEvent):
                entered_new_scene = True

            prev_text = self.director.ui_state.text if event.type == "append" else None

            self.dispatcher.dispatch(event)
            self._last_event = event

            self._record_backlog_event(event)

            if isinstance(event, SceneExitEvent):
                self._flush_persistent()

            if event.type in self.INTERACTION_TYPES:
                # Record (scene_id, beat_index) into persistent seen_beats for interactive beats
                scene_id = self.vm.current_scene_id
                if scene_id is not None:
                    beat_key = f"{scene_id}:{self.vm.beat_index}"
                    self._last_beat_key = beat_key
                    seen_beats = self.persistent.get("seen_beats")
                    if not isinstance(seen_beats, list):
                        seen_beats = list(self._seen_beats_set)
                        self.persistent["seen_beats"] = seen_beats
                    self._current_beat_previously_seen = beat_key in self._seen_beats_set
                    if not self._current_beat_previously_seen:
                        self._seen_beats_set.add(beat_key)
                        seen_beats.append(beat_key)
                        self._persistent_dirty = True
                else:
                    self._last_beat_key = None
                    self._current_beat_previously_seen = False

                if event.type in ("dialogue", "narration", "fresh_box"):
                    self._setup_text_reveal(getattr(event, "text", ""))
                elif event.type == "append":
                    initial_chars = 0
                    if prev_text:
                        from eager.core.text import parse_text_tags

                        initial_chars = len(parse_text_tags(prev_text).plain_text)
                    self._setup_text_reveal(self.director.ui_state.text, initial_visible_chars=initial_chars)
                elif event.type in ("choice_prompt", "story_end"):
                    self.text_reveal = None
                    self.director.ui_state.visible_chars = None

                if isinstance(event, ChoicePromptEvent):
                    self.active_choice_prompt = event
                    if hasattr(self.overlay, "set_choice_options"):
                        self.overlay.set_choice_options(event.options)
                elif isinstance(event, StoryEndEvent):
                    self.is_finished = True
                    self.mode = "ended"
                    self._flush_persistent()

                cp = self._capture_checkpoint()
                self.checkpoints.push(cp)
                if (
                    (entered_new_scene or isinstance(event, StoryEndEvent))
                    and getattr(self.preferences, "autosave_enabled", True)
                    and not self.skip_mode
                ):
                    self.save_manager.autosave(cp, playtime_seconds=self._playtime)
                return event

        if self.vm.is_ended:
            self.is_finished = True
            self.mode = "ended"
            self._flush_persistent()
            cp = self._capture_checkpoint()
            self.checkpoints.push(cp)
            if getattr(self.preferences, "autosave_enabled", True) and not self.skip_mode:
                self.save_manager.autosave(cp, playtime_seconds=self._playtime)

        return None

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

    def rollback(self) -> bool:
        """Roll back to the previous interactive checkpoint."""
        return _rollback(self)

    def restart_story(self) -> StoryEvent | None:
        """Reset the session to the beginning of the screenplay and advance the initial beat."""
        logger.info("Restarting story session")
        self.vm = StoryVM(
            self.graph,
            persistent=self.persistent,
        )
        if hasattr(self.stage, "clear_stage"):
            self.stage.clear_stage()
        self.audio.stop_all()

        self.checkpoints.clear()
        self.backlog.clear()
        self.is_finished = False
        self.mode = "game"
        self._playtime = 0.0
        self.skip_mode = False
        self._skip_timer = 0.0
        self.auto_mode = False
        self.auto_timer = 0.0
        self.active_choice_prompt = None
        self.text_reveal = None
        self._last_event = None
        self._last_beat_key = None
        self._current_beat_previously_seen = False

        if hasattr(self.screens, "hide"):
            self.screens.hide(self)

        return self.advance()

    def return_to_title(self) -> bool:
        """Halt story execution and return to the main TitleScreen."""
        logger.info("Returning to title screen")
        self._flush_persistent()
        self.audio.stop_all()
        self.skip_mode = False
        self._skip_timer = 0.0
        self.auto_mode = False
        self.mode = "title"
        if hasattr(self.screens, "show"):
            return bool(self.screens.show("title", self))
        return False

    def is_current_beat_read(self) -> bool:
        """Return True if the current beat was already seen in a previous playthrough."""
        return self._current_beat_previously_seen

    def update(self, dt: float) -> None:
        """Update animation timelines, compositor, audio, typewriter reveal, timers, and playtime."""
        safe_dt = max(0.0, dt)
        self.audio.update(safe_dt)

        if bool(getattr(self.screens, "is_active", False)) or self.mode == "title":
            return

        if safe_dt > 0.0:
            self._playtime += safe_dt

        self.director.step(safe_dt)

        if self.text_reveal is not None and not self.text_reveal.is_complete:
            self.text_reveal.update(safe_dt)
            if self.text_reveal.is_complete:
                self.director.ui_state.visible_chars = None
            else:
                self.director.ui_state.visible_chars = int(self.text_reveal.visible_chars)

        if hasattr(self.overlay, "update_toast"):
            self.overlay.update_toast(safe_dt)

        if self.skip_mode and not self.is_finished:
            if self.text_reveal is not None:
                self.text_reveal.complete_immediately()
                self.director.ui_state.visible_chars = None
            if self.active_choice_prompt is not None:
                self.skip_mode = False
            else:
                self._skip_timer += safe_dt
                step_interval = getattr(self, "skip_interval", 0.03)
                if step_interval <= 0.0:
                    step_interval = 0.001
                max_skip_per_frame = 32
                advances = 0
                while (
                    self.skip_mode
                    and not self.is_finished
                    and self.active_choice_prompt is None
                    and self._skip_timer >= step_interval
                    and advances < max_skip_per_frame
                ):
                    self._skip_timer -= step_interval
                    advances += 1
                    if not getattr(self.preferences, "skip_unseen", False) and not self._current_beat_previously_seen:
                        self.skip_mode = False
                        break

                    self.advance()
                    if not getattr(self.preferences, "skip_unseen", False) and not self._current_beat_previously_seen:
                        self.skip_mode = False
                        break
                if advances >= max_skip_per_frame and self._skip_timer >= step_interval:
                    self._skip_timer = step_interval * 0.5
        elif (
            self.auto_mode
            and not self.is_finished
            and self.active_choice_prompt is None
        ):
            reveal_done = self.text_reveal is None or self.text_reveal.is_complete
            voice_playing = self.audio.is_playing("voice")
            if reveal_done and not voice_playing:
                self.auto_timer += safe_dt
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

    def draw(
        self,
        ui_backend: Any,
        width: int,
        height: int,
        *,
        include_screens: bool = True,
    ) -> None:
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
                is_finished=self.is_finished,
                show_quick_menu=True,
                status_badge=status_badge,
                is_read=is_read,
            )

        if include_screens and self.screens.active_screen:
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
