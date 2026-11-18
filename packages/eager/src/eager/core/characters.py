"""Registration metadata and expression resolution for story characters."""

from __future__ import annotations

from dataclasses import dataclass, field

from eager.core.types import Color

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
        """Resolve an expression string, expanding any alias configured for the character."""
        expr_clean = expr.strip()
        if not expr_clean:
            return expr_clean
        return self.expressions.get(expr_clean, expr_clean)
