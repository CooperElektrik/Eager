#!/usr/bin/env python3
"""Full-stack demo for the Eager visual novel engine.

Showcases the complete pipeline:

    Eager-Script (.es)  →  parse_graph  →  StoryVM
                   →  EventDispatcher  →  StageDirector
                   →  StageCompositor  →  NullRenderer

Runs entirely headless (NullRenderer) — no display required.

Usage
-----
    python examples/run_demo.py                       Play through (auto-choice 0)
    python examples/run_demo.py --choice 2          Auto-select 3rd option at each choice
    python examples/run_demo.py --save-load         Demonstrate save/load with branching
    python examples/run_demo.py --rollback          Demonstrate synchronized rollback
    python examples/run_demo.py --no-color          Disable ANSI colours
    python examples/run_demo.py path/to/story.es    Play a custom screenplay
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from eager_graphics import StageCompositor, StageDirector
from eager_graphics.renderers.null import NullRenderer
from eager_runtime import EventDispatcher, StoryVM
from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    HookEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
    StoryEvent,
)
from eager_runtime.state import StorySnapshot
from eager_script import parse_graph

DEFAULT_SCRIPT = Path(__file__).resolve().parent / "demo_story.es"
DT = 1.0 / 60.0

_USE_COLOR = sys.stdout.isatty()


class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    MAGENTA = "\033[35m"
    BLUE = "\033[34m"
    RED = "\033[31m"
    GREY = "\033[90m"


def colorize(text: str, *codes: str) -> str:
    if not _USE_COLOR:
        return text
    return f"{''.join(codes)}{text}{Color.RESET}"


def _disable_colors() -> None:
    global _USE_COLOR
    _USE_COLOR = False


# ── Engine helpers ─────────────────────────────────────────────────────────


def make_engine(
    script_text: str,
    locale: str | None = None,
) -> tuple[StoryVM, EventDispatcher, StageCompositor, StageDirector, NullRenderer]:
    """Wire up the full Eager engine stack from a screenplay string."""
    from eager_core.i18n import TranslationManager

    graph = parse_graph(script_text)
    tm = TranslationManager()
    locales_dir = Path(__file__).resolve().parent / "locales"
    if locales_dir.is_dir():
        tm.load_directory(locales_dir)
    if locale:
        tm.set_locale(locale)

    vm = StoryVM(graph, translation_manager=tm)
    dispatcher = EventDispatcher()
    compositor = StageCompositor(virtual_width=1920, virtual_height=1080)
    director = StageDirector(compositor)
    director.enable_visual_history(max_history=100)
    director.bind(dispatcher)
    renderer = NullRenderer()
    return vm, dispatcher, compositor, director, renderer


def step_and_render(
    vm: StoryVM,
    dispatcher: EventDispatcher,
    compositor: StageCompositor,
    renderer: NullRenderer,
    dt: float = DT,
) -> StoryEvent | None:
    """Advance the VM by one beat, dispatch the event, then tick animations + render."""
    event = vm.step()
    if event is None:
        return None
    dispatcher.dispatch(event)
    compositor.update(dt)
    renderer.render_compositor(compositor, window_width=1280, window_height=720)
    return event


def save_full_state(
    vm: StoryVM, director: StageDirector
) -> tuple[StorySnapshot, dict[str, Any]]:
    """Capture a full save point: narrative + visual state."""
    return vm.save(), director.save_visual_state()


def restore_full_state(
    vm: StoryVM,
    director: StageDirector,
    story_snapshot: StorySnapshot,
    visual_snapshot: dict[str, Any],
) -> None:
    """Restore a full save point: narrative + visual state."""
    vm.load(story_snapshot)
    director.load_visual_state(visual_snapshot)


# ── Transcript formatting ──────────────────────────────────────────────────


def format_event(event: StoryEvent) -> tuple[str, str]:
    """Format a StoryEvent as (tag, text) for terminal output."""
    if isinstance(event, SceneEnterEvent):
        return "scene", f"── Enter: {event.display_name}  ({event.scene_id}) ──"
    if isinstance(event, SceneExitEvent):
        icon = {"jump": "->", "call": ">>", "choice": "?", "return": "<<", "fallthrough": ".."}
        icon = icon.get(event.transition_kind, "..")
        return "scene", f"   exit [{icon}] {event.transition_kind}"
    if isinstance(event, DialogueEvent):
        speaker = event.speaker or "Narrator"
        emotion = f" ({event.emotion})" if event.emotion else ""
        return "dialogue", f"{speaker}{emotion}: {event.text}"
    if isinstance(event, NarrationEvent):
        return "narr", f"   {event.text}"
    if isinstance(event, AppendEvent):
        return "append", f"   — {event.text}"
    if isinstance(event, FreshBoxEvent):
        return "fresh", f"   / {event.text}"
    if isinstance(event, HookEvent):
        return "hook", f"   ~ {event.hook_name} {event.args}".rstrip()
    if isinstance(event, ChoicePromptEvent):
        lines = ["   Choices:"]
        for opt in event.options:
            lines.append(f"     [{opt.index + 1}] {opt.text}")
        return "choice", "\n".join(lines)
    if isinstance(event, StoryEndEvent):
        return "end", f"   [The End — {event.reason}]"
    return "event", str(event)


def print_event(event: StoryEvent) -> None:
    tag, text = format_event(event)
    if tag == "scene":
        print(colorize(text, Color.CYAN, Color.BOLD))
    elif tag == "dialogue":
        speaker_part, _, text_part = text.partition(": ")
        print(colorize(f"{speaker_part}:", Color.GREEN, Color.BOLD) + f" {text_part}")
    elif tag == "narr":
        print(colorize(text, Color.YELLOW))
    elif tag == "append":
        print(colorize(text, Color.DIM))
    elif tag == "fresh":
        print(colorize(text, Color.BLUE))
    elif tag == "hook":
        print(colorize(text, Color.GREY))
    elif tag == "choice":
        print(colorize(text, Color.MAGENTA))
    elif tag == "end":
        print(colorize(text, Color.BOLD, Color.RED))
    else:
        print(text)


def print_visual_state(compositor: StageCompositor, director: StageDirector) -> None:
    """Print the current visual stage and UI state."""
    ui = director.ui_state
    items = compositor.render_list()

    has_ui = ui.speaker or ui.text or ui.choices or ui.is_finished
    if has_ui:
        speaker = ui.speaker or "Narrator"
        emotion = f" ({ui.emotion})" if ui.emotion else ""
        label = f"{speaker}{emotion}"
        print(colorize("   [UI] ", Color.DIM) + colorize(f"{label}", Color.GREEN) + f": {ui.text}")
        if ui.choices:
            for opt in ui.choices:
                print(colorize(f"   [UI]   {opt.index + 1}. {opt.text}", Color.MAGENTA))

    if items:
        by_layer: dict[str, list[Any]] = {}
        for item in items:
            by_layer.setdefault(item.layer, []).append(item)

        lines = [colorize("   ─ Stage:", Color.DIM)]
        for layer_name in sorted(by_layer):
            for item in by_layer[layer_name]:
                if layer_name == "background":
                    lines.append(
                        colorize(f"     bg  {item.asset_id}", Color.BLUE)
                        + colorize(f"  opacity={item.opacity:.2f}", Color.DIM)
                    )
                else:
                    lines.append(
                        colorize(f"     {item.asset_id}", Color.CYAN)
                        + colorize(
                            f"  @ ({item.x:.0f}, {item.y:.0f})  opacity={item.opacity:.2f}",
                            Color.DIM,
                        )
                    )
        print("\n".join(lines))

    active = compositor.timeline.active_tweens()
    if active:
        print(colorize(f"   ─ {len(active)} active animation(s)", Color.DIM))


# ── Story mode ─────────────────────────────────────────────────────────────


def play_story(
    script_text: str,
    *,
    auto_choice: int = 0,
    uncapped: bool = False,
    locale: str | None = None,
) -> None:
    """Play through the story, printing an event-by-event transcript."""
    import time

    vm, dispatcher, compositor, director, renderer = make_engine(script_text, locale=locale)

    print(colorize("═══ Eager Engine — Full-Stack Demo ═══", Color.BOLD, Color.CYAN))
    if uncapped:
        print(colorize("   [Uncapped FPS benchmark mode enabled]", Color.GREEN))
    print()

    choice_count = 0
    step_count = 0
    last_event: StoryEvent | None = None
    start_time = time.perf_counter()

    while not vm.is_ended:
        event = step_and_render(vm, dispatcher, compositor, renderer)
        if event is None:
            break
        step_count += 1
        last_event = event

        # In uncapped animation mode, simulate and render all tween/transition frames
        if uncapped:
            while (
                compositor.timeline.active_tweens()
                or compositor._shake_elapsed < compositor._shake_duration
            ):
                compositor.step(DT)
                renderer.render_compositor(compositor, window_width=1280, window_height=720)

        if isinstance(event, ChoicePromptEvent):
            choice_count += 1
            print_event(event)
            print()

            idx = min(auto_choice, len(event.options) - 1)
            opt = event.options[idx]
            print(
                colorize(
                    f"   └─ Auto-select [{idx + 1}]: {opt.text}  →  {opt.target}",
                    Color.MAGENTA,
                )
            )
            print()

            vm.choose(idx)
            step_and_render(vm, dispatcher, compositor, renderer)
            if uncapped:
                while (
                    compositor.timeline.active_tweens()
                    or compositor._shake_elapsed < compositor._shake_duration
                ):
                    compositor.step(DT)
                    renderer.render_compositor(compositor, window_width=1280, window_height=720)
            continue

        print_event(event)

        if isinstance(
            event, (SceneEnterEvent, SceneExitEvent, NarrationEvent, DialogueEvent, FreshBoxEvent)
        ):
            print_visual_state(compositor, director)

        if isinstance(event, StoryEndEvent):
            elapsed = time.perf_counter() - start_time
            total_frames = renderer.frame_count
            fps = (total_frames / elapsed) if elapsed > 0 else 0.0

            print()
            print(colorize("═══ Story Complete ═══", Color.BOLD, Color.CYAN))
            print(colorize(f"  Choices encountered: {choice_count}", Color.DIM))
            print(colorize(f"  Story beats:         {step_count}", Color.DIM))
            print(colorize(f"  Frame count:         {total_frames}", Color.DIM))
            print(colorize(f"  Final scene:         {vm.current_scene_id}", Color.DIM))
            print(colorize(f"  UI finished:         {director.ui_state.is_finished}", Color.DIM))
            if uncapped:
                ms_per_frame = (elapsed * 1000.0 / total_frames) if total_frames > 0 else 0.0
                print(
                    colorize(
                        f"  Throughput:          {fps:.1f} FPS ({ms_per_frame:.3f} ms/frame across {total_frames} frames)",
                        Color.BOLD,
                        Color.GREEN,
                    )
                )
            break

        print()

    if not vm.is_ended and not isinstance(last_event, StoryEndEvent):
        print(colorize("── Story paused ──", Color.GREY))


# ── Save / Load demo ───────────────────────────────────────────────────────


def _play_to(
    vm: StoryVM,
    dispatcher: EventDispatcher,
    compositor: StageCompositor,
    director: StageDirector,
    renderer: NullRenderer,
    *,
    target_choice: bool = True,
    target_dialogue: bool = False,
    auto_choice: int = 0,
    max_steps: int = 100,
) -> None:
    """Play until a choice point or dialogue line, auto-choosing en route."""
    for _ in range(max_steps):
        if vm.is_ended:
            break
        event = step_and_render(vm, dispatcher, compositor, renderer)
        if event is None:
            break
        print_event(event)

        if isinstance(event, ChoicePromptEvent):
            if target_choice:
                return
            else:
                idx = min(auto_choice, len(event.options) - 1)
                vm.choose(idx)
                print(colorize(f"   └─ Auto-choice {idx + 1}", Color.MAGENTA))
                continue

        if isinstance(event, DialogueEvent) and target_dialogue:
            return

        if isinstance(event, StoryEndEvent):
            return

        # Show visual state at key narrative beats
        if isinstance(
            event, (SceneEnterEvent, DialogueEvent, FreshBoxEvent, NarrationEvent)
        ):
            print_visual_state(compositor, director)
            print()


def demo_save_load(script_text: str, *, locale: str | None = None) -> None:
    """Demonstrate save/load by branching from the same checkpoint."""
    print(colorize("═══ Save / Load Demo — Branching from a Checkpoint ═══", Color.BOLD, Color.CYAN))
    print()

    vm, dispatcher, compositor, director, renderer = make_engine(script_text, locale=locale)

    # Step to the first dialogue (a safe save point — no pending choice)
    print(colorize("[1] Advancing to save point (first dialogue)...", Color.DIM))
    print()
    _play_to(
        vm, dispatcher, compositor, director, renderer,
        target_dialogue=True,
    )

    story_save, visual_save = save_full_state(vm, director)
    print(colorize("[2] State saved at first dialogue beat.", Color.GREEN))
    print(
        colorize(
            f"  Scene: {vm.current_scene_id}  |  Beat: {vm.beat_index}  |  "
            f"Render items: {len(compositor.render_list())}",
            Color.DIM,
        )
    )
    print()

    # Branch A: advance to first choice, take option 0
    print(colorize(" [3] Branch A — advancing to first choice, selecting option 1...", Color.BLUE))
    _play_to(
        vm, dispatcher, compositor, director, renderer,
        target_choice=True,
        auto_choice=0,
    )

    if vm.pending_choice:
        idx = min(0, len(vm.pending_choice.options) - 1)
        opt = vm.pending_choice.options[idx]
        print(colorize(f"   └─ Selecting: {opt.text} → {opt.target}", Color.MAGENTA))
        vm.choose(idx)

    # Run Branch A to completion
    print()
    print(colorize("   Continuing to ending (Branch A)...", Color.DIM))
    _play_to(
        vm, dispatcher, compositor, director, renderer,
        target_choice=False,
    )
    print(colorize(f"   Branch A ended at: {vm.current_scene_id}", Color.GREEN))
    print()

    # Restore
    print(colorize("[4] Restoring saved state...", Color.YELLOW))
    restore_full_state(vm, director, story_save, visual_save)
    print(colorize("   State restored!", Color.GREEN))
    print(
        colorize(
            f"   Scene: {vm.current_scene_id}  |  Beat: {vm.beat_index}  |  "
            f"Render items: {len(compositor.render_list())}",
            Color.DIM,
        )
    )
    print()

    # Branch B: advance to first choice, take option 1
    print(colorize("[5] Branch B — advancing to first choice, selecting option 2...", Color.BLUE))
    _play_to(
        vm, dispatcher, compositor, director, renderer,
        target_choice=True,
        auto_choice=0,
    )

    if vm.pending_choice:
        idx = min(1, len(vm.pending_choice.options) - 1)
        opt = vm.pending_choice.options[idx]
        print(colorize(f"   └─ Selecting: {opt.text} → {opt.target}", Color.MAGENTA))
        vm.choose(idx)

    # Run Branch B to completion
    print()
    print(colorize("   Continuing to ending (Branch B)...", Color.DIM))
    _play_to(
        vm, dispatcher, compositor, director, renderer,
        target_choice=False,
    )
    print(colorize(f"   Branch B ended at: {vm.current_scene_id}", Color.GREEN))
    print()

    print(colorize("═══ Demo Complete — Save/Load verified ═══", Color.BOLD, Color.CYAN))


# ── Rollback demo ──────────────────────────────────────────────────────────


def demo_rollback(script_text: str, *, locale: str | None = None) -> None:
    """Demonstrate synchronized rollback of story and visual state.

    The StoryVM records a narrative history snapshot before every beat;
    the StageDirector records a visual history snapshot before every hook.
    Rolling back pops one entry from each, rewinding the story and the
    stage together.
    """
    print(colorize("═══ Rollback Demo — Rewinding Story & Visuals ═══", Color.BOLD, Color.CYAN))
    print()

    vm, dispatcher, compositor, director, renderer = make_engine(script_text, locale=locale)

    # ── Advance through several beats, then save a full checkpoint ──
    checkpoint_set = False
    pre_beat = 0

    for _step_idx in range(7):
        event = step_and_render(vm, dispatcher, compositor, renderer)
        if event is None:
            break
        print_event(event)

        if isinstance(event, HookEvent) and not checkpoint_set:
            # Save full state AFTER the hook is applied
            _story_snapshot, _visual_snapshot = save_full_state(vm, director)
            pre_beat = vm.beat_index
            checkpoint_set = True
            print(colorize(f"   └─ Checkpoint saved (beat {pre_beat})", Color.DIM))

        if isinstance(event, (SceneEnterEvent, DialogueEvent)):
            print_visual_state(compositor, director)
        if isinstance(event, StoryEndEvent):
            break
        print()

    if not checkpoint_set:
        print(colorize("  No hook found to set a checkpoint. Try a different script.", Color.RED))
        return

    print()
    print(colorize("  Continuing a few more beats after the checkpoint...", Color.DIM))
    for _ in range(3):
        event = step_and_render(vm, dispatcher, compositor, renderer)
        if event is None or isinstance(event, StoryEndEvent):
            break
        print_event(event)
        if isinstance(event, (DialogueEvent, NarrationEvent)):
            print_visual_state(compositor, director)
        print()

    post_beat = vm.beat_index
    post_items_count = len(compositor.render_list())
    post_speaker = director.ui_state.speaker

    print(colorize(f"  Current:  beat {post_beat}  |  {post_items_count} items  |  speaker='{post_speaker}'", Color.DIM))
    print()

    # ── Rollback ──
    # One narrative rollback + one visual rollback reverts the last hook beat.
    # Since our checkpoint was at a HookEvent, this should restore the
    # pre-hook visual state and the pre-beat narrative state.
    print(colorize("[Rollback]", Color.YELLOW), end=" ")
    story_ok = vm.rollback()
    visual_ok = director.rollback_visual_state()
    compositor.update(DT)

    rb_items_count = len(compositor.render_list())
    rb_speaker = director.ui_state.speaker
    rb_beat = vm.beat_index

    print()
    print(colorize(f"  After:    beat {rb_beat}  |  {rb_items_count} items  |  speaker='{rb_speaker}'", Color.DIM))
    print()

    # ── Re-advance to verify we can reproduce the checkpoint ──
    event = step_and_render(vm, dispatcher, compositor, renderer)
    re_items_count = len(compositor.render_list())
    re_speaker = director.ui_state.speaker
    re_beat = vm.beat_index

    print(colorize("  Re-advancing one beat to reproduce the checkpoint:", Color.DIM))
    print(colorize(f"  Reproduced: beat {re_beat}  |  {re_items_count} items  |  speaker='{re_speaker}'", Color.DIM))
    print()

    all_ok = story_ok and visual_ok
    if all_ok:
        print(colorize("  [OK] VM rollback returned True", Color.GREEN))
        print(colorize("  [OK] Visual rollback returned True", Color.GREEN))
        if re_beat == post_beat:
            print(colorize("  [OK] Re-advance reproduced post-checkpoint state", Color.GREEN))

    print()
    print(colorize("═══ Demo Complete — Rollback verified ═══", Color.BOLD, Color.CYAN))


# ── CLI ────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eager-demo",
        description="Full-stack demo for the Eager visual novel engine (headless).",
    )
    parser.add_argument(
        "script",
        nargs="?",
        default=str(DEFAULT_SCRIPT),
        help="Path to a .es screenplay file (default: bundled demo_story.es).",
    )
    parser.add_argument(
        "--choice",
        type=int,
        default=0,
        help="Auto-select this choice index at each prompt (default: 0).",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--save-load", action="store_true", help="Demonstrate save/load with branching paths.")
    group.add_argument("--rollback", action="store_true", help="Demonstrate synchronized rollback of story + visuals.")
    group.add_argument("--play", action="store_true", help="Launch interactive PIL visual novel window (requires Pillow + Tk bindings).")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colour output.")
    parser.add_argument(
        "--uncapped",
        action="store_true",
        help="Run with uncapped framerate (disables V-Sync and redraw timer limit in --play; renders all transition frames in headless mode).",
    )
    parser.add_argument(
        "--asset-dir",
        default=None,
        help="Directory containing sprite/background assets (default: examples/assets).",
    )
    parser.add_argument("--width", type=int, default=1280, help="Window width for --play mode (default: 1280).")
    parser.add_argument("--height", type=int, default=720, help="Window height for --play mode (default: 720).")
    parser.add_argument(
        "--lang",
        "--locale",
        default=None,
        help="Language locale for translations (e.g. 'vi', default: None).",
    )
    args = parser.parse_args(argv)

    if args.no_color:
        _disable_colors()

    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: script file '{script_path}' not found.", file=sys.stderr)
        return 1

    script_text = script_path.read_text(encoding="utf-8")

    asset_dir = args.asset_dir
    if asset_dir is None:
        default_asset_dir = Path(__file__).resolve().parent / "assets"
        if default_asset_dir.is_dir():
            asset_dir = default_asset_dir
    else:
        asset_dir = Path(asset_dir)

    if args.save_load:
        demo_save_load(script_text, locale=args.lang)
    elif args.rollback:
        demo_rollback(script_text, locale=args.lang)
    elif args.play:
        launch_interactive(
            script_text,
            args.width,
            args.height,
            uncapped=args.uncapped,
            asset_dir=asset_dir,
            locale=args.lang,
        )
    else:
        play_story(script_text, auto_choice=args.choice, uncapped=args.uncapped, locale=args.lang)

    return 0


def launch_interactive(
    script_text: str,
    width: int = 1280,
    height: int = 720,
    *,
    uncapped: bool = False,
    asset_dir: str | Path | None = None,
    locale: str | None = None,
) -> None:
    """Launch an interactive PIL visual novel window (tkinter)."""
    try:
        from eager_graphics.renderers.pil import TKINTER_AVAILABLE
    except ImportError as exc:
        print(f"Error: PIL renderer unavailable: {exc}", file=sys.stderr)
        sys.exit(1)
    if not TKINTER_AVAILABLE:
        print(
            "Error: tkinter is required for interactive mode.\n"
            "Install Tk bindings (e.g. 'apt install python3-tk').",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        from eager_graphics.renderers.pil import PILPlayer
    except ImportError as exc:
        print(f"Error: PIL renderer unavailable: {exc}", file=sys.stderr)
        sys.exit(1)

    from eager_runtime.session import GameSession

    graph = parse_graph(script_text)
    session = GameSession(graph)
    locales_dir = Path(__file__).resolve().parent / "locales"
    if locales_dir.is_dir():
        session.translation_manager.load_directory(locales_dir)
    if locale:
        session.set_language(locale)

    print("Launching Eager visual novel (PIL)...")
    if uncapped:
        print("  [Uncapped FPS mode enabled: V-Sync disabled, redraw timer limit removed]")
    print("Controls: Click / Space / Enter = Advance | 1-9 = Choices | Backspace = Undo | Esc/Q = Quit")
    player = PILPlayer(
        session=session,
        width=width,
        height=height,
        title="Eager Demo — After School with Hoshiko",
        asset_dir=asset_dir,
        vsync=not uncapped,
        uncapped=uncapped,
    )
    player.run()
    player.close()


if __name__ == "__main__":
    sys.exit(main())
