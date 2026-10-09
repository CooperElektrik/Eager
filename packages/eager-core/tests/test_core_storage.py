from pathlib import Path

from eager_core.storage import atomic_write_json, get_default_save_dir, safe_read_json


def test_atomic_write_and_safe_read(tmp_path: Path):
    target = tmp_path / "sub" / "data.json"
    data = {"score": 42, "items": ["sword", "shield"]}

    atomic_write_json(target, data)
    assert target.exists()

    loaded = safe_read_json(target)
    assert loaded == data


def test_safe_read_missing_or_corrupt(tmp_path: Path):
    missing = tmp_path / "missing.json"
    assert safe_read_json(missing, default={"empty": True}) == {"empty": True}

    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{bad json!", encoding="utf-8")
    assert safe_read_json(corrupt, default=None) is None


def test_get_default_save_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    save_dir = get_default_save_dir("my_game")
    assert save_dir == tmp_path / "eager" / "my_game"
    assert save_dir.is_dir()
