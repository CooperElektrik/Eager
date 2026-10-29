"""Tests for script hot-reloading, state reconciliation, and file watching."""

from __future__ import annotations

import time
from pathlib import Path

import eager_script
from eager_core.input import InputAction

from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_runtime.watcher import FileWatcher


def test_story_vm_hot_reload_capping_beat_index() -> None:
    """StoryVM should cap beat_index to len(new_scene.body) - 1 if current_scene still exists."""
    script_v1 = """
## Start --- intro
Narrator: Line 1
Narrator: Line 2
Narrator: Line 3
Narrator: Line 4
"""
    graph_v1 = eager_script.parse_graph(script_v1)
    vm = StoryVM(graph_v1)

    # Step through 3 beats: entering scene + 2 lines of dialogue
    vm.step()  # enter intro
    vm.step()  # Line 1 (beat_index becomes 1)
    vm.step()  # Line 2 (beat_index becomes 2)
    assert vm.current_scene_id == "intro"
    assert vm.beat_index == 2
    vm.set_variable("score", 100)

    # Version 2 has only 2 lines in body (index 0 and 1)
    script_v2 = """
## Start --- intro
Narrator: Only Line 1
Narrator: Only Line 2
"""
    graph_v2 = eager_script.parse_graph(script_v2)

    # Hot reload
    success = vm.hot_reload(graph_v2)
    assert success is True
    assert vm.graph is graph_v2
    assert vm.current_scene_id == "intro"
    # beat_index was 2, now capped to len(body) - 1 = 2 - 1 = 1
    assert vm.beat_index == 1
    # variables preserved
    assert vm.variables["score"] == 100


def test_story_vm_hot_reload_deleted_scene_jumps_to_entry() -> None:
    """If current scene was deleted, hot_reload should jump to entry node."""
    script_v1 = """
## Scene A --- a
Narrator: In scene A
-> b

## Scene B --- b
Narrator: In scene B
"""
    graph_v1 = eager_script.parse_graph(script_v1)
    vm = StoryVM(graph_v1)
    vm.jump("b")
    assert vm.current_scene_id == "b"

    # Version 2 deletes scene B
    script_v2 = """
## Scene A --- a
Narrator: In scene A only
"""
    graph_v2 = eager_script.parse_graph(script_v2)
    success = vm.hot_reload(graph_v2)
    assert success is True
    # Gracefully jumped to entry node 'a'
    assert vm.current_scene_id == "a"
    assert vm.beat_index == 0


def test_story_vm_hot_reload_deleted_scene_no_entry() -> None:
    """If current scene was deleted and no entry exists, hot_reload gracefully clears scene."""
    script_v1 = """
## Scene B --- b
Narrator: In scene B
"""
    graph_v1 = eager_script.parse_graph(script_v1)
    vm = StoryVM(graph_v1)
    vm.jump("b")

    # Empty graph
    graph_v2 = eager_script.parse_graph("")
    success = vm.hot_reload(graph_v2)
    assert success is False
    assert vm.current_scene_id is None
    assert vm.beat_index == 0


def test_file_watcher_modification_detection(tmp_path: Path) -> None:
    """FileWatcher should detect changes when a file is modified."""
    test_file = tmp_path / "story.es"
    test_file.write_text("## Start --- start\nNarrator: Hello\n", encoding="utf-8")

    notified = False

    def on_change() -> None:
        nonlocal notified
        notified = True

    watcher = FileWatcher(test_file, interval=0.01, on_change=on_change)
    # First check without modifications should be False
    assert watcher.check_modified(force=True) is False

    # Modify file timestamp & content
    time.sleep(0.05)
    test_file.write_text("## Start --- start\nNarrator: Updated!\n", encoding="utf-8")

    # Should detect modification
    assert watcher.check_modified(force=True) is True
    assert notified is True

    # Immediate second check should be False
    assert watcher.check_modified(force=True) is False


def test_game_session_hot_reload(tmp_path: Path) -> None:
    """GameSession should capture state, re-parse, hot-swap VM, reconcile state, and force redraw."""
    script_file = tmp_path / "main.es"
    script_file.write_text(
        """## Start --- start
Narrator: Line 1
Narrator: Line 2
Narrator: Line 3
""",
        encoding="utf-8",
    )

    session = GameSession(script_file)
    session.vm.set_variable("hero_level", 42)

    # Advance to line 1
    session.advance()
    assert session.director.ui_state.text == "Line 1"
    assert session.vm.current_scene_id == "start"
    assert session.vm.beat_index == 1

    # Advance to line 2
    session.advance()
    assert session.director.ui_state.text == "Line 2"
    assert session.vm.beat_index == 2

    # Edit script file on disk: line 2 text changed, line 3 deleted
    time.sleep(0.05)
    script_file.write_text(
        """## Start --- start
Narrator: Line 1
Narrator: Line 2 EDITED
""",
        encoding="utf-8",
    )

    # Clear dirty flag to test that hot_reload sets it
    session._ui_dirty = False

    # Trigger hot-reload
    success = session.hot_reload()
    assert success is True

    # Check 1: State captured & preserved
    assert session.vm.variables["hero_level"] == 42

    # Check 2 & 3: Re-parsed and VM graph swapped
    assert len(session.graph.nodes["start"].body) == 2
    assert session.vm.graph is session.graph

    # Check 4: Reconciled state & presentation
    # beat_index was 2, body len is 2 -> capped to len - 1 = 1
    assert session.vm.beat_index == 1
    assert session.director.ui_state.text == "Line 2 EDITED"

    # Check 5: Force a redraw
    assert session._ui_dirty is True


def test_game_session_hot_reload_scene_deleted_with_entry(tmp_path: Path) -> None:
    """When the active scene is deleted on reload, session should jump to the entry scene."""
    script_file = tmp_path / "main.es"
    script_file.write_text(
        """## Intro --- intro
Narrator: Welcome!
-> secret

## Secret --- secret
Narrator: You found the secret.
""",
        encoding="utf-8",
    )

    session = GameSession(script_file)
    session.vm.jump("secret")
    session.advance()
    assert session.vm.current_scene_id == "secret"

    # Delete secret scene in script
    time.sleep(0.05)
    script_file.write_text(
        """## Intro --- intro
Narrator: Only intro remains.
""",
        encoding="utf-8",
    )

    session.hot_reload()
    # Gracefully jumped to entry node ('intro') and advanced
    assert session.vm.current_scene_id == "intro"
    assert session.director.ui_state.text == "Only intro remains."
    assert session._ui_dirty is True


def test_game_session_hot_reload_scene_deleted_without_entry(tmp_path: Path) -> None:
    """When the active scene is deleted and no entry exists, display error overlay."""
    script_file = tmp_path / "main.es"
    script_file.write_text(
        """## Secret --- secret
Narrator: Secret scene.
""",
        encoding="utf-8",
    )

    session = GameSession(script_file)
    session.advance()
    assert session.vm.current_scene_id == "secret"

    # Empty script with no scenes
    time.sleep(0.05)
    script_file.write_text("", encoding="utf-8")

    session.hot_reload()
    assert session.overlay.error_overlay is not None
    assert "Scene not found" in session.overlay.error_overlay
    assert session._ui_dirty is True


def test_game_session_handle_input_reload(tmp_path: Path) -> None:
    """InputAction.RELOAD should trigger hot_reload on GameSession."""
    script_file = tmp_path / "main.es"
    script_file.write_text(
        """## Start --- start
Narrator: Version 1
""",
        encoding="utf-8",
    )
    session = GameSession(script_file)
    session.advance()
    assert session.director.ui_state.text == "Version 1"

    time.sleep(0.05)
    script_file.write_text(
        """## Start --- start
Narrator: Version 2
""",
        encoding="utf-8",
    )

    # Send InputAction.RELOAD (which is mapped to Shift+R in Keymap)
    result = session.handle_input(InputAction.RELOAD)
    assert result is True
    assert session.director.ui_state.text == "Version 2"


def test_game_session_hot_reload_parse_error_preserves_story(tmp_path: Path) -> None:
    script_file = tmp_path / "main.es"
    script_file.write_text(
        """## Start --- start
Narrator: Safe text
""",
        encoding="utf-8",
    )
    session = GameSession(script_file)
    session.advance()
    assert session.director.ui_state.text == "Safe text"

    # Write invalid syntax
    script_file.write_text(
        """## Start --- start
@if
""",
        encoding="utf-8",
    )
    success = session.hot_reload()
    assert success is False
    assert session.overlay.error_overlay is not None
    assert "Hot-reload parse error" in session.overlay.error_overlay
    # VM state should still be on the working version
    assert session.vm.current_scene_id == "start"


def test_game_session_hot_reload_syncs_characters_and_defaults(tmp_path: Path) -> None:
    script_file = tmp_path / "main.es"
    script_file.write_text(
        """## Start --- start
Narrator: Initial
""",
        encoding="utf-8",
    )
    session = GameSession(script_file)
    session.advance()

    # Update with character declaration and default variable
    script_file.write_text(
        """@character h "Hoshiko" color=#ff00ff
@default affinity = 10

## Start --- start
h: Reloaded
""",
        encoding="utf-8",
    )
    success = session.hot_reload()
    assert success is True
    assert "h" in session.director.characters
    assert session.director.characters["h"].name == "Hoshiko"
    assert session.vm.get_variable("affinity") == 10

    assert session._ui_dirty is True


def test_game_session_auto_reload_in_update(tmp_path: Path) -> None:
    """When auto_reload=True, session.update(dt) should hot reload on file modification."""
    script_file = tmp_path / "main.es"
    script_file.write_text(
        """## Start --- start
Narrator: Before auto reload
""",
        encoding="utf-8",
    )
    session = GameSession(script_file, auto_reload=True)
    session.advance()
    assert session.director.ui_state.text == "Before auto reload"

    time.sleep(0.05)
    script_file.write_text(
        """## Start --- start
Narrator: After auto reload!
""",
        encoding="utf-8",
    )

    # Set watcher interval to 0 so update immediately checks
    if session.watcher:
        session.watcher.interval = 0.0

    session.update(0.016)
    assert session.director.ui_state.text == "After auto reload!"
    assert session._ui_dirty is True
