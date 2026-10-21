"""Base interactive player abstraction driving a GameSession."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from eager_core.events import ChoicePromptEvent
from eager_core.input import InputAction, Keymap

from eager_graphics.types import DebugOverlayMode, ScaleMode
from eager_graphics.ui_components import UIOverlay

if TYPE_CHECKING:
    from pathlib import Path


class BasePlayer:
    """Base interactive visual novel player driving a GameSession.

    Extracts state mirroring, overlay synchronization, story progression,
    rollback, hot reload, keysym normalization, and input routing so that backend
    players only need to handle window creation, frame loops, and renderer presentation.
    """

    def __init__(
        self,
        session: Any,
        width: int = 1280,
        height: int = 720,
        title: str = "Eager-Graphics Visual Novel",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        vsync: bool = True,
        visible: bool = True,
        show_fps: bool | str | DebugOverlayMode = True,
        uncapped: bool = False,
    ) -> None:
        self.session: Any = session
        self.width: int = width
        self.height: int = height
        self.title: str = title
        self.asset_dir: str | Path | None = asset_dir
        self.scale_mode: ScaleMode = scale_mode
        self.uncapped: bool = uncapped

        self.vm: Any = getattr(session, "vm", None)
        self.compositor: Any = getattr(session, "compositor", None)
        self.director: Any = getattr(session, "director", None)
        self.dispatcher: Any = getattr(session, "dispatcher", None)
        self.audio: Any = getattr(session, "audio", None)
        self.keymap: Keymap = getattr(session, "keymap", None) or Keymap()
        self.overlay: Any = getattr(session, "overlay", None) or UIOverlay(width=width, height=height)
        self.overlay.set_viewport(width, height)

        # Debug overlay mode
        if isinstance(show_fps, DebugOverlayMode):
            self.debug_mode: DebugOverlayMode = show_fps
        elif isinstance(show_fps, str):
            try:
                self.debug_mode = DebugOverlayMode(show_fps.lower())
            except ValueError:
                self.debug_mode = DebugOverlayMode.FPS if show_fps else DebugOverlayMode.OFF
        elif show_fps:
            self.debug_mode = DebugOverlayMode.FPS
        else:
            self.debug_mode = DebugOverlayMode.OFF

        # Narrative UI State
        self.current_speaker: str | None = None
        self.current_text: str = ""
        self.current_emotion: str | None = None
        self.active_choice_prompt: ChoicePromptEvent | None = None
        self.active_input_prompt: Any | None = None
        self.is_finished: bool = False
        self._ui_dirty: bool = True

    @property
    def show_fps(self) -> bool:
        """True if the debug overlay is active in either FPS or DETAILED mode."""
        return self.debug_mode != DebugOverlayMode.OFF

    @show_fps.setter
    def show_fps(self, value: bool | str | DebugOverlayMode) -> None:
        if isinstance(value, DebugOverlayMode):
            self.debug_mode = value
        elif isinstance(value, str):
            try:
                self.debug_mode = DebugOverlayMode(value.lower())
            except ValueError:
                self.debug_mode = DebugOverlayMode.FPS if value else DebugOverlayMode.OFF
        elif value:
            self.debug_mode = DebugOverlayMode.FPS
        else:
            self.debug_mode = DebugOverlayMode.OFF

    def toggle_debug_overlay(self) -> None:
        """Toggle or cycle debug overlay visibility."""
        self.show_fps = not self.show_fps

    def _mark_ui_dirty(self) -> None:
        """Mark UI dirty for backends that optimize rendering based on dirty state."""
        self._ui_dirty = True

    def _sync_overlay(self) -> None:
        """Mirror current narrative state onto the UI components.

        Called whenever the active choice prompt, input prompt, or dialogue changes so that
        input handling sees up-to-date layout even before the next draw.
        """
        if self.director is not None:
            self.current_speaker = self.director.ui_state.speaker
            self.current_text = self.director.ui_state.text
            self.current_emotion = self.director.ui_state.emotion
        input_text = getattr(self.session, "input_text", None)
        is_read = (
            self.session.is_current_beat_read()
            if hasattr(self.session, "is_current_beat_read")
            else False
        )
        self.overlay.sync(
            self.director.ui_state if self.director is not None else None,
            self.active_choice_prompt,
            self.active_input_prompt,
            input_text=input_text,
            is_read=is_read,
        )

    def _sync_state(self) -> None:
        """Mirror active prompts and finished flag from session and refresh overlay."""
        self.active_choice_prompt = self.session.active_choice_prompt
        self.active_input_prompt = self.session.active_input_prompt
        self.is_finished = self.session.is_finished
        self._sync_overlay()

    def advance_story(self) -> None:
        """Advance the story by forwarding to the owning :class:`GameSession`."""
        self._mark_ui_dirty()
        self.session.advance()
        self._sync_state()

    def make_choice(self, choice_index: int) -> None:
        """Select a branching choice option and continue execution."""
        self._mark_ui_dirty()
        self.session.choose(choice_index)
        self._sync_state()

    def rollback(self) -> bool:
        """Rollback narrative and stage state by one beat."""
        self._mark_ui_dirty()
        success = self.session.rollback()
        self._sync_state()
        return success

    def hot_reload(self) -> bool:
        """Hot-reload screenplay from disk, hot-swap VM, reconcile state, and force a redraw."""
        result = self.session.hot_reload()
        self._sync_state()
        self._mark_ui_dirty()
        return result

    def step_initial_beat(self) -> None:
        """Step first beat if not starting in an active menu screen."""
        has_active_screen = getattr(getattr(self.session, "screens", None), "is_active", False)
        if not has_active_screen:
            self.advance_story()

    def on_resize(self, width: int, height: int) -> None:
        """Keep the UI components laid out against the new window size."""
        self.width = width
        self.height = height
        self.overlay.set_viewport(width, height)

    def tick(self, dt: float) -> None:
        """Advance animations and pump audio mixer / session logic."""
        self.session.update(dt)
        if getattr(self.session, "_ui_dirty", False):
            self.session._ui_dirty = False
            self._mark_ui_dirty()
            self._sync_overlay()
        self.active_choice_prompt = self.session.active_choice_prompt
        self.active_input_prompt = self.session.active_input_prompt
        self.is_finished = self.session.is_finished

    def close(self) -> None:
        """Release audio mixer resources."""
        if self.audio is not None:
            self.audio.shutdown()

    @staticmethod
    def normalize_keysym(raw_key: str) -> str:
        """Normalize platform/backend keysym strings to canonical Eager key names."""
        k = raw_key.lower()
        if k.startswith("_") and len(k) == 2 and k[1].isdigit():
            return k[1]
        if k.startswith("num_") and len(k) == 5 and k[4].isdigit():
            return k[4]
        if k in ("return", "num_enter"):
            return "enter"
        if k == "prior":
            return "pageup"
        if k == "next":
            return "pagedown"
        if k in ("control_l", "control_r", "lctrl", "rctrl"):
            return "ctrl"
        return k

    def handle_key_press(
        self,
        raw_key: str,
        *,
        is_shift: bool = False,
        char: str | None = None,
    ) -> bool:
        """Handle a key press with normalized keysym, prompt handling, and action mapping."""
        keysym = self.normalize_keysym(raw_key)

        # Active input prompt handling
        if self.active_input_prompt is not None:
            if keysym == "enter":
                self._mark_ui_dirty()
                self.session.handle_input(InputAction.CONFIRM)
                self._sync_state()
                return True
            if keysym == "backspace":
                self._mark_ui_dirty()
                self.session.handle_input(InputAction.TEXT_BACKSPACE)
                self._sync_overlay()
                return True
            if char and char.isprintable():
                self._mark_ui_dirty()
                self.session.handle_input(InputAction.TEXT_CHAR, char=char)
                self._sync_overlay()
                return True

        # 1-9 choice keys
        if self.active_choice_prompt is not None and keysym in "123456789":
            idx = int(keysym) - 1
            if idx < len(self.active_choice_prompt.options):
                self._mark_ui_dirty()
                self.session.handle_input(InputAction.CHOOSE, index=idx)
                self._sync_state()
                return True

        combo = f"shift+{keysym}" if is_shift else keysym
        action = self.keymap.map_key(combo) or self.keymap.map_key(keysym)
        if action == InputAction.QUIT:
            self.close()
            return True
        if action == InputAction.DEBUG_OVERLAY:
            self.toggle_debug_overlay()
            return True
        if action:
            self._mark_ui_dirty()
            self.session.handle_input(action)
            self._sync_state()
            return True

        return False

    def handle_text_input(self, text: str) -> bool:
        """Handle typed text input when an input prompt is active."""
        if self.active_input_prompt is not None and text and text.isprintable():
            self._mark_ui_dirty()
            for char in text:
                self.session.handle_input(InputAction.TEXT_CHAR, char=char)
            self._sync_overlay()
            return True
        return False

    def handle_pointer_move(self, x: float, y: float) -> bool:
        """Handle mouse movement for screen and button hover states."""
        changed = self.session.handle_input(InputAction.POINTER_MOVE, x=x, y=y)
        if changed:
            self._mark_ui_dirty()
        return bool(changed)

    def handle_pointer_click(self, x: float, y: float) -> None:
        """Handle mouse clicks for advancement, screens, or choice selection."""
        self._mark_ui_dirty()
        self.session.handle_input(InputAction.POINTER_CLICK, x=x, y=y)
        self._sync_state()

    def handle_scroll(self, dy: float) -> None:
        """Handle mouse wheel scrolling for rollback or roll-forward."""
        self._mark_ui_dirty()
        if dy > 0:
            self.session.handle_input(InputAction.ROLLBACK)
        elif dy < 0:
            self.session.handle_input(InputAction.ROLL_FORWARD)
        self._sync_state()

    def handle_skip_release(self) -> None:
        """Handle key release for skip keys (e.g. releasing Ctrl)."""
        self.session.handle_input(InputAction.SKIP_RELEASE)
