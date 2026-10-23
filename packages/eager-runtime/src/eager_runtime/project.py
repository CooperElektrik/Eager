"""Project configuration parser for game.toml and multi-file scene graph merging."""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eager_core.types import Color
from eager_script import SceneGraph, parse_graph, to_graph

logger = logging.getLogger(__name__)


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

    @classmethod
    def load(cls, toml_path: Path) -> ProjectConfig:
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

        return cls(
            title=game_data.get("title", "Untitled Project"),
            version=game_data.get("version", "0.1.0"),
            author=game_data.get("author", "Anonymous"),
            entry_script=game_data.get("entry_script", "main.es"),
            virtual_width=int(window_data.get("width", 1920)),
            virtual_height=int(window_data.get("height", 1080)),
            theme=theme_name,
            theme_overrides=theme_overrides,
        )


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

    # Validate reachability from entry
    if merged.entry:
        if merged.entry not in combined_nodes:
            raise ValueError(f"Entry scene '{merged.entry}' does not exist in merged graphs")
        reachable = merged.reachable_from(merged.entry)
        unreachable = set(combined_nodes.keys()) - reachable
        if unreachable:
            unreachable_list = sorted(unreachable)
            msg = f"Unreachable scenes detected from entry '{merged.entry}': {', '.join(unreachable_list)}"
            logger.warning(msg)
            if strict:
                raise ValueError(msg)

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
        # Load script and any includes recursively
        project_root = target_path.resolve().parent
        visited: set[Path] = set()
        queue = [target_path.resolve()]

        while queue:
            current = queue.pop(0)
            if current in visited or not current.is_file():
                continue

            visited.add(current)
            es_files.append(current)

            try:
                text = current.read_text(encoding="utf-8")
                for line in text.splitlines():
                    # Check for @include "filename.es" or 'filename.es'
                    m = re.match(r'^\s*@include\s+["\']([^"\']+)["\']', line)
                    if m:
                        inc_name = m.group(1)
                        inc_path = (current.parent / inc_name).resolve()
                        if not inc_path.is_relative_to(project_root):
                            raise ValueError(
                                f"Path traversal detected: @include '{inc_name}' resolves outside project root"
                            )
                        queue.append(inc_path)
            except OSError:
                pass

    return es_files


def load_project_graph(target_path: Path, *, strict: bool = False) -> SceneGraph:
    """Load and merge all scene graphs for a project or script file."""

    es_files = resolve_project_scripts(target_path)
    graphs: list[SceneGraph] = []

    for es_file in es_files:
        try:
            text = es_file.read_text(encoding="utf-8")
            graphs.append(parse_graph(text))
        except (ValueError, TypeError, OSError):
            logger.warning(f"Failed to parse {es_file}")

    if not graphs:
        return to_graph([])

    return merge_graphs(graphs, strict=strict)
