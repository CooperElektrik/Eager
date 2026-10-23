from pathlib import Path

import pytest

from eager_core.audio import AudioMixer


def test_audio_mixer_path_traversal_protection(tmp_path: Path):
    asset_dir = tmp_path / "game_assets"
    asset_dir.mkdir()
    mixer = AudioMixer(backend=None, asset_dir=asset_dir)

    # Legitimate relative asset should resolve or return path
    legit = mixer._resolve_asset("sound.wav")
    assert legit == "sound.wav"

    # Traversal attempt escaping asset_dir must raise ValueError
    with pytest.raises(ValueError, match="Path traversal detected"):
        mixer._resolve_asset("../../../etc/passwd")
