"""Unit tests for composite (layered) asset resolution and validation in eager-runtime."""

from __future__ import annotations

import tempfile
from pathlib import Path

import eager_script

from eager_runtime.assets import (
    AssetReference,
    check_assets,
    resolve_candidate_paths,
)


def test_resolve_candidate_paths_composite():
    """resolve_candidate_paths produces candidates for all constituent layers."""
    ref = AssetReference(
        kind="character",
        identifier="hoshiko/base+uniform+smile",
        line_number=1,
        character_id="hoshiko",
        expression="base+uniform+smile",
    )
    candidates = resolve_candidate_paths(ref)

    assert "hoshiko/base.png" in candidates
    assert "hoshiko/uniform.png" in candidates
    assert "hoshiko/smile.png" in candidates
    assert "characters/hoshiko/base.png" in candidates


def test_resolve_candidate_paths_alias():
    """resolve_candidate_paths expands aliases configured for characters."""
    ref = AssetReference(
        kind="character",
        identifier="hoshiko/happy",
        line_number=1,
        character_id="hoshiko",
        expression="happy",
    )
    char_configs = {
        "hoshiko": {
            "name": "Hoshiko",
            "happy": "base+uniform+smile",
        }
    }
    candidates = resolve_candidate_paths(ref, char_configs)

    assert "hoshiko/base.png" in candidates
    assert "hoshiko/uniform.png" in candidates
    assert "hoshiko/smile.png" in candidates


def test_check_assets_composite_all_present():
    """check_assets passes when all constituent layers exist on disk."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        char_dir = root / "characters" / "hoshiko"
        char_dir.mkdir(parents=True)
        (char_dir / "base.png").write_bytes(b"dummy_png")
        (char_dir / "uniform.png").write_bytes(b"dummy_png")
        (char_dir / "smile.png").write_bytes(b"dummy_png")

        script = """
@character hoshiko "Hoshiko" smile="base+uniform+smile"
label start:
    Hoshiko (smile): Hello!
    ~ show hoshiko base+uniform+smile at center
"""
        items = eager_script.parse(script)
        report = check_assets(items, root, check_unused=True)

        assert len(report.missing) == 0
        assert report.resolved_count == 2
        assert len(report.unused) == 0


def test_check_assets_composite_missing_layer():
    """check_assets identifies specific missing constituent layers."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        char_dir = root / "characters" / "hoshiko"
        char_dir.mkdir(parents=True)
        (char_dir / "base.png").write_bytes(b"dummy_png")
        # uniform.png is deliberately missing
        (char_dir / "smile.png").write_bytes(b"dummy_png")

        script = """
@character hoshiko "Hoshiko" smile="base+uniform+smile"
label start:
    Hoshiko (smile): Hello!
"""
        items = eager_script.parse(script)
        report = check_assets(items, root)

        assert len(report.missing) == 1
        issue = report.missing[0]
        assert "uniform" in issue.message
        assert report.resolved_count == 0
