"""Unit tests for BasePlayer class and deduplicated player functionality."""

from __future__ import annotations

from unittest.mock import MagicMock

from eager.core.events import ChoiceOption, ChoicePromptEvent
from eager.core.input import InputAction, Keymap
from eager.script import parse_graph
from eager.ui.player import BasePlayer


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
    session.is_finished = False

    player = BasePlayer(
        session=session,
        width=1280,
        height=720,
    )

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
    session.is_finished = False

    player = BasePlayer(session=session)

    # Mouse actions
    player.handle_pointer_move(100.0, 200.0)
    session.handle_input.assert_called_with(InputAction.POINTER_MOVE, x=100.0, y=200.0)

    player.handle_pointer_click(100.0, 200.0)
    session.handle_input.assert_called_with(InputAction.POINTER_CLICK, x=100.0, y=200.0)

    player.handle_scroll(1.0)
    session.handle_input.assert_called_with(InputAction.SCROLL, dy=1.0)

    player.handle_scroll(-1.0)
    session.handle_input.assert_called_with(InputAction.SCROLL, dy=-1.0)

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


def test_pyglet_player_inherits_base_player() -> None:
    from eager.session import GameSession
    from eager.ui.pyglet_player import PygletPlayer

    screenplay = """
    ## Start --- start
    Alice: Hello!
    """
    graph = parse_graph(screenplay)
    session = GameSession(graph)

    pyglet_player = PygletPlayer(session=session, visible=False)

    try:
        assert isinstance(pyglet_player, BasePlayer)
        assert hasattr(pyglet_player, "advance_story")
        assert hasattr(pyglet_player, "normalize_keysym")

        # C8: PygletPlayer.on_resize must propagate to overlay & renderer even after Window updates width/height
        pyglet_player.on_resize(1600, 900)
        assert pyglet_player.overlay.choice_menu.viewport_width == 1600
        assert pyglet_player.renderer.width == 1600
        assert pyglet_player.renderer.height == 900
    finally:
        pyglet_player.close()


def test_base_player_shift_tab_and_resize() -> None:
    from unittest.mock import MagicMock

    from eager.ui.player import BasePlayer
    from eager.ui.screens.builtin import TitleScreen
    from eager.ui.screens.screen import ScreenManager

    session = MagicMock()
    session.keymap = None
    mgr = ScreenManager()
    title = TitleScreen()
    mgr.register(title)
    session.screens = mgr
    session.active_choice_prompt = None
    session.is_finished = False

    player = BasePlayer(session=session)
    player.close = MagicMock()  # type: ignore[method-assign]

    # Shift+Tab navigates backward on active Screen
    mgr.show("title", session)
    title.handle_key("down")
    title.handle_key("down")
    assert title._focused_button_index == 1
    assert player.handle_key_press("tab", is_shift=True) is True
    assert title._focused_button_index == 0

    # on_resize updates screens viewport
    player.on_resize(1920, 1080)
    assert mgr.viewport_width == 1920
    assert mgr.viewport_height == 1080

    # C2: InputAction.QUIT routes through session.handle_input(InputAction.QUIT)
    assert player.handle_key_press("q") is True
    from eager.core.input import InputAction

    session.handle_input.assert_any_call(InputAction.QUIT)
    player.close.assert_not_called()


def test_pyglet_player_close_flushes_session_and_unschedules_clock(tmp_path, monkeypatch) -> None:
    import pyglet

    from eager.session import GameSession
    from eager.ui.pyglet_player import PygletPlayer

    screenplay = """
    ## Start --- start
    Alice: Hello!
    """
    graph = parse_graph(screenplay)
    session = GameSession(graph, save_dir=tmp_path)
    player = PygletPlayer(session=session, visible=False)

    unscheduled: list[object] = []
    orig_unschedule = pyglet.clock.unschedule

    def spy_unschedule(func: object) -> None:
        unscheduled.append(func)
        orig_unschedule(func)  # type: ignore[arg-type]

    monkeypatch.setattr(pyglet.clock, "unschedule", spy_unschedule)

    # Mark persistent dirty so request_quit() has observable side effects
    session.persistent.unlocked = True
    session._persistent_dirty = True

    player.close()

    assert player.tick in unscheduled
    assert not session._persistent_dirty
    assert (tmp_path / "persistent.json").is_file()
    assert (tmp_path / "auto_1.json").is_file()
