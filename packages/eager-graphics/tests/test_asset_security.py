from pathlib import Path

import pytest

from eager_graphics.renderers.pil.assets import PILAssetResolver
from eager_graphics.renderers.pyglet import PygletAssetResolver


def test_pil_asset_resolver_path_traversal(tmp_path: Path):
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    resolver = PILAssetResolver(asset_dir=asset_dir)

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolver.get_image("../../../secret")


def test_pyglet_asset_resolver_path_traversal(tmp_path: Path):
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    resolver = PygletAssetResolver(asset_dir=asset_dir)

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolver.get_texture("../../../secret")


def test_pyglet_asset_resolver_path_traversal_with_index(tmp_path: Path):
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    resolver = PygletAssetResolver(asset_dir=asset_dir)
    # Populate asset index to ensure traversal check is not bypassed
    resolver._asset_index = {"dummy": asset_dir / "dummy.png"}

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolver.get_texture("../../../secret")

