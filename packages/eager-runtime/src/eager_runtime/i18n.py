"""Translation extraction and catalog management tooling for Eager screenplays."""

from __future__ import annotations

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


def extract_catalog(
    graph: SceneGraph,
    locale: str = "template",
) -> TranslationCatalog:
    """Extract all translatable beats from a SceneGraph into a TranslationCatalog."""
    strings: dict[str, str] = {}
    speakers: dict[str, str] = {}

    for scene_id, node in graph.nodes.items():
        for idx, item in enumerate(node.body):
            beat_id = f"{scene_id}.{idx}"

            if isinstance(item, ParsedDialogue):
                spk = item.speaker.strip()
                if spk.lower() not in ("narrator", ""):
                    speakers[spk] = spk
                strings[beat_id] = item.text

            elif isinstance(item, (ParsedNarration, ParsedAppend, ParsedFreshBox)):
                strings[beat_id] = item.text

            elif isinstance(item, ParsedChoiceSet):
                for opt_idx, opt in enumerate(item.options):
                    opt_beat_id = f"{beat_id}.choice_{opt_idx}"
                    strings[opt_beat_id] = opt.text

            elif isinstance(item, ParsedHook):
                hook_str = item.hook_name.strip()
                if hook_str.startswith("input"):
                    parts = hook_str.split(None, 2)
                    prompt = parts[2].strip().strip("\"'") if len(parts) > 2 else "Enter input:"
                    strings[f"{beat_id}.input"] = prompt

    return TranslationCatalog(
        locale=locale,
        strings=strings,
        speakers=speakers,
        metadata={
            "generator": "eager i18n",
            "entry_scene": graph.entry or "",
            "total_strings": str(len(strings)),
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
    total_strings = len(template.strings)

    translated_keys: list[str] = []
    untranslated_keys: list[str] = []
    obsolete_keys: list[str] = []

    for key in template.strings:
        val = catalog.strings.get(key)
        if val is not None and val.strip():
            translated_keys.append(key)
        else:
            untranslated_keys.append(key)

    for key in catalog.strings:
        if key not in template.strings:
            obsolete_keys.append(key)

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
