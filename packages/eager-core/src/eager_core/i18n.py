"""Internationalization and translation catalog primitives."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from eager_core.storage import atomic_write_json, safe_read_json

logger = logging.getLogger(__name__)


@dataclass
class TranslationCatalog:
    """Translation catalog for a specific language locale."""

    locale: str
    strings: dict[str, str] = field(default_factory=dict)
    speakers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)

    def get_text(self, key: str, default: str) -> str:
        """Return translated string if present and non-empty, otherwise default."""
        val = self.strings.get(key)
        if val is not None and val.strip():
            return val
        return default

    def get_speaker(self, speaker: str, default: str | None = None) -> str:
        """Return translated speaker name if present, otherwise default or speaker."""
        fallback = default if default is not None else speaker
        val = self.speakers.get(speaker)
        if val is not None and val.strip():
            return val
        return fallback

    def to_dict(self) -> dict[str, object]:
        """Serialize catalog to dictionary."""
        return {
            "locale": self.locale,
            "metadata": self.metadata,
            "speakers": self.speakers,
            "strings": self.strings,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> TranslationCatalog:
        """Create catalog from dictionary."""
        locale = str(data.get("locale", "default"))
        meta_raw = data.get("metadata")
        meta = {str(k): str(v) for k, v in cast(Mapping[object, object], meta_raw).items()} if isinstance(meta_raw, Mapping) else {}
        speakers_raw = data.get("speakers")
        speakers = {str(k): str(v) for k, v in cast(Mapping[object, object], speakers_raw).items()} if isinstance(speakers_raw, Mapping) else {}
        strings_raw = data.get("strings")
        strings = {str(k): str(v) for k, v in cast(Mapping[object, object], strings_raw).items()} if isinstance(strings_raw, Mapping) else {}
        return cls(locale=locale, strings=strings, speakers=speakers, metadata=meta)

    def save_json(self, path: Path | str) -> None:
        """Save catalog atomically to a JSON file."""
        atomic_write_json(Path(path), self.to_dict())

    @classmethod
    def load_json(cls, path: Path | str) -> TranslationCatalog:
        """Load catalog from a JSON file."""
        data = safe_read_json(Path(path), default={})
        if not isinstance(data, Mapping):
            return cls(locale=Path(path).stem)
        dict_data: dict[str, object] = {str(k): v for k, v in cast(Mapping[object, object], data).items()}
        if "locale" not in dict_data:
            dict_data["locale"] = Path(path).stem
        return cls.from_dict(dict_data)


class TranslationManager:
    """Manages loaded translation catalogs and active locale resolution."""

    def __init__(self, default_locale: str = "default") -> None:
        self.catalogs: dict[str, TranslationCatalog] = {}
        self.active_locale: str = default_locale
        self.fallback_locale: str = default_locale

    def register_catalog(self, catalog: TranslationCatalog) -> None:
        """Register or replace a translation catalog."""
        self.catalogs[catalog.locale.lower()] = catalog

    def load_directory(self, locales_dir: Path | str) -> list[str]:
        """Scan a directory for JSON translation catalogs and load them."""
        p = Path(locales_dir)
        loaded: list[str] = []
        if not p.is_dir():
            return loaded

        for file_path in p.glob("*.json"):
            if file_path.name.startswith((".", "template")):
                continue
            try:
                catalog = TranslationCatalog.load_json(file_path)
                self.register_catalog(catalog)
                loaded.append(catalog.locale.lower())
                logger.debug("Loaded translation catalog %r from %s", catalog.locale, file_path)
            except Exception:
                logger.warning("Failed to load translation catalog %s", file_path, exc_info=True)
        return loaded

    def set_locale(self, locale: str) -> None:
        """Set active locale for translations."""
        self.active_locale = locale.lower()

    def translate(self, key: str, default: str) -> str:
        """Translate string key with fallback to fallback_locale then source default."""
        if self.active_locale in self.catalogs:
            cat = self.catalogs[self.active_locale]
            val = cat.get_text(key, default)
            if val != default:
                logger.debug("Translation key %r resolved in locale %r", key, self.active_locale)
                return val

        if (
            self.fallback_locale != self.active_locale
            and self.fallback_locale in self.catalogs
        ):
            cat = self.catalogs[self.fallback_locale]
            val = cat.get_text(key, default)
            if val != default:
                logger.debug("Translation fallback to %r for key %r", self.fallback_locale, key)
                return val

        logger.debug("Translation key %r not found in any catalog, returning default", key)
        return default

    def translate_speaker(self, speaker: str) -> str:
        """Translate speaker name with fallback to source speaker."""
        if self.active_locale in self.catalogs:
            cat = self.catalogs[self.active_locale]
            return cat.get_speaker(speaker)

        if (
            self.fallback_locale != self.active_locale
            and self.fallback_locale in self.catalogs
        ):
            cat = self.catalogs[self.fallback_locale]
            return cat.get_speaker(speaker)

        return speaker

    def available_locales(self) -> list[str]:
        """Return sorted list of registered locale codes."""
        locales = set(self.catalogs.keys())
        locales.add("default")
        return sorted(locales)
