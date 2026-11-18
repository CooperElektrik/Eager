"""Project configuration parser for game.toml and multi-file scene graph merging."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eager.core.types import Color
from eager.script import (
    IncludeError,
    ParseError,
    SceneGraph,
    discover_includes,
    parse_file,
    to_graph,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ProjectConfig",
    "load_project_graph",
    "merge_graphs",
    "resolve_project_scripts",
]


@dataclass
class ProjectConfig:
    """Settings defined in game.toml."""

    title: str = "Untitled Project"
    version: str = "0.1.0"
    author: str = "Anonymous"
    entry_script: str = "main.es"
    virtual_width: int = 1920
    virtual_height: int = 1080
    theme: str = "default"
    theme_overrides: dict[str, Any] = field(default_factory=dict)
    auto_highlight_speaker: bool = False
    highlight_duration: float = 0.25
    dim_color: Color | None = None
    pop_scale: float | None = None
    pop_hop: float | None = None
    scene_backgrounds: dict[str, tuple[str, str, float]] = field(default_factory=dict)
    scale_mode: str = "letterbox"
    render_preset: str = "balanced"
    show_fps: bool = True

    @classmethod
    def load(cls, toml_path: Path) -> ProjectConfig:
        """Load and parse game.toml configuration file.

        Args:
            toml_path: Path to the game.toml project file.

        Returns:
            Parsed ProjectConfig instance, or default settings if file is absent.
        """
        if not toml_path.exists():
            return cls()
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        game_data = data.get("game", {})
        window_data = data.get("window", {})
        theme_section = data.get("theme", {})

        theme_name = "default"
        theme_overrides: dict[str, Any] = {}

        if isinstance(theme_section, str):
            theme_name = theme_section
        elif isinstance(theme_section, dict):
            theme_name = str(theme_section.get("name") or game_data.get("theme") or "default")
            for k, v in theme_section.items():
                if k == "name":
                    continue
                if isinstance(v, str) and (
                    v.startswith("#")
                    or v.lower() in ("black", "white", "red", "green", "blue", "transparent")
                ):
                    try:
                        theme_overrides[k] = Color.from_hex(v)
                    except (ValueError, TypeError):
                        theme_overrides[k] = v
                else:
                    theme_overrides[k] = v
        else:
            theme_name = str(game_data.get("theme", "default"))

        pres_section = data.get("presentation", {}) or data.get("stage", {})
        auto_highlight = bool(pres_section.get("auto_highlight_speaker", False))
        highlight_dur = float(pres_section.get("highlight_duration", 0.25))
        dim_col: Color | None = None
        raw_dim = pres_section.get("dim_color")
        if isinstance(raw_dim, str):
            try:
                dim_col = Color.from_hex(raw_dim)
            except (ValueError, TypeError):
                pass
        pop_scale = float(pres_section["pop_scale"]) if "pop_scale" in pres_section else None
        pop_hop = float(pres_section["pop_hop"]) if "pop_hop" in pres_section else None

        scene_bgs: dict[str, tuple[str, str, float]] = {}
        scenes_sec = data.get("scenes", {})
        if isinstance(scenes_sec, dict):
            for sc_id, s_data in scenes_sec.items():
                if isinstance(s_data, dict) and "background" in s_data:
                    bg_asset = str(s_data["background"])
                    trans = str(s_data.get("transition", "crossfade"))
                    dur = float(s_data.get("duration", 0.5))
                    scene_bgs[str(sc_id)] = (bg_asset, trans, dur)
                elif isinstance(s_data, str):
                    scene_bgs[str(sc_id)] = (s_data, "crossfade", 0.5)

        return cls(
            title=game_data.get("title", "Untitled Project"),
            version=game_data.get("version", "0.1.0"),
            author=game_data.get("author", "Anonymous"),
            entry_script=game_data.get("entry_script", "main.es"),
            virtual_width=int(window_data.get("width", 1920)),
            virtual_height=int(window_data.get("height", 1080)),
            theme=theme_name,
            theme_overrides=theme_overrides,
            auto_highlight_speaker=auto_highlight,
            highlight_duration=highlight_dur,
            dim_color=dim_col,
            pop_scale=pop_scale,
            pop_hop=pop_hop,
            scene_backgrounds=scene_bgs,
            scale_mode=str(window_data.get("scale_mode") or pres_section.get("scale_mode", "letterbox")),
            render_preset=str(pres_section.get("render_preset", "balanced")),
            show_fps=bool(window_data.get("show_fps", pres_section.get("show_fps", True))),
        )


def _validate_reachability(graph: SceneGraph, *, strict: bool) -> None:
    """Validate that all scenes in graph are reachable from graph.entry."""
    if not graph.entry:
        return
    if graph.entry not in graph.nodes:
        raise ValueError(f"Entry scene '{graph.entry}' does not exist in merged graphs")
    reachable = graph.reachable_from(graph.entry)
    unreachable = set(graph.nodes.keys()) - reachable
    if unreachable:
        unreachable_list = sorted(unreachable)
        msg = f"Unreachable scenes detected from entry '{graph.entry}': {', '.join(unreachable_list)}"
        logger.warning(msg)
        if strict:
            raise ValueError(msg)


def merge_graphs(graphs: list[SceneGraph], *, strict: bool = False) -> SceneGraph:
    """Merge multiple SceneGraph instances into one unified SceneGraph.

    Validates that:
    1. Scene IDs are unique across all merged graphs (raises ValueError on duplicates).
    2. All transition edge targets exist in the combined scene nodes (raises ValueError on broken links).
    3. All scenes are reachable from the entry point (logs warning, and raises ValueError if strict=True).
    """
    if not graphs:
        return to_graph([])

    entry = next((g.entry for g in graphs if g.entry is not None), None)
    combined_nodes: dict[str, Any] = {}
    combined_edges: list[Any] = []
    combined_preamble: list[Any] = []
    combined_characters: dict[str, Any] = {}
    combined_defaults: list[Any] = []

    for g in graphs:
        for node_id, node in g.nodes.items():
            if node_id in combined_nodes:
                raise ValueError(f"Duplicate scene label '{node_id}' across merged graphs")
            combined_nodes[node_id] = node

        combined_edges.extend(g.edges)
        combined_preamble.extend(g.preamble)
        combined_characters.update(g.characters)
        combined_defaults.extend(g.defaults)

    # Validate transition targets
    for edge in combined_edges:
        if edge.target not in combined_nodes:
            raise ValueError(
                f"Invalid transition target '{edge.target}' from scene '{edge.source}' at line {edge.line_number}"
            )

    merged = SceneGraph(
        entry=entry,
        nodes=combined_nodes,
        edges=tuple(combined_edges),
        preamble=tuple(combined_preamble),
        characters=combined_characters,
        defaults=tuple(combined_defaults),
    )

    _validate_reachability(merged, strict=strict)
    return merged


def resolve_project_scripts(target_path: Path) -> list[Path]:
    """Resolve all .es files in a project directory or via @include directives."""
    es_files: list[Path] = []

    if target_path.is_dir():
        project_root = target_path.resolve()
        cfg_path = target_path / "game.toml"
        cfg = ProjectConfig.load(cfg_path) if cfg_path.exists() else ProjectConfig()

        discovered: list[Path] = []
        for p in target_path.rglob("*.es"):
            if not any(part.startswith((".", "venv", "__pycache__")) or part in ("dist", "build") for part in p.parts):
                resolved_p = p.resolve()
                if not resolved_p.is_relative_to(project_root):
                    raise ValueError(
                        f"Path traversal detected: script '{p.name}' resolves outside project root"
                    )
                discovered.append(resolved_p)

        discovered.sort(key=lambda p: str(p))
        entry_file = (target_path / cfg.entry_script).resolve()
        if entry_file in discovered:
            discovered.remove(entry_file)
            discovered.insert(0, entry_file)
        es_files = discovered
    else:
        try:
            es_files = discover_includes(target_path, missing_ok=True)
        except IncludeError as exc:
            raise ValueError(str(exc)) from exc

    return es_files


def load_project_graph(
    target_path: Path,
    *,
    strict: bool = False,
    raise_parse_error: bool = False,
) -> SceneGraph:
    """Load and merge all scene graphs for a project or script file."""
    if not target_path.is_dir():
        try:
            items = parse_file(target_path, resolve_includes_flag=True)
            graph = to_graph(items)
        except (ValueError, TypeError, OSError, ParseError, IncludeError) as exc:
            if raise_parse_error and isinstance(exc, (ParseError, IncludeError, ValueError)):
                raise
            logger.warning("Failed to parse %s: %s", target_path, exc)
            return to_graph([])
        _validate_reachability(graph, strict=strict)
        return graph

    es_files = resolve_project_scripts(target_path)
    project_root = target_path.resolve()

    included_by_others: set[Path] = set()
    for es_file in es_files:
        try:
            included = discover_includes(es_file, root_dir=project_root, missing_ok=True)
            included_by_others.update(included[1:])
        except (IncludeError, OSError):
            continue

    graphs: list[SceneGraph] = []
    for es_file in es_files:
        if es_file in included_by_others:
            continue
        try:
            items = parse_file(es_file, resolve_includes_flag=True, root_dir=project_root)
            graphs.append(to_graph(items))
        except (ValueError, TypeError, OSError, ParseError, IncludeError) as exc:
            if raise_parse_error and isinstance(exc, (ParseError, IncludeError, ValueError)):
                raise
            logger.warning("Failed to parse %s: %s", es_file, exc)

    if not graphs:
        return to_graph([])

    return merge_graphs(graphs, strict=strict)

