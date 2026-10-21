"""Abstract protocols for stage management and UI integration.

These protocols define the boundary between the narrative runtime (eager-runtime)
and presentation subsystems (eager-graphics or custom engines).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class UIStateProtocol(Protocol):
    """Protocol for UI state sidecar data tracking dialogue, choices, and story state."""

    speaker: str | None
    text: str
    emotion: str | None
    choices: list[object]
    is_finished: bool
    visible_chars: int | None

    def clear_choices(self) -> None:
        """Clear active choice options."""
        ...

    def clear_dialogue(self) -> None:
        """Clear active dialogue and speaker information."""
        ...

    def to_dict(self) -> dict[str, object]:
        """Serialize UI state to a dictionary."""
        ...


@runtime_checkable
class StageProtocol(Protocol):
    """Protocol for visual stage management and event binding in visual novel sessions."""

    ui_state: Any

    def bind(self, dispatcher: object) -> None:
        """Bind stage event handlers to the given event dispatcher."""
        ...

    def step(self, dt: float) -> None:
        """Advance stage animations and timelines by *dt* seconds."""
        ...

    def finish_animations(self) -> None:
        """Immediately complete active stage animations."""
        ...

    def save_visual_state(self) -> dict[str, object]:
        """Serialize current visual stage state for checkpointing."""
        ...

    def load_visual_state(self, state: dict[str, object]) -> None:
        """Restore visual stage state from serialized checkpoint data."""
        ...


@runtime_checkable
class UIProtocol(Protocol):
    """Protocol for user interface overlay components (dialogue box, choices, HUD)."""

    error_overlay: str | None

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions for layout calculation."""
        ...

    def draw(self, *args: object, **kwargs: object) -> None:
        """Draw UI chrome and elements to the render target."""
        ...

    def sync(self, *args: object, **kwargs: object) -> None:
        """Synchronize UI components with current UI state."""
        ...

    def hit_test_choice(self, x: float, y: float) -> int | None:
        """Return the choice index under cursor coords (x, y), or None."""
        ...

    def hit_test_quick_action(self, x: float, y: float) -> str | None:
        """Return the quick action name under cursor coords (x, y), or None."""
        ...

    def get_selected_choice(self) -> int | None:
        """Return the index of the currently selected choice option, or None."""
        ...

    def set_selected_choice(self, index: int | None) -> None:
        """Update the selected choice option index."""
        ...

    def set_choice_options(self, options: object) -> None:
        """Update the displayed choice menu options."""
        ...

    def set_input_text(self, text: str) -> None:
        """Update the text buffer displayed by the input box."""
        ...

    def update_input(self, dt: float) -> None:
        """Advance cursor animation or timers in the input box."""
        ...

    def set_dialogue_visible_chars(
        self,
        visible_chars: int | None = None,
        *,
        show_arrow: bool = True,
    ) -> None:
        """Update visible character limit and advance indicator on the dialogue box."""
        ...

    def complete_dialogue_reveal(self, *, show_arrow: bool = True) -> None:
        """Snap dialogue box typewriter reveal to fully revealed."""
        ...

    def get_hovered_quick_action(self) -> str | None:
        """Return the currently hovered quick action identifier."""
        ...

    def set_hovered_quick_action(self, action: str | None) -> None:
        """Update the hovered quick action identifier."""
        ...


@runtime_checkable
class ScreenManagerProtocol(Protocol):
    """Protocol for menu screen stack and registry management."""

    screens: dict[str, object]
    active_screen: object
    is_active: bool

    def register(self, screen: object) -> None:
        """Register a screen under its name."""
        ...

    def show(self, name: str, session: object) -> bool:
        """Display the screen with the given name."""
        ...

    def hide(self, session: object) -> None:
        """Dismiss the active screen."""
        ...

    def draw(self, *args: object, **kwargs: object) -> None:
        """Render the active screen."""
        ...

    def handle_mouse_click(self, x: float, y: float) -> bool:
        """Forward mouse click to active screen."""
        ...

    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Forward mouse move to active screen."""
        ...


# ── Provider & Factory Inversion of Control ──────────────────────────

StageFactory = Callable[..., StageProtocol]
UIFactory = Callable[..., UIProtocol]
ScreenManagerFactory = Callable[..., ScreenManagerProtocol]

_stage_factory: StageFactory | None = None
_ui_factory: UIFactory | None = None
_screen_manager_factory: ScreenManagerFactory | None = None

_player_factories: dict[str, Any] = {}
_audio_backends: dict[str, Any] = {}
_renderer_factories: dict[str, Any] = {}

_providers_loaded: bool = False


def register_stage_factory(factory: StageFactory | None) -> None:
    """Register a global factory callable returning a StageProtocol instance."""
    global _stage_factory
    _stage_factory = factory


def get_stage_factory() -> StageFactory | None:
    """Return the registered stage factory callable, if any."""
    return _stage_factory


def register_ui_factory(factory: UIFactory | None) -> None:
    """Register a global factory callable returning a UIProtocol instance."""
    global _ui_factory
    _ui_factory = factory


def get_ui_factory() -> UIFactory | None:
    """Return the registered UI factory callable, if any."""
    return _ui_factory


def register_screen_manager_factory(factory: ScreenManagerFactory | None) -> None:
    """Register a global factory callable returning a ScreenManagerProtocol instance."""
    global _screen_manager_factory
    _screen_manager_factory = factory


def get_screen_manager_factory() -> ScreenManagerFactory | None:
    """Return the registered screen manager factory callable, if any."""
    return _screen_manager_factory


def register_player(backend: str, player_cls: Any) -> None:
    """Register an interactive player implementation for *backend* (e.g. 'pil', 'pyglet')."""
    _player_factories[backend.lower()] = player_cls


def get_player(backend: str) -> Any | None:
    """Retrieve an interactive player implementation by backend name."""
    return _player_factories.get(backend.lower())


def list_players() -> list[str]:
    """Return list of registered player backend names."""
    return sorted(_player_factories.keys())


def register_audio_backend(backend: str, audio_factory: Any) -> None:
    """Register an audio backend factory for *backend* (e.g. 'pyglet', 'miniaudio')."""
    _audio_backends[backend.lower()] = audio_factory


def get_audio_backend(backend: str) -> Any | None:
    """Retrieve an audio backend factory by backend name."""
    return _audio_backends.get(backend.lower())


def register_renderer(backend: str, renderer_factory: Any) -> None:
    """Register a renderer backend factory (e.g. 'null', 'pil', 'pyglet')."""
    _renderer_factories[backend.lower()] = renderer_factory


def get_renderer(backend: str) -> Any | None:
    """Retrieve a renderer backend factory by name."""
    return _renderer_factories.get(backend.lower())


def load_providers() -> None:
    """Discover and execute provider entry points registered under 'eager.providers'."""
    global _providers_loaded
    if _providers_loaded:
        return
    _providers_loaded = True
    try:
        import importlib.metadata

        eps = importlib.metadata.entry_points()
        selected: Any
        if hasattr(eps, "select"):
            selected = eps.select(group="eager.providers")
        else:
            selected = eps.get("eager.providers", [])
        for ep in selected:
            try:
                fn = ep.load()
                if callable(fn):
                    fn()
            except Exception:  # noqa: BLE001, S110
                pass
    except Exception:  # noqa: BLE001, S110
        pass


def reset_providers() -> None:
    """Reset all registered factories and providers (primarily for unit testing)."""
    global _stage_factory, _ui_factory, _screen_manager_factory, _providers_loaded
    _stage_factory = None
    _ui_factory = None
    _screen_manager_factory = None
    _player_factories.clear()
    _audio_backends.clear()
    _renderer_factories.clear()
    _providers_loaded = False

