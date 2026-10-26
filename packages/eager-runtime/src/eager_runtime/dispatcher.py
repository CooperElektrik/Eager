"""Event and engine hook dispatcher for Eager narrative runtimes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from eager_core.events import (
    ChoicePromptEvent,
    HookEvent,
    InputPromptEvent,
    StoryEndEvent,
    StoryEvent,
)

__all__ = [
    "EventDispatcher",
]


class EventDispatcher:
    """Dispatches narrative events and script engine hooks to registered callbacks."""

    def __init__(self) -> None:
        self._hook_handlers: dict[str, list[Callable[..., Any]]] = {}
        self._event_handlers: dict[type[StoryEvent], list[Callable[[Any], Any]]] = {}
        self._any_hook_handlers: list[Callable[[HookEvent], Any]] = []
        self._any_event_handlers: list[Callable[[StoryEvent], Any]] = []

    def on_hook(self, hook_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a callback for a specific engine hook name (~ hook_name)."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._hook_handlers.setdefault(hook_name, []).append(func)
            return func

        return decorator

    def on_event(
        self, event_type: type[StoryEvent]
    ) -> Callable[[Callable[[Any], Any]], Callable[[Any], Any]]:
        """Decorator to register a callback for a specific StoryEvent type."""

        def decorator(func: Callable[[Any], Any]) -> Callable[[Any], Any]:
            self._event_handlers.setdefault(event_type, []).append(func)
            return func

        return decorator

    def on_any_hook(self, func: Callable[[HookEvent], Any]) -> Callable[[HookEvent], Any]:
        """Register a callback that receives every HookEvent."""
        self._any_hook_handlers.append(func)
        return func

    def on_any_event(self, func: Callable[[StoryEvent], Any]) -> Callable[[StoryEvent], Any]:
        """Register a callback that receives every StoryEvent."""
        self._any_event_handlers.append(func)
        return func

    def dispatch(self, event: StoryEvent) -> None:
        """Dispatch a single StoryEvent to all matching registered handlers."""
        # 1. Global event listeners
        for handler in list(self._any_event_handlers):
            handler(event)

        # 2. Type-specific event listeners
        event_cls = type(event)
        if event_cls in self._event_handlers:
            for handler in list(self._event_handlers[event_cls]):
                handler(event)

        # 3. Hook-specific listeners
        if isinstance(event, HookEvent):
            for any_hook in list(self._any_hook_handlers):
                any_hook(event)
            if event.hook_name in self._hook_handlers:
                for handler in list(self._hook_handlers[event.hook_name]):
                    handler(event.args)

    def run_until_pause(self, vm: Any) -> StoryEvent | None:
        """Step the VM and dispatch events until a ChoicePromptEvent, InputPromptEvent, or StoryEndEvent is encountered."""
        while not vm.is_ended:
            event = vm.step()
            if event is None:
                break

            self.dispatch(event)

            if isinstance(event, (ChoicePromptEvent, InputPromptEvent, StoryEndEvent)):
                return event

        return None
