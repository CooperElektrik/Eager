"""Unit tests for VisualHistoryManager, StageDirector rollback, and interactive players."""

import pytest
from eager_script import parse_graph

from eager_graphics import StageCompositor, StageDirector, VisualHistoryManager


def test_visual_history_manager_push_pop_clear() -> None:
    history = VisualHistoryManager(max_history=5)
    assert not history.can_rollback
    assert history.depth == 0
    assert history.pop() is None

    # Push items
    history.push({"step": 1, "data": [1, 2, 3]})
    history.push({"step": 2, "data": [4, 5]})
    assert history.can_rollback
    assert history.depth == 2

    # Verify deep copy isolation
    item2 = history.pop()
    assert item2 == {"step": 2, "data": [4, 5]}
    assert history.depth == 1

    item1 = history.pop()
    assert item1 == {"step": 1, "data": [1, 2, 3]}
    assert history.depth == 0
    assert not history.can_rollback

    # Clear
    history.push({"a": 1})
    history.push({"b": 2})
    assert history.depth == 2
    history.clear()
    assert history.depth == 0
    assert not history.can_rollback


def test_visual_history_manager_capacity_limit() -> None:
    history = VisualHistoryManager(max_history=3)
    for i in range(5):
        history.push({"val": i})

    assert history.depth == 3
    # Oldest 0 and 1 dropped, should pop 4, 3, 2
    assert history.pop() == {"val": 4}
    assert history.pop() == {"val": 3}
    assert history.pop() == {"val": 2}
    assert history.pop() is None


def test_visual_history_manager_invalid_capacity() -> None:
    with pytest.raises(ValueError, match="max_history must be at least 1"):
        VisualHistoryManager(max_history=0)


def test_visual_history_manager_serialization_roundtrip() -> None:
    history = VisualHistoryManager(max_history=10)
    history.push({"stage": "scene1", "count": 42})
    history.push({"stage": "scene2", "count": 99})

    data = history.to_dict()
    restored = VisualHistoryManager.from_dict(data)

    assert restored.max_history == 10
    assert restored.depth == 2
    assert restored.pop() == {"stage": "scene2", "count": 99}
    assert restored.pop() == {"stage": "scene1", "count": 42}
    assert restored.pop() is None


def test_director_visual_rollback_removes_character() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    director.enable_visual_history()

    # Initial state: empty stage
    director.snapshot_visual_state()

    # Show a character on stage
    comp.show_character("alice", "happy", position="center", transition="cut")
    assert len(comp.render_list()) == 1
    assert comp.render_list()[0].asset_id == "alice/happy"

    # Rollback removes character
    assert director.rollback_visual_state() is True
    assert len(comp.render_list()) == 0

    # Further rollback returns False since history is empty
    assert director.rollback_visual_state() is False


def test_director_save_load_visual_state_roundtrip() -> None:
    comp = StageCompositor(1920, 1080)
    director = StageDirector(comp)
    director.enable_visual_history()

    # Initial snapshot
    director.snapshot_visual_state()

    comp.set_background("bg/castle", transition="cut")
    comp.show_character("bob", "stern", position="left", transition="cut")
    director.ui_state.speaker = "Bob"
    director.ui_state.text = "State check"

    # Save state
    saved = director.save_visual_state()
    assert "compositor" in saved
    assert "ui_state" in saved
    assert "history" in saved

    # Modify state further
    comp.show_character("alice", "happy", position="right", transition="cut")
    director.ui_state.speaker = "Alice"
    assert len(comp.render_list()) == 3

    # Restore state
    director.load_visual_state(saved)
    assert len(comp.render_list()) == 2
    assert director.ui_state.speaker == "Bob"
    assert director.ui_state.text == "State check"

    # Verify history stack works after restore
    assert director.rollback_visual_state() is True
    # Initial state had empty stage
    assert len(comp.render_list()) == 0


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

    finally:
        player.close()
