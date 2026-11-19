"""Shared visual asset candidate resolution and path-traversal validation."""

from __future__ import annotations

from pathlib import Path

from eager.backends.exceptions import AssetSecurityError
from eager.core.assets import AssetKind, AssetReference, resolve_candidate_paths

__all__ = [
    "resolve_visual_asset_candidates",
    "validate_asset_path",
]


def validate_asset_path(asset_dir: Path, relative_candidate: str, asset_id: str) -> Path:
    """Resolve *relative_candidate* under *asset_dir* and guard against path traversal."""
    resolved_base = asset_dir.resolve()
    cand_path = (asset_dir / relative_candidate).resolve()
    if not cand_path.is_relative_to(resolved_base):
        raise AssetSecurityError(f"Path traversal detected in asset ID: {asset_id}")
    return cand_path


def resolve_visual_asset_candidates(asset_id: str) -> list[str]:
    """Return ordered relative candidate paths for a visual *asset_id* using core rules."""
    candidates: list[str] = []
    if asset_id.startswith(("bg/", "backgrounds/")):
        candidates.extend(
            resolve_candidate_paths(
                AssetReference(kind=AssetKind.BACKGROUND, identifier=asset_id, line_number=0)
            )
        )
    elif "/" in asset_id:
        cid, expr = asset_id.split("/", 1)
        candidates.extend(
            resolve_candidate_paths(
                AssetReference(
                    kind=AssetKind.CHARACTER,
                    identifier=asset_id,
                    line_number=0,
                    character_id=cid,
                    expression=expr,
                )
            )
        )
        candidates.extend(
            resolve_candidate_paths(
                AssetReference(kind=AssetKind.IMAGE, identifier=asset_id, line_number=0)
            )
        )
        candidates.extend(
            resolve_candidate_paths(
                AssetReference(kind=AssetKind.BACKGROUND, identifier=asset_id, line_number=0)
            )
        )
    else:
        candidates.extend(
            resolve_candidate_paths(
                AssetReference(kind=AssetKind.IMAGE, identifier=asset_id, line_number=0)
            )
        )
        candidates.extend(
            resolve_candidate_paths(
                AssetReference(
                    kind=AssetKind.CHARACTER,
                    identifier=asset_id,
                    line_number=0,
                    character_id=asset_id,
                    expression="default",
                )
            )
        )
        # Also allow flat `characters/<asset_id><ext>` when `asset_id` has no slash.
        for ext in ("", ".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            candidates.append(f"characters/{asset_id}{ext}")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for cand in candidates:
        if cand not in seen:
            seen.add(cand)
            unique.append(cand)
    return unique
