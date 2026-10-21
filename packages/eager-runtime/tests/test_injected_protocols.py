"""Tests for injecting abstract StageProtocol and UIProtocol into GameSession."""

from typing import Any

import eager_script
from eager_core.events import ChoicePromptEvent, DialogueEvent
from eager_core.protocols import StageProtocol, UIProtocol

from eager_runtime import GameSession
from eager_runtime.headless import NullStage, NullUI

SAMPLE_SCRIPT = """
## Start --- start
Alice: Welcome to the abstract stage!
Bob: Where visuals are decoupled.
? Path A (path_a)
? Path B (path_b)

## Path A --- path_a
Alice: You chose Path A.

## Path B --- path_b
Bob: You chose Path B.
"""


class CustomMockUIState:
    def __init__(self) -> None:
        self.speaker: str | None = None
        self.text: str = ""
        self.emotion: str | None = None
        self.choices: list[Any] = []
        self.is_finished: bool = False
        self.visible_chars: int | None = None

    def clear_choices(self) -> None:
        self.choices.clear()

    def clear_dialogue(self) -> None:
        self.speaker = None
        self.text = ""
        self.emotion = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "choices": self.choices,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CustomMockUIState":
        inst = cls()
        inst.speaker = data.get("speaker")
        inst.text = data.get("text", "")
        inst.choices = data.get("choices", [])
        return inst


class CustomMockStage:
    def __init__(self) -> None:
        self.ui_state = CustomMockUIState()
        self.bound_dispatcher: Any = None
        self.stepped_dt: float = 0.0
        self.saved_states: list[dict[str, Any]] = []

    def bind(self, dispatcher: Any) -> None:
        self.bound_dispatcher = dispatcher
        dispatcher.on_event(DialogueEvent)(self._on_dialogue)
        dispatcher.on_event(ChoicePromptEvent)(self._on_choice)

    def _on_dialogue(self, event: DialogueEvent) -> None:
        self.ui_state.speaker = event.speaker
        self.ui_state.text = event.text

    def _on_choice(self, event: ChoicePromptEvent) -> None:
        self.ui_state.choices = list(event.options)

    def step(self, dt: float) -> None:
        self.stepped_dt += dt

    def save_visual_state(self) -> dict[str, Any]:
        state = {"custom_marker": 42}
        self.saved_states.append(state)
        return state

    def load_visual_state(self, state: dict[str, Any]) -> None:
        pass

    def save_ui_state(self) -> dict[str, Any]:
        return self.ui_state.to_dict()

    def restore_ui_state(self, state: dict[str, Any]) -> None:
        self.ui_state = CustomMockUIState.from_dict(state)


class CustomMockUI:
    def __init__(self) -> None:
        self.error_overlay: str | None = None
        self.viewports: list[tuple[int, int]] = []
        self.draw_calls: int = 0

    def set_viewport(self, width: int, height: int) -> None:
        self.viewports.append((width, height))

    def draw(self, *args: Any, **kwargs: Any) -> None:
        self.draw_calls += 1

    def sync(self, *args: Any, **kwargs: Any) -> None:
        pass

    def hit_test_choice(self, x: float, y: float) -> int | None:
        return None

    def hit_test_quick_action(self, x: float, y: float) -> str | None:
        return None


def test_injected_stage_and_ui():
    graph = eager_script.parse_graph(SAMPLE_SCRIPT)
    custom_stage = CustomMockStage()
    custom_ui = CustomMockUI()

    assert isinstance(custom_stage, StageProtocol)
    assert isinstance(custom_ui, UIProtocol)

    session = GameSession(graph, stage=custom_stage, ui=custom_ui)

    assert session.stage is custom_stage
    assert session.director is custom_stage
    assert session.ui is custom_ui
    assert session.overlay is custom_ui
    assert custom_stage.bound_dispatcher is session.dispatcher

    # Advance dialogue
    evt = session.advance()
    assert evt is not None
    assert evt.type == "dialogue"
    assert custom_stage.ui_state.speaker == "Alice"
    assert custom_stage.ui_state.text == "Welcome to the abstract stage!"

    # Step update
    session.update(0.016)
    assert custom_stage.stepped_dt > 0.0

    # Draw
    dummy_backend = object()
    session.draw(dummy_backend, 1920, 1080)
    assert (1920, 1080) in custom_ui.viewports
    assert custom_ui.draw_calls == 1

    # Checkpoint capture and rollback
    session.advance()  # Bob
    assert custom_stage.ui_state.speaker == "Bob"

    assert session.can_rollback
    session.rollback()
    # Rolled back to Alice
    assert custom_stage.ui_state.speaker == "Alice"


def test_null_stage_and_null_ui():
    graph = eager_script.parse_graph(SAMPLE_SCRIPT)
    stage = NullStage()
    ui = NullUI()

    session = GameSession(graph, stage=stage, ui=ui)
    assert isinstance(session.stage, StageProtocol)
    assert isinstance(session.ui, UIProtocol)

    evt = session.advance()
    assert evt is not None
    assert session.director.ui_state.speaker == "Alice"
    assert session.director.ui_state.text == "Welcome to the abstract stage!"

    evt2 = session.advance()
    assert evt2 is not None
    assert session.director.ui_state.speaker == "Bob"

    evt3 = session.advance()
    assert evt3 is not None
    assert evt3.type == "choice_prompt"

    session.choose(0)
    assert session.director.ui_state.speaker == "Alice"
    assert "Path A" in session.director.ui_state.text


def test_default_headless_fallback_when_providers_empty():
    from unittest.mock import patch

    from eager_core.protocols import reset_providers
    from eager_graphics import register_providers

    try:
        reset_providers()
        graph = eager_script.parse_graph(SAMPLE_SCRIPT)
        # 1. Explicit headless=True creates headless NullStage / NullUI
        session_headless = GameSession(graph, headless=True)
        assert isinstance(session_headless.stage, NullStage)
        assert isinstance(session_headless.ui, NullUI)

        # 2. When provider loading finds no providers, defaults to NullStage / NullUI
        with patch("eager_runtime.session.load_providers"):
            reset_providers()
            session_no_providers = GameSession(graph)
            assert isinstance(session_no_providers.stage, NullStage)
            assert isinstance(session_no_providers.ui, NullUI)

            evt = session_no_providers.advance()
            assert evt is not None
            assert session_no_providers.director.ui_state.speaker == "Alice"
    finally:
        # Restore graphics providers so subsequent tests have them
        register_providers()
