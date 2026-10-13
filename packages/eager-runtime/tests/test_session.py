"""Tests for GameSession, interactions, unified checkpoints, and rollback."""

from __future__ import annotations

import eager_script

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



