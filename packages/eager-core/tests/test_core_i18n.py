"""Unit tests for internationalization catalog and manager primitives."""

from __future__ import annotations

from pathlib import Path

from eager_core.i18n import TranslationCatalog, TranslationManager


def test_translation_catalog_get_text_fallback() -> None:
    cat = TranslationCatalog(
        locale="es",
        strings={"scene.0": "Hola, mundo!", "scene.1": ""},
        speakers={"Alice": "Alicia"},
    )

    assert cat.get_text("scene.0", "Hello, world!") == "Hola, mundo!"
    # Empty string falls back to default
    assert cat.get_text("scene.1", "Default text") == "Default text"
    # Missing key falls back to default
    assert cat.get_text("scene.2", "Default text") == "Default text"

    assert cat.get_speaker("Alice") == "Alicia"
    assert cat.get_speaker("Bob") == "Bob"


def test_translation_catalog_serialization(tmp_path: Path) -> None:
    cat = TranslationCatalog(
        locale="es",
        strings={"intro.0": "Bienvenido"},
        speakers={"Narrator": "Narrador"},
        metadata={"author": "Translator"},
    )

    file_path = tmp_path / "es.json"
    cat.save_json(file_path)

    loaded = TranslationCatalog.load_json(file_path)
    assert loaded.locale == "es"
    assert loaded.strings["intro.0"] == "Bienvenido"
    assert loaded.speakers["Narrator"] == "Narrador"
    assert loaded.metadata["author"] == "Translator"


def test_translation_manager_resolution() -> None:
    tm = TranslationManager()
    cat_es = TranslationCatalog(
        locale="es",
        strings={"start.0": "Hola", "start.1": "Amigo"},
        speakers={"Hero": "Héroe"},
    )
    cat_ja = TranslationCatalog(
        locale="ja",
        strings={"start.0": "こんにちは"},
    )
    tm.register_catalog(cat_es)
    tm.register_catalog(cat_ja)

    assert tm.available_locales() == ["default", "es", "ja"]

    # In default locale, returns default text
    tm.set_locale("default")
    assert tm.translate("start.0", "Hello") == "Hello"
    assert tm.translate_speaker("Hero") == "Hero"

    # In es locale, returns Spanish
    tm.set_locale("es")
    assert tm.translate("start.0", "Hello") == "Hola"
    assert tm.translate_speaker("Hero") == "Héroe"

    # In ja locale, start.0 is translated, start.1 falls back to default
    tm.set_locale("ja")
    assert tm.translate("start.0", "Hello") == "こんにちは"
    assert tm.translate("start.1", "Friend") == "Friend"


def test_translation_manager_load_directory(tmp_path: Path) -> None:
    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()

    cat_fr = TranslationCatalog(locale="fr", strings={"s.0": "Bonjour"})
    cat_fr.save_json(locales_dir / "fr.json")

    # Template file should be ignored
    template = TranslationCatalog(locale="template", strings={"s.0": "Hello"})
    template.save_json(locales_dir / "template.json")

    tm = TranslationManager()
    loaded = tm.load_directory(locales_dir)
    assert loaded == ["fr"]
    assert "fr" in tm.available_locales()

    tm.set_locale("fr")
    assert tm.translate("s.0", "Hello") == "Bonjour"
