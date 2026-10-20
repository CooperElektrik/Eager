from typing import Any

from eager_core.protocols import (
    ScreenManagerProtocol,
    StageProtocol,
    UIProtocol,
    UIStateProtocol,
)


class DummyUIState:
    def __init__(self) -> None:
        self.speaker: str | None = "Alice"
        self.text: str = "Hello"
        self.emotion: str | None = "happy"
        self.choices: list[Any] = []
        self.is_finished: bool = False
        self.visible_chars: int | None = None

    def clear_choices(self) -> None:
        self.choices.clear()

    def clear_dialogue(self) -> None:
        self.speaker = None
        self.text = ""

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text}


class DummyStage:
    def __init__(self) -> None:
        self.ui_state = DummyUIState()

    def bind(self, dispatcher: Any) -> None:
        pass

    def step(self, dt: float) -> None:
        pass

    def save_visual_state(self) -> dict[str, Any]:
        return {}

    def load_visual_state(self, state: dict[str, Any]) -> None:
        pass


class DummyUI:
    def __init__(self) -> None:
        self.error_overlay: str | None = None

    def set_viewport(self, width: int, height: int) -> None:
        pass

    def draw(self, *args: Any, **kwargs: Any) -> None:
        pass

    def sync(self, *args: Any, **kwargs: Any) -> None:
        pass

    def hit_test_choice(self, x: float, y: float) -> int | None:
        return None

    def hit_test_quick_action(self, x: float, y: float) -> str | None:
        return None


class DummyScreenManager:
    def __init__(self) -> None:
        self.screens: dict[str, Any] = {}
        self.active_screen: Any = None
        self.is_active: bool = False

    def register(self, screen: Any) -> None:
        pass

    def show(self, name: str, session: Any) -> bool:
        return False

    def hide(self, session: Any) -> None:
        pass

    def draw(self, *args: Any, **kwargs: Any) -> None:
        pass

    def handle_mouse_click(self, x: float, y: float) -> bool:
        return False

    def handle_mouse_move(self, x: float, y: float) -> bool:
        return False


def test_protocols_runtime_checkable():
    state = DummyUIState()
    assert isinstance(state, UIStateProtocol)

    stage = DummyStage()
    assert isinstance(stage, StageProtocol)

    ui = DummyUI()
    assert isinstance(ui, UIProtocol)

    mgr = DummyScreenManager()
    assert isinstance(mgr, ScreenManagerProtocol)
