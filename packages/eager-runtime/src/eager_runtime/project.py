"""Project configuration parser for game.toml and multi-file scene graph merging."""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eager_script import SceneGraph, to_graph

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

    @classmethod
    def load(cls, toml_path: Path) -> ProjectConfig:
        if not toml_path.exists():
            return cls()
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

        game_data = data.get("game", {})
        window_data = data.get("window", {})

        return cls(
            title=game_data.get("title", "Untitled Project"),
            version=game_data.get("version", "0.1.0"),
            author=game_data.get("author", "Anonymous"),
            entry_script=game_data.get("entry_script", "main.es"),
            virtual_width=int(window_data.get("width", 1920)),
            virtual_height=int(window_data.get("height", 1080)),
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
