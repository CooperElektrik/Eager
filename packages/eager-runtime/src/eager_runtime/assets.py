"""Asset validation and consistency linter for Eager screenplays.

Verifies that assets referenced in screenplay scripts (backgrounds, character
sprites, audio tracks, and voice clips) exist in the specified asset directory.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import eager_script
from eager_script import (
    ParsedDialogue,
    ParsedHook,
    ParsedItem,
    parse_hook_args,
)

if TYPE_CHECKING:
    from eager_script.graph import SceneGraph

IMAGE_EXTENSIONS = ("", ".png", ".jpg", ".jpeg", ".webp", ".bmp")
AUDIO_EXTENSIONS = ("", ".ogg", ".wav", ".mp3", ".flac", ".opus", ".m4a")


@dataclass(frozen=True, slots=True)
class AssetReference:
    """A reference to an external asset found within a screenplay."""

    kind: str  # "background" | "character" | "audio" | "voice" | "image"
    identifier: str
    line_number: int
    scene_id: str | None = None
    character_id: str | None = None
    expression: str | None = None
    channel: str | None = None


@dataclass(frozen=True, slots=True)
class MissingAssetIssue:
    """Details of an asset reference that failed to resolve on disk."""

    reference: AssetReference
    expected_paths: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class AssetCheckReport:
    """Aggregated results of an asset consistency check."""

    total_references: int
    resolved_count: int
    missing: tuple[MissingAssetIssue, ...]
    unused: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return True if all referenced assets were resolved."""
        return len(self.missing) == 0


def extract_asset_references(
    graph_or_items: SceneGraph | Sequence[ParsedItem],
) -> tuple[list[AssetReference], dict[str, dict[str, str]]]:
    """Extract all asset references and character definitions from a graph or AST items."""
    references: list[AssetReference] = []
    character_configs: dict[str, dict[str, str]] = {}

    items_to_scan: list[tuple[ParsedItem, str | None]] = []

    # Check if this is a SceneGraph
    if hasattr(graph_or_items, "nodes") and hasattr(graph_or_items, "preamble"):
        graph: SceneGraph = graph_or_items  # type: ignore[assignment]
        # Preamble items
        for it in graph.preamble:
            items_to_scan.append((it, None))
        # Scene nodes
        for node_id, node in graph.nodes.items():
            for it in node.body:
                items_to_scan.append((it, node_id))
        # Preamble character definitions from graph.characters
        if graph.characters:
            for cid, cdef in graph.characters.items():
                c_id = str(cid).strip().lower()
                attrs_dict: dict[str, str] = {}
                if isinstance(cdef, dict):
                    attrs_dict = {str(k): str(v) for k, v in cdef.items()}
                character_configs[c_id] = attrs_dict
    else:
        for it in graph_or_items:  # type: ignore[union-attr]
            items_to_scan.append((it, None))

    for item, scene_id in items_to_scan:
        if isinstance(item, eager_script.ParsedCharacter):
            c_id = item.id.strip().lower()
            attrs_dict = dict(item.attrs)
            character_configs[c_id] = attrs_dict

        elif isinstance(item, ParsedHook):
            hook_str = item.hook_name.strip()
            if not hook_str:
                continue

            hook_cmd = hook_str.split()[0].lower()
            args = hook_str[len(hook_cmd) :].strip()
            parsed = parse_hook_args(args)

            if hook_cmd in ("bg", "scene"):
                if parsed.positional:
                    asset_id = parsed.positional[0].strip()
                    references.append(
                        AssetReference(
                            kind="background",
                            identifier=asset_id,
                            line_number=item.line_number,
                            scene_id=scene_id,
                        )
                    )

            elif hook_cmd == "show":
                if parsed.positional:
                    char_id = parsed.positional[0].strip().lower()
                    cfg = character_configs.get(char_id, {})
                    if len(parsed.positional) > 1:
                        expr = parsed.positional[1].strip().lower()
                    else:
                        expr = cfg.get("default_expression", "default")
                    references.append(
                        AssetReference(
                            kind="character",
                            identifier=f"{char_id}/{expr}",
                            line_number=item.line_number,
                            scene_id=scene_id,
                            character_id=char_id,
                            expression=expr,
                        )
                    )

            elif hook_cmd == "expr":
                if len(parsed.positional) >= 2:
                    char_id = parsed.positional[0].strip().lower()
                    expr = parsed.positional[1].strip().lower()
                    references.append(
                        AssetReference(
                            kind="character",
                            identifier=f"{char_id}/{expr}",
                            line_number=item.line_number,
                            scene_id=scene_id,
                            character_id=char_id,
                            expression=expr,
                        )
                    )

            elif hook_cmd == "image":
                if len(parsed.positional) >= 2:
                    asset_name = parsed.positional[1].strip()
                    references.append(
                        AssetReference(
                            kind="image",
                            identifier=asset_name,
                            line_number=item.line_number,
                            scene_id=scene_id,
                        )
                    )

            elif hook_cmd == "play":
                if len(parsed.positional) >= 2:
                    chan = parsed.positional[0].strip().lower()
                    track = parsed.positional[1].strip()
                    kind = "voice" if chan == "voice" else "audio"
                    references.append(
                        AssetReference(
                            kind=kind,
                            identifier=track,
                            line_number=item.line_number,
                            scene_id=scene_id,
                            channel=chan,
                        )
                    )

            elif (
                hook_cmd in ("play_bgm", "play_sfx", "play_music", "play_sound", "play_voice")
                and parsed.positional
            ):
                track = parsed.positional[0].strip()
                chan = hook_cmd.replace("play_", "")
                kind = "voice" if chan == "voice" else "audio"
                references.append(
                    AssetReference(
                        kind=kind,
                        identifier=track,
                        line_number=item.line_number,
                        scene_id=scene_id,
                        channel=chan,
                    )
                )

        elif isinstance(item, ParsedDialogue):
            # Check speaker emotion sprite
            speaker = item.speaker.strip()
            speaker_lower = speaker.lower()
            if item.emotion and speaker_lower not in ("narrator", ""):
                expr = item.emotion.strip().lower()
                references.append(
                    AssetReference(
                        kind="character",
                        identifier=f"{speaker_lower}/{expr}",
                        line_number=item.line_number,
                        scene_id=scene_id,
                        character_id=speaker_lower,
                        expression=expr,
                    )
                )

            # Check dialogue voice tag
            if item.voice:
                voice_clip = item.voice.strip()
                references.append(
                    AssetReference(
                        kind="voice",
                        identifier=voice_clip,
                        line_number=item.line_number,
                        scene_id=scene_id,
                        channel="voice",
                    )
                )

    return references, character_configs


def resolve_candidate_paths(
    ref: AssetReference,
    character_configs: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    """Generate potential relative asset paths for an asset reference."""
    candidates: list[str] = []
    configs = character_configs or {}

    if ref.kind == "background":
        name = ref.identifier
        if name.startswith("bg/"):
            name_no_prefix = name[3:]
        else:
            name_no_prefix = name

        for ext in IMAGE_EXTENSIONS:
            candidates.append(f"{name}{ext}")
            candidates.append(f"bg/{name_no_prefix}{ext}")
            candidates.append(f"backgrounds/{name_no_prefix}{ext}")

    elif ref.kind == "character":
        cid = ref.character_id or ref.identifier.split("/")[0]
        expr = ref.expression or (ref.identifier.split("/")[1] if "/" in ref.identifier else "default")
        cfg = configs.get(cid, {})
        prefix = cfg.get("asset_prefix")

        for ext in IMAGE_EXTENSIONS:
            candidates.append(f"{cid}/{expr}{ext}")
            candidates.append(f"{cid}_{expr}{ext}")
            candidates.append(f"characters/{cid}/{expr}{ext}")
            candidates.append(f"characters/{cid}_{expr}{ext}")
            if prefix:
                candidates.append(f"{prefix}_{expr}{ext}")
                candidates.append(f"{prefix}/{expr}{ext}")
                candidates.append(f"characters/{prefix}_{expr}{ext}")
                candidates.append(f"characters/{prefix}/{expr}{ext}")

    elif ref.kind == "audio":
        track = ref.identifier
        chan = ref.channel or "audio"
        for ext in AUDIO_EXTENSIONS:
            candidates.append(f"{track}{ext}")
            candidates.append(f"audio/{track}{ext}")
            candidates.append(f"{chan}/{track}{ext}")
            candidates.append(f"audio/{chan}/{track}{ext}")

    elif ref.kind == "voice":
        track = ref.identifier
        for ext in AUDIO_EXTENSIONS:
            candidates.append(f"{track}{ext}")
            candidates.append(f"voice/{track}{ext}")
            candidates.append(f"audio/voice/{track}{ext}")
            candidates.append(f"audio/{track}{ext}")

    elif ref.kind == "image":
        name = ref.identifier
        for ext in IMAGE_EXTENSIONS:
            candidates.append(f"{name}{ext}")
            candidates.append(f"images/{name}{ext}")

    # Remove duplicates while preserving order
    unique_candidates: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique_candidates.append(c)
    return unique_candidates


def check_assets(
    graph_or_items: SceneGraph | Sequence[ParsedItem],
    asset_dir: str | Path,
    *,
    check_unused: bool = False,
) -> AssetCheckReport:
    """Validate screenplay asset references against an asset directory."""
    path_asset_dir = Path(asset_dir).resolve()
    references, char_configs = extract_asset_references(graph_or_items)

    missing: list[MissingAssetIssue] = []
    used_files: set[Path] = set()
    resolved_count = 0

    if not path_asset_dir.is_dir():
        for ref in references:
            candidates = resolve_candidate_paths(ref, char_configs)
            missing.append(
                MissingAssetIssue(
                    reference=ref,
                    expected_paths=tuple(candidates[:4]),
                    message=(
                        f"Asset directory '{path_asset_dir}' does not exist. "
                        f"Missing {ref.kind} '{ref.identifier}'."
                    ),
                )
            )
        return AssetCheckReport(
            total_references=len(references),
            resolved_count=0,
            missing=tuple(missing),
            unused=(),
        )

    for ref in references:
        candidates = resolve_candidate_paths(ref, char_configs)
        found_file: Path | None = None

        for cand in candidates:
            cand_path = path_asset_dir / cand
            if cand_path.is_file():
                found_file = cand_path
                break

        if found_file is not None:
            resolved_count += 1
            used_files.add(found_file.resolve())
        else:
            missing.append(
                MissingAssetIssue(
                    reference=ref,
                    expected_paths=tuple(candidates[:5]),
                    message=(
                        f"Line {ref.line_number}: {ref.kind.capitalize()} asset "
                        f"'{ref.identifier}' not found in '{asset_dir}'"
                    ),
                )
            )

    unused_list: list[str] = []
    if check_unused and path_asset_dir.is_dir():
        for f in path_asset_dir.rglob("*"):
            if not f.is_file():
                continue
            if f.name.startswith(".") or f.suffix.lower() not in (
                ".png",
                ".jpg",
                ".jpeg",
                ".webp",
                ".bmp",
                ".ogg",
                ".wav",
                ".mp3",
                ".flac",
            ):
                continue
            if f.resolve() not in used_files:
                try:
                    rel = str(f.relative_to(path_asset_dir))
                    unused_list.append(rel)
                except ValueError:
                    pass
        unused_list.sort()

    return AssetCheckReport(
        total_references=len(references),
        resolved_count=resolved_count,
        missing=tuple(missing),
        unused=tuple(unused_list),
    )
