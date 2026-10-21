"""Abstract protocols for stage management and UI integration.

These protocols define the boundary between the narrative runtime (eager-runtime)
and presentation subsystems (eager-graphics or custom engines).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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

    ui_state: object

    def bind(self, dispatcher: object) -> None:
        """Bind stage event handlers to the given event dispatcher."""
        ...

    def step(self, dt: float) -> None:
        """Advance stage animations and timelines by *dt* seconds."""
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
