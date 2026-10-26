"""Tests for GameSession, interactions, unified checkpoints, and rollback."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import eager_script
import pytest
from eager_core.audio import NullAudioBackend
from eager_core.events import DialogueEvent
from eager_core.types import Color

from eager_runtime import ChoicePromptEvent, GameSession, InputAction, InputPromptEvent

SAMPLE_STORY = """
## Intro --- intro
~ bg castle with cut
~ show alice cheerful at left with cut
Alice: Hello traveler!
~ show bob stern at right with cut
Bob: What do you want?
? Ask about castle (castle)
? Ask about forest (forest)

## Castle --- castle
~ bg throne_room with cut
Alice: Welcome to the throne room.
> end_scene

## Forest --- forest
~ bg deep_forest with cut
Bob: The trees are thick here.
> end_scene

## End Scene --- end_scene
Narrator: The journey concludes.
"""


def test_session_advance_stops_only_on_interactions() -> None:
    graph = eager_script.parse_graph(SAMPLE_STORY)
    session = GameSession(graph)

    # First advance: moves past ~ bg and ~ show, stops at first dialogue
    evt1 = session.advance()
    assert evt1 is not None
    assert evt1.type == "dialogue"
    assert session.director.ui_state.speaker == "Alice"
    assert session.director.ui_state.text == "Hello traveler!"
    # Sprites should already be displayed by the compositor
    items = session.compositor.render_list()
    char_items = [it for it in items if it.layer == "characters"]
    assert len(char_items) == 1
    assert char_items[0].asset_id == "alice/cheerful"

    # Second advance: moves past ~ show bob, stops at Bob's dialogue
    evt2 = session.advance()
    assert evt2 is not None
    assert evt2.type == "dialogue"
    assert session.director.ui_state.speaker == "Bob"
    assert session.director.ui_state.text == "What do you want?"
    char_items = [it for it in session.compositor.render_list() if it.layer == "characters"]
    assert len(char_items) == 2

    # Third advance: stops at choice prompt
    evt3 = session.advance()
    assert evt3 is not None
    assert evt3.type == "choice_prompt"
    assert isinstance(evt3, ChoicePromptEvent)
    assert len(evt3.options) == 2


def test_session_rollback_restores_state_and_visuals() -> None:
    graph = eager_script.parse_graph(SAMPLE_STORY)
    session = GameSession(graph)

    # Advance to Alice
    session.advance()
    assert len([it for it in session.compositor.render_list() if it.layer == "characters"]) == 1

    # Advance to Bob (spawns second character)
    session.advance()
    assert len([it for it in session.compositor.render_list() if it.layer == "characters"]) == 2
    assert session.director.ui_state.speaker == "Bob"

    # Roll back to Alice
    ok = session.rollback()
    assert ok is True
    assert session.director.ui_state.speaker == "Alice"
    assert session.director.ui_state.text == "Hello traveler!"
    char_items = [it for it in session.compositor.render_list() if it.layer == "characters"]
    assert len(char_items) == 1
    assert char_items[0].asset_id == "alice/cheerful"


def test_session_transitory_animation_on_save_and_rollback() -> None:
    fade_story = """
## Scene 1 --- scene1
~ bg garden with cut
~ show alice cheerful at center with fade duration=0.5
Alice: Welcome to the garden!
~ show bob stern at right with cut
Bob: I followed you here.
"""
    graph = eager_script.parse_graph(fade_story)
    session = GameSession(graph)

    # Advance lands on Alice: Welcome to the garden!
    session.advance()
    assert session.director.ui_state.speaker == "Alice"

    # Advance to Bob
    session.advance()
    assert session.director.ui_state.speaker == "Bob"

    # Roll back to Alice: Welcome to the garden!
    ok = session.rollback()
    assert ok is True
    assert session.director.ui_state.speaker == "Alice"

    # Alice must be fully visible and in render_list, not invisible at opacity 0.0
    char_items = [it for it in session.compositor.render_list() if it.layer == "characters"]
    assert len(char_items) == 1
    assert char_items[0].asset_id == "alice/cheerful"
    assert char_items[0].opacity == 1.0


def test_session_fade_in_and_fade_out_live_animation_lifecycle() -> None:
    fade_story = """
## Scene 1 --- scene1
~ bg garden with cut
~ fade_in duration=1.0
Alice: Welcome to the world!
~ fade_out duration=0.8 color=#ffffff
Alice: Goodbye world!
"""
    graph = eager_script.parse_graph(fade_story)
    session = GameSession(graph)

    # 1. Advance lands on first beat
    session.advance()
    assert session.director.ui_state.speaker == "Alice"
    assert session.director.ui_state.text == "Welcome to the world!"

    # Active animation must NOT be wiped by checkpoint capture
    assert session.compositor.timeline.active_count == 1
    overlays = [it for it in session.compositor.render_list() if it.layer == "overlay"]
    assert len(overlays) == 1
    assert overlays[0].opacity == pytest.approx(1.0)

    # Midway through fade_in
    session.update(0.5)
    assert session.compositor.timeline.active_count == 1
    overlays_mid = [it for it in session.compositor.render_list() if it.layer == "overlay"]
    assert len(overlays_mid) == 1
    assert overlays_mid[0].opacity == pytest.approx(0.5)

    # Complete fade_in
    session.update(0.5)
    assert session.compositor.timeline.active_count == 0
    overlays_done = [it for it in session.compositor.render_list() if it.layer == "overlay"]
    assert len(overlays_done) == 0

    # 2. Advance to second beat (fade_out to white)
    session.advance()
    assert session.director.ui_state.text == "Goodbye world!"
    assert session.compositor.timeline.active_count == 1

    # Midway through fade_out
    session.update(0.4)
    overlays_white = [it for it in session.compositor.render_list() if it.layer == "overlay"]
    assert len(overlays_white) == 1
    assert overlays_white[0].opacity == pytest.approx(0.5)
    assert overlays_white[0].tint.r == pytest.approx(1.0)
    assert overlays_white[0].tint.g == pytest.approx(1.0)
    assert overlays_white[0].tint.b == pytest.approx(1.0)

    # Complete fade_out
    session.update(0.4)
    overlays_white_done = [it for it in session.compositor.render_list() if it.layer == "overlay"]
    assert len(overlays_white_done) == 1
    assert overlays_white_done[0].opacity == pytest.approx(1.0)

    # 3. Rollback restores settled state without transitory overlay glitches
    ok = session.rollback()
    assert ok is True
    assert session.director.ui_state.text == "Welcome to the world!"
    overlays_rb = [it for it in session.compositor.render_list() if it.layer == "overlay"]
    assert len(overlays_rb) == 0



def test_session_rollback_onto_choice_reshows_menu() -> None:
    graph = eager_script.parse_graph(SAMPLE_STORY)
    session = GameSession(graph)

    session.advance()  # Alice
    session.advance()  # Bob
    session.advance()  # Choice prompt
    assert session.active_choice_prompt is not None

    # Choose option 0 (Castle)
    session.choose(0)
    assert session.director.ui_state.speaker == "Alice"
    assert session.director.ui_state.text == "Welcome to the throne room."
    assert session.active_choice_prompt is None

    # Roll back onto choice
    ok = session.rollback()
    assert ok is True
    assert session.active_choice_prompt is not None
    assert len(session.active_choice_prompt.options) == 2


def test_session_handle_input_actions() -> None:
    graph = eager_script.parse_graph(SAMPLE_STORY)
    session = GameSession(graph)

    session.handle_input(InputAction.ADVANCE)
    assert session.director.ui_state.speaker == "Alice"

    # Toggle UI hide
    session.handle_input(InputAction.HIDE_UI)
    assert session.ui_hidden is True
    session.handle_input(InputAction.HIDE_UI)
    assert session.ui_hidden is False


def test_session_input_prompt_checkpoint_restoration_and_mode_rollback() -> None:
    input_script = """
## Start --- start
Alice: Hello traveler!
~ input hero_name "Enter name:" "Traveler"
Alice: Welcome, [hero_name]!
"""
    graph = eager_script.parse_graph(input_script)
    session = GameSession(graph)

    # 1. Advance to first dialogue (Alice: Hello traveler!)
    ev1 = session.advance()
    assert ev1 is not None
    assert session.director.ui_state.text == "Hello traveler!"

    # 2. Advance to input prompt
    ev2 = session.advance()
    assert ev2 is not None
    assert ev2.type == "input_prompt"
    assert isinstance(ev2, InputPromptEvent)
    assert session.active_input_prompt is not None
    assert session.active_input_prompt.var_name == "hero_name"
    assert session.active_input_prompt.prompt == "Enter name:"
    assert session.active_input_prompt.default == "Traveler"

    # 3. Submit player input
    ev3 = session.submit_input("Valiant")
    assert ev3 is not None
    assert session.director.ui_state.text == "Welcome, Valiant!"
    assert session.active_input_prompt is None
    assert session.mode == "game"

    # 4. Advance to end of story
    ev4 = session.advance()
    assert ev4 is not None
    assert ev4.type == "story_end"
    assert session.is_finished is True
    assert session.mode == "ended"

    # 5. Rollback from ended state: mode must reset to != "ended" ("game")
    ok1 = session.rollback()
    assert ok1 is True
    assert session.is_finished is False
    assert session.mode == "game"
    assert session.director.ui_state.text == "Welcome, Valiant!"

    # 6. Rollback again onto input prompt: restores active_input_prompt
    ok2 = session.rollback()
    assert ok2 is True
    assert session.mode == "game"
    assert session.active_input_prompt is not None
    assert session.active_input_prompt.var_name == "hero_name"
    assert session.active_input_prompt.prompt == "Enter name:"
    assert session.active_input_prompt.default == "Traveler"

    # 7. Resubmit input with different value
    session.submit_input("Champion")
    assert session.director.ui_state.text == "Welcome, Champion!"


def test_session_screens_and_extended_inputs() -> None:
    test_script = """
## Start --- start
Alice: Hello traveler!
Alice: Another day, another adventure.
"""
    graph = eager_script.parse_graph(test_script)
    session = GameSession(graph)

    # Built-in screens registered
    assert "title" in session.screens.screens
    assert "save" in session.screens.screens
    assert "load" in session.screens.screens
    assert "preferences" in session.screens.screens
    assert "history" in session.screens.screens

    session.advance()
    assert session.director.ui_state.text == "Hello traveler!"

    # Quicksave / Quickload via InputAction
    session.handle_input(InputAction.QUICK_SAVE)
    session.advance()
    assert session.director.ui_state.text == "Another day, another adventure."

    session.handle_input(InputAction.QUICK_LOAD)
    assert session.director.ui_state.text == "Hello traveler!"

    # Open / close menus via InputAction
    session.handle_input(InputAction.GAME_MENU)
    assert session.screens.is_active
    assert session.screens.active_screen.name == "save"

    # Pointer click on Back button in save screen
    back_btn = session.screens.active_screen.buttons[-1]
    session.handle_input(InputAction.POINTER_CLICK, x=back_btn.rect.x + 5, y=back_btn.rect.y + 5)
    assert not session.screens.is_active

    # Open history screen via InputAction.HISTORY
    session.handle_input(InputAction.HISTORY)
    assert session.screens.is_active
    assert session.screens.active_screen.name == "history"

    session.handle_input(InputAction.CANCEL)
    assert not session.screens.is_active


def test_session_typewriter_reveal_and_click_skip() -> None:
    story = """
## Start --- start
Alice: Long dialogue string that takes multiple seconds to reveal fully.
Bob: Second dialogue beat.
"""
    graph = eager_script.parse_graph(story)
    session = GameSession(graph)
    session.preferences.text_speed = 10.0  # 10 chars per second

    # Step to first dialogue: starts typewriter reveal
    session.advance()
    assert session.director.ui_state.text.startswith("Long dialogue")
    assert session.text_reveal is not None
    assert not session.text_reveal.is_complete
    assert session.director.ui_state.visible_chars == 0

    # Advance 0.5s: 5 chars revealed
    session.update(0.5)
    assert session.director.ui_state.visible_chars == 5
    assert not session.text_reveal.is_complete

    # First ADVANCE press: should immediately complete reveal without advancing to Bob
    session.handle_input(InputAction.ADVANCE)
    assert session.text_reveal.is_complete
    assert session.director.ui_state.visible_chars is None
    assert session.director.ui_state.speaker == "Alice"

    # Second ADVANCE press: now advances to Bob
    session.handle_input(InputAction.ADVANCE)
    assert session.director.ui_state.speaker == "Bob"


def test_session_typewriter_append_continuation() -> None:
    story = """
## Start --- start
Alice: Part one.
- Part two.
- Part three.
"""
    graph = eager_script.parse_graph(story)
    session = GameSession(graph)
    session.preferences.text_speed = 10.0  # 10 chars per second

    # Step to first dialogue: starts typewriter reveal from 0
    session.advance()
    assert session.director.ui_state.text == "Part one."
    assert session.director.ui_state.visible_chars == 0
    assert session.text_reveal is not None
    assert session.text_reveal.current_visible_plain_text == ""

    # Advance typewriter to complete
    session.handle_input(InputAction.ADVANCE)
    assert session.director.ui_state.visible_chars is None

    # Advance to first append beat: should continue from already present text ("Part one.")
    session.handle_input(InputAction.ADVANCE)
    assert session.director.ui_state.text == "Part one. Part two."
    assert session.text_reveal is not None
    assert not session.text_reveal.is_complete
    assert session.director.ui_state.visible_chars == len("Part one.")
    assert session.text_reveal.current_visible_plain_text == "Part one."

    # Update 0.5s: 5 chars revealed (" Part")
    session.update(0.5)
    assert session.director.ui_state.visible_chars == len("Part one.") + 5
    assert session.text_reveal.current_visible_plain_text == "Part one. Part"

    # Complete typewriter for first append
    session.handle_input(InputAction.ADVANCE)
    assert session.director.ui_state.visible_chars is None

    # Advance to second append beat: should continue from "Part one. Part two."
    session.handle_input(InputAction.ADVANCE)
    assert session.director.ui_state.text == "Part one. Part two. Part three."
    assert session.text_reveal is not None
    assert not session.text_reveal.is_complete
    assert session.director.ui_state.visible_chars == len("Part one. Part two.")
    assert session.text_reveal.current_visible_plain_text == "Part one. Part two."

    # Update 0.5s: 5 chars revealed
    session.update(0.5)
    assert session.director.ui_state.visible_chars == len("Part one. Part two.") + 5
    assert session.text_reveal.current_visible_plain_text == "Part one. Part two. Part"


def test_session_choice_keyboard_navigation() -> None:
    story = """
## Start --- start
? Option Alpha (alpha)
? Option Beta (beta)
? Option Gamma (gamma)

## Alpha --- alpha
Narrator: Alpha chosen.

## Beta --- beta
Narrator: Beta chosen.

## Gamma --- gamma
Narrator: Gamma chosen.
"""
    graph = eager_script.parse_graph(story)
    session = GameSession(graph)
    session.advance()  # reaches choice prompt

    assert session.active_choice_prompt is not None

    # Navigate down: selects first option (0)
    session.handle_input(InputAction.NAV_DOWN)
    assert session.overlay.choice_menu.selected_index == 0

    # Navigate down again: selects second option (1)
    session.handle_input(InputAction.NAV_DOWN)
    assert session.overlay.choice_menu.selected_index == 1

    # Navigate up: selects first option (0)
    session.handle_input(InputAction.NAV_UP)
    assert session.overlay.choice_menu.selected_index == 0

    # Navigate up again: wraps around to last option (2)
    session.handle_input(InputAction.NAV_UP)
    assert session.overlay.choice_menu.selected_index == 2

    # Confirm selection: selects Option Gamma
    session.handle_input(InputAction.CONFIRM)
    assert session.director.ui_state.text == "Gamma chosen."


def test_session_backlog_voice_replay_in_history_screen() -> None:
    story = """
## Main --- main
Alice: {voice:alice_01.ogg} Line with voice.
Bob: Line without voice.
Alice: {voice:alice_02.ogg} Second line with voice.
"""
    graph = eager_script.parse_graph(story)
    session = GameSession(graph)

    # Step through all 3 lines
    session.advance()
    session.advance()
    session.advance()

    assert len(session.backlog.entries) == 3
    assert session.backlog.entries[0].voice == "alice_01.ogg"
    assert session.backlog.entries[1].voice is None
    assert session.backlog.entries[2].voice == "alice_02.ogg"

    # Open history screen
    session.handle_input(InputAction.HISTORY)
    assert session.screens.is_active
    assert session.screens.active_screen is not None
    assert session.screens.active_screen.name == "history"

    history_screen = session.screens.active_screen
    # Should have 2 speaker buttons (indices 0 and 2 have voice)
    speaker_btns = [b for b in history_screen.buttons if b.text == "🔊"]
    assert len(speaker_btns) == 2
    assert speaker_btns[0].voice == "alice_01.ogg"
    assert speaker_btns[1].voice == "alice_02.ogg"

    class MockBackend(NullAudioBackend):
        def play(self, channel: str, asset_path: str | Path, **kwargs: Any) -> None:
            self.calls.append(("voice", str(asset_path)))

        def stop(self, channel, **kwargs):
            pass

        def is_playing(self, channel):
            return False

    mock_backend = MockBackend()
    session.audio.backend = mock_backend

    # Click the first speaker button via session click input
    btn0 = speaker_btns[0]
    session.handle_input(InputAction.POINTER_CLICK, x=btn0.rect.x + 1, y=btn0.rect.y + 1)
    assert any(c[0] == "voice" and isinstance(c[1], str) and "alice_01.ogg" in c[1] for c in mock_backend.calls)

    # Also test session.play_voice directly
    session.play_voice("direct_call.ogg")
    assert any(c[0] == "voice" and isinstance(c[1], str) and "direct_call.ogg" in c[1] for c in mock_backend.calls)


def test_session_input_prompt_handle_input_wiring() -> None:
    input_script = """
## Start --- start
Alice: What is your name?
~ input hero_name "Enter name:" "Traveler"
Alice: Welcome, [hero_name]!
"""
    graph = eager_script.parse_graph(input_script)
    session = GameSession(graph)

    session.advance()  # Alice: What is your name?
    ev = session.advance()  # input_prompt
    assert ev is not None
    assert isinstance(ev, InputPromptEvent)
    assert ev.type == "input_prompt"
    assert ev.prompt == "Enter name:"
    assert ev.default == "Traveler"
    assert session.active_input_prompt is not None
    assert session.input_text == "Traveler"

    # Reset input_text to test typing
    session.input_text = ""
    # Test TEXT_CHAR
    for ch in "Hero":
        session.handle_input(InputAction.TEXT_CHAR, char=ch)
    assert session.input_text == "Hero"

    # Test TEXT_BACKSPACE
    session.handle_input(InputAction.TEXT_BACKSPACE)
    assert session.input_text == "Her"

    session.handle_input(InputAction.TEXT_CHAR, char="o")
    assert session.input_text == "Hero"

    # Test CONFIRM (Enter)
    session.handle_input(InputAction.CONFIRM)
    assert session.active_input_prompt is None
    assert session.director.ui_state.text == "Welcome, Hero!"


def test_session_seen_beats_tracking_and_skip_unseen_protection(tmp_path) -> None:
    test_script = """
## Start --- start
Alice: Line 1
Alice: Line 2
Alice: Line 3
"""
    script_file = tmp_path / "game.es"
    script_file.write_text(test_script, encoding="utf-8")
    save_dir = tmp_path / "saves"
    session = GameSession(script_file, save_dir=save_dir)

    # 1. Initially seen_beats should be empty
    assert session.persistent.get("seen_beats") is None

    # Advance through Line 1
    ev1 = session.advance()
    assert isinstance(ev1, DialogueEvent)
    assert ev1.beat_id is not None
    seen1 = session.persistent.get("seen_beats")
    assert isinstance(seen1, list)
    assert ev1.beat_id in seen1
    assert session.is_current_beat_read() is True

    # 2. Advance through Line 2
    ev2 = session.advance()
    assert isinstance(ev2, DialogueEvent)
    assert ev2.beat_id is not None
    assert ev2.beat_id in session.persistent["seen_beats"]

    # 3. Create a fresh session with same persistent data (playthrough 2)
    # Line 1 and 2 are seen, but Line 3 has not been seen yet
    session2 = GameSession(script_file, save_dir=save_dir)
    # By default, preferences.skip_unseen is False
    assert session2.preferences.skip_unseen is False

    # Start at line 1
    session2.advance()
    assert session2.director.ui_state.text == "Line 1"
    assert session2.is_current_beat_read() is True

    # Enable skip mode
    session2.skip_mode = True
    session2.update(0.1)

    # Line 2 was seen, so skip should advance through Line 2.
    # But Line 3 was NOT seen previously in session.persistent!
    # Therefore skip_mode must automatically drop out at Line 3!
    assert session2.director.ui_state.text == "Line 3"
    assert session2.skip_mode is False

    # 4. Now Line 3 has been recorded into seen_beats
    ev3_beat_id = getattr(session2._last_event, "beat_id", None)
    assert ev3_beat_id in session2.persistent["seen_beats"]

    # 5. Playthrough 3: with all lines now seen, skip mode should skip through to the end
    session3 = GameSession(script_file, save_dir=save_dir)
    session3.advance()
    session3.skip_mode = True
    session3.update(0.1)
    assert session3.is_finished is True


def test_session_roll_forward_redo_stack() -> None:
    test_script = """
## Start --- start
Alice: Line 1
Alice: Line 2
Alice: Line 3
? Option A (scene_a)
? Option B (scene_b)

## Scene A --- scene_a
Alice: Reached Scene A!

## Scene B --- scene_b
Alice: Reached Scene B!
"""
    graph = eager_script.parse_graph(test_script)
    session = GameSession(graph)

    # Initially cannot roll forward
    assert session.checkpoints.can_roll_forward is False
    assert session.roll_forward() is False

    # Advance through lines 1, 2, 3
    session.advance()
    assert session.director.ui_state.text == "Line 1"

    session.advance()
    assert session.director.ui_state.text == "Line 2"

    session.advance()
    assert session.director.ui_state.text == "Line 3"

    # Advance to choice prompt
    ev_choice = session.advance()
    assert ev_choice is not None and ev_choice.type == "choice_prompt"
    assert session.active_choice_prompt is not None

    # Roll back from choice prompt to Line 3
    assert session.handle_input(InputAction.ROLLBACK) is True
    assert session.director.ui_state.text == "Line 3"
    assert session.active_choice_prompt is None
    assert session.checkpoints.can_roll_forward is True

    # Roll back from Line 3 to Line 2
    assert session.handle_input(InputAction.ROLLBACK) is True
    assert session.director.ui_state.text == "Line 2"

    # Roll back from Line 2 to Line 1
    assert session.handle_input(InputAction.ROLLBACK) is True
    assert session.director.ui_state.text == "Line 1"

    # Now roll forward using InputAction.ROLL_FORWARD back to Line 2
    assert session.handle_input(InputAction.ROLL_FORWARD) is True
    assert session.director.ui_state.text == "Line 2"

    # Roll forward to Line 3
    assert session.handle_input(InputAction.ROLL_FORWARD) is True
    assert session.director.ui_state.text == "Line 3"

    # Roll forward to Choice Prompt (restores choice menu without re-triggering choices)
    assert session.handle_input(InputAction.ROLL_FORWARD) is True
    assert session.active_choice_prompt is not None
    assert session.checkpoints.can_roll_forward is False

    # Cannot roll forward any further
    assert session.handle_input(InputAction.ROLL_FORWARD) is False

    # Rollback 1 step to Line 3
    session.rollback()
    assert session.director.ui_state.text == "Line 3"
    assert session.checkpoints.can_roll_forward is True

    # If the player advances past the head or makes a new interaction, redo stack is cleared
    session.advance()
    assert session.active_choice_prompt is not None
    # Now redo stack is cleared because a new checkpoint was pushed
    assert session.checkpoints.can_roll_forward is False
    assert session.roll_forward() is False

    # Test choice clears redo stack as well
    session.rollback()
    assert session.director.ui_state.text == "Line 3"
    assert session.checkpoints.can_roll_forward is True

    # Roll forward to choice prompt
    session.roll_forward()
    assert session.active_choice_prompt is not None
    # Make a choice
    session.choose(0)
    assert session.director.ui_state.text == "Reached Scene A!"
    assert session.checkpoints.can_roll_forward is False


def test_session_voice_aware_auto_forward() -> None:
    test_script = """
## Start --- start
Alice: Hello traveler!
Alice: Another day, another adventure.
"""
    graph = eager_script.parse_graph(test_script)
    session = GameSession(graph)
    session.preferences.auto_forward_time = 0.5

    # 1. Start dialogue with typewriter reveal active
    session.preferences.text_speed = 10.0  # 10 chars/sec; ~1.5s for 15 chars
    session.advance()
    assert session.director.ui_state.text == "Hello traveler!"
    assert session.text_reveal is not None
    assert not session.text_reveal.is_complete

    # In auto_mode, while reveal is incomplete, auto_timer does not tick
    session.auto_mode = True
    session.update(0.5)
    assert not session.text_reveal.is_complete
    assert session.auto_timer == 0.0
    assert session.vm.beat_index == 1

    # 2. Complete reveal manually / naturally
    session.text_reveal.complete_immediately()
    assert session.text_reveal.is_complete

    # 3. Simulate voice clip playing
    class MockVoiceBackend:
        def __init__(self):
            self.voice_playing = True

        def is_playing(self, channel: str) -> bool:
            return self.voice_playing if channel == "voice" else False

        def play(self, *args, **kwargs): pass
        def stop(self, *args, **kwargs): pass
        def set_volume(self, *args, **kwargs): pass
        def pause(self, *args, **kwargs): pass
        def resume(self, *args, **kwargs): pass
        def update(self, *args, **kwargs): pass
        def shutdown(self): pass

    mock_backend = MockVoiceBackend()
    session.audio.backend = mock_backend
    session.audio.channels["voice"].is_playing = True

    # While voice clip is playing, auto_timer does NOT tick
    session.update(0.5)
    assert session.audio.is_playing("voice") is True
    assert session.auto_timer == 0.0
    assert session.vm.beat_index == 1

    # 4. Once voice clip finishes, auto_timer ticks and scales by character count
    mock_backend.voice_playing = False
    session.audio.channels["voice"].is_playing = False
    assert session.audio.is_playing("voice") is False

    # Threshold = 0.5 (base) + 15 * 0.02 = 0.8s
    session.update(0.5)
    assert session.auto_timer == 0.5
    assert session.vm.beat_index == 1

    # Now step past remaining threshold
    session.update(0.35)
    assert session.vm.beat_index == 2
    assert session.director.ui_state.text == "Another day, another adventure."


def test_session_disabled_choices_ignore_clicks_and_keyboard() -> None:
    test_script = """
## Start --- start
Alice: Choose your path.
? Available Option (scene_a)
? Locked Option (scene_b) if has_key
? Another Valid Option (scene_c)

## Scene A --- scene_a
Alice: Path A taken.

## Scene B --- scene_b
Alice: Path B taken.

## Scene C --- scene_c
Alice: Path C taken.
"""
    graph = eager_script.parse_graph(test_script)
    session = GameSession(graph)

    # Initially has_key is not set, so second option is disabled (enabled=False)
    ev = session.advance()
    assert ev is not None and ev.type == "dialogue"
    ev_choice = session.advance()
    assert isinstance(ev_choice, ChoicePromptEvent)
    assert len(ev_choice.options) == 3
    assert ev_choice.options[0].enabled is True
    assert ev_choice.options[1].enabled is False
    assert ev_choice.options[2].enabled is True

    # 1. Overlay choice menu hit test on disabled option returns None
    menu = session.overlay.choice_menu
    r1 = menu.layout()[1]
    # Click on disabled option via POINTER_CLICK is ignored (does not crash or select)
    assert session.handle_input(InputAction.POINTER_CLICK, x=r1[0] + r1[2] / 2, y=r1[1] + r1[3] / 2) is None
    assert session.active_choice_prompt is not None

    # 2. Calling session.choose on disabled option index returns None without raising StoryRuntimeError
    assert session.choose(1) is None
    assert session.active_choice_prompt is not None

    # 3. Keyboard navigation skips disabled option
    # First NAV_DOWN moves to first enabled option (index 0)
    session.handle_input(InputAction.NAV_DOWN)
    assert menu.selected_index == 0
    # Next NAV_DOWN skips index 1 and goes directly to index 2!
    session.handle_input(InputAction.NAV_DOWN)
    assert menu.selected_index == 2
    # NAV_UP goes back to index 0 (skipping 1)
    session.handle_input(InputAction.NAV_UP)
    assert menu.selected_index == 0

    # 4. Confirming enabled option branches properly
    res = session.handle_input(InputAction.CONFIRM)
    assert res is not None
    assert session.director.ui_state.text == "Path A taken."


def test_session_disables_vm_beat_history() -> None:
    from eager_runtime.runtime import StoryVM

    graph = eager_script.parse_graph(SAMPLE_STORY)
    session = GameSession(graph)
    assert not hasattr(session.vm, "_history")
    assert not hasattr(session.vm, "history_enabled")

    vm_standalone = StoryVM(graph)
    assert not hasattr(vm_standalone, "_history")
    assert not hasattr(vm_standalone, "history_enabled")
    session2 = GameSession(vm_standalone)
    assert not hasattr(session2.vm, "_history")


def test_character_metadata_registration_and_speaker_styling() -> None:
    script = """
@character alice "Alice" asset_prefix=alice_uniform color="#ff0000" default_expression=smile side_image="alice_side.png"
## Start --- start
alice: Hello there!
"""
    graph = eager_script.parse_graph(script)
    session = GameSession(graph)

    # Check character was registered on director
    assert "alice" in session.director.characters
    cfg = session.director.characters["alice"]
    assert (cfg.get("asset_prefix") if isinstance(cfg, dict) else cfg.asset_prefix) == "alice_uniform"
    assert (cfg.get("side_image") if isinstance(cfg, dict) else cfg.side_image) == "alice_side.png"

    # Advance dialogue
    ev = session.advance()
    assert ev is not None
    assert session.director.ui_state.speaker == "Alice"
    assert session.director.ui_state.side_image == "alice_side.png"
    assert session.director.ui_state.speaker_color == Color.from_hex("#ff0000")


def test_session_handle_input_delegates_to_ui_protocol_methods() -> None:
    """Verify handle_input interacts with UI purely via UIProtocol methods without widget reaching."""
    from eager_core.protocols import UIProtocol

    class PureProtocolUI:
        def __init__(self) -> None:
            self.error_overlay: str | None = None
            self.selected_choice: int | None = None
            self.input_text: str = ""
            self.revealed: bool = False
            self.input_updated_dt: float = 0.0

        def set_viewport(self, width: int, height: int) -> None:
            pass

        def draw(self, *args: Any, **kwargs: Any) -> None:
            pass

        def sync(self, *args: Any, **kwargs: Any) -> None:
            pass

        def hit_test_choice(self, x: float, y: float) -> int | None:
            return 1

        def hit_test_quick_action(self, x: float, y: float) -> str | None:
            return None

        def get_selected_choice(self) -> int | None:
            return self.selected_choice

        def set_selected_choice(self, index: int | None) -> None:
            self.selected_choice = index

        def set_choice_options(self, options: Any) -> None:
            pass

        def set_input_text(self, text: str) -> None:
            self.input_text = text

        def update_input(self, dt: float) -> None:
            self.input_updated_dt += dt

        def set_dialogue_visible_chars(
            self,
            visible_chars: int | None = None,
            *,
            show_arrow: bool = True,
        ) -> None:
            pass

        def complete_dialogue_reveal(self, *, show_arrow: bool = True) -> None:
            self.revealed = True

        def get_hovered_quick_action(self) -> str | None:
            return None

        def set_hovered_quick_action(self, action: str | None) -> None:
            pass

    ui = PureProtocolUI()
    assert isinstance(ui, UIProtocol)

    story = """
## Start --- start
? Opt 1 (opt1)
? Opt 2 (opt2)

## Opt 1 --- opt1
Alice: Chosen 1.

## Opt 2 --- opt2
Alice: Chosen 2.
"""
    graph = eager_script.parse_graph(story)
    session = GameSession(graph, ui=ui)
    session.advance()

    # 1. Choice navigation delegates to get_selected_choice and set_selected_choice
    session.handle_input(InputAction.NAV_DOWN)
    assert ui.selected_choice == 0

    session.handle_input(InputAction.NAV_DOWN)
    assert ui.selected_choice == 1

    # Hover update
    session.handle_input(InputAction.POINTER_MOVE, x=10.0, y=10.0)
    assert ui.selected_choice == 1

    # Confirm choice
    session.handle_input(InputAction.CONFIRM)
    assert session.director.ui_state.text == "Chosen 2."


def test_input_prompt_event_and_submission(tmp_path: Path):
    script = """
## Start
~ input player_name "What is your name?"
Alice: Hello, [player_name]!
"""
    script_file = tmp_path / "story.es"
    script_file.write_text(script, encoding="utf-8")

    session = GameSession(script_file)
    ev = session.advance()

    # Should pause on input_prompt
    assert isinstance(ev, InputPromptEvent)
    assert ev.var_name == "player_name"
    assert ev.prompt == "What is your name?"

    # Advance is blocked until input is submitted
    assert session.advance() == ev

    # Submit input
    diag = session.submit_input("Hero")
    assert isinstance(diag, DialogueEvent)
    assert "Hello, Hero!" in diag.text
    assert session.vm.get_variable("player_name") == "Hero"





