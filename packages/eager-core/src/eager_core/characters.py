"""Registration metadata and expression resolution for story characters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eager_core.types import Color

__all__ = [
    "CharacterConfig",
]


@dataclass
class CharacterConfig:
    """Registration metadata for a story character."""

    character_id: str
    name: str | None = None
    asset_prefix: str | None = None
    default_expression: str = "default"
    default_position: str = "center"
    side_image: str | None = None
    color: Color | None = None
    expressions: dict[str, str] = field(default_factory=dict)

    def resolve_expression(self, expr: str) -> str:
        """Resolve an expression string, expanding any aliases configured for the character.

        Supports single expressions, comma-separated, and plus-separated layer combinations.
        Aliases defined in `expressions` are expanded recursively.
        """
        expr_clean = expr.strip()
        if not expr_clean:
            return expr_clean

        if expr_clean in self.expressions:
            return self.expressions[expr_clean]

        if "," in expr_clean or "+" in expr_clean:
            parts = [
                pt.strip()
                for pt in expr_clean.replace(",", "+").split("+")
                if pt.strip()
            ]
            expanded: list[str] = []
            for pt in parts:
                resolved = self.expressions.get(pt, pt)
                for sub in resolved.split("+"):
                    s = sub.strip()
                    if s and s not in expanded:
                        expanded.append(s)
            return "+".join(expanded) if expanded else expr_clean

        return expr_clean
