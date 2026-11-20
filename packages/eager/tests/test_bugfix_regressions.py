"""Regression tests for parser, graph, VM, core, stage, session, and UI fixes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest

from eager.backends.types import UIDrawBackend
from eager.core.input import InputAction, Keymap
from eager.core.preferences import Preferences
from eager.core.state import Checkpoint, StorySnapshot
from eager.core.text import TextReveal, parse_text_tags, wrap_text
from eager.core.types import Rect
from eager.script.ast import ParsedCharacter, ParsedChoiceSet, ParsedDialogue
from eager.script.expr import compile_expr
from eager.script.graph import to_graph
from eager.script.parser import ParseError, parse
from eager.script.validator import validate
from eager.session.session import GameSession
from eager.stage.compositor import StageCompositor
from eager.stage.director import StageDirector
from eager.ui.screens.builtin import HistoryScreen
from eager.ui.screens.screen import Button, Screen, Slider
from eager.vm.runtime import StoryRuntimeError, StoryVM


def test_stray_top_level_elif_else_end_do_not_truncate_scene() -> None:
    script = "## Start --- start\n@elif True\n@else\n@end\nAlice: Still here!\n"
    graph = to_graph(parse(script))
    body = graph.nodes["start"].body
    assert any(isinstance(item, ParsedDialogue) and item.text == "Still here!" for item in body)


def test_inline_choice_menus_separated_by_blank_lines_do_not_merge() -> None:
    script = (
        "## Start --- start\n"
        "? First A\n"
        "    Alice: A\n"
        "\n"
        "? Second B\n"
        "    Alice: B\n"
    )
    items = parse(script)
    choice_sets = [it for it in items if isinstance(it, ParsedChoiceSet)]
    assert len(choice_sets) == 2
    assert choice_sets[0].options[0].text == "First A"
    assert choice_sets[1].options[0].text == "Second B"


def test_inline_choice_preserves_malformed_condition_for_validation() -> None:
    script = "## Start --- start\n? Open door if a === b\n    Alice: Opened\n"
    items = parse(script)
    choice_sets = [it for it in items if isinstance(it, ParsedChoiceSet)]
    assert len(choice_sets) == 1
    assert choice_sets[0].options[0].text == "Open door"
    assert choice_sets[0].options[0].condition == "a === b"
    res = validate(items)
    assert not res.is_valid
    assert any("Invalid choice condition" in e.message for e in res.errors)


def test_bare_character_and_directive_word_boundaries() -> None:
    items = parse("@character alice\n## Start --- start\nAlice: Hi\n")
    chars = [it for it in items if isinstance(it, ParsedCharacter)]
    assert len(chars) == 1
    assert chars[0].id == "alice"
    assert chars[0].name == "alice"

    with pytest.raises(ParseError, match="Unknown directive '@default_x'"):
        parse("@default_x = 1\n## Start --- start\nHi\n")


def test_tab_indented_inline_block_ast_columns() -> None:
    script = "## Start --- start\n? Go\n\tAlice: Hello\n"
    items = parse(script)
    choice_sets = [it for it in items if isinstance(it, ParsedChoiceSet)]
    dlg = choice_sets[0].options[0].body[0]
    assert isinstance(dlg, ParsedDialogue)
    # 1 tab character before 'Alice: Hello' -> start_col == 1
    assert dlg.start_col == 1


def test_expr_builtins_not_shadowed_by_user_vars() -> None:
    assert compile_expr("min(3, 5)").evaluate({"min": 99}) == 3
    assert compile_expr("max(1, 2)").evaluate({"max": "bad"}) == 2


def test_vm_eval_env_does_not_overwrite_user_vars_and_case_insensitive_chars() -> None:
    script = (
        '@character Alice "Alice Wonderland"\n'
        "@default visited = False\n"
        "## Start --- start\n"
        "@if visited\n"
        "alice: Was visited\n"
        "@else\n"
        "alice: Not visited\n"
        "@end\n"
    )
    graph = to_graph(parse(script))
    assert "alice" in graph.characters
    vm = StoryVM(graph)
    vm.step()  # SceneEnterEvent
    ev = vm.step()
    assert ev is not None
    assert getattr(ev, "speaker", None) == "Alice Wonderland"
    assert getattr(ev, "text", None) == "Not visited"


def test_vm_set_zero_division_and_invalid_targets() -> None:
    graph_div = to_graph(parse("@default x = 10\n## Start --- start\n$ x /= 0\nHi\n"))
    vm_div = StoryVM(graph_div)
    vm_div.step()
    with pytest.raises(StoryRuntimeError, match="Error executing"):
        vm_div.step()

    graph_dot = to_graph(parse("## Start --- start\n$ foo.bar = 1\nHi\n"))
    vm_dot = StoryVM(graph_dot)
    vm_dot.step()
    with pytest.raises(StoryRuntimeError, match="Invalid variable target"):
        vm_dot.step()

    graph_priv = to_graph(parse("## Start --- start\n$ persistent._seen_scenes = []\nHi\n"))
    vm_priv = StoryVM(graph_priv)
    vm_priv.step()
    with pytest.raises(StoryRuntimeError, match="Invalid persistent variable target"):
        vm_priv.step()


def test_vm_load_applies_new_defaults_and_dirty_seen_scenes(tmp_path: Path) -> None:
    script = "@default new_flag = 42\n## Start --- start\nHi\n"
    graph = to_graph(parse(script))
    session = GameSession(graph, save_dir=tmp_path)
    old_snap = StorySnapshot(
        current_scene="start",
        beat_index=0,
        call_stack=(),
        variables={},
        visited_scenes=(),
    )
    session.vm.load(old_snap)
    assert session.vm.variables["new_flag"] == 42

    # Entering a scene marks VM persistent dirty so _flush_persistent saves _seen_scenes
    assert session.vm._persistent_dirty is True
    session._flush_persistent()
    assert session.vm._persistent_dirty is False
    assert "start" in session.persistent.get("_seen_scenes", [])


def test_session_save_load_resilience_and_metadata(tmp_path: Path) -> None:
    graph = to_graph(parse("## Intro Scene --- intro\nAlice: Hello!\n"))
    session = GameSession(graph, save_dir=tmp_path)
    session.advance()
    session._playtime = 12.5
    meta = session.save_game("slot_1")
    assert meta.scene_name == "Intro Scene"

    # Quickload missing slot does not clobber _playtime
    session._playtime = 55.0
    assert session.quickload() is False
    assert session._playtime == 55.0

    # Corrupted save referencing deleted scene returns False instead of crashing
    bad_cp = Checkpoint(
        story={"current_scene": "nonexistent", "beat_index": 0},
        visual={},
        audio={},
        backlog_len=0,
        ui={},
    )
    session.save_manager.save_slot("bad_slot", bad_cp)
    assert session.load_game("bad_slot") is False


def test_director_and_compositor_state_roundtrip() -> None:
    comp = StageCompositor(1280, 720)
    director = StageDirector(comp)
    director.handle_scene_bg("intro bg_intro with cut duration=0.2")
    saved = director.save_visual_state()
    assert "scene_backgrounds" in saved

    comp2 = StageCompositor(800, 600)
    director2 = StageDirector(comp2)
    director2.load_visual_state(saved)
    assert "intro" in director2.scene_backgrounds
    assert comp2.virtual_width == 1280
    assert comp2.layout.virtual_width == 1280
    assert comp2.layout.virtual_height == 720


def test_director_show_case_and_move_invalid_easing() -> None:
    comp = StageCompositor(1280, 720)
    director = StageDirector(comp)
    director.handle_show("alice Happy at center with cut")
    char_layer = comp.stage.get_layer("characters")
    assert char_layer is not None
    elem = char_layer.elements.get("alice")
    assert elem is not None
    assert elem.asset_id == "alice/happy"

    # Should not raise ValueError on unknown easing
    director.handle_move("alice to left duration=0.5 easing=bogus_easing")


def test_preferences_load_rejects_methods_and_invalid_types(tmp_path: Path) -> None:
    p = tmp_path / "prefs.json"
    p.write_text(
        json.dumps(
            {
                "load": "evil",
                "__class__": "bad",
                "master_volume": "loud",
                "text_speed": None,
                "fullscreen": "yes",
                "music_volume": 0.4,
            }
        ),
        encoding="utf-8",
    )
    prefs = Preferences.load(p)
    assert prefs.master_volume == 1.0
    assert prefs.text_speed == 50.0
    assert prefs.fullscreen is False
    assert prefs.music_volume == 0.4


def test_keymap_bind_unbind_normalizes_aliases() -> None:
    km = Keymap()
    km.bind("RETURN", InputAction.ADVANCE)
    assert km.map_key("enter") == InputAction.ADVANCE
    km.unbind("Enter")
    assert km.map_key("return") is None


def test_text_tags_reveal_and_wrap_font_family() -> None:
    fmt = parse_text_tags("{id=line_001}Hello{w=0.5}")
    assert fmt.plain_text == "Hello"
    assert len(fmt.pauses) == 1
    assert fmt.pauses[0].char_index == 5

    reveal = TextReveal(fmt, chars_per_second=100.0)
    reveal.update(1.0)
    assert reveal._pause_timer == pytest.approx(0.5)
    assert reveal.is_complete is False
    reveal.update(0.6)
    assert reveal.is_complete is True

    seen_families: list[str | None] = []

    def mock_measure(text: str, font_size: int = 14, font_family: str | None = None):
        seen_families.append(font_family)
        return (len(text) * 8.0, float(font_size))

    wrap_text("Hello world", 50.0, mock_measure, font_family="CustomFont")
    assert seen_families and all(f == "CustomFont" for f in seen_families)


def test_screen_slider_keyboard_reachability_and_skip_release(tmp_path: Path) -> None:
    scr = Screen("prefs_test")
    scr.buttons.append(Button(Rect(0, 0, 100, 30), "Back"))
    scr.sliders.append(Slider(Rect(0, 50, 200, 20), value=0.5))

    # Up from initial state wraps to the last focus item (the slider)
    assert scr.handle_key("up") is True
    assert scr._focused_slider_index == 0
    assert scr.handle_key("right") is True
    assert scr.sliders[0].value == pytest.approx(0.55)

    # SKIP_RELEASE while modal screen is active clears skip_mode
    graph = to_graph(parse("## Start --- start\nHi\n"))
    session = GameSession(graph, save_dir=tmp_path)
    session.skip_mode = True
    session.screens.show("history", session)
    session.handle_input(InputAction.SKIP_RELEASE)
    assert session.skip_mode is False

    # return_to_title clears screen stack
    session.screens.show("game_menu", session)
    session.return_to_title()
    assert len(session.screens._history_stack) == 0


def test_validator_dead_if_preamble_and_set_targets() -> None:
    script = (
        "Dialogue in preamble\n"
        "## Start --- start\n"
        "$ foo.bar = 1\n"
        "> start\n"
        "@if True\n"
        "> secret\n"
        "@end\n"
        "## Secret --- secret\n"
        "Never reached\n"
    )
    res = validate(parse(script))
    assert any("preamble" in e.message for e in res.errors)
    assert any("Invalid variable target" in e.message for e in res.errors)
    assert any("Unreachable code" in w.message for w in res.warnings)
    assert any("never targeted" in w.message or "unreachable" in w.message.lower() for w in res.warnings)


def test_history_screen_removes_offscreen_voice_buttons() -> None:
    class MockBackend:
        def draw_rect(self, *args, **kwargs):
            pass

        def draw_text(self, *args, **kwargs):
            pass

        def measure_text(
            self,
            text: str,
            *,
            font_size: int = 14,
            bold: bool = False,
            italic: bool = False,
            cache: bool = True,
            font_family: str | None = None,
        ):
            return (len(text) * 8.0, float(font_size))

    from eager.core.backlog import Backlog

    backlog = Backlog()
    for i in range(7):
        backlog.add("Alice", "Line " * 60, voice=f"v{i}.ogg")

    session = MagicMock()
    session.backlog = backlog
    session.overlay = None
    scr = HistoryScreen(viewport_width=640, viewport_height=40)
    scr.on_enter(session)
    assert len([b for b in scr.buttons if getattr(b, "voice", None)]) == 7
    scr.draw(cast(UIDrawBackend, MockBackend()), 640, 40)
    remaining_voice = [b for b in scr.buttons if getattr(b, "voice", None)]
    assert len(remaining_voice) < 7
