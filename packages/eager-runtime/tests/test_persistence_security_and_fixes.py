import argparse
from pathlib import Path

import pytest
from eager_core.events import AppendEvent, ChoiceOption, DialogueEvent, SceneEnterEvent
from eager_script import parse_graph

from eager_runtime.cli import _cmd_build
from eager_runtime.headless import NullStage
from eager_runtime.persistent import PersistentData
from eager_runtime.project import resolve_project_scripts
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_runtime.state import StorySnapshot


def test_persistent_variable_mutation_and_rollback_isolation(tmp_path: Path):
    script = """
## Start --- start
$ persistent.coins = 10
$ persistent.coins += 5
$ normal_coins = 100
Narrator: Coins: [persistent.coins] and normal: [normal_coins]
@if persistent.coins > 10
    Narrator: Rich!
@else
    Narrator: Poor!
@end
"""
    p_file = tmp_path / "persistent.json"
    p_data = PersistentData(p_file)

    graph = parse_graph(script)
    vm = StoryVM(graph, persistent=p_data)

    # Step past scene enter and sets to dialogue
    enter_ev = vm.step()
    assert isinstance(enter_ev, SceneEnterEvent)
    assert enter_ev.type == "scene_enter"
    ev = vm.step()
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Coins: 15 and normal: 100"

    # Verify persistent object directly mutated
    assert p_data["coins"] == 15
    assert p_data.coins == 15
    assert "persistent.coins" not in vm.variables
    assert vm.get_variable("persistent.coins") == 15

    # Checkpoint save
    snap = vm.save()
    assert "persistent" not in snap.variables
    assert "persistent.coins" not in snap.variables
    assert snap.variables.get("normal_coins") == 100

    # Step to next beat inside if branch
    ev2 = vm.step()
    assert isinstance(ev2, DialogueEvent)
    assert ev2.text == "Rich!"

    # Now mutate persistent and mutate normal_coins
    vm.set_variable("persistent.coins", 999)
    vm.set_variable("normal_coins", 0)
    assert p_data.coins == 999
    assert vm.get_variable("normal_coins") == 0

    # Restore snapshot (rollback)
    vm.load(snap)
    # normal_coins should be restored, but persistent.coins must NOT be rolled back
    assert vm.get_variable("normal_coins") == 100
    assert vm.get_variable("persistent.coins") == 999
    assert p_data.coins == 999


def test_default_expression_with_persistent(tmp_path: Path):
    script = """
@default bonus = persistent.starting_bonus or 42

## Start --- start
Narrator: Bonus is [bonus].
"""
    proj_dir = tmp_path / "game"
    proj_dir.mkdir()
    (proj_dir / "main.es").write_text(script, encoding="utf-8")

    # Persistent has starting_bonus = 100
    p_file = proj_dir / "persistent.json"
    p = PersistentData(p_file)
    p.starting_bonus = 100
    p.save()

    session = GameSession(proj_dir / "main.es", save_dir=proj_dir)
    ev = session.advance()
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Bonus is 100."


def test_resolve_project_scripts_include_traversal(tmp_path: Path):
    outside = tmp_path / "outside.es"
    outside.write_text("## Secret --- secret\nNarrator: secret.\n", encoding="utf-8")

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    main = proj_dir / "main.es"
    main.write_text('@include "../outside.es"\n## Main --- main\nNarrator: Hello.\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolve_project_scripts(main)


def test_resolve_project_scripts_deterministic_and_entry_script(tmp_path: Path):
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "game.toml").write_text('[game]\nentry_script = "ch1.es"\n', encoding="utf-8")
    (proj_dir / "ch2.es").write_text("## SceneB --- scene_b\nNarrator: B.\n", encoding="utf-8")
    (proj_dir / "ch1.es").write_text("## SceneA --- scene_a\nNarrator: A.\n", encoding="utf-8")
    (proj_dir / "ch3.es").write_text("## SceneC --- scene_c\nNarrator: C.\n", encoding="utf-8")

    scripts = resolve_project_scripts(proj_dir)
    # ch1.es must be first (configured entry_script), followed by ch2.es and ch3.es sorted
    assert [s.name for s in scripts] == ["ch1.es", "ch2.es", "ch3.es"]


def test_resolve_project_scripts_symlink_traversal(tmp_path: Path):
    outside = tmp_path / "outside.es"
    outside.write_text("## Secret --- secret\nNarrator: secret.\n", encoding="utf-8")

    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    symlink = proj_dir / "symlink.es"
    try:
        symlink.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks not supported in environment")

    with pytest.raises(ValueError, match="Path traversal detected"):
        resolve_project_scripts(proj_dir)



def test_story_snapshot_non_monotonic_migration():
    StorySnapshot.clear_migrations()

    # Register buggy migration that doesn't advance version
    def bad_migration(data):
        return data  # version remains 1

    StorySnapshot.register_migration(1, bad_migration)

    with pytest.raises(ValueError, match="monotonically"):
        StorySnapshot.from_dict({"version": 1}, target_version=2)

    StorySnapshot.clear_migrations()


def test_null_stage_on_append():
    stage = NullStage()
    stage.ui_state.text = "Hello"
    stage.ui_state.choices = [ChoiceOption(index=0, text="Option A"), ChoiceOption(index=1, text="Option B")]

    stage._on_append(AppendEvent(text="world!", line_number=1))
    assert stage.ui_state.text == "Hello world!"
    assert stage.ui_state.choices == []


def test_cmd_build_excludes_output_zip(tmp_path: Path):
    proj_dir = tmp_path / "my_project"
    proj_dir.mkdir()
    (proj_dir / "game.toml").write_text('[game]\ntitle = "Test"\n', encoding="utf-8")
    (proj_dir / "main.es").write_text("## Start --- start\nNarrator: Test.\n", encoding="utf-8")

    out_zip = proj_dir / "dist.zip"
    args = argparse.Namespace(project_dir=str(proj_dir), output=str(out_zip))
    res = _cmd_build(args)
    assert res == 0
    assert out_zip.exists()

    import zipfile
    with zipfile.ZipFile(out_zip, "r") as zf:
        names = zf.namelist()
        assert "dist.zip" not in names
        assert "main.es" in names
        assert "game.toml" in names
