# pyright: reportImportCycles=false
"""Scene warp / fast-forward simulation helpers for GameSession."""

from __future__ import annotations

from typing import TYPE_CHECKING

from eager_core.events import (
    ChoicePromptEvent,
    InputPromptEvent,
    SceneEnterEvent,
)

if TYPE_CHECKING:
    from eager_runtime.session import GameSession


def _pick_warp_choice(session: GameSession, event: ChoicePromptEvent, path: list[str], target_scene: str) -> int:
    """Select the choice option index that leads toward target_scene."""
    curr_scene = session.vm.current_scene_id
    if curr_scene in path:
        curr_idx = path.index(curr_scene)
        remaining_targets = set(path[curr_idx + 1 :])
        for idx, opt in enumerate(event.options):
            if opt.target and opt.target in remaining_targets and opt.enabled:
                return idx
    for idx, opt in enumerate(event.options):
        if opt.target and opt.enabled and target_scene in session.vm.graph.reachable_from(opt.target):
            return idx
    return 0


def finalize_warp(session: GameSession, prev_skip: bool = False) -> bool:
    """Reset transient UI/prompt state and push a fresh checkpoint after warping."""
    if hasattr(session.stage, "finish_animations"):
        session.stage.finish_animations()

    if hasattr(session.director, "ui_state"):
        session.director.ui_state.clear_dialogue()
        session.director.ui_state.clear_choices()
        session.director.ui_state.is_finished = False

    session.is_finished = False
    session.mode = "game"
    session.text_reveal = None
    session.active_choice_prompt = None
    session.active_input_prompt = None
    session.skip_mode = prev_skip

    session.checkpoints.clear()
    session.checkpoints.push(session._capture_checkpoint())
    return True


def warp(
    session: GameSession,
    target_scene: str,
    *,
    simulate: bool = True,
    max_steps: int = 10000,
) -> bool:
    """Fast-forward / jump directly to target_scene, reconstructing stage and story state."""
    if target_scene not in session.vm.graph.nodes:
        return False

    if not simulate:
        session.vm.jump(target_scene)
        return finalize_warp(session, prev_skip=session.skip_mode)

    if session.vm.current_scene_id == target_scene and not session.vm.is_ended:
        return True

    entry = session.vm.graph.entry
    path = session.vm.graph.find_path(entry, target_scene) if entry else None
    if path is None:
        root = session.vm.graph.find_root_ancestor(target_scene)
        if root:
            path = session.vm.graph.find_path(root, target_scene)

    if path is None or len(path) <= 1:
        session.vm.jump(target_scene)
        return finalize_warp(session, prev_skip=session.skip_mode)

    session.vm.jump(path[0])
    prev_skip = session.skip_mode
    session.skip_mode = True
    step_count = 0

    seen_beats = session.persistent.get("seen_beats")
    if not isinstance(seen_beats, list):
        seen_beats = []
        session.persistent["seen_beats"] = seen_beats
    seen_beats_set: set[str] = set(seen_beats)
    dirty_persistent = False

    while not session.vm.is_ended and step_count < max_steps:
        step_count += 1
        event = session.vm.step()
        if event is None:
            break

        if isinstance(event, SceneEnterEvent) and event.scene_id == target_scene:
            session.dispatcher.dispatch(event)
            break

        session.dispatcher.dispatch(event)
        session._last_event = event

        beat_id = getattr(event, "beat_id", None)
        if beat_id and beat_id not in seen_beats_set:
            seen_beats_set.add(beat_id)
            seen_beats.append(beat_id)
            dirty_persistent = True

        session._record_backlog_event(event)

        if hasattr(session.director, "finish_animations"):
            session.director.finish_animations()
        elif hasattr(session.stage, "finish_animations"):
            session.stage.finish_animations()

        if isinstance(event, ChoicePromptEvent):
            chosen_idx = _pick_warp_choice(session, event, path, target_scene)
            session.vm.choose(chosen_idx)
        elif isinstance(event, InputPromptEvent):
            val = event.default or "Player"
            session.vm.set_variable(event.var_name, val)
            session.vm._pending_input = None

    if dirty_persistent:
        session.persistent.save()

    if session.vm.current_scene_id != target_scene:
        session.vm.jump(target_scene)

    return finalize_warp(session, prev_skip=prev_skip)
