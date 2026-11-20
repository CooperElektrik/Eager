"""Regression tests for eager-script-lsp feature provider fixes."""

from __future__ import annotations

from pathlib import Path

from lsprotocol.types import Position, TextEdit

from eager_script_lsp.features.completion import compute_completions
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.features.navigation import compute_document_symbols, compute_references
from eager_script_lsp.features.tokens import compute_folding_ranges
from eager_script_lsp.workspace import WorkspaceIndex


def test_document_symbols_scene_ranges_duplicate_ids_and_var_roles(tmp_path: Path) -> None:
    text = (
        "@default hp = 10\n"
        "@default max_hp = hp\n"
        "## Scene One --- one\n"
        "$ hp = max_hp + 1\n"
        "## Scene One --- one\n"
        "Alice: Second\n"
    )
    ws = WorkspaceIndex(tmp_path)
    ws.asset_index.scan_assets(tmp_path / "assets")
    doc = ws.update_document((tmp_path / "main.es").as_uri(), text)
    syms = compute_document_symbols(doc)

    # Preamble only lists 'def' variables ($hp), not read RHS 'max_hp' wait:
    # Line 1: @default hp = 10 (def), Line 2: @default max_hp = hp (def=max_hp, read=hp)
    preamble = next(s for s in syms if s.name == "Preamble")
    preamble_names = [c.name for c in (preamble.children or [])]
    assert preamble_names == ["$hp", "$max_hp"]

    scenes = [s for s in syms if s.name == "Scene One"]
    assert len(scenes) == 2
    # First scene ends before line 4 (second scene starts at line 4)
    assert scenes[0].range.start.line == 2
    assert scenes[0].range.end.line == 3
    # selection_range must lie inside range even for duplicate scene IDs
    assert scenes[0].range.start.line <= scenes[0].selection_range.start.line <= scenes[0].range.end.line
    assert scenes[1].range.start.line <= scenes[1].selection_range.start.line <= scenes[1].range.end.line

    # Scene 1 children only include written variable $hp, not read $max_hp
    s1_vars = [c.name for c in (scenes[0].children or [])]
    assert s1_vars == ["$hp"]


def test_references_character_name_display_speaker_and_hook_arg(tmp_path: Path) -> None:
    text = (
        '@character alice "Alice Wonderland"\n'
        "## Start --- start\n"
        "~ show alice happy\n"
        "Alice Wonderland: Hi!\n"
    )
    ws = WorkspaceIndex(tmp_path)
    uri = (tmp_path / "main.es").as_uri()
    doc = ws.update_document(uri, text)

    # Cursor on "Alice Wonderland" in @character definition (line 0, col 19)
    locs_name = compute_references(doc, ws, Position(line=0, character=19), include_declaration=True)
    assert len(locs_name) >= 2

    # Cursor on "alice" in `~ show alice happy` (line 2, col 8)
    locs_hook = compute_references(doc, ws, Position(line=2, character=8), include_declaration=True)
    assert len(locs_hook) >= 2

    # Cursor on display name speaker `Alice Wonderland:` (line 3, col 2)
    locs_spk = compute_references(doc, ws, Position(line=3, character=2), include_declaration=True)
    assert len(locs_spk) >= 2


def test_completions_text_edit_for_tags_vars_and_speaker_display_name(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets" / "characters" / "alice"
    assets_dir.mkdir(parents=True)
    (assets_dir / "happy.png").write_bytes(b"PNG")
    (tmp_path / "assets" / "voice").mkdir(parents=True)
    (tmp_path / "assets" / "voice" / "intro.ogg").write_bytes(b"OGG")

    text = (
        '@character alice "Alice Wonderland"\n'
        "@default gold = 10\n"
        "## Start --- start\n"
        "Alice Wonderland (ha\n"
        "Alice: {vo\n"
        "Alice: [go\n"
    )
    ws = WorkspaceIndex(tmp_path)
    ws.asset_index.scan_assets(tmp_path / "assets")
    doc = ws.update_document((tmp_path / "main.es").as_uri(), text)

    # Emotion completion resolves display name "Alice Wonderland" -> "alice"
    emo_res = compute_completions(doc, ws, Position(line=3, character=20))
    assert any(it.label == "happy" for it in emo_res.items)

    # {vo completion uses TextEdit starting at '{' so it doesn't produce '{{voice:...}'
    tag_res = compute_completions(doc, ws, Position(line=4, character=10))
    voice_item = next(it for it in tag_res.items if it.label == "voice:intro")
    assert isinstance(voice_item.text_edit, TextEdit)
    assert voice_item.text_edit.range.start.character == 7
    assert voice_item.text_edit.new_text == "{voice:intro}"

    # [go completion uses TextEdit starting at '[' so it doesn't produce '[[gold]'
    var_res = compute_completions(doc, ws, Position(line=5, character=10))
    gold_item = next(it for it in var_res.items if it.label == "gold")
    assert isinstance(gold_item.text_edit, TextEdit)
    assert gold_item.text_edit.range.start.character == 7
    assert gold_item.text_edit.new_text == "[gold]"


def test_cross_file_character_assets_in_diagnostics(tmp_path: Path) -> None:
    char_dir = tmp_path / "assets" / "characters" / "hero_sprite"
    char_dir.mkdir(parents=True)
    (char_dir / "default.png").write_bytes(b"PNG")

    ws = WorkspaceIndex(tmp_path)
    ws.update_document(
        (tmp_path / "chars.es").as_uri(),
        '@character hero "Hero" asset_prefix="hero_sprite"\n',
    )
    doc2 = ws.update_document(
        (tmp_path / "scene.es").as_uri(),
        "## Start --- start\n~ show hero default\nHero: Hi\n",
    )
    diags = compute_diagnostics(doc2, ws, check_disk_assets=True)
    assert not any("Missing" in d.message or "hero" in d.message.lower() for d in diags)


def test_two_space_indented_choice_folding(tmp_path: Path) -> None:
    text = "## Start --- start\n? Option A\n  Alice: Line 1\n  Alice: Line 2\nAlice: After\n"
    ws = WorkspaceIndex(tmp_path)
    ws.asset_index.scan_assets(tmp_path / "assets")
    doc = ws.update_document((tmp_path / "main.es").as_uri(), text)
    folds = compute_folding_ranges(doc)
    assert any(f.start_line == 1 and f.end_line == 3 for f in folds)
