"""Tests for headless NullStage parity with StageDirector."""

from __future__ import annotations

from eager_core.dispatcher import EventDispatcher
from eager_core.events import (
    DialogueEvent,
    HookEvent,
    InputPromptEvent,
    SceneExitEvent,
)
from eager_core.headless import NullStage


def test_null_stage_binds_scene_exit_input_prompt_and_nvl() -> None:
    stage = NullStage()
    dispatcher = EventDispatcher()
    stage.bind(dispatcher)

    stage.register_character("h", name="Hoshiko", side_image="side_h")

    # Enable NVL mode via hook
    dispatcher.dispatch(HookEvent(hook_name="nvl", args="on", line_number=1))
    assert stage.ui_state.nvl_mode is True

    # Dialogue with character_id
    dispatcher.dispatch(
        DialogueEvent(
            speaker="Hoshiko",
            text="Hello!",
            emotion="happy",
            voice=None,
            line_number=2,
            character_id="h",
        )
    )
    assert stage.ui_state.side_image == "side_h"
    assert len(stage.ui_state.nvl_entries) == 1
    assert stage.ui_state.nvl_entries[0].text == "Hello!"

    # InputPromptEvent
    prompt = InputPromptEvent(var_name="player_name", prompt="Your name?", default="Alex")
    dispatcher.dispatch(prompt)
    assert stage.ui_state.active_input_prompt == prompt

    # SceneExitEvent clears dialogue, choices, and active_input_prompt
    dispatcher.dispatch(
        SceneExitEvent(scene_id="intro", transition_kind="jump", target="next", line_number=3)
    )
    assert stage.ui_state.text == ""
    assert stage.ui_state.active_input_prompt is None

    # nvl_clear hook
    dispatcher.dispatch(HookEvent(hook_name="nvl_clear", args="", line_number=2))
    assert stage.ui_state.nvl_entries == []

    # clear_stage() works without raising TypeError
    stage.clear_stage()
