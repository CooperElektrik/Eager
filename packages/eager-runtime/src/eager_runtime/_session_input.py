"""Semantic InputAction routing and quick-menu dispatch for GameSession."""

from __future__ import annotations

from typing import Any

from eager_core.input import InputAction

_SCREEN_NAV_KEYS = {
    InputAction.NAV_LEFT: "left",
    InputAction.NAV_RIGHT: "right",
    InputAction.CONFIRM: "confirm",
}


def handle_quick_action(session: Any, action_name: str) -> Any:
    """Handle clicks on the in-game quick menu buttons."""
    if action_name == "log":
        return session.screens.show("history", session)
    if action_name == "skip":
        session.skip_mode = not session.skip_mode
        return session.skip_mode
    if action_name == "auto":
        session.auto_mode = not session.auto_mode
        return session.auto_mode
    if action_name == "save":
        return session.screens.show("save", session)
    if action_name == "load":
        return session.screens.show("load", session)
    if action_name == "quicksave":
        return session.quicksave()
    if action_name == "quickload":
        return session.quickload()
    if action_name == "prefs":
        return session.screens.show("preferences", session)
    return None


def _complete_text_reveal(session: Any) -> bool:
    """Finish an active typewriter reveal immediately if still in progress."""
    if session.text_reveal is None or session.text_reveal.is_complete:
        return False
    session.text_reveal.complete_immediately()
    session.director.ui_state.visible_chars = None
    if hasattr(session.overlay, "complete_dialogue_reveal"):
        session.overlay.complete_dialogue_reveal(show_arrow=(session.active_choice_prompt is None))
    return True


def _handle_screen_input(session: Any, action: InputAction, payload: dict[str, Any]) -> Any:
    """Route input while a modal screen (title, save, load, history, prefs) is active."""
    if action in (InputAction.GAME_MENU, InputAction.CANCEL):
        if getattr(session.screens.active_screen, "name", "") == "title":
            return True
        session.screens.hide(session)
        return True
    if action == InputAction.SCROLL:
        dy = float(payload.get("dy", 0.0))
        active = session.screens.active_screen
        if dy > 0 and hasattr(active, "scroll_up"):
            active.scroll_up()
            return True
        if dy < 0 and hasattr(active, "scroll_down"):
            active.scroll_down()
            return True
    if action in (InputAction.ROLLBACK, InputAction.NAV_UP):
        active = session.screens.active_screen
        if hasattr(active, "scroll_up"):
            active.scroll_up()
            return True
        if hasattr(session.screens, "handle_key"):
            return session.screens.handle_key("nav_up", session)
    if action in (InputAction.ROLL_FORWARD, InputAction.NAV_DOWN):
        active = session.screens.active_screen
        if hasattr(active, "scroll_down"):
            active.scroll_down()
            return True
        if hasattr(session.screens, "handle_key"):
            return session.screens.handle_key("nav_down", session)
    if action in _SCREEN_NAV_KEYS and hasattr(session.screens, "handle_key"):
        return session.screens.handle_key(_SCREEN_NAV_KEYS[action], session)
    if action == InputAction.POINTER_CLICK:
        return session.screens.handle_mouse_click(payload.get("x", 0.0), payload.get("y", 0.0))
    if action == InputAction.POINTER_MOVE:
        return bool(session.screens.handle_mouse_move(payload.get("x", 0.0), payload.get("y", 0.0)))
    if action == InputAction.SCREENSHOT:
        return session.take_screenshot(**payload)
    if hasattr(session.screens, "handle_key"):
        raw_key = payload.get("key") or str(action.value)
        return session.screens.handle_key(raw_key, session)
    return None


def _handle_choice_nav_input(session: Any, action: InputAction) -> tuple[bool, Any]:
    """Handle keyboard navigation for an active choice prompt.

    Returns (handled, result).
    """
    opts = session.active_choice_prompt.options
    enabled_indices = [i for i, opt in enumerate(opts) if opt.enabled]
    cur_choice = (
        session.overlay.get_selected_choice()
        if hasattr(session.overlay, "get_selected_choice")
        else None
    )
    if action == InputAction.NAV_UP and enabled_indices:
        if cur_choice in enabled_indices:
            new_idx = enabled_indices[(enabled_indices.index(cur_choice) - 1) % len(enabled_indices)]
        else:
            new_idx = enabled_indices[-1]
        if hasattr(session.overlay, "set_selected_choice"):
            session.overlay.set_selected_choice(new_idx)
        return True, True
    if action == InputAction.NAV_DOWN and enabled_indices:
        if cur_choice in enabled_indices:
            new_idx = enabled_indices[(enabled_indices.index(cur_choice) + 1) % len(enabled_indices)]
        else:
            new_idx = enabled_indices[0]
        if hasattr(session.overlay, "set_selected_choice"):
            session.overlay.set_selected_choice(new_idx)
        return True, True
    if action in (InputAction.ADVANCE, InputAction.CONFIRM) and cur_choice is not None:
        if hasattr(session.overlay, "set_selected_choice"):
            session.overlay.set_selected_choice(None)
        if 0 <= cur_choice < len(opts) and opts[cur_choice].enabled:
            return True, session.choose(cur_choice)
        return True, False
    return False, None


def _handle_text_prompt_input(
    session: Any,
    action: InputAction,
    payload: dict[str, Any],
) -> tuple[bool, Any]:
    """Handle text entry and modal blocking while an InputPromptEvent is active."""
    if action == InputAction.TEXT_CHAR:
        ch = payload.get("char", "")
        if ch:
            session.input_text += ch
            if hasattr(session.overlay, "set_input_text"):
                session.overlay.set_input_text(session.input_text)
            session._ui_dirty = True
            return True, True
    elif action == InputAction.TEXT_BACKSPACE:
        if session.input_text:
            session.input_text = session.input_text[:-1]
            if hasattr(session.overlay, "set_input_text"):
                session.overlay.set_input_text(session.input_text)
            session._ui_dirty = True
            return True, True
    elif action == InputAction.CONFIRM:
        return True, session.submit_input(session.input_text)
    if action in (InputAction.ADVANCE, InputAction.ROLLBACK, InputAction.ROLL_FORWARD):
        return True, None
    return False, None


def _handle_pointer_click(session: Any, x: float, y: float) -> Any:
    """Handle in-game pointer click (unhide UI, quick actions, choices, reveal, advance)."""
    if session.ui_hidden:
        session.ui_hidden = False
        session._ui_dirty = True
        return True
    qa = session.overlay.hit_test_quick_action(x, y)
    if qa:
        return handle_quick_action(session, qa)
    if session.active_choice_prompt is not None:
        idx = session.overlay.hit_test_choice(x, y)
        if idx is not None:
            return session.choose(idx)
        return None
    if _complete_text_reveal(session):
        return True
    if session.is_finished:
        return session.return_to_title()
    if session.active_choice_prompt is None and session.active_input_prompt is None:
        return session.advance()
    return None


def _handle_pointer_move(session: Any, x: float, y: float) -> bool:
    """Update hover highlights for choices and quick-menu buttons."""
    if session.ui_hidden:
        return False
    hover_changed = False
    if session.active_choice_prompt is not None:
        idx = session.overlay.hit_test_choice(x, y)
        cur_idx = session.overlay.get_selected_choice() if hasattr(session.overlay, "get_selected_choice") else None
        if cur_idx != idx:
            if hasattr(session.overlay, "set_selected_choice"):
                session.overlay.set_selected_choice(idx)
            hover_changed = True
    qa = session.overlay.hit_test_quick_action(x, y)
    cur_qa = (
        session.overlay.get_hovered_quick_action()
        if hasattr(session.overlay, "get_hovered_quick_action")
        else None
    )
    if cur_qa != qa:
        if hasattr(session.overlay, "set_hovered_quick_action"):
            session.overlay.set_hovered_quick_action(qa)
        hover_changed = True
    return hover_changed


def handle_input(session: Any, action: InputAction, **payload: Any) -> Any:
    """Process semantic InputAction events."""
    if session.screens.is_active:
        return _handle_screen_input(session, action, payload)

    if action == InputAction.SCROLL:
        dy = float(payload.get("dy", 0.0))
        if dy > 0:
            return session.rollback()
        if dy < 0:
            return session.roll_forward()
        return None

    if session.active_choice_prompt is not None and session.active_choice_prompt.options:
        handled, result = _handle_choice_nav_input(session, action)
        if handled:
            return result

    if session.active_input_prompt is not None:
        handled, result = _handle_text_prompt_input(session, action, payload)
        if handled:
            return result

    if action in (InputAction.ADVANCE, InputAction.CONFIRM):
        if _complete_text_reveal(session):
            return True
        if session.is_finished:
            return session.return_to_title()
        if session.active_choice_prompt is None and session.active_input_prompt is None:
            return session.advance()
        return None

    if action in (InputAction.ROLLBACK, InputAction.NAV_LEFT):
        return session.rollback()
    if action in (InputAction.ROLL_FORWARD, InputAction.NAV_RIGHT):
        return session.roll_forward()
    if action == InputAction.CHOOSE:
        idx = payload.get("index")
        return session.choose(idx) if idx is not None else None
    if action == InputAction.HIDE_UI:
        session.ui_hidden = not session.ui_hidden
        return session.ui_hidden
    if action == InputAction.SKIP_TOGGLE:
        session.skip_mode = not session.skip_mode
        return session.skip_mode
    if action == InputAction.SKIP_HOLD:
        session.skip_mode = True
        return True
    if action == InputAction.SKIP_RELEASE:
        session.skip_mode = False
        return True
    if action == InputAction.AUTO_TOGGLE:
        session.auto_mode = not session.auto_mode
        return session.auto_mode
    if action == InputAction.QUICK_SAVE:
        return session.quicksave()
    if action == InputAction.QUICK_LOAD:
        return session.quickload()
    if action == InputAction.GAME_MENU:
        if hasattr(session.screens, "is_active") and session.screens.is_active:
            session.screens.hide(session)
            return True
        if hasattr(session.screens, "screens") and "game_menu" in session.screens.screens:
            return session.screens.show("game_menu", session)
        return session.screens.show("save", session)
    if action == InputAction.HISTORY:
        return session.screens.show("history", session)
    if action == InputAction.FULLSCREEN:
        session.request_fullscreen()
        return True
    if action == InputAction.QUIT:
        return session.request_quit()
    if action == InputAction.RELOAD:
        return session.hot_reload()
    if action == InputAction.SCREENSHOT:
        return session.take_screenshot(**payload)
    if action == InputAction.POINTER_CLICK:
        return _handle_pointer_click(session, payload.get("x", 0.0), payload.get("y", 0.0))
    if action == InputAction.POINTER_MOVE:
        return _handle_pointer_move(session, payload.get("x", 0.0), payload.get("y", 0.0))
    return None
