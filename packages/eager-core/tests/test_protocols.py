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

    def finish_animations(self) -> None:
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

    def get_selected_choice(self) -> int | None:
        return None

    def set_selected_choice(self, index: int | None) -> None:
        pass

    def set_choice_options(self, options: Any) -> None:
        pass

    def set_input_text(self, text: str) -> None:
        pass

    def update_input(self, dt: float) -> None:
        pass

    def set_dialogue_visible_chars(
        self,
        visible_chars: int | None = None,
        *,
        show_arrow: bool = True,
    ) -> None:
        pass

    def complete_dialogue_reveal(self, *, show_arrow: bool = True) -> None:
        pass

    def get_hovered_quick_action(self) -> str | None:
        return None

    def set_hovered_quick_action(self, action: str | None) -> None:
        pass


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


def test_provider_registry():
    from eager_core.protocols import (
        get_audio_backend,
        get_player,
        get_renderer,
        get_screen_manager_factory,
        get_stage_factory,
        get_theme_factory,
        get_ui_factory,
        list_players,
        register_audio_backend,
        register_player,
        register_renderer,
        register_screen_manager_factory,
        register_stage_factory,
        register_theme_factory,
        register_ui_factory,
        reset_providers,
    )

    reset_providers()
    assert get_stage_factory() is None
    assert get_ui_factory() is None
    assert get_theme_factory() is None
    assert get_screen_manager_factory() is None
    assert get_player("foo") is None
    assert get_audio_backend("foo") is None
    assert get_renderer("foo") is None
    assert list_players() == []

    # Register dummies
    def dummy_stage_factory(**kwargs):
        return DummyStage()

    def dummy_ui_factory(**kwargs):
        return DummyUI()

    def dummy_screens_factory(**kwargs):
        return DummyScreenManager()

    def dummy_theme_factory(**kwargs):
        return {"name": "dummy"}

    register_stage_factory(dummy_stage_factory)
    register_ui_factory(dummy_ui_factory)
    register_theme_factory(dummy_theme_factory)
    register_screen_manager_factory(dummy_screens_factory)
    register_player("test_player", object)
    register_audio_backend("test_audio", object)
    register_renderer("test_renderer", object)

    assert get_stage_factory() is dummy_stage_factory
    assert get_ui_factory() is dummy_ui_factory
    assert get_theme_factory() is dummy_theme_factory
    assert get_screen_manager_factory() is dummy_screens_factory
    assert get_player("test_player") is object
    assert get_player("TEST_PLAYER") is object
    assert list_players() == ["test_player"]
    assert get_audio_backend("test_audio") is object
    assert get_renderer("test_renderer") is object

    reset_providers()
    assert get_stage_factory() is None
    assert get_theme_factory() is None
    assert list_players() == []
