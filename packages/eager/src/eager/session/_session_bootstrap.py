# pyright: reportImportCycles=false
"""Subsystem factory, theme resolution, and graph registration helpers for GameSession."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager.core.theme import Theme
    from eager.session.session import GameSession
    from eager.stage.director import StageDirector
    from eager.ui.components import UIOverlay
    from eager.ui.screens.screen import ScreenManager

_CHARACTER_KNOWN_KEYS = frozenset({
    "asset_prefix",
    "default_expression",
    "default_position",
    "side_image",
    "color",
})


def create_default_stage(
    virtual_width: int,
    virtual_height: int,
    audio: Any,
    skip_mode_cb: Any,
    **kwargs: Any,
) -> StageDirector:
    """Create the default StageDirector wired with a StageCompositor."""
    from eager.stage.compositor import StageCompositor
    from eager.stage.director import StageDirector

    compositor = StageCompositor(
        virtual_width=virtual_width,
        virtual_height=virtual_height,
    )
    return StageDirector(compositor, audio=audio, skip_mode_cb=skip_mode_cb, **kwargs)


def resolve_theme(config: Any) -> Theme | None:
    """Instantiate a Theme object from ProjectConfig if configured."""
    if config is None:
        return None
    theme_name = getattr(config, "theme", None)
    theme_overrides = getattr(config, "theme_overrides", {}) or {}
    if not theme_name and not theme_overrides:
        return None
    kwargs: dict[str, Any] = {}
    if theme_name:
        kwargs["name"] = theme_name
    kwargs.update(theme_overrides)
    try:
        from eager.core.theme import Theme

        return Theme(**kwargs)
    except (TypeError, ValueError, AttributeError):
        return None


def create_default_ui(
    width: int = 1280,
    height: int = 720,
    theme: Theme | dict[str, Any] | None = None,
) -> UIOverlay:
    """Create the default UIOverlay instance."""
    from eager.core.theme import Theme
    from eager.ui.components import UIOverlay

    resolved_theme: Theme | None = None
    if isinstance(theme, Theme):
        resolved_theme = theme
    elif isinstance(theme, dict):
        try:
            resolved_theme = Theme(**theme)
        except (TypeError, ValueError, AttributeError):
            resolved_theme = None
    return UIOverlay(width=width, height=height, theme=resolved_theme)


def create_default_screens(
    config: Any,
    session: GameSession,
) -> ScreenManager:
    """Create the default ScreenManager with built-in modal screens registered."""
    from eager.core.theme import Theme
    from eager.ui.screens import (
        GameMenuScreen,
        HistoryScreen,
        PreferencesScreen,
        SaveLoadScreen,
        ScreenManager,
        TitleScreen,
    )

    w = int(getattr(getattr(session, "overlay", None), "width", 1280) or 1280)
    h = int(getattr(getattr(session, "overlay", None), "height", 720) or 720)
    theme = getattr(getattr(session, "overlay", None), "theme", None)
    if isinstance(theme, dict):
        try:
            theme = Theme(**theme)
        except (TypeError, ValueError, AttributeError):
            theme = None

    mgr = ScreenManager(viewport_width=w, viewport_height=h, theme=theme)
    mgr.register(
        TitleScreen(
            title=getattr(config, "title", "Eager Visual Novel"),
            theme=theme,
            viewport_width=w,
            viewport_height=h,
        )
    )
    mgr.register(GameMenuScreen(theme=theme, viewport_width=w, viewport_height=h))
    mgr.register(SaveLoadScreen("save", theme=theme, viewport_width=w, viewport_height=h))
    mgr.register(SaveLoadScreen("load", theme=theme, viewport_width=w, viewport_height=h))
    mgr.register(PreferencesScreen(theme=theme, viewport_width=w, viewport_height=h))
    mgr.register(HistoryScreen(theme=theme, viewport_width=w, viewport_height=h))
    return mgr


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


def register_graph_characters(director: Any, graph: Any) -> None:
    """Register character definitions from a SceneGraph onto the director."""
    if not getattr(graph, "characters", None):
        return
    if not hasattr(director, "register_character"):
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
