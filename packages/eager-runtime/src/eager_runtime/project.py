"""Project configuration parser for game.toml and multi-file scene graph merging."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from eager_script import SceneGraph, to_graph


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


def merge_graphs(graphs: list[SceneGraph]) -> SceneGraph:
    """Merge multiple SceneGraph instances into one unified SceneGraph."""
    if not graphs:
        return to_graph([])

    entry = graphs[0].entry
    combined_nodes = {}
    combined_edges = []
    combined_preamble = []
    combined_characters = {}
    combined_defaults = []

    for g in graphs:
        combined_nodes.update(g.nodes)
        combined_edges.extend(g.edges)
        combined_preamble.extend(g.preamble)
        if hasattr(g, "characters"):
            combined_characters.update(g.characters)
        if hasattr(g, "defaults"):
            combined_defaults.extend(g.defaults)

    return SceneGraph(
        entry=entry,
        nodes=combined_nodes,
        edges=tuple(combined_edges),
        preamble=tuple(combined_preamble),
        characters=combined_characters,
        defaults=tuple(combined_defaults),
    )
