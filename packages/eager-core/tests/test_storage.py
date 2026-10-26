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


def test_safe_read_json_corrupt_creates_backup(tmp_path: Path):
    corrupt_file = tmp_path / "save_slot_1.json"
    corrupt_content = '{"unclosed_bracket": 123'
    corrupt_file.write_text(corrupt_content, encoding="utf-8")

    expected_bak = tmp_path / "save_slot_1.json.corrupt.bak"
    assert not expected_bak.exists()

    result = safe_read_json(corrupt_file, default={"fallback": True}, backup_corrupt=True)
    assert result == {"fallback": True}

    assert expected_bak.exists()
    assert expected_bak.read_text(encoding="utf-8") == corrupt_content
    assert corrupt_file.read_text(encoding="utf-8") == corrupt_content


def test_safe_read_json_corrupt_without_backup_creates_no_file(tmp_path: Path):
    corrupt_file = tmp_path / "save_slot_2.json"
    corrupt_file.write_text("invalid json!", encoding="utf-8")

    expected_bak = tmp_path / "save_slot_2.json.corrupt.bak"
    result = safe_read_json(corrupt_file, default=None, backup_corrupt=False)
    assert result is None
    assert not expected_bak.exists()


def test_safe_read_json_corrupt_backup_os_error_resilience(tmp_path: Path, monkeypatch):
    corrupt_file = tmp_path / "save_slot_3.json"
    corrupt_file.write_text("{bad json!", encoding="utf-8")

    import shutil

    def mock_copy2_failure(src: object, dst: object):
        raise OSError("Permission denied")

    monkeypatch.setattr(shutil, "copy2", mock_copy2_failure)

    result = safe_read_json(corrupt_file, default="recovered_default", backup_corrupt=True)
    assert result == "recovered_default"


def test_safe_read_json_valid_does_not_create_backup(tmp_path: Path):
    valid_file = tmp_path / "valid.json"
    valid_file.write_text('{"score": 100}', encoding="utf-8")

    result = safe_read_json(valid_file, default=None, backup_corrupt=True)
    assert result == {"score": 100}

    expected_bak = tmp_path / "valid.json.corrupt.bak"
    assert not expected_bak.exists()
