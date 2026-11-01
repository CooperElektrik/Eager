"""Unit and integration tests for composite (layered) sprites."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from eager_core.events import DialogueEvent
from PIL import Image

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import CharacterConfig, StageDirector
from eager_graphics.renderers.pil import PILAssetResolver, PILRenderer
from eager_graphics.renderers.pyglet import PygletAssetResolver


@pytest.fixture
def temp_character_assets():
    """Create temporary layered character sprite PNGs."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        char_dir = root / "characters" / "hoshiko"
        char_dir.mkdir(parents=True)

        # 1. Base layer (100x100 solid blue with full opacity)
        base = Image.new("RGBA", (100, 100), (0, 0, 255, 255))
        base.save(char_dir / "base.png")

        # 2. Uniform layer (100x100 half-transparent green over bottom half)
        uniform = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for y in range(50, 100):
            for x in range(100):
                uniform.putpixel((x, y), (0, 255, 0, 200))
        uniform.save(char_dir / "uniform.png")

        # 3. Smile layer (100x100 red dot in center)
        smile = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for y in range(40, 50):
            for x in range(40, 50):
                smile.putpixel((x, y), (255, 0, 0, 255))
        smile.save(char_dir / "smile.png")

        # 4. Small overlay layer (50x50 yellow patch, smaller size)
        small_patch = Image.new("RGBA", (50, 50), (255, 255, 0, 180))
        small_patch.save(char_dir / "patch.png")

        yield root


def test_pil_asset_resolver_composite_layers(temp_character_assets: Path):
    """PILAssetResolver flattens constituent layers and caches under the composite asset ID."""
    resolver = PILAssetResolver(asset_dir=temp_character_assets)
    asset_id = "hoshiko/base+uniform+smile"

    img = resolver.get_image(asset_id)
    assert img.size == (100, 100)
    assert asset_id in resolver._image_cache

    # Base pixel at (10, 10) untouched by upper layers -> blue
    assert img.getpixel((10, 10)) == (0, 0, 255, 255)

    # Smile pixel at (45, 45) -> red
    assert img.getpixel((45, 45)) == (255, 0, 0, 255)

    # Cache hit returns exact same instance
    cached_img = resolver.get_image(asset_id)
    assert cached_img is img


def test_pil_asset_resolver_size_mismatch_compositing(temp_character_assets: Path):
    """PILAssetResolver safely normalizes and composites layers with different dimensions."""
    resolver = PILAssetResolver(asset_dir=temp_character_assets)
    asset_id = "hoshiko/base+patch"

    img = resolver.get_image(asset_id)
    assert img.size == (100, 100)
    # Patch covers top-left 50x50
    patch_px = img.getpixel((25, 25))
    assert patch_px[0] > 0  # Red channel blended in from yellow
    assert patch_px[1] > 0  # Green channel blended in from yellow


def test_pil_asset_resolver_placeholder_composite():
    """PILAssetResolver procedurally composites layers when files are missing on disk."""
    resolver = PILAssetResolver(asset_dir=None)
    asset_id = "unknown_char/layer1+layer2"

    img = resolver.get_image(asset_id)
    assert img.size == (400, 800)
    assert asset_id in resolver._image_cache


def test_pyglet_asset_resolver_composite_layers(temp_character_assets: Path):
    """PygletAssetResolver loads and composites layers into a single hardware texture."""
    resolver = PygletAssetResolver(asset_dir=temp_character_assets)
    asset_id = "hoshiko/base+uniform+smile"

    tex = resolver.get_texture(asset_id)
    assert tex is not None
    assert asset_id in resolver._cache

    cached_tex = resolver.get_texture(asset_id)
    assert cached_tex is tex


def test_character_config_expression_resolution():
    """CharacterConfig resolves direct aliases, comma-separated, and nested layers."""
    cfg = CharacterConfig(
        character_id="hoshiko",
        expressions={
            "happy": "base+uniform+eyes_happy+mouth_open",
            "blush": "cheeks_blush",
            "outfit": "base+uniform",
        },
    )

    # Direct alias
    assert cfg.resolve_expression("happy") == "base+uniform+eyes_happy+mouth_open"

    # Unmapped expression
    assert cfg.resolve_expression("angry") == "angry"

    # Delimited combinations with alias expansion
    assert (
        cfg.resolve_expression("happy+blush")
        == "base+uniform+eyes_happy+mouth_open+cheeks_blush"
    )

    # Comma-delimited syntax in screenplay dialogue tags
    assert (
        cfg.resolve_expression("outfit, blush")
        == "base+uniform+cheeks_blush"
    )


def test_stage_director_composite_aliases(temp_character_assets: Path):
    """StageDirector automatically expands aliases in show, expr, and dialogue events."""
    compositor = StageCompositor(virtual_width=1920, virtual_height=1080)
    director = StageDirector(compositor=compositor)

    director.register_character(
        "hoshiko",
        name="Hoshiko",
        smile="base+uniform+smile",
        embarrassed="base+uniform+blush",
    )

    # 1. handle_show with alias
    director.handle_show("hoshiko smile at center")
    char_layer = compositor.stage.get_layer("characters")
    assert char_layer is not None
    elem = char_layer.get_element("hoshiko")
    assert elem is not None
    assert elem.asset_id == "hoshiko/base+uniform+smile"

    # 2. handle_expr with alias
    director.handle_expr("hoshiko embarrassed")
    assert elem.asset_id == "hoshiko/base+uniform+blush"

    # 3. handle_dialogue_event with speaker display name and emotion alias
    director.handle_dialogue_event(
        DialogueEvent(
            speaker="Hoshiko",
            text="Hello world!",
            voice=None,
            emotion="smile",
            line_number=1,
        )
    )
    assert elem.asset_id == "hoshiko/base+uniform+smile"


def test_pil_renderer_renders_composite_sprite(temp_character_assets: Path):
    """End-to-end integration: composite sprite renders through PILRenderer cleanly."""
    compositor = StageCompositor(virtual_width=1920, virtual_height=1080)
    director = StageDirector(compositor=compositor)
    renderer = PILRenderer(
        width=1920,
        height=1080,
        asset_dir=temp_character_assets,
    )

    director.register_character("hoshiko", smile="base+uniform+smile")
    director.handle_show("hoshiko smile at center")
    director.finish_animations()

    # Render frame
    frame = renderer.render_compositor(compositor, 1920, 1080)
    assert isinstance(frame, Image.Image)
    assert frame.size == (1920, 1080)
    assert "hoshiko/base+uniform+smile" in renderer.asset_resolver._image_cache
