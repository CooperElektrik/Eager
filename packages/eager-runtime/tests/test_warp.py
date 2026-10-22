"""Tests for simulated scene warping in GameSession."""

from __future__ import annotations

import eager_script
from eager_core.events import DialogueEvent

from eager_runtime import GameSession

WARP_STORY = """
## Intro --- intro
~ bg classroom with cut
~ show guide smile at center with cut
$ gold = 100
~ play music bgm.mp3
~ play sound sfx.wav
Guide: Welcome to class!
> act1

## Act 1 --- act1
~ expr guide happy
Guide: Time for our first lesson.
? Study history (history)
? Study science (science)

## History --- history
$ subject = "history"
~ bg library with cut
Guide: History is fascinating.
> exam

## Science --- science
$ subject = "science"
~ bg lab with cut
Guide: Science is wonderful.
> exam

## Exam --- exam
Guide: Time for the exam!
"""

DISCONNECTED_STORY = """
## Main --- main
Narrator: Hello.

## Secret Start --- secret_start
~ bg dungeon with cut
~ show monster angry at center with cut
$ secret_found = True
> secret_end

## Secret End --- secret_end
Narrator: The dungeon ends here.
"""


def test_warp_simulates_stage_state_and_variables() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)

    # Warp directly to Act 1
    success = session.warp("act1")
    assert success is True
    assert session.vm.current_scene_id == "act1"

    # Stage background should be classroom from intro
    items = session.compositor.render_list()
    bg_items = [it for it in items if it.layer == "background"]
    assert len(bg_items) == 1
    assert "classroom" in bg_items[0].asset_id

    # Character guide should be present with expression from intro
    char_items = [it for it in items if it.layer == "characters"]
    assert len(char_items) == 1
    assert "guide" in char_items[0].asset_id

    # Variable from intro should be set
    assert session.vm.get_variable("gold") == 100

    # Backlog should contain Intro dialogue
    assert len(session.backlog.entries) >= 1
    assert any("Welcome to class!" in entry.text for entry in session.backlog.entries)

    # Continuous audio (music) was requested; one-shot sound was suppressed
    music_chan = session.audio.channels.get("music")
    assert music_chan is not None
    assert music_chan.is_playing is True

    sound_chan = session.audio.channels.get("sound")
    assert sound_chan is None or sound_chan.is_playing is False

    # UI text should be clean for Act 1
    assert session.director.ui_state.text is None

    # Advancing now executes Act 1 beats (modifying expression to happy)
    evt = session.advance()
    assert isinstance(evt, DialogueEvent)
    assert evt.speaker == "Guide"
    assert evt.text == "Time for our first lesson."

    char_items = [it for it in session.compositor.render_list() if it.layer == "characters"]
    assert len(char_items) == 1
    assert "happy" in char_items[0].asset_id


def test_warp_branching_choices() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)

    # Warp to Exam via History branch by warping to history and advancing, or warping to Exam directly.
    # When warping to History directly, preceding scenes (intro, act1) are simulated.
    assert session.warp("history") is True
    assert session.vm.current_scene_id == "history"
    # Stage from predecessors
    bg_items = [it for it in session.compositor.render_list() if it.layer == "background"]
    assert "classroom" in bg_items[0].asset_id

    # Advancing into History executes its beats
    evt = session.advance()
    assert isinstance(evt, DialogueEvent)
    assert evt.text == "History is fascinating."
    assert session.vm.get_variable("subject") == "history"
    bg_items = [it for it in session.compositor.render_list() if it.layer == "background"]
    assert "library" in bg_items[0].asset_id

    # New session: Warp to Exam (which follows history/science branch)
    session2 = GameSession(graph)
    assert session2.warp("exam") is True
    assert session2.vm.current_scene_id == "exam"
    # Either history or science was chosen along the shortest path to exam
    assert session2.vm.get_variable("subject") in ("history", "science")
    bg_items2 = [it for it in session2.compositor.render_list() if it.layer == "background"]
    assert len(bg_items2) == 1
    assert any(bg in bg_items2[0].asset_id for bg in ("library", "lab"))


def test_warp_disconnected_root_ancestor() -> None:
    graph = eager_script.parse_graph(DISCONNECTED_STORY)
    session = GameSession(graph)

    # secret_end is not reachable from main, but reachable from secret_start
    assert session.warp("secret_end") is True
    assert session.vm.current_scene_id == "secret_end"

    # Stage state from secret_start should be simulated
    items = session.compositor.render_list()
    bg_items = [it for it in items if it.layer == "background"]
    assert "dungeon" in bg_items[0].asset_id
    char_items = [it for it in items if it.layer == "characters"]
    assert len(char_items) == 1
    assert "monster" in char_items[0].asset_id
    assert session.vm.get_variable("secret_found") is True


def test_warp_direct_without_simulation() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)

    # Warp with simulate=False performs a bare jump
    assert session.warp("act1", simulate=False) is True
    assert session.vm.current_scene_id == "act1"

    # Preceding variables and background are NOT set
    assert session.vm.get_variable("gold") is None
    bg_items = [it for it in session.compositor.render_list() if it.layer == "background"]
    assert len(bg_items) == 0


def test_warp_invalid_target() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)
    assert session.warp("nonexistent_scene") is False
