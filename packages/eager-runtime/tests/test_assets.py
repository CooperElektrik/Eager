"""Tests for asset validation and consistency linter."""

from __future__ import annotations

import argparse
from pathlib import Path

import eager_script
import pytest

from eager_runtime.assets import check_assets, extract_asset_references
from eager_runtime.cli import _cmd_check


def test_extract_asset_references() -> None:
    text = """
@character hero "Hero" asset_prefix=hero_spr default_expression=idle
## Scene --- start
~ bg classroom_day
~ show hero smile at center
Hero (happy): Good morning!
Narrator: Just narration.
~ play bgm theme_song
Hero: {voice:hero_01.ogg} Let's head out.
~ image banner logo_img
"""
    items = eager_script.parse(text)
    graph = eager_script.to_graph(items)
    refs, char_configs = extract_asset_references(graph)

    assert "hero" in char_configs
    assert char_configs["hero"]["asset_prefix"] == "hero_spr"

    kinds = [r.kind for r in refs]
    assert kinds == ["background", "character", "character", "audio", "voice", "image"]

    assert refs[0].identifier == "classroom_day"
    assert refs[1].character_id == "hero"
    assert refs[1].expression == "smile"
    assert refs[2].character_id == "hero"
    assert refs[2].expression == "happy"
    assert refs[3].identifier == "theme_song"
    assert refs[4].identifier == "hero_01.ogg"
    assert refs[5].identifier == "logo_img"


def test_check_assets_all_resolved(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    (asset_dir / "bg").mkdir()
    (asset_dir / "bg" / "school.png").write_text("fake_png")
    (asset_dir / "characters").mkdir()
    (asset_dir / "characters" / "alice_smile.png").write_text("fake_png")
    (asset_dir / "audio").mkdir()
    (asset_dir / "audio" / "theme.ogg").write_text("fake_ogg")

    text = """
## Intro --- intro
~ bg school
~ show alice smile
~ play bgm theme
"""
    graph = eager_script.parse_graph(text)
    report = check_assets(graph, asset_dir)

    assert report.is_valid
    assert report.total_references == 3
    assert report.resolved_count == 3
    assert len(report.missing) == 0


def test_check_assets_missing_assets(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()

    text = """
## Intro --- intro
~ bg missing_school
~ show alice missing_expr
Alice (crying): Oh no!
~ play sfx missing_sound
"""
    graph = eager_script.parse_graph(text)
    report = check_assets(graph, asset_dir)

    assert not report.is_valid
    assert report.total_references == 4
    assert report.resolved_count == 0
    assert len(report.missing) == 4

    missing_kinds = [m.reference.kind for m in report.missing]
    assert "background" in missing_kinds
    assert "character" in missing_kinds
    assert "audio" in missing_kinds


def test_check_assets_with_prefix(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    (asset_dir / "hoshiko_swim_smile.png").write_text("data")

    text = """
@character hoshiko "Hoshiko" asset_prefix=hoshiko_swim
## Detour --- detour
~ show hoshiko smile
Hoshiko (smile): Hello!
"""
    graph = eager_script.parse_graph(text)
    report = check_assets(graph, asset_dir)

    assert report.is_valid
    assert report.resolved_count == 2
    assert len(report.missing) == 0


def test_check_assets_unused_detection(tmp_path: Path) -> None:
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    (asset_dir / "used.png").write_text("used")
    (asset_dir / "extra.png").write_text("extra")

    text = """
## Scene --- s1
~ bg used
"""
    graph = eager_script.parse_graph(text)
    report = check_assets(graph, asset_dir, check_unused=True)

    assert report.is_valid
    assert report.resolved_count == 1
    assert "extra.png" in report.unused
    assert "used.png" not in report.unused


def test_check_assets_nonexistent_directory(tmp_path: Path) -> None:
    text = """
## Scene --- s1
~ bg classroom
"""
    graph = eager_script.parse_graph(text)
    non_existent = tmp_path / "does_not_exist"
    report = check_assets(graph, non_existent)

    assert not report.is_valid
    assert len(report.missing) == 1
    assert "does not exist" in report.missing[0].message


def test_cli_check_command_assets(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script_file = tmp_path / "main.es"
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    (asset_dir / "classroom.png").write_text("fake")

    script_file.write_text(
        """
## Start --- start
~ bg classroom
Narrator: All good.
""",
        encoding="utf-8",
    )

    args = argparse.Namespace(
        script=str(script_file),
        assets=True,
        asset_dir=str(asset_dir),
    )
    exit_code = _cmd_check(args)
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Script validation PASSED" in captured.out
    assert "All referenced assets resolved successfully" in captured.out
