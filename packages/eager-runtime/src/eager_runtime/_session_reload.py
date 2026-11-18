"""Hot-reload, error overlay, and presentation reconciliation helpers for GameSession."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eager_runtime._session_bootstrap import discover_locales_dir, register_graph_characters
from eager_runtime.project import load_project_graph, resolve_project_scripts


def set_error_overlay(session: Any, msg: str) -> None:
    """Set error overlay and clear active choices/prompts."""
    session.overlay.error_overlay = msg
    session.director.ui_state.speaker = "Error"
    session.director.ui_state.text = msg
    session.director.ui_state.clear_choices()
    session.active_choice_prompt = None


def clear_error_overlay(session: Any) -> None:
    """Clear the error overlay from the UI."""
    session.overlay.error_overlay = None


def refresh_presentation_after_reload(session: Any, new_scene: Any, display_idx: int) -> None:
    """Update active dialogue/choice display to reflect the reloaded scene body."""
    if not new_scene.body or not (0 <= display_idx < len(new_scene.body)):
        return

    from eager_script import ParsedChoiceSet, ParsedDialogue, ParsedNarration

    from eager_runtime.i18n import compute_beat_id, get_beat_occurrence

    item = new_scene.body[display_idx]
    occ = get_beat_occurrence(new_scene.body, display_idx)
    cid = compute_beat_id(session.vm.current_scene_id or "", item, occurrence=occ)

    if isinstance(item, ParsedDialogue):
        raw_speaker = session.vm._interpolate(item.speaker)
        display_speaker = raw_speaker
        if session.vm._graph.characters:
            cid_match = raw_speaker if raw_speaker in session.vm._graph.characters else raw_speaker.lower()
            if cid_match in session.vm._graph.characters:
                display_speaker = session.vm._graph.characters[cid_match].get("name", raw_speaker)
        interp_speaker = session.vm._translate_speaker(display_speaker)
        if interp_speaker == display_speaker and raw_speaker != display_speaker:
            translated_raw = session.vm._translate_speaker(raw_speaker)
            if translated_raw != raw_speaker:
                interp_speaker = translated_raw

        raw_text, _ = session.vm._translate_beat(cid, item.text)
        final_text = session.vm._interpolate(raw_text)

        char_cfg = None
        if hasattr(session.director, "find_character"):
            char_cfg = session.director.find_character(interp_speaker)
            if char_cfg is None and raw_speaker != interp_speaker:
                char_cfg = session.director.find_character(raw_speaker)
            if char_cfg is None and display_speaker != interp_speaker:
                char_cfg = session.director.find_character(display_speaker)

        char_color = (
            getattr(char_cfg, "color", None)
            if not isinstance(char_cfg, dict)
            else char_cfg.get("color")
        )

        session.director.ui_state.speaker = interp_speaker
        session.director.ui_state.text = final_text
        session.director.ui_state.emotion = item.emotion
        if hasattr(session.director, "resolve_side_image"):
            side = session.director.resolve_side_image(interp_speaker, item.emotion)
            if not side and raw_speaker != interp_speaker:
                side = session.director.resolve_side_image(raw_speaker, item.emotion)
            session.director.ui_state.side_image = side
        elif isinstance(char_cfg, dict):
            session.director.ui_state.side_image = char_cfg.get("side_image")
        session.director.ui_state.speaker_color = char_color

        if getattr(session.director.ui_state, "nvl_mode", False) and getattr(
            session.director.ui_state, "nvl_entries", None
        ):
            session.director.ui_state.nvl_entries[-1].speaker = interp_speaker
            session.director.ui_state.nvl_entries[-1].text = final_text
            session.director.ui_state.nvl_entries[-1].emotion = item.emotion

        session.director.ui_state.visible_chars = None
        session.text_reveal = None
    elif isinstance(item, ParsedNarration):
        raw_text, _ = session.vm._translate_beat(cid, item.text)
        final_text = session.vm._interpolate(raw_text)
        session.director.ui_state.speaker = None
        session.director.ui_state.text = final_text
        session.director.ui_state.emotion = None
        session.director.ui_state.visible_chars = None
        session.text_reveal = None
    elif isinstance(item, ParsedChoiceSet):
        if session.active_choice_prompt is not None or session.vm.pending_choice is not None:
            prompt = session.vm._build_choice_prompt(item)
            session.active_choice_prompt = prompt
            session.vm._pending_choice = prompt


def hot_reload(session: Any, script_path: str | Path | None = None) -> bool:
    """Hot-reload the screenplay from disk, hot-swapping the VM and reconciling state."""
    target_path = Path(script_path) if script_path else session.script_path
    if target_path is None or not target_path.exists():
        set_error_overlay(session, "Hot-reload error: script file not found.")
        session._ui_dirty = True
        return False

    cur_scene_id = session.vm.current_scene_id
    b_idx = session.vm.beat_index

    try:
        new_graph = load_project_graph(target_path, raise_parse_error=True)
        session._project_scripts = resolve_project_scripts(target_path)
        if session.watcher is not None:
            session.watcher.target_paths = session._project_scripts
    except Exception as exc:  # noqa: BLE001
        set_error_overlay(session, f"Hot-reload parse error: {exc}")
        session._ui_dirty = True
        return False

    session.graph = new_graph
    reloaded = session.vm.hot_reload(new_graph)

    if session.translation_manager is not None:
        locales_dir = discover_locales_dir(target_path)
        if locales_dir is not None:
            session.translation_manager.load_directory(locales_dir)

    register_graph_characters(session.director, new_graph, require_protocol=True)
    session.vm.apply_graph_defaults()

    from eager_core.events import HookEvent
    from eager_script import ParsedHook

    for p_item in new_graph.preamble:
        if isinstance(p_item, ParsedHook):
            parts = p_item.hook_name.split(None, 1)
            hook_name = parts[0] if parts else ""
            args = parts[1] if len(parts) > 1 else ""
            session.dispatcher.dispatch(
                HookEvent(
                    hook_name=hook_name,
                    args=args,
                    line_number=p_item.line_number,
                )
            )

    if reloaded and cur_scene_id is not None and cur_scene_id in new_graph.nodes:
        new_scene = new_graph.nodes[cur_scene_id]
        if new_scene.body:
            active_idx = min(max(0, b_idx - 1) if b_idx > 0 else 0, len(new_scene.body) - 1)
        else:
            active_idx = 0
        clear_error_overlay(session)
        refresh_presentation_after_reload(session, new_scene, active_idx)
    else:
        if reloaded and new_graph.entry and new_graph.entry in new_graph.nodes:
            clear_error_overlay(session)
            session.advance()
        else:
            set_error_overlay(session, f"Scene not found: '{cur_scene_id}'")

    session._ui_dirty = True
    session.overlay.sync(
        session.director.ui_state,
        session.active_choice_prompt,
        session.active_input_prompt,
        input_text=session.input_text,
        is_read=session.is_current_beat_read(),
    )

    return True
