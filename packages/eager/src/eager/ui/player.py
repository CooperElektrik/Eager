"""Base interactive player abstraction driving a GameSession."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Any as GameSessionProtocol

from eager.core.events import ChoicePromptEvent
from eager.core.input import InputAction, Keymap, normalize_keysym
from eager.core.types import ScaleMode
from eager.ui.components import UIOverlay

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "BasePlayer",
]


class BasePlayer:
    """Base interactive visual novel player driving a GameSession."""

    def __init__(
        self,
        session: GameSessionProtocol,
        width: int = 1280,
        height: int = 720,
        title: str = "Eager-Graphics Visual Novel",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        vsync: bool = True,
        visible: bool = True,
        uncapped: bool = False,
    ) -> None:
        self.session: GameSessionProtocol = session
        if session is not None and hasattr(session, "add_lifecycle_listener"):
            session.add_lifecycle_listener(self)
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

        # Narrative UI State
        self.current_speaker: str | None = None
        self.current_text: str = ""
        self.current_emotion: str | None = None
        self.active_choice_prompt: ChoicePromptEvent | None = None
        self.is_finished: bool = False

    def toggle_fullscreen(self) -> None:
        """Toggle fullscreen mode if supported by the player implementation."""

    def _sync_overlay(self) -> None:
        """Mirror current narrative state onto the UI components."""
        if self.director is not None:
            self.current_speaker = self.director.ui_state.speaker
            self.current_text = self.director.ui_state.text
            self.current_emotion = self.director.ui_state.emotion
        is_read = (
            self.session.is_current_beat_read()
            if hasattr(self.session, "is_current_beat_read")
            else False
        )
        self.overlay.sync(
            self.director.ui_state if self.director is not None else None,
            self.active_choice_prompt,
            is_read=is_read,
        )

    def sync_state(self) -> None:
        """Mirror active prompts and finished flag from session and refresh overlay."""
        self.active_choice_prompt = self.session.active_choice_prompt
        self.is_finished = self.session.is_finished
        self._sync_overlay()

    def advance_story(self) -> None:
        """Advance the story by forwarding to the owning :class:`GameSession`."""
        self.session.advance()
        self.sync_state()

    def make_choice(self, choice_index: int) -> None:
        """Select a branching choice option and continue execution."""
        self.session.choose(choice_index)
        self.sync_state()

    def rollback(self) -> bool:
        """Rollback narrative and stage state by one beat."""
        success = self.session.rollback()
        self.sync_state()
        return success

    def step_initial_beat(self) -> None:
        """Step first beat if not starting in an active menu screen."""
        screens = getattr(self.session, "screens", None)
        has_active_screen = screens.is_active if screens is not None else False
        if not has_active_screen:
            self.advance_story()

    def on_resize(self, width: int, height: int) -> None:
        """Keep the UI components laid out against the new window size."""
        if width == self.width and height == self.height:
            return
        self.width = width
        self.height = height
        self.overlay.set_viewport(width, height)
        screens = getattr(self.session, "screens", None)
        if screens is not None and hasattr(screens, "set_viewport"):
            screens.set_viewport(width, height)

    def tick(self, dt: float) -> None:
        """Advance animations and pump audio mixer / session logic."""
        self.session.update(dt)
        self._sync_overlay()
        self.active_choice_prompt = self.session.active_choice_prompt
        self.is_finished = self.session.is_finished

    def on_request_fullscreen(self) -> None:
        """Handle fullscreen toggle request from session input."""
        self.toggle_fullscreen()

    def on_request_quit(self) -> None:
        """Handle quit request from session input."""
        self.close()

    def on_state_restored(self) -> None:
        """Handle session checkpoint/state restoration."""
        self.sync_state()

    def close(self) -> None:
        """Release session listener and audio mixer resources."""
        if self.session is not None and hasattr(self.session, "remove_lifecycle_listener"):
            self.session.remove_lifecycle_listener(self)
        if self.audio is not None:
            self.audio.shutdown()

    @staticmethod
    def normalize_keysym(raw_key: str) -> str:
        """Normalize platform/backend keysym strings to canonical Eager key names."""
        return normalize_keysym(raw_key)

    def handle_key_press(
        self,
        raw_key: str,
        *,
        is_shift: bool = False,
        char: str | None = None,
    ) -> bool:
        """Handle a key press with normalized keysym, prompt handling, and action mapping."""
        keysym = self.normalize_keysym(raw_key)
        combo = f"shift+{keysym}" if is_shift else keysym

        screens = getattr(self.session, "screens", None)
        if (
            screens is not None
            and getattr(screens, "is_active", False) is True
            and hasattr(screens, "handle_key")
            and screens.handle_key(combo, self.session) is True
        ):
            self.sync_state()
            return True

        # 1-9 choice keys
        if self.active_choice_prompt is not None and keysym in "123456789":
            idx = int(keysym) - 1
            if idx < len(self.active_choice_prompt.options):
                self.session.handle_input(InputAction.CHOOSE, index=idx)
                self.sync_state()
                return True

        action = self.keymap.map_key(combo) or self.keymap.map_key(keysym)
        if action == InputAction.QUIT:
            self.close()
            return True
        if action == InputAction.FULLSCREEN:
            self.toggle_fullscreen()
            return True
        if action:
            self.session.handle_input(action)
            self.sync_state()
            return True

        return False

    def handle_pointer_move(self, x: float, y: float) -> bool:
        """Handle mouse movement for screen and button hover states."""
        return bool(self.session.handle_input(InputAction.POINTER_MOVE, x=x, y=y))

    def handle_pointer_click(self, x: float, y: float) -> None:
        """Handle mouse clicks for advancement, screens, or choice selection."""
        self.session.handle_input(InputAction.POINTER_CLICK, x=x, y=y)
        self.sync_state()

    def handle_scroll(self, dy: float) -> None:
        """Handle mouse wheel scrolling."""
        self.session.handle_input(InputAction.SCROLL, dy=dy)
        self.sync_state()

    def handle_skip_release(self) -> None:
        """Handle key release for skip keys (e.g. releasing Ctrl)."""
        self.session.handle_input(InputAction.SKIP_RELEASE)
