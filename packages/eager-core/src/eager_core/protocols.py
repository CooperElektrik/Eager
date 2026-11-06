"""Abstract protocols for stage management and UI integration.

These protocols define the boundary between the narrative runtime (eager-runtime)
and presentation subsystems (eager-graphics or custom engines).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from eager_core.characters import CharacterConfig
from eager_core.types import WHITE, Anchor, Color

if TYPE_CHECKING:
    from eager_core.dispatcher import EventDispatcher

__all__ = [
    "AudioBackendFactory",
    "CharacterRegistryProtocol",
    "GameSessionProtocol",
    "HostLifecycleListener",
    "PlayerFactory",
    "PlayerProtocol",
    "ProviderRegistry",
    "RenderBackend",
    "RenderItem",
    "RendererFactory",
    "ScreenManagerFactory",
    "ScreenManagerProtocol",
    "ScreenProtocol",
    "StageFactory",
    "StageProtocol",
    "StoryVMProtocol",
    "ThemeFactory",
    "UIDrawBackend",
    "UIFactory",
    "UIProtocol",
    "UIStateProtocol",
    "get_audio_backend",
    "get_default_registry",
    "get_player",
    "get_renderer",
    "get_screen_manager_factory",
    "get_stage_factory",
    "get_theme_factory",
    "get_ui_factory",
    "list_players",
    "load_providers",
    "register_audio_backend",
    "register_player",
    "register_renderer",
    "register_screen_manager_factory",
    "register_stage_factory",
    "register_theme_factory",
    "register_ui_factory",
    "reset_providers",
]

logger = logging.getLogger(__name__)


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

    def bind(self, dispatcher: EventDispatcher) -> None:
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
class CharacterRegistryProtocol(Protocol):
    """Protocol for stages or registries that manage character definitions."""

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
        expressions: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Register character attributes, colors, and expression aliases."""
        ...

    def find_character(self, speaker: str | None) -> CharacterConfig | None:
        """Find CharacterConfig matching character ID or display name."""
        ...

    def resolve_side_image(self, speaker: str | None, expression: str | None = None) -> str | None:
        """Resolve the active side image asset ID for a character and expression."""
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
class HostLifecycleListener(Protocol):
    """Protocol for host environments (such as window players) receiving lifecycle requests."""

    def on_request_fullscreen(self) -> None:
        """Handle fullscreen toggle request."""
        ...

    def on_request_quit(self) -> None:
        """Handle application quit request."""
        ...

    def on_state_restored(self) -> None:
        """Handle narrative state restoration (load game, rollback)."""
        ...


@runtime_checkable
class ScreenProtocol(Protocol):
    """Protocol for visual novel modal/full-screen UI menus."""

    name: str
    visible: bool

    def set_viewport(self, width: int, height: int) -> None:
        """Update viewport dimensions for layout calculation."""
        ...

    def set_theme(self, theme: Any) -> None:
        """Update visual theme across widgets."""
        ...

    def on_enter(self, session: Any) -> None:
        """Called when screen is displayed."""
        ...

    def on_exit(self, session: Any) -> None:
        """Called when screen is hidden."""
        ...

    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Update hover state on widgets."""
        ...

    def handle_mouse_click(self, x: float, y: float) -> bool:
        """Process mouse click event."""
        ...

    def handle_key(self, key_name: str, session: Any = None) -> bool:
        """Process keyboard shortcut event."""
        ...

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render screen contents to drawing surface."""
        ...


@runtime_checkable
class ScreenManagerProtocol(Protocol):
    """Protocol for menu screen stack and registry management."""

    screens: dict[str, Any]
    active_screen: Any

    @property
    def is_active(self) -> bool:
        """Return True if a screen is currently active/visible."""
        ...

    def register(self, screen: Any) -> None:
        """Register a screen under its name."""
        ...

    def show(self, name: str, session: Any) -> bool:
        """Display the screen with the given name."""
        ...

    def hide(self, session: Any) -> None:
        """Dismiss the active screen."""
        ...

    def hide_all(self, session: Any) -> None:
        """Dismiss all screens and clear navigation stack."""
        ...

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render the active screen."""
        ...

    def handle_mouse_click(self, x: float, y: float) -> bool:
        """Forward mouse click to active screen."""
        ...

    def handle_mouse_move(self, x: float, y: float) -> bool:
        """Forward mouse move to active screen."""
        ...

    def handle_key(self, key_name: str, session: Any = None) -> bool:
        """Forward key event to active screen."""
        ...


@runtime_checkable
class GameSessionProtocol(Protocol):
    """Protocol for narrative game session host managing story state and presentation."""

    backlog: Any
    preferences: Any
    save_manager: Any
    translation_manager: Any
    screens: ScreenManagerProtocol | None
    mode: str
    is_finished: bool
    input_text: str
    active_choice_prompt: Any | None
    active_input_prompt: Any | None
    text_reveal: Any
    _ui_dirty: bool

    def advance(self) -> Any:
        """Advance story execution by one beat."""
        ...

    def choose(self, choice_index: int) -> None:
        """Make branching story choice by index."""
        ...

    def restart_story(self) -> None:
        """Restart story from beginning."""
        ...

    def save_game(self, slot_name: str) -> bool:
        """Save game to named slot."""
        ...

    def load_game(self, slot_name: str) -> bool:
        """Load game from named slot."""
        ...

    def apply_preferences(self) -> None:
        """Apply active preferences to audio, locale, and display subsystems."""
        ...

    def request_fullscreen(self) -> None:
        """Request host environment fullscreen toggle."""
        ...

    def request_quit(self) -> bool:
        """Request host environment quit."""
        ...

    def play_audio(self, channel: str, track: str) -> None:
        """Play audio asset on given channel."""
        ...

    def play_voice(self, voice_path: str) -> None:
        """Play voice asset."""
        ...

    def set_language(self, locale: str) -> None:
        """Set active translation locale."""
        ...

    def is_current_beat_read(self) -> bool:
        """Return True if current beat has been read."""
        ...

    def rollback(self) -> bool:
        """Roll back narrative by one beat."""
        ...

    def roll_forward(self) -> bool:
        """Roll forward through redo stack by one beat."""
        ...

    def hot_reload(self, script_path: Any = None) -> bool:
        """Hot-reload script from disk."""
        ...

    def return_to_title(self) -> None:
        """Return to title screen."""
        ...

    def update(self, dt: float) -> None:
        """Advance session timers, audio, and state."""
        ...

    def draw(self, ui_backend: Any, width: int, height: int) -> None:
        """Draw current stage and overlay to renderer."""
        ...

    def handle_input(self, action: Any, *args: Any, **kwargs: Any) -> bool:
        """Process input action."""
        ...

    def add_lifecycle_listener(self, listener: HostLifecycleListener) -> None:
        """Register lifecycle listener."""
        ...

    def remove_lifecycle_listener(self, listener: HostLifecycleListener) -> None:
        """Unregister lifecycle listener."""
        ...


@runtime_checkable
class StoryVMProtocol(Protocol):
    """Protocol for story virtual machine step execution."""

    @property
    def is_ended(self) -> bool:
        """Return True if story execution has ended."""
        ...

    def step(self) -> Any:
        """Advance VM by one narrative beat and return the resulting StoryEvent."""
        ...


@runtime_checkable
class PlayerProtocol(Protocol):
    """Protocol for interactive player runner."""

    def run(self) -> None:
        """Execute player main frame loop until termination."""
        ...

    def close(self) -> None:
        """Close window or terminate player resources."""
        ...


@dataclass(frozen=True, slots=True)
class RenderItem:
    """An individual visual draw command output by the compositor in global render order."""

    asset_id: str
    x: float
    y: float
    opacity: float
    scale_x: float
    scale_y: float
    rotation: float
    anchor: Anchor
    tint: Color
    flip_h: bool
    flip_v: bool
    layer: str
    z_order: int

    def to_dict(self) -> dict[str, Any]:
        """Convert render item to dictionary for serialization / IPC transmission."""
        return {
            "asset_id": self.asset_id,
            "x": self.x,
            "y": self.y,
            "opacity": self.opacity,
            "scale_x": self.scale_x,
            "scale_y": self.scale_y,
            "rotation": self.rotation,
            "anchor": self.anchor.value,
            "tint": self.tint.to_dict(),
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
            "layer": self.layer,
            "z_order": self.z_order,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RenderItem:
        """Construct RenderItem from dictionary."""
        return cls(
            asset_id=data["asset_id"],
            x=float(data["x"]),
            y=float(data["y"]),
            opacity=float(data.get("opacity", 1.0)),
            scale_x=float(data.get("scale_x", 1.0)),
            scale_y=float(data.get("scale_y", 1.0)),
            rotation=float(data.get("rotation", 0.0)),
            anchor=Anchor.from_str(data.get("anchor", "bottom_center")),
            tint=Color.from_dict(data.get("tint", {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0})),
            flip_h=bool(data.get("flip_h", False)),
            flip_v=bool(data.get("flip_v", False)),
            layer=data.get("layer", "characters"),
            z_order=int(data.get("z_order", 0)),
        )


@runtime_checkable
class RenderBackend(Protocol):
    """Protocol implemented by the rendering backends (Null, PIL, Pyglet)."""

    def begin_frame(self) -> None:
        """Invoked at the beginning of each frame render pass."""
        ...

    def clear(self, color: Color) -> None:
        """Clear the frame buffer with the given background color."""
        ...

    def draw_item(self, item: RenderItem) -> None:
        """Render a single compositor item to the target display buffer."""
        ...

    def draw_particles(self, batch: Any) -> None:
        """Render a pre-baked particle batch to the display buffer."""
        ...

    def render_lightmap(self, lightmap: Any) -> None:
        """Composite a screen-space low-res lightmap onto the display buffer."""
        ...

    def end_frame(self) -> None:
        """Invoked when all items for the frame have been submitted."""
        ...


@runtime_checkable
class UIDrawBackend(Protocol):
    """Low-level drawing primitives used by renderer-agnostic UI components."""

    def draw_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: Color,
        *,
        border_color: Color | None = None,
        border_width: float = 0.0,
    ) -> None:
        """Fill a rectangle, optionally stroking a border of *border_width* pixels."""
        ...

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        """Fill a rectangle with a vertical linear gradient from top_color to bottom_color."""
        ...

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: int = 14,
        color: Color = WHITE,
        bold: bool = False,
        italic: bool = False,
        anchor_x: str = "left",
        anchor_y: str = "top",
        cache: bool = True,
    ) -> None:
        """Draw a single line of text."""
        ...

    def draw_image(
        self,
        asset_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        tint: Color = WHITE,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        """Draw a resolved asset scaled into the given box, with optional tint."""
        ...

    def measure_text(
        self,
        text: str,
        *,
        font_size: int = 14,
        bold: bool = False,
        italic: bool = False,
        cache: bool = True,
    ) -> tuple[float, float]:
        """Return the ``(width, height)`` the given text would occupy."""
        ...


# ── Provider & Factory Inversion of Control ──────────────────────────

StageFactory = Callable[..., StageProtocol]
UIFactory = Callable[..., UIProtocol]
ScreenManagerFactory = Callable[..., ScreenManagerProtocol]
ThemeFactory = Callable[..., Any]
PlayerFactory = Callable[..., Any]
AudioBackendFactory = Callable[..., Any]
RendererFactory = Callable[..., Any]


class ProviderRegistry:
    """Registry container for IoC provider factories (stages, UI, screens, players, audio, renderers)."""

    def __init__(self) -> None:
        self._stage_factory: StageFactory | None = None
        self._ui_factory: UIFactory | None = None
        self._screen_manager_factory: ScreenManagerFactory | None = None
        self._theme_factory: ThemeFactory | None = None
        self._player_factories: dict[str, PlayerFactory] = {}
        self._audio_backends: dict[str, AudioBackendFactory] = {}
        self._renderer_factories: dict[str, RendererFactory] = {}
        self._providers_loaded: bool = False

    def register_stage_factory(self, factory: StageFactory | None) -> None:
        """Register factory callable returning a StageProtocol instance."""
        logger.debug("Registering stage factory: %s", factory)
        self._stage_factory = factory

    def get_stage_factory(self) -> StageFactory | None:
        """Return registered stage factory callable, if any."""
        return self._stage_factory

    def register_ui_factory(self, factory: UIFactory | None) -> None:
        """Register factory callable returning a UIProtocol instance."""
        logger.debug("Registering UI factory: %s", factory)
        self._ui_factory = factory

    def get_ui_factory(self) -> UIFactory | None:
        """Return registered UI factory callable, if any."""
        return self._ui_factory

    def register_screen_manager_factory(self, factory: ScreenManagerFactory | None) -> None:
        """Register factory callable returning a ScreenManagerProtocol instance."""
        logger.debug("Registering screen manager factory: %s", factory)
        self._screen_manager_factory = factory

    def get_screen_manager_factory(self) -> ScreenManagerFactory | None:
        """Return registered screen manager factory callable, if any."""
        return self._screen_manager_factory

    def register_theme_factory(self, factory: ThemeFactory | None) -> None:
        """Register factory callable returning a theme instance."""
        logger.debug("Registering theme factory: %s", factory)
        self._theme_factory = factory

    def get_theme_factory(self) -> ThemeFactory | None:
        """Return registered theme factory callable, if any."""
        return self._theme_factory

    def register_player(self, backend: str, player_cls: PlayerFactory) -> None:
        """Register interactive player implementation for backend."""
        logger.debug("Registering player backend %r: %s", backend, player_cls)
        self._player_factories[backend.lower()] = player_cls

    def get_player(self, backend: str) -> PlayerFactory | None:
        """Retrieve interactive player implementation by backend name."""
        return self._player_factories.get(backend.lower())

    def list_players(self) -> list[str]:
        """Return sorted list of registered player backend names."""
        return sorted(self._player_factories.keys())

    def register_audio_backend(self, backend: str, audio_factory: AudioBackendFactory) -> None:
        """Register audio backend factory for backend."""
        logger.debug("Registering audio backend %r: %s", backend, audio_factory)
        self._audio_backends[backend.lower()] = audio_factory

    def get_audio_backend(self, backend: str) -> AudioBackendFactory | None:
        """Retrieve audio backend factory by backend name."""
        return self._audio_backends.get(backend.lower())

    def register_renderer(self, backend: str, renderer_factory: RendererFactory) -> None:
        """Register renderer backend factory."""
        logger.debug("Registering renderer backend %r: %s", backend, renderer_factory)
        self._renderer_factories[backend.lower()] = renderer_factory

    def get_renderer(self, backend: str) -> RendererFactory | None:
        """Retrieve renderer backend factory by name."""
        factory = self._renderer_factories.get(backend.lower())
        if factory is None and backend.lower() == "null":
            from eager_core.headless import NullRenderer

            return NullRenderer
        return factory

    def load_providers(self) -> None:
        """Discover and execute provider entry points registered under 'eager.providers'."""
        if self._providers_loaded:
            return
        self._providers_loaded = True
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
                        logger.debug("Loading provider entry point %r", ep.name)
                        try:
                            fn(self)
                        except TypeError:
                            fn()
                except Exception:
                    logger.warning("Failed to load provider entry point %r", ep.name, exc_info=True)
        except Exception:
            logger.warning("Failed to discover eager.providers entry points", exc_info=True)

    def reset(self) -> None:
        """Reset all registered factories and providers in this registry."""
        self._stage_factory = None
        self._ui_factory = None
        self._screen_manager_factory = None
        self._theme_factory = None
        self._player_factories.clear()
        self._audio_backends.clear()
        self._renderer_factories.clear()
        self._providers_loaded = False


_default_registry = ProviderRegistry()


def get_default_registry() -> ProviderRegistry:
    """Return the global default ProviderRegistry instance."""
    return _default_registry


def register_stage_factory(factory: StageFactory | None) -> None:
    """Register a global factory callable returning a StageProtocol instance."""
    _default_registry.register_stage_factory(factory)


def get_stage_factory() -> StageFactory | None:
    """Return the registered stage factory callable, if any."""
    return _default_registry.get_stage_factory()


def register_ui_factory(factory: UIFactory | None) -> None:
    """Register a global factory callable returning a UIProtocol instance."""
    _default_registry.register_ui_factory(factory)


def get_ui_factory() -> UIFactory | None:
    """Return the registered UI factory callable, if any."""
    return _default_registry.get_ui_factory()


def register_screen_manager_factory(factory: ScreenManagerFactory | None) -> None:
    """Register a global factory callable returning a ScreenManagerProtocol instance."""
    _default_registry.register_screen_manager_factory(factory)


def get_screen_manager_factory() -> ScreenManagerFactory | None:
    """Return the registered screen manager factory callable, if any."""
    return _default_registry.get_screen_manager_factory()


def register_theme_factory(factory: ThemeFactory | None) -> None:
    """Register a global factory callable returning a theme instance."""
    _default_registry.register_theme_factory(factory)


def get_theme_factory() -> ThemeFactory | None:
    """Return the registered theme factory callable, if any."""
    return _default_registry.get_theme_factory()


def register_player(backend: str, player_cls: PlayerFactory) -> None:
    """Register an interactive player implementation for *backend* (e.g. 'pil', 'pyglet')."""
    _default_registry.register_player(backend, player_cls)


def get_player(backend: str) -> PlayerFactory | None:
    """Retrieve an interactive player implementation by backend name."""
    return _default_registry.get_player(backend)


def list_players() -> list[str]:
    """Return list of registered player backend names."""
    return _default_registry.list_players()


def register_audio_backend(backend: str, audio_factory: AudioBackendFactory) -> None:
    """Register an audio backend factory for *backend* (e.g. 'pyglet', 'miniaudio')."""
    _default_registry.register_audio_backend(backend, audio_factory)


def get_audio_backend(backend: str) -> AudioBackendFactory | None:
    """Retrieve an audio backend factory by backend name."""
    return _default_registry.get_audio_backend(backend)


def register_renderer(backend: str, renderer_factory: RendererFactory) -> None:
    """Register a renderer backend factory (e.g. 'null', 'pil', 'pyglet')."""
    _default_registry.register_renderer(backend, renderer_factory)


def get_renderer(backend: str) -> RendererFactory | None:
    """Retrieve a renderer backend factory by name."""
    return _default_registry.get_renderer(backend)


def load_providers() -> None:
    """Discover and execute provider entry points registered under 'eager.providers'."""
    _default_registry.load_providers()


def reset_providers() -> None:
    """Reset all registered factories and providers (primarily for unit testing)."""
    _default_registry.reset()

