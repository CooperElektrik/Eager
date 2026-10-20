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

    def clear_dialogue(self) -> None:
        self.speaker = None
        self.text = ""
        self.emotion = None
        self.side_image = None
        self.visible_chars = None

    def clear_choices(self) -> None:
        self.choices.clear()

    def to_dict(self) -> dict[str, Any]:
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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HeadlessUIState:
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
        )


class NullCompositor:
    """Headless compositor stub."""

    def __init__(self, virtual_width: int = 1920, virtual_height: int = 1080) -> None:
        self.virtual_width = virtual_width
        self.virtual_height = virtual_height

    def step(self, dt: float) -> None:
        pass

    def render_list(self) -> list[Any]:
        return []

    def save_state(self) -> dict[str, Any]:
        return {}

    def load_state(self, state: dict[str, Any]) -> None:
        pass


class NullStage:
    """Headless stage implementing StageProtocol."""

    def __init__(self, virtual_width: int = 1920, virtual_height: int = 1080) -> None:
        self.ui_state = HeadlessUIState()
        self.compositor = NullCompositor(virtual_width, virtual_height)

    def bind(self, dispatcher: Any) -> None:
        dispatcher.on_event(DialogueEvent)(self._on_dialogue)
        dispatcher.on_event(NarrationEvent)(self._on_narration)
        dispatcher.on_event(AppendEvent)(self._on_append)
        dispatcher.on_event(FreshBoxEvent)(self._on_fresh_box)
        dispatcher.on_event(ChoicePromptEvent)(self._on_choice)
        dispatcher.on_event(StoryEndEvent)(self._on_story_end)

    def _on_dialogue(self, event: DialogueEvent) -> None:
        self.ui_state.speaker = event.speaker
        self.ui_state.text = event.text
        self.ui_state.emotion = event.emotion
        self.ui_state.visible_chars = None
        self.ui_state.clear_choices()

    def _on_narration(self, event: NarrationEvent) -> None:
        self.ui_state.speaker = None
        self.ui_state.text = event.text
        self.ui_state.emotion = None
        self.ui_state.visible_chars = None
        self.ui_state.clear_choices()

    def _on_append(self, event: AppendEvent) -> None:
        self.ui_state.text += event.text

    def _on_fresh_box(self, event: FreshBoxEvent) -> None:
        self.ui_state.speaker = event.speaker
        self.ui_state.text = event.text
        self.ui_state.emotion = event.emotion
        self.ui_state.visible_chars = None
        self.ui_state.clear_choices()

    def _on_choice(self, event: ChoicePromptEvent) -> None:
        self.ui_state.choices = list(event.options)

    def _on_story_end(self, event: StoryEndEvent) -> None:
        self.ui_state.is_finished = True

    def step(self, dt: float) -> None:
        self.compositor.step(dt)

    def save_visual_state(self) -> dict[str, Any]:
        return {
            "compositor": self.compositor.save_state(),
            "ui_state": self.ui_state.to_dict(),
        }

    def load_visual_state(self, state: dict[str, Any]) -> None:
        if comp := state.get("compositor"):
            self.compositor.load_state(comp)
        if ui := state.get("ui_state"):
            self.ui_state = HeadlessUIState.from_dict(ui)

    def save_ui_state(self) -> dict[str, Any]:
        return self.ui_state.to_dict()

    def restore_ui_state(self, state: dict[str, Any]) -> None:
        self.ui_state = HeadlessUIState.from_dict(state)


class NullUI:
    """Headless UI stub implementing UIProtocol."""

    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.width = width
        self.height = height
        self.error_overlay: str | None = None
        self.choice_menu: Any = None
        self.dialogue_box: Any = None
        self.input_box: Any = None
        self.quick_menu: Any = None

    def set_viewport(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def draw(self, *args: Any, **kwargs: Any) -> None:
        pass

    def sync(self, *args: Any, **kwargs: Any) -> None:
        pass

    def hit_test_choice(self, x: float, y: float) -> int | None:
        return None

    def hit_test_quick_action(self, x: float, y: float) -> str | None:
        return None


class NullScreenManager:
    """Headless screen manager stub implementing ScreenManagerProtocol."""

    def __init__(self) -> None:
        self.screens: dict[str, Any] = {}
        self.active_screen: Any = None

    @property
    def is_active(self) -> bool:
        return False

    def register(self, screen: Any) -> None:
        name = getattr(screen, "name", None)
        if name:
            self.screens[name] = screen

    def show(self, name: str, session: Any) -> bool:
        return False

    def hide(self, session: Any) -> None:
        pass

    def hide_all(self, session: Any) -> None:
        pass

    def draw(self, *args: Any, **kwargs: Any) -> None:
        pass

    def handle_mouse_move(self, x: float, y: float) -> bool:
        return False

    def handle_mouse_click(self, x: float, y: float) -> bool:
        return False

    def handle_key(self, key_name: str, session: Any = None) -> bool:
        return False
