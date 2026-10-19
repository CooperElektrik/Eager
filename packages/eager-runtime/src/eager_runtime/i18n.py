"""Translation extraction and catalog management tooling for Eager screenplays."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from eager_core.i18n import TranslationCatalog
from eager_script import (
    ParsedAppend,
    ParsedChoiceSet,
    ParsedDialogue,
    ParsedFreshBox,
    ParsedHook,
    ParsedNarration,
)

if TYPE_CHECKING:
    from eager_script.graph import SceneGraph


def strip_explicit_id(text: str) -> str:
    """Strip inline {id=...} beat ID metadata tag from dialogue or narration text."""
    if not text or "{id=" not in text:
        return text
    return re.sub(r"\s*\{id=[a-zA-Z0-9_-]+\}\s*", " ", text).strip()


def _get_item_content_key(item: Any) -> str:
    """Extract a content key for counting identical beats within a scene."""
    if isinstance(item, ParsedDialogue):
        return f"{item.speaker}:{strip_explicit_id(item.text)}"
    if isinstance(item, (ParsedNarration, ParsedAppend, ParsedFreshBox)):
        return f"{item.type}:{strip_explicit_id(item.text)}"
    if isinstance(item, ParsedChoiceSet):
        return "choices:" + "|".join(strip_explicit_id(opt.text) for opt in item.options)
    if isinstance(item, ParsedHook):
        return f"hook:{strip_explicit_id(item.hook_name.strip())}"
    return strip_explicit_id(str(getattr(item, "text", type(item).__name__)))


def get_beat_occurrence(body: Sequence[Any], index: int) -> int:
    """Calculate the 1-based occurrence count of the item at index within the scene body."""
    if index < 0 or index >= len(body):
        return 1
    key = _get_item_content_key(body[index])
    count = 0
    for i in range(index + 1):
        if _get_item_content_key(body[i]) == key:
            count += 1
    return count


def compute_beat_id(scene_id: str, item: Any, occurrence: int = 1) -> str:
    """Compute a stable content-addressed beat ID for a narrative beat.

    Uses explicit beat IDs if specified on the AST item (item.id or item.beat_id or {id=...}),
    otherwise derives an MD5 content hash from the scene ID and item payload so that
    inserting or deleting surrounding beats does not shift IDs.
    """
    explicit = getattr(item, "id", None) or getattr(item, "beat_id", None)
    if explicit:
        return f"{scene_id}.{explicit}" if not str(explicit).startswith(f"{scene_id}.") else str(explicit)

    text = getattr(item, "text", None)
    if text and "{id=" in text:
        m = re.search(r"\{id=([a-zA-Z0-9_-]+)\}", text)
        if m:
            return f"{scene_id}.{m.group(1)}"

    content = _get_item_content_key(item)
    digest = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    suffix = f"_{occurrence}" if occurrence > 1 else ""
    return f"{scene_id}.{digest}{suffix}"


def extract_catalog(
    graph: SceneGraph,
    locale: str = "template",
) -> TranslationCatalog:
    """Extract all translatable beats from a SceneGraph into a TranslationCatalog.

    Generates stable content-addressed MD5/explicit keys so inserting lines
    does not break translations.
    """
    strings: dict[str, str] = {}
    speakers: dict[str, str] = {}
    total_beats = 0

    for scene_id, node in graph.nodes.items():
        content_counts: dict[str, int] = {}
        for item in node.body:
            c_key = _get_item_content_key(item)
            cnt = content_counts.get(c_key, 0) + 1
            content_counts[c_key] = cnt
            cid = compute_beat_id(scene_id, item, occurrence=cnt)

            if isinstance(item, ParsedDialogue):
                spk = item.speaker.strip()
                if spk.lower() not in ("narrator", ""):
                    speakers[spk] = spk
                clean_text = strip_explicit_id(item.text)
                strings[cid] = clean_text
                total_beats += 1

            elif isinstance(item, (ParsedNarration, ParsedAppend, ParsedFreshBox)):
                clean_text = strip_explicit_id(item.text)
                strings[cid] = clean_text
                total_beats += 1

            elif isinstance(item, ParsedChoiceSet):
                for opt_idx, opt in enumerate(item.options):
                    clean_opt = strip_explicit_id(opt.text)
                    strings[f"{cid}.choice_{opt_idx}"] = clean_opt
                    total_beats += 1

            elif isinstance(item, ParsedHook):
                hook_str = item.hook_name.strip()
                if hook_str.startswith("input"):
                    parts = hook_str.split(None, 2)
                    prompt = parts[2].strip().strip("\"'") if len(parts) > 2 else "Enter input:"
                    clean_prompt = strip_explicit_id(prompt)
                    strings[f"{cid}.input"] = clean_prompt
                    total_beats += 1

    return TranslationCatalog(
        locale=locale,
        strings=strings,
        speakers=speakers,
        metadata={
            "generator": "eager i18n",
            "entry_scene": graph.entry or "",
            "total_strings": str(total_beats),
            "total_beats": str(total_beats),
        },
    )


def merge_catalog(
    template: TranslationCatalog,
    existing: TranslationCatalog,
    *,
    keep_source_untranslated: bool = False,
) -> tuple[TranslationCatalog, dict[str, int]]:
    """Merge newly extracted template with an existing translation catalog.

    Preserves existing translations, adds new keys (empty or source text),
    and tracks obsolete keys.
    """
    merged_strings: dict[str, str] = {}
    merged_speakers: dict[str, str] = {}

    translated_count = 0
    new_count = 0
    obsolete_count = 0

    # 1. Strings
    for key, source_text in template.strings.items():
        if key in existing.strings and existing.strings[key].strip():
            merged_strings[key] = existing.strings[key]
            translated_count += 1
        else:
            merged_strings[key] = source_text if keep_source_untranslated else ""
            new_count += 1

    for key in existing.strings:
        if key not in template.strings:
            obsolete_count += 1

    # 2. Speakers
    for spk, default_name in template.speakers.items():
        if spk in existing.speakers and existing.speakers[spk].strip():
            merged_speakers[spk] = existing.speakers[spk]
        else:
            merged_speakers[spk] = existing.speakers.get(spk, default_name)

    meta = dict(existing.metadata)
    meta["generator"] = "eager i18n"
    meta["total_strings"] = str(len(merged_strings))

    merged = TranslationCatalog(
        locale=existing.locale or template.locale,
        strings=merged_strings,
        speakers=merged_speakers,
        metadata=meta,
    )

    stats = {
        "translated": translated_count,
        "new": new_count,
        "obsolete": obsolete_count,
        "total": len(merged_strings),
    }
    return merged, stats


def validate_catalog(
    catalog: TranslationCatalog,
    graph: SceneGraph,
) -> dict[str, Any]:
    """Validate a translation catalog against a scene graph."""
    template = extract_catalog(graph, locale=catalog.locale)
    total_strings = int(template.metadata.get("total_beats", len(template.strings)))

    translated_keys: list[str] = []
    untranslated_keys: list[str] = []
    known_keys: set[str] = set()

    for scene_id, node in graph.nodes.items():
        content_counts: dict[str, int] = {}
        for item in node.body:
            c_key = _get_item_content_key(item)
            cnt = content_counts.get(c_key, 0) + 1
            content_counts[c_key] = cnt
            cid = compute_beat_id(scene_id, item, occurrence=cnt)

            if isinstance(item, (ParsedDialogue, ParsedNarration, ParsedAppend, ParsedFreshBox)):
                known_keys.add(cid)
                val = catalog.strings.get(cid)
                if val is not None and val.strip():
                    translated_keys.append(cid)
                else:
                    untranslated_keys.append(cid)

            elif isinstance(item, ParsedChoiceSet):
                for opt_idx, _ in enumerate(item.options):
                    c_opt = f"{cid}.choice_{opt_idx}"
                    known_keys.add(c_opt)
                    val = catalog.strings.get(c_opt)
                    if val is not None and val.strip():
                        translated_keys.append(c_opt)
                    else:
                        untranslated_keys.append(c_opt)

            elif isinstance(item, ParsedHook):
                hook_str = item.hook_name.strip()
                if hook_str.startswith("input"):
                    c_inp = f"{cid}.input"
                    known_keys.add(c_inp)
                    val = catalog.strings.get(c_inp)
                    if val is not None and val.strip():
                        translated_keys.append(c_inp)
                    else:
                        untranslated_keys.append(c_inp)

    # Obsolete keys in catalog: keys that do not match content-addressed IDs of any beat
    obsolete_keys = [k for k in catalog.strings if k not in known_keys]

    coverage = (len(translated_keys) / total_strings * 100.0) if total_strings > 0 else 100.0

    return {
        "locale": catalog.locale,
        "total": total_strings,
        "translated": len(translated_keys),
        "untranslated": len(untranslated_keys),
        "obsolete": len(obsolete_keys),
        "coverage_percent": round(coverage, 1),
        "missing_keys": untranslated_keys,
        "obsolete_keys": obsolete_keys,
        "is_complete": len(untranslated_keys) == 0,
    }
