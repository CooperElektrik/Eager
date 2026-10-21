"""Unit tests for BasePlayer class and deduplicated player functionality."""

from __future__ import annotations

from unittest.mock import MagicMock

from eager_core.events import ChoiceOption, ChoicePromptEvent, InputPromptEvent
from eager_core.input import InputAction, Keymap
from eager_script import parse_graph

from eager_graphics import BasePlayer, DebugOverlayMode


def test_base_player_keysym_normalization() -> None:
    # Digits with underscore or num_
    assert BasePlayer.normalize_keysym("_1") == "1"
    assert BasePlayer.normalize_keysym("_9") == "9"
    assert BasePlayer.normalize_keysym("num_1") == "1"
    assert BasePlayer.normalize_keysym("num_7") == "7"

    # Enters
    assert BasePlayer.normalize_keysym("return") == "enter"
    assert BasePlayer.normalize_keysym("num_enter") == "enter"
    assert BasePlayer.normalize_keysym("enter") == "enter"

    # Navigation / pages
    assert BasePlayer.normalize_keysym("prior") == "pageup"
    assert BasePlayer.normalize_keysym("next") == "pagedown"

    # Control keys
    assert BasePlayer.normalize_keysym("control_l") == "ctrl"
    assert BasePlayer.normalize_keysym("control_r") == "ctrl"
    assert BasePlayer.normalize_keysym("lctrl") == "ctrl"
    assert BasePlayer.normalize_keysym("rctrl") == "ctrl"
    assert BasePlayer.normalize_keysym("ctrl") == "ctrl"

    # Other keys unchanged (lowercased)
    assert BasePlayer.normalize_keysym("SPACE") == "space"
    assert BasePlayer.normalize_keysym("Escape") == "escape"


def test_base_player_lifecycle_and_state_sync() -> None:
    session = MagicMock()
    session.vm = MagicMock()
    session.compositor = MagicMock()
    session.director = MagicMock()
    session.dispatcher = MagicMock()
    session.audio = MagicMock()
    session.keymap = Keymap()
    session.overlay = MagicMock()
    session.screens = None
    session.active_choice_prompt = None
    session.active_input_prompt = None
    session.is_finished = False

    player = BasePlayer(
        session=session,
        width=1280,
        height=720,
        show_fps=True,
    )

    assert player.show_fps is True
    assert player.debug_mode == DebugOverlayMode.FPS

    # Toggle debug overlay
    player.toggle_debug_overlay()
    assert player.show_fps is False
    assert player.debug_mode == DebugOverlayMode.OFF

    # Story advancement
    player.advance_story()
    session.advance.assert_called_once()

    # Choice selection
    player.make_choice(2)
    session.choose.assert_called_once_with(2)

    # Rollback
    session.rollback.return_value = True
    assert player.rollback() is True
    session.rollback.assert_called_once()

    # Hot reload
    session.hot_reload.return_value = True
    assert player.hot_reload() is True
    session.hot_reload.assert_called_once()

    # Viewport resize
    player.on_resize(1920, 1080)
    assert player.width == 1920
    assert player.height == 1080
    session.overlay.set_viewport.assert_called_with(1920, 1080)

    # Close audio
    player.close()
    session.audio.shutdown.assert_called_once()


def test_base_player_input_routing() -> None:
    session = MagicMock()
    session.keymap = Keymap()
    session.active_choice_prompt = None
    session.active_input_prompt = None
    session.is_finished = False

    player = BasePlayer(session=session)

    # Mouse actions
    player.handle_pointer_move(100.0, 200.0)
    session.handle_input.assert_called_with(InputAction.POINTER_MOVE, x=100.0, y=200.0)

    player.handle_pointer_click(100.0, 200.0)
    session.handle_input.assert_called_with(InputAction.POINTER_CLICK, x=100.0, y=200.0)

    player.handle_scroll(1.0)
    session.handle_input.assert_called_with(InputAction.ROLLBACK)

    player.handle_scroll(-1.0)
    session.handle_input.assert_called_with(InputAction.ROLL_FORWARD)

    player.handle_skip_release()
    session.handle_input.assert_called_with(InputAction.SKIP_RELEASE)

    # Key press: Choice selection 1-9
    choice_event = ChoicePromptEvent(
        options=(ChoiceOption(index=0, text="Option 1", target="opt1"), ChoiceOption(index=1, text="Option 2", target="opt2")),
        line_number=1,
    )
    player.active_choice_prompt = choice_event
    assert player.handle_key_press("num_1") is True
    session.handle_input.assert_called_with(InputAction.CHOOSE, index=0)

    # Key press: Text input prompt
    player.active_choice_prompt = None
    input_ev = InputPromptEvent(var_name="name", prompt="Name:")
    player.active_input_prompt = input_ev
    session.active_input_prompt = input_ev

    assert player.handle_key_press("backspace") is True
    session.handle_input.assert_called_with(InputAction.TEXT_BACKSPACE)

    assert player.handle_key_press("a", char="A") is True
    session.handle_input.assert_called_with(InputAction.TEXT_CHAR, char="A")

    assert player.handle_key_press("return") is True
    session.handle_input.assert_called_with(InputAction.CONFIRM)

    assert player.handle_text_input("Bob") is True


def test_concrete_players_inherit_base_player() -> None:
    from eager_runtime import GameSession

    from eager_graphics import PILPlayer, PygletPlayer

    screenplay = """
    ## Start --- start
    Alice: Hello!
    """
    graph = parse_graph(screenplay)
    session = GameSession(graph)

    pil_player = PILPlayer(session=session, visible=False)
    pyglet_player = PygletPlayer(session=session, visible=False)

    try:
        assert isinstance(pil_player, BasePlayer)
        assert isinstance(pyglet_player, BasePlayer)
        assert hasattr(pil_player, "advance_story")
        assert hasattr(pyglet_player, "advance_story")
        assert hasattr(pil_player, "normalize_keysym")
        assert hasattr(pyglet_player, "normalize_keysym")
    finally:
        pil_player.close()
        pyglet_player.close()
