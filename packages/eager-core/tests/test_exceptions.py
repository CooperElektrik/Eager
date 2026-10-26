"""Tests for eager_core custom domain exceptions and backward compatibility."""

import pytest

from eager_core.audio import AudioMixer
from eager_core.exceptions import (
    AudioError,
    ColorParseError,
    EagerCoreError,
    I18nError,
    StorageError,
)
from eager_core.i18n import TranslationCatalog, TranslationManager
from eager_core.storage import atomic_write_json
from eager_core.types import Color


def test_exception_inheritance_hierarchy():
    assert issubclass(AudioError, EagerCoreError)
    assert issubclass(AudioError, ValueError)

    assert issubclass(ColorParseError, EagerCoreError)
    assert issubclass(ColorParseError, ValueError)

    assert issubclass(StorageError, EagerCoreError)
    assert issubclass(StorageError, OSError)

    assert issubclass(I18nError, EagerCoreError)
    assert issubclass(I18nError, ValueError)


def test_exception_instantiation_with_informative_context():
    err = ColorParseError("Malformed hex code", raw_value="#XYZ123")
    assert "Malformed hex code" in str(err)
    assert getattr(err, "raw_value", None) == "#XYZ123"

    audio_err = AudioError("Failed to play track", channel="bgm", track_id="intro.ogg")
    assert "Failed to play track" in str(audio_err)
    assert getattr(audio_err, "channel", None) == "bgm"
    assert getattr(audio_err, "track_id", None) == "intro.ogg"


def test_exception_cause_chaining():
    original = FileNotFoundError("save_01.json not found")
    try:
        raise StorageError("Could not load save") from original
    except StorageError as exc:
        assert exc.__cause__ is original


def test_audio_error_on_path_traversal(tmp_path):
    mixer = AudioMixer(backend=None, asset_dir=tmp_path)
    with pytest.raises(AudioError, match="Path traversal detected"):
        mixer._resolve_asset("../outside.wav")


def test_color_parse_error_on_invalid_hex():
    with pytest.raises(ColorParseError, match="Invalid hex color string"):
        Color.from_hex("invalid-color")

    # Verify backward compatibility with ValueError
    with pytest.raises(ValueError):
        Color.from_hex("invalid-color")


def test_storage_error_on_non_serializable(tmp_path):
    target = tmp_path / "bad.json"
    with pytest.raises(StorageError, match="Failed to serialize data"):
        atomic_write_json(target, object())


def test_i18n_error_on_empty_locale():
    mgr = TranslationManager()
    with pytest.raises(I18nError, match="Locale cannot be empty"):
        mgr.set_locale("")

    with pytest.raises(I18nError, match="Expected mapping"):
        TranslationCatalog.from_dict("not_a_mapping")  # type: ignore[arg-type]
