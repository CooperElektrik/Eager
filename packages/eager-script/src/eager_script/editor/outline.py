"""Scene outline extractor for screenplay navigation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from eager_script import slugify


@dataclass(frozen=True)
class SceneEntry:
    """Represents a scene/label in the screenplay."""

    line_index: int  # 0-indexed
    line_number: int  # 1-indexed
    display_name: str
    label_id: str


def extract_outline(lines: Sequence[str]) -> list[SceneEntry]:
    """Scan lines for '##' scene definitions and build an outline list."""
    scenes: list[SceneEntry] = []
    for idx, line in enumerate(lines):
        trimmed = line.strip()
        if trimmed.startswith("##"):
            rest = trimmed[2:].strip()
            if not rest:
                continue

            if "---" in rest:
                display, name = rest.split("---", 1)
                display_name = display.strip()
                label_id = name.strip()
            else:
                display_name = rest
                label_id = slugify(rest)

            scenes.append(
                SceneEntry(
                    line_index=idx,
                    line_number=idx + 1,
                    display_name=display_name,
                    label_id=label_id,
                )
            )
    return scenes
