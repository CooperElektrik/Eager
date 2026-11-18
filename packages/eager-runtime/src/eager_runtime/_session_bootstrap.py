"""Subsystem factory, theme resolution, and graph registration helpers for GameSession."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eager_core.headless import NullScreenManager, NullStage, NullUI
from eager_core.protocols import (
    CharacterRegistryProtocol,
    ProviderRegistry,
    get_default_registry,
    load_providers,
)

_CHARACTER_KNOWN_KEYS = frozenset({
    "asset_prefix",
    "default_expression",
    "default_position",
    "side_image",
    "color",
})


def _get_loaded_registry(registry: ProviderRegistry | None = None) -> ProviderRegistry:
    """Return a ProviderRegistry with providers loaded."""
    reg = registry or get_default_registry()
    if registry is not None and registry is not get_default_registry():
        reg.load_providers()
    else:
        import eager_runtime.session as _session_mod

        loader = getattr(_session_mod, "load_providers", load_providers)
        loader()
    return reg


def create_default_stage(
    virtual_width: int,
    virtual_height: int,
    audio: Any,
    skip_mode_cb: Any,
    *,
    registry: ProviderRegistry | None = None,
    **kwargs: Any,
) -> Any:
    """Create the default Stage instance via the provider registry or NullStage."""
    reg = _get_loaded_registry(registry)
    factory = reg.get_stage_factory()
    if factory is not None:
        return factory(
            virtual_width=virtual_width,
            virtual_height=virtual_height,
            audio=audio,
            skip_mode_cb=skip_mode_cb,
            **kwargs,
        )
    return NullStage(virtual_width=virtual_width, virtual_height=virtual_height)


def resolve_theme(config: Any, *, registry: ProviderRegistry | None = None) -> Any:
    """Instantiate a Theme object or options dict from ProjectConfig."""
    if config is None:
        return None
    theme_name = getattr(config, "theme", None)
    theme_overrides = getattr(config, "theme_overrides", {}) or {}
    if not theme_name and not theme_overrides:
        return None
    reg = _get_loaded_registry(registry)
    factory = reg.get_theme_factory()
    kwargs: dict[str, Any] = {}
    if theme_name:
        kwargs["name"] = theme_name
    kwargs.update(theme_overrides)
    if factory is not None:
        try:
            return factory(**kwargs)
        except (TypeError, ValueError, AttributeError):
            pass
    try:
        from eager_core.theme import Theme

        return Theme(**kwargs)
    except (TypeError, ValueError, AttributeError):
        return kwargs


def create_default_ui(
    width: int = 1280,
    height: int = 720,
    theme: Any = None,
    *,
    registry: ProviderRegistry | None = None,
) -> Any:
    """Create the default UI overlay via the provider registry or NullUI."""
    reg = _get_loaded_registry(registry)
    factory = reg.get_ui_factory()
    if factory is not None:
        try:
            return factory(width=width, height=height, theme=theme)
        except TypeError:
            return factory(width=width, height=height)
    return NullUI(width=width, height=height)


def create_default_screens(
    config: Any,
    session: Any,
    *,
    registry: ProviderRegistry | None = None,
) -> Any:
    """Create the default ScreenManager via the provider registry or NullScreenManager."""
    reg = _get_loaded_registry(registry)
    factory = reg.get_screen_manager_factory()
    if factory is not None:
        return factory(config=config, session=session)
    return NullScreenManager()


def discover_locales_dir(script_path: Path | None) -> Path | None:
    """Return the locales directory adjacent to script_path if it exists."""
    if script_path is None:
        return None
    resolved = script_path.resolve()
    base_dir = resolved if script_path.is_dir() else resolved.parent
    candidate = base_dir / "locales"
    return candidate if candidate.is_dir() else None


def register_scene_backgrounds(director: Any, config: Any) -> None:
    """Register configured scene backgrounds on the director if supported."""
    if (
        config is None
        or not getattr(config, "scene_backgrounds", None)
        or not hasattr(director, "register_scene_bg")
    ):
        return
    for sc_id, bg_info in config.scene_backgrounds.items():
        if isinstance(bg_info, (tuple, list)) and len(bg_info) >= 3:
            director.register_scene_bg(
                sc_id, str(bg_info[0]), transition=str(bg_info[1]), duration=float(bg_info[2])
            )
        elif isinstance(bg_info, (tuple, list)) and len(bg_info) == 1:
            director.register_scene_bg(sc_id, str(bg_info[0]))
        elif isinstance(bg_info, str):
            director.register_scene_bg(sc_id, bg_info)


def register_graph_characters(director: Any, graph: Any, *, require_protocol: bool = False) -> None:
    """Register character definitions from a SceneGraph onto the director."""
    if not getattr(graph, "characters", None):
        return
    if require_protocol and not isinstance(director, CharacterRegistryProtocol):
        return
    for cid, cinfo in graph.characters.items():
        attrs = cinfo.get("attrs", {}) if isinstance(cinfo, dict) else {}
        name = cinfo.get("name") if isinstance(cinfo, dict) else None
        custom_expressions = {k: v for k, v in attrs.items() if k not in _CHARACTER_KNOWN_KEYS}
        director.register_character(
            cid,
            name=name,
            asset_prefix=attrs.get("asset_prefix"),
            default_expression=attrs.get("default_expression", "default"),
            default_position=attrs.get("default_position", "center"),
            side_image=attrs.get("side_image"),
            color=attrs.get("color"),
            expressions=custom_expressions,
        )
