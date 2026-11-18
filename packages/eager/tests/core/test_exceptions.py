"""Tests for eager.core custom domain exceptions and backward compatibility."""

import pytest

from eager.core.audio import AudioMixer
from eager.core.exceptions import (
    AudioError,
    ColorParseError,
    EagerCoreError,
    StorageError,
)
from eager.core.storage import atomic_write_json
from eager.core.types import Color


def test_exception_inheritance_hierarchy():
    assert issubclass(AudioError, EagerCoreError)
    assert not issubclass(AudioError, ValueError)

    assert issubclass(ColorParseError, EagerCoreError)
    assert not issubclass(ColorParseError, ValueError)

    assert issubclass(StorageError, EagerCoreError)
    assert not issubclass(StorageError, OSError)


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


def test_storage_error_on_non_serializable(tmp_path):
    target = tmp_path / "bad.json"
    with pytest.raises(StorageError, match="Failed to serialize data"):
        atomic_write_json(target, object())
