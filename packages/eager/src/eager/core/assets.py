"""Asset validation and consistency linter for Eager screenplays.

Verifies that assets referenced in screenplay scripts (backgrounds, character
sprites, audio tracks, and voice clips) exist in the specified asset directory.
"""

from __future__ import annotations

import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [  # noqa: RUF022
    "AUDIO_EXTENSIONS",
    "AssetCheckReport",
    "AssetKind",
    "AssetReference",
    "IMAGE_EXTENSIONS",
    "MissingAssetIssue",
    "check_assets",
    "extract_asset_references",
    "resolve_candidate_paths",
]


def _parse_hook_tokens(raw_args: str) -> tuple[list[str], dict[str, str]]:
    """Parse positional tokens and key=value pairs from a raw hook argument string."""
    if not raw_args or not raw_args.strip():
        return [], {}
    try:
        tokens = shlex.split(raw_args)
    except ValueError:
        tokens = raw_args.strip().split()
    positional: list[str] = []
    kwargs: dict[str, str] = {}
    idx = 0
    num_tokens = len(tokens)
    while idx < num_tokens:
        tok = tokens[idx]
        if "=" in tok:
            k, v = tok.split("=", 1)
            k = k.strip()
            if k.isidentifier():
                kwargs[k] = v.strip()
                idx += 1
                continue
        tok_lower = tok.lower()
        if tok_lower in ("at", "with", "to") and idx + 1 < num_tokens and "=" not in tokens[idx + 1]:
            idx += 2
            continue
        positional.append(tok)
        idx += 1
    return positional, kwargs

IMAGE_EXTENSIONS = ("", ".png", ".jpg", ".jpeg", ".webp", ".bmp")
AUDIO_EXTENSIONS = ("", ".ogg", ".wav", ".mp3", ".flac", ".opus", ".m4a")


class AssetKind(str, Enum):
    """Classification of external assets referenced in screenplays."""

    BACKGROUND = "background"
    CHARACTER = "character"
    AUDIO = "audio"
    VOICE = "voice"
    IMAGE = "image"


@dataclass(frozen=True, slots=True)
class AssetReference:
    """A reference to an external asset found within a screenplay."""

    kind: AssetKind | str
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
    graph_or_items: Any,
    *,
    extra_characters: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[AssetReference], dict[str, dict[str, str]]]:
    """Extract all asset references and character definitions from a graph or AST items."""
    references: list[AssetReference] = []
    character_configs: dict[str, dict[str, str]] = {}
    if extra_characters:
        for cid, cdef in extra_characters.items():
            c_id = str(cid).strip().lower()
            extra_attrs_dict: dict[str, str] = {}
            if isinstance(cdef, dict):
                raw_attrs = cdef.get("attrs")
                if isinstance(raw_attrs, dict):
                    extra_attrs_dict.update({str(k): str(v) for k, v in raw_attrs.items()})
                if "name" in cdef and cdef["name"] is not None:
                    extra_attrs_dict["name"] = str(cdef["name"])
            character_configs[c_id] = extra_attrs_dict

    items_to_scan: list[tuple[Any, str | None]] = []

    def collect_items(seq: Iterable[Any], sc_id: str | None) -> None:
        for it in seq:
            items_to_scan.append((it, sc_id))
            if getattr(it, "type", None) == "choice_set":
                for opt in it.options:
                    if opt.body:
                        collect_items(opt.body, sc_id)

    # Check if this is a SceneGraph
    if hasattr(graph_or_items, "nodes") and hasattr(graph_or_items, "preamble"):
        graph = graph_or_items
        # Preamble items
        collect_items(graph.preamble, None)
        # Scene nodes
        for node_id, node in graph.nodes.items():
            collect_items(node.body, node_id)
        # Preamble character definitions from graph.characters
        if graph.characters:
            for cid, cdef in graph.characters.items():
                c_id = str(cid).strip().lower()
                attrs_dict: dict[str, str] = {}
                if isinstance(cdef, dict):
                    raw_attrs = cdef.get("attrs")
                    if isinstance(raw_attrs, dict):
                        attrs_dict.update({str(k): str(v) for k, v in raw_attrs.items()})
                    if "name" in cdef and cdef["name"] is not None:
                        attrs_dict["name"] = str(cdef["name"])
                    if "side_image" in attrs_dict:
                        references.append(
                            AssetReference(
                                kind="character",
                                identifier=attrs_dict["side_image"],
                                line_number=cdef.get("line_number", 0) or 0,
                                scene_id=None,
                                character_id=c_id,
                            )
                        )
                character_configs[c_id] = attrs_dict
    else:
        collect_items(graph_or_items, None)

    # First pass: collect all character definitions from items_to_scan
    has_graph_characters = hasattr(graph_or_items, "characters") and isinstance(
        graph_or_items.characters, dict
    )
    for item, _ in items_to_scan:
        if getattr(item, "type", None) == "character":
            c_id = item.id.strip().lower()
            attrs_dict = dict(item.attrs)
            if item.name:
                attrs_dict["name"] = item.name
            character_configs[c_id] = attrs_dict
            if not has_graph_characters:
                side_img = attrs_dict.get("side_image")
                if side_img:
                    references.append(
                        AssetReference(
                            kind="character",
                            identifier=side_img,
                            line_number=item.line_number,
                            scene_id=None,
                            character_id=c_id,
                        )
                    )

    def resolve_char_id(raw_name: str) -> str:
        clean = raw_name.strip().lower()
        if clean in character_configs:
            return clean
        for cid, cfg in character_configs.items():
            name = cfg.get("name")
            if name and name.strip().lower() == clean:
                return cid
        return clean

    for item, scene_id in items_to_scan:
        item_type = getattr(item, "type", None)
        if item_type == "character":
            continue

        elif item_type == "hook":
            hook_str = item.hook_name.strip()
            if not hook_str:
                continue

            hook_cmd = hook_str.split()[0].lower()
            args = hook_str[len(hook_cmd) :].strip()
            positional, hook_kwargs = _parse_hook_tokens(args)

            if hook_cmd in ("bg", "scene", "scene_bg"):
                if hook_cmd == "scene_bg":
                    if len(positional) >= 2:
                        asset_id = positional[1].strip()
                        references.append(
                            AssetReference(
                                kind="background",
                                identifier=asset_id,
                                line_number=item.line_number,
                                scene_id=scene_id,
                            )
                        )
                elif positional:
                    asset_id = positional[0].strip()
                    references.append(
                        AssetReference(
                            kind="background",
                            identifier=asset_id,
                            line_number=item.line_number,
                            scene_id=scene_id,
                        )
                    )

            elif hook_cmd == "show":
                if positional:
                    raw_char = positional[0].strip()
                    char_id = resolve_char_id(raw_char)
                    cfg = character_configs.get(char_id, {})
                    if len(positional) > 1:
                        expr = positional[1].strip().lower()
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
                if len(positional) >= 2:
                    raw_char = positional[0].strip()
                    char_id = resolve_char_id(raw_char)
                    expr = positional[1].strip().lower()
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
                if len(positional) >= 2:
                    asset_name = positional[1].strip()
                    references.append(
                        AssetReference(
                            kind="image",
                            identifier=asset_name,
                            line_number=item.line_number,
                            scene_id=scene_id,
                        )
                    )

            elif hook_cmd in ("play", "play_bgm", "play_music", "play_sfx", "play_sound", "play_ambient", "play_voice"):
                track_kw = hook_kwargs.get("track")
                chan_kw = hook_kwargs.get("channel")
                chan: str | None = None
                track: str | None = None
                if hook_cmd != "play":
                    shorthand_chan = hook_cmd.removeprefix("play_")
                    chan = {"bgm": "music", "sfx": "sound"}.get(shorthand_chan, shorthand_chan)
                    if positional:
                        track = positional[0].strip()
                    elif track_kw:
                        track = track_kw.strip()
                elif positional:
                    raw_chan = positional[0].strip().lower()
                    chan = {"bgm": "music", "sfx": "sound"}.get(raw_chan, raw_chan)
                    if len(positional) >= 2:
                        track = positional[1].strip()
                    elif track_kw:
                        track = track_kw.strip()
                elif chan_kw and track_kw:
                    raw_chan = chan_kw.strip().lower()
                    chan = {"bgm": "music", "sfx": "sound"}.get(raw_chan, raw_chan)
                    track = track_kw.strip()
                    chan = chan_kw.strip().lower()
                    track = track_kw.strip()
                if chan and track:
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

        elif item_type == "dialogue":
            # Check speaker emotion sprite
            speaker = item.speaker.strip()
            speaker_lower = resolve_char_id(speaker)
            if item.emotion and speaker.lower() not in ("narrator", ""):
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


def _expand_character_expression(raw_expr: str, cfg: dict[str, str]) -> list[str]:
    """Expand character expression alias into its target expression name."""
    if not raw_expr:
        return ["default"]
    return [cfg.get(raw_expr, raw_expr)]


def _candidate_paths_for_character_layer(cid: str, layer: str, cfg: dict[str, str]) -> list[str]:
    cands: list[str] = []
    prefix = cfg.get("asset_prefix")
    name = cfg.get("name")
    for ext in IMAGE_EXTENSIONS:
        cands.append(f"{cid}/{layer}{ext}")
        cands.append(f"{cid}_{layer}{ext}")
        cands.append(f"characters/{cid}/{layer}{ext}")
        cands.append(f"characters/{cid}_{layer}{ext}")
        if prefix:
            cands.append(f"{prefix}_{layer}{ext}")
            cands.append(f"{prefix}/{layer}{ext}")
            cands.append(f"characters/{prefix}_{layer}{ext}")
            cands.append(f"characters/{prefix}/{layer}{ext}")
        if name:
            name_clean = name.strip().lower()
            if name_clean != cid and name_clean != (prefix or "").lower():
                cands.append(f"{name_clean}/{layer}{ext}")
                cands.append(f"{name_clean}_{layer}{ext}")
                cands.append(f"characters/{name_clean}/{layer}{ext}")
                cands.append(f"characters/{name_clean}_{layer}{ext}")
    return cands


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
        if ref.expression is None and "/" not in ref.identifier and ref.identifier != cid:
            # Explicit side_image or flat character asset identifier (e.g. side_image="hoshiko_side")
            side_name = ref.identifier.strip()
            for ext in IMAGE_EXTENSIONS:
                candidates.append(f"{side_name}{ext}")
                candidates.append(f"characters/{side_name}{ext}")
                candidates.append(f"{cid}/{side_name}{ext}")
                candidates.append(f"characters/{cid}/{side_name}{ext}")
        elif ref.expression is None and "/" in ref.identifier:
            side_path = ref.identifier.strip()
            for ext in IMAGE_EXTENSIONS:
                candidates.append(f"{side_path}{ext}")
                if not side_path.startswith("characters/"):
                    candidates.append(f"characters/{side_path}{ext}")
                if not side_path.startswith(f"{cid}/"):
                    candidates.append(f"{cid}/{side_path}{ext}")
                    candidates.append(f"characters/{cid}/{side_path}{ext}")
        else:
            expr = ref.expression or (ref.identifier.split("/")[1] if "/" in ref.identifier else "default")
            cfg = configs.get(cid, {})
            layers = _expand_character_expression(expr, cfg)
            for layer in layers:
                candidates.extend(_candidate_paths_for_character_layer(cid, layer, cfg))

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


def _find_asset_file(base_dir: Path, candidates: list[str]) -> Path | None:
    """Return the first existing file under *base_dir* from *candidates*, guarding against traversal."""
    for cand in candidates:
        cand_path = (base_dir / cand).resolve()
        if not cand_path.is_relative_to(base_dir):
            continue
        if cand_path.is_file():
            return cand_path
    return None


def check_assets(
    graph_or_items: Any,
    asset_dir: str | Path,
    *,
    check_unused: bool = False,
    extra_characters: dict[str, dict[str, Any]] | None = None,
) -> AssetCheckReport:
    """Validate screenplay asset references against an asset directory."""
    path_asset_dir = Path(asset_dir).resolve()
    references, char_configs = extract_asset_references(
        graph_or_items,
        extra_characters=extra_characters,
    )

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
        configs = char_configs or {}
        if ref.kind == "character":
            cid = ref.character_id or ref.identifier.split("/")[0]
            expr = ref.expression or (ref.identifier.split("/")[1] if "/" in ref.identifier else "default")
            cfg = configs.get(cid, {})
            layers = _expand_character_expression(expr, cfg)
            if len(layers) > 1:
                missing_layers: list[str] = []
                missing_candidates: list[str] = []
                found_layer_files: list[Path] = []
                for layer in layers:
                    layer_cands = _candidate_paths_for_character_layer(cid, layer, cfg)
                    layer_file = _find_asset_file(path_asset_dir, layer_cands)
                    if layer_file is not None:
                        found_layer_files.append(layer_file)
                    else:
                        missing_layers.append(layer)
                        missing_candidates.extend(layer_cands[:2])

                if not missing_layers:
                    resolved_count += 1
                    for f in found_layer_files:
                        used_files.add(f.resolve())
                else:
                    missing.append(
                        MissingAssetIssue(
                            reference=ref,
                            expected_paths=tuple(missing_candidates[:5]),
                            message=(
                                f"Line {ref.line_number}: Character asset '{ref.identifier}' is missing "
                                f"constituent layer(s): {', '.join(missing_layers)} in '{asset_dir}'"
                            ),
                        )
                    )
                continue

        candidates = resolve_candidate_paths(ref, char_configs)
        found_file = _find_asset_file(path_asset_dir, candidates)

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
