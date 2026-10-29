"""Unit tests for StageDirector visual state roundtrip and interactive player rollback."""

from eager_script import parse_graph

from eager_graphics import StageCompositor, StageDirector


def test_director_save_load_visual_state_roundtrip() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)

    comp.set_background("bg/castle", transition="cut")
    comp.show_character("bob", "stern", position="left", transition="cut")
    director.ui_state.speaker = "Bob"
    director.ui_state.text = "State check"

    # Save visual state (contains stage compositor state and UI state)
    saved = director.save_visual_state()
    assert "compositor" in saved
    assert "ui_state" in saved
    ui_saved = director.save_ui_state()

    # Modify state further
    comp.show_character("alice", "happy", position="right", transition="cut")
    director.ui_state.speaker = "Alice"
    assert len(comp.render_list()) == 3

    # Restore state via load_visual_state alone
    director.load_visual_state(saved)
    assert len(comp.render_list()) == 2
    assert director.ui_state.speaker == "Bob"
    assert director.ui_state.text == "State check"

    director.restore_ui_state(ui_saved)
    assert len(comp.render_list()) == 2
    assert director.ui_state.speaker == "Bob"
    assert director.ui_state.text == "State check"


def test_interactive_player_rollback_updates_compositor_stage_pyglet() -> None:
    from eager_graphics.renderers.pyglet import PygletPlayer

    screenplay = """
    ## Start --- start
    ~ bg tavern with cut
    ~ show alice smiling at left with cut
    Alice: Welcome!
    ~ show bob sad at right with cut
    Bob: I am sad.
    """
    from eager_runtime import GameSession

    graph = parse_graph(screenplay)
    session = GameSession(graph)
    compositor = session.compositor

    player = PygletPlayer(
        session=session,
        width=800,
        height=450,
        visible=False,
    )

    try:
        # Initial beat: Alice on stage
        assert player.current_speaker == "Alice"
        assert player.current_text == "Welcome!"
        items1 = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items1)
        assert not any(it.asset_id == "bob/sad" for it in items1)

        # Advance to Bob
        player.advance_story()
        assert player.current_speaker == "Bob"
        assert player.current_text == "I am sad."
        items2 = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items2)
        assert any(it.asset_id == "bob/sad" for it in items2)

        # Rollback
        assert player.rollback() is True
        assert player.current_speaker == "Alice"
        assert player.current_text == "Welcome!"
        items_rolled_back = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items_rolled_back)
        assert not any(it.asset_id == "bob/sad" for it in items_rolled_back)

        # Roll forward (Redo)
        assert player.roll_forward() is True
        assert player.current_speaker == "Bob"
        assert player.current_text == "I am sad."
        items_redone = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items_redone)
        assert any(it.asset_id == "bob/sad" for it in items_redone)

    finally:
        player.close()


def test_interactive_player_rollback_updates_compositor_stage_pil() -> None:
    from eager_graphics.renderers.pil import PILPlayer

    screenplay = """
    ## Start --- start
    ~ bg tavern with cut
    ~ show alice smiling at left with cut
    Alice: Welcome!
    ~ show bob sad at right with cut
    Bob: I am sad.
    """
    from eager_runtime import GameSession

    graph = parse_graph(screenplay)
    session = GameSession(graph)
    compositor = session.compositor

    player = PILPlayer(
        session=session,
        width=800,
        height=450,
        visible=False,
    )

    try:
        # Initial beat: Alice on stage
        assert player.current_speaker == "Alice"
        assert player.current_text == "Welcome!"
        items1 = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items1)
        assert not any(it.asset_id == "bob/sad" for it in items1)

        # Advance to Bob
        player.advance_story()
        assert player.current_speaker == "Bob"
        assert player.current_text == "I am sad."
        items2 = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items2)
        assert any(it.asset_id == "bob/sad" for it in items2)

        # Rollback
        assert player.rollback() is True
        assert player.current_speaker == "Alice"
        assert player.current_text == "Welcome!"
        items_rolled_back = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items_rolled_back)
        assert not any(it.asset_id == "bob/sad" for it in items_rolled_back)

        # Roll forward (Redo)
        assert player.roll_forward() is True
        assert player.current_speaker == "Bob"
        assert player.current_text == "I am sad."
        items_redone = compositor.render_list()
        assert any(it.asset_id == "alice/smiling" for it in items_redone)
        assert any(it.asset_id == "bob/sad" for it in items_redone)

    finally:
        player.close()
