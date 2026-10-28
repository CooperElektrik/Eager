"""Headless, dependency-free implementations of Stage and UI protocols.

These classes satisfy StageProtocol and UIProtocol so that GameSession can
operate completely headless without requiring eager-graphics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eager_core.events import (
    AppendEvent,
    ChoiceOption,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    NarrationEvent,
    StoryEndEvent,
)

__all__ = [
    "HeadlessUIState",
    "NullCompositor",
    "NullScreenManager",
    "NullStage",
    "NullUI",
]


@dataclass
class HeadlessUIState:
    """Headless state tracking dialogue, choices, and story state."""

    speaker: str | None = None
    text: str = ""
    emotion: str | None = None
    choices: list[ChoiceOption] = field(default_factory=list)
    is_finished: bool = False
    side_image: str | None = None
    visible_chars: int | None = None
    speaker_color: Any = None

    def clear_dialogue(self) -> None:
        """Clear active speaker, dialogue text, emotion, and side image."""
        self.speaker = None
        self.text = ""
        self.emotion = None
        self.side_image = None
        self.visible_chars = None
        self.speaker_color = None

    def clear_choices(self) -> None:
        """Clear all active choice options."""
        self.choices.clear()

    def to_dict(self) -> dict[str, Any]:
        """Serialize headless UI state to a dictionary.

        Returns:
            Dictionary containing UI state fields.
        """
        return {
            "speaker": self.speaker,
            "text": self.text,
            "emotion": self.emotion,
            "choices": [
                c.to_dict() if hasattr(c, "to_dict") else c
                for c in self.choices
            ],
            "is_finished": self.is_finished,
            "side_image": self.side_image,
            "visible_chars": self.visible_chars,
            "speaker_color": self.speaker_color,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HeadlessUIState:
        """Reconstruct a HeadlessUIState from a serialized dictionary.

        Args:
            data: Dictionary containing serialized UI state attributes.

        Returns:
            Constructed HeadlessUIState instance.
        """
        raw_choices = data.get("choices", [])
        choices = [
            ChoiceOption.from_dict(c) if isinstance(c, dict) else c
            for c in raw_choices
        ]
        return cls(
            speaker=data.get("speaker"),
            text=data.get("text", ""),
            emotion=data.get("emotion"),
            choices=choices,
            is_finished=bool(data.get("is_finished", False)),
            side_image=data.get("side_image"),
            visible_chars=data.get("visible_chars"),
            speaker_color=data.get("speaker_color"),
        )


class NullCompositor:
    """Headless compositor stub."""

    def __init__(self, virtual_width: int = 1920, virtual_height: int = 1080) -> None:
        """Initialize NullCompositor with virtual dimensions.

        Args:
            virtual_width: Virtual stage width in pixels. Defaults to 1920.
            virtual_height: Virtual stage height in pixels. Defaults to 1080.
        """
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height

    def step(self, dt: float) -> None:
        """Advance headless animation timers by dt seconds.

        Args:
            dt: Delta time elapsed in seconds.
        """

    def finish_animations(self) -> None:
        """Immediately complete active headless animations."""

    def render_list(self) -> list[Any]:
        """Return empty list of render items for headless operation.

        Returns:
            Empty list.
        """
        return []

    def save_state(self) -> dict[str, Any]:
        """Serialize compositor state to a dictionary.

        Returns:
            Empty dictionary for headless compositor.
        """
        return {}

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore compositor state from a dictionary.

        Args:
            state: Serialized compositor state dictionary.
        """


class NullStage:
    """Headless stage implementing StageProtocol."""

    def __init__(self, virtual_width: int = 1920, virtual_height: int = 1080) -> None:
        """Initialize NullStage with virtual dimensions.

        Args:
            virtual_width: Virtual stage width in pixels.
            virtual_height: Virtual stage height in pixels.
        """
        self.ui_state = HeadlessUIState()
        self.compositor = NullCompositor(virtual_width, virtual_height)
        self.characters: dict[str, dict[str, Any]] = {}

    def register_character(
        self,
        character_id: str,
        *,
        name: str | None = None,
        asset_prefix: str | None = None,
        default_expression: str = "default",
        default_position: str = "center",
        side_image: str | None = None,
        color: Any = None,
    ) -> None:
        """Register a character metadata configuration on the headless stage.

        Args:
            character_id: Unique character identifier string.
            name: Character display name.
            asset_prefix: File prefix for character art assets.
            default_expression: Initial expression tag.
            default_position: Initial stage position tag.
            side_image: Path or identifier of dialogue side image.
            color: Color value or hex string for speaker label.
        """
        cid = character_id.strip().lower()
        self.characters[cid] = {
            "name": name,
            "asset_prefix": asset_prefix,
            "default_expression": default_expression,
            "default_position": default_position,
            "side_image": side_image,
            "color": color,
        }

    def bind(self, dispatcher: Any) -> None:
        """Bind stage event handlers to the runtime event dispatcher.

        Args:
            dispatcher: EventDispatcher instance.
        """
        dispatcher.on_event(DialogueEvent)(self._on_dialogue)
        dispatcher.on_event(NarrationEvent)(self._on_narration)
        dispatcher.on_event(AppendEvent)(self._on_append)
        dispatcher.on_event(FreshBoxEvent)(self._on_fresh_box)
        dispatcher.on_event(ChoicePromptEvent)(self._on_choice)
        dispatcher.on_event(StoryEndEvent)(self._on_story_end)

    def _on_dialogue(self, event: DialogueEvent) -> None:
        char_info: dict[str, Any] | None = None
        if event.speaker:
            sid = event.speaker.strip().lower()
            if sid in self.characters:
                char_info = self.characters[sid]
            else:
                for cinfo in self.characters.values():
                    if cinfo.get("name") and str(cinfo["name"]).strip().lower() == sid:
                        char_info = cinfo
                        break

        self.ui_state.speaker = event.speaker
        self.ui_state.text = event.text
        self.ui_state.emotion = event.emotion
        self.ui_state.visible_chars = None
        self.ui_state.speaker_color = char_info.get("color") if char_info else None
        self.ui_state.side_image = char_info.get("side_image") if char_info else None
        self.ui_state.clear_choices()

    def _on_narration(self, event: NarrationEvent) -> None:
        self.ui_state.speaker = None
        self.ui_state.text = event.text
        self.ui_state.emotion = None
        self.ui_state.visible_chars = None
        self.ui_state.clear_choices()

    def _on_append(self, event: AppendEvent) -> None:
        add_text = event.text
        current = self.ui_state.text or ""
        self.ui_state.text = f"{current} {add_text}".strip()
        self.ui_state.clear_choices()

    def _on_fresh_box(self, event: FreshBoxEvent) -> None:
        self.ui_state.text = event.text
        self.ui_state.visible_chars = None
        self.ui_state.clear_choices()

    def _on_choice(self, event: ChoicePromptEvent) -> None:
        self.ui_state.choices = list(event.options)

    def _on_story_end(self, event: StoryEndEvent) -> None:
        self.ui_state.is_finished = True

    def step(self, dt: float) -> None:
        """Advance headless stage animations by dt seconds.

        Args:
            dt: Delta time elapsed in seconds.
        """
        self.compositor.step(dt)

    def finish_animations(self) -> None:
        """Immediately complete active stage animations."""
        self.compositor.finish_animations()

    def save_visual_state(self) -> dict[str, Any]:
        """Serialize current visual stage state for checkpointing.

        Returns:
            Dictionary containing compositor state.
        """
        return {
            "compositor": self.compositor.save_state(),
        }

    def load_visual_state(self, state: dict[str, Any]) -> None:
        """Restore visual stage state from serialized checkpoint data.

        Args:
            state: Serialized checkpoint state dictionary.
        """
        if comp := state.get("compositor"):
            self.compositor.load_state(comp)
        if ui := state.get("ui_state"):
            self.ui_state = HeadlessUIState.from_dict(ui)

    def save_ui_state(self) -> dict[str, Any]:
        """Serialize current headless UI state.

        Returns:
            Serialized UI state dictionary.
        """
        return self.ui_state.to_dict()

    def restore_ui_state(self, state: dict[str, Any]) -> None:
        """Restore headless UI state from serialized dictionary.

        Args:
            state: Serialized UI state dictionary.
        """
        self.ui_state = HeadlessUIState.from_dict(state)


class NullUI:
    """Headless UI stub implementing UIProtocol."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        """Initialize NullUI with viewport dimensions.

        Args:
            width: Viewport width in pixels. Defaults to 1280.
            height: Viewport height in pixels. Defaults to 720.
        """
        self.width = width
        self.height = height
        self.error_overlay: str | None = None
        self.choice_menu: Any = None
        self.dialogue_box: Any = None
        self.input_box: Any = None
        self.quick_menu: Any = None
        self._selected_choice: int | None = None
        self._hovered_quick_action: str | None = None
        self._input_text: str = ""

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions for layout calculations.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """
        self.width = width
        self.height = height

    def draw(self, *args: Any, **kwargs: Any) -> None:
        """No-op draw method for headless UI."""

    def sync(self, *args: Any, **kwargs: Any) -> None:
        """No-op sync method for headless UI."""

    def hit_test_choice(self, x: float, y: float) -> int | None:
        """Always return None for headless choice hit test.

        Args:
            x: Cursor X coordinate.
            y: Cursor Y coordinate.

        Returns:
            Always None.
        """
        return None

    def hit_test_quick_action(self, x: float, y: float) -> str | None:
        """Always return None for headless quick action hit test.

        Args:
            x: Cursor X coordinate.
            y: Cursor Y coordinate.

        Returns:
            Always None.
        """
        return None

    def get_selected_choice(self) -> int | None:
        """Return index of the currently selected choice option, or None.

        Returns:
            Selected choice index or None.
        """
        return self._selected_choice

    def set_selected_choice(self, index: int | None) -> None:
        """Update selected choice option index.

        Args:
            index: Target choice option index, or None to deselect.
        """
        self._selected_choice = index

    def set_choice_options(self, options: Any) -> None:
        """No-op update for choice menu options.

        Args:
            options: Choice options list or sequence.
        """

    def set_input_text(self, text: str) -> None:
        """Set current text buffer for input prompt.

        Args:
            text: Input string.
        """
        self._input_text = text

    def update_input(self, dt: float) -> None:
        """Advance cursor or timers in input prompt.

        Args:
            dt: Delta time elapsed in seconds.
        """

    def set_dialogue_visible_chars(
        self,
        visible_chars: int | None = None,
        *,
        show_arrow: bool = True,
    ) -> None:
        """No-op update of visible character count.

        Args:
            visible_chars: Maximum visible characters, or None for all.
            show_arrow: Whether to display continuation indicator. Defaults to True.
        """

    def complete_dialogue_reveal(self, *, show_arrow: bool = True) -> None:
        """No-op immediate reveal for dialogue box text.

        Args:
            show_arrow: Whether to display continuation indicator. Defaults to True.
        """

    def get_hovered_quick_action(self) -> str | None:
        """Return currently hovered quick action identifier.

        Returns:
            Hovered quick action identifier string or None.
        """
        return self._hovered_quick_action

    def set_hovered_quick_action(self, action: str | None) -> None:
        """Update currently hovered quick action identifier.

        Args:
            action: Quick action string identifier or None.
        """
        self._hovered_quick_action = action


class NullScreenManager:
    """Headless screen manager stub implementing ScreenManagerProtocol."""

    def __init__(self) -> None:
        """Initialize empty screen manager."""
        self.screens: dict[str, Any] = {}
        self.active_screen: Any = None

    @property
    def is_active(self) -> bool:
        """Always False for headless screen manager."""
        return False

    def register(self, screen: Any) -> None:
        """Register a screen instance.

        Args:
            screen: Screen instance with a name attribute.
        """
        name = getattr(screen, "name", None)
        if name:
            self.screens[name] = screen

    def show(self, name: str, session: Any) -> bool:
        """Always return False for headless screen display.

        Args:
            name: Screen identifier.
            session: Active GameSession instance.

        Returns:
            Always False.
        """
        return False

    def hide(self, session: Any) -> None:
        """Dismiss active screen.

        Args:
            session: Active GameSession instance.
        """

    def hide_all(self, session: Any) -> None:
        """Dismiss all screens.

        Args:
            session: Active GameSession instance.
        """

    def draw(self, *args: Any, **kwargs: Any) -> None:
        """No-op draw call for headless screen rendering."""

    def handle_mouse_move(self, x: float, y: float) -> bool:
        """No-op mouse move handler.

        Args:
            x: Cursor X coordinate.
            y: Cursor Y coordinate.

        Returns:
            Always False.
        """
        return False

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions.

        Args:
            width: Viewport width in pixels.
            height: Viewport height in pixels.
        """

    def handle_mouse_click(self, x: float, y: float) -> bool:
        """No-op mouse click handler.

        Args:
            x: Cursor X coordinate.
            y: Cursor Y coordinate.

        Returns:
            Always False.
        """
        return False

    def handle_key(self, key_name: str, session: Any = None) -> bool:
        """No-op key press handler.

        Args:
            key_name: Key identifier string.
            session: Active GameSession instance.

        Returns:
            Always False.
        """
        return False
