"""Command-line interface for the Eager runtime.

Single entry point is provided:

* ``eager`` — unified commands (``play``, ``inspect``,
  ``test-run``, ``render``, ``run``, ``new``, ``check``, ``build``,
  ``i18n``, ``parse``, ``graph``).  Graphical backends require ``eager[gui]`` extras.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

import eager.script
from eager.script.project import load_project_graph, resolve_project_scripts
from eager.ui.terminal_player import TerminalPlayer
from eager.vm.runtime import StoryVM

__all__ = [
    "build_parser",
    "main",
    "run_inspect",
    "run_play",
    "run_test_run",
]

# ── shared helpers ────────────────────────────────────────────────────


def _build_common_script_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("script", help="Path to the .es screenplay script file.")
    parser.add_argument(
        "--lang",
        "--locale",
        default=None,
        help="Language locale for translations (e.g. 'vi').",
    )


def _version_string() -> str:
    import eager

    return f"eager {eager.__version__}"


# ── eager CLI (text-only, no graphics) ────────────────────────────────


class _SubParsersLike(Protocol):
    def add_parser(self, name: str, *, help: str = ...) -> argparse.ArgumentParser: ...


def _add_i18n_subparser(subparsers: _SubParsersLike) -> None:
    i18n_p = subparsers.add_parser(
        "i18n",
        help="Translation catalog extraction, validation, and management.",
    )
    i18n_sub = i18n_p.add_subparsers(dest="i18n_command", required=True)

    # extract
    ext_p = i18n_sub.add_parser(
        "extract", help="Extract translatable dialogue and choices into a catalog JSON."
    )
    ext_p.add_argument("script", help="Path to .es screenplay file or project directory.")
    ext_p.add_argument("-o", "--output", default=None, help="Output JSON path (default: locales/<locale>.json).")
    ext_p.add_argument("--locale", default="template", help="Target locale code (default: template).")
    ext_p.add_argument("--merge", action="store_true", help="Merge with existing output file, preserving translations.")
    ext_p.set_defaults(func=_cmd_i18n_extract)

    # check
    chk_p = i18n_sub.add_parser(
        "check", help="Check translation coverage and missing strings for a catalog."
    )
    chk_p.add_argument("catalog", help="Path to translation catalog JSON file or locales directory.")
    chk_p.add_argument("--script", required=True, help="Path to .es screenplay file or project directory.")
    chk_p.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if translation coverage is below 100 percent.",
    )
    chk_p.set_defaults(func=_cmd_i18n_check)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``eager`` CLI."""
    parser = argparse.ArgumentParser(
        prog="eager",
        description="Eager narrative runtime and player for Eager-Script screenplay scripts.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=_version_string(),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # play
    play_p = subparsers.add_parser(
        "play", help="Play an Eager-Script screenplay interactively."
    )
    _build_common_script_args(play_p)
    play_p.add_argument("--no-color", action="store_true", help="Disable colored terminal output.")
    play_p.add_argument(
        "--backend",
        choices=["terminal", "pyglet", "pil"],
        default="pil",
        help="Player backend (default: pil). Graphical backends require eager-graphics.",
    )
    play_p.add_argument("--asset-dir", default=None, help="Directory containing sprite/background assets.")
    play_p.add_argument("--warp", default=None, help="Fast-forward / jump directly to scene label.")
    play_p.add_argument("--no-warp-sim", action="store_true", help="Bypass state simulation and jump directly when warping.")
    play_p.add_argument("--skip-title", action="store_true", help="Bypass title screen and start story immediately.")
    play_p.add_argument("--no-audio", action="store_true", help="Disable audio playback (use NullAudioBackend).")
    play_p.add_argument("--watch", "--hot-reload", dest="watch", action="store_true", help="Automatically hot-reload when script changes on disk.")
    play_p.set_defaults(func=run_play)

    # inspect
    inspect_p = subparsers.add_parser(
        "inspect", help="Inspect scenes, entry points, and topology of a screenplay."
    )
    _build_common_script_args(inspect_p)
    inspect_p.set_defaults(func=run_inspect)

    # test-run
    test_p = subparsers.add_parser(
        "test-run", help="Perform a headless dry-run execution of a screenplay."
    )
    _build_common_script_args(test_p)
    test_p.add_argument("--max-steps", type=int, default=10000, help="Maximum steps before terminating.")
    test_p.add_argument("--all-paths", action="store_true", help="Exhaustively explore all choice branches.")
    test_p.set_defaults(func=run_test_run)

    # check
    check_p = subparsers.add_parser(
        "check", help="Validate screenplay script, project directory, and asset consistency."
    )
    check_p.add_argument("script", help="Path to .es screenplay file or project directory.")
    check_p.add_argument(
        "--assets",
        action="store_true",
        help="Verify all referenced background, sprite, and audio assets exist on disk.",
    )
    check_p.add_argument(
        "--asset-dir",
        default=None,
        help="Path to assets directory (defaults to assets/ next to script or project).",
    )
    check_p.set_defaults(func=_cmd_check)

    # render
    render_p = subparsers.add_parser(
        "render",
        help="Run a story to completion in headless mode (NullRenderer, no window).",
    )
    render_p.add_argument("script", help="Path to .es screenplay file")
    render_p.add_argument("--asset-dir", default=None, help="Directory containing sprite/background assets.")
    render_p.add_argument("--lang", "--locale", default=None, help="Language locale for translations (e.g. 'vi').")
    render_p.add_argument(
        "--dt",
        type=float,
        default=1.0 / 60.0,
        help="Simulated timestep per frame (default: 1/60 ≈ 60 FPS)",
    )
    render_p.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Safety cap on total story steps",
    )
    render_p.add_argument(
        "--auto-choose",
        type=int,
        default=0,
        help="Automatically select this choice index when a choice prompt appears (default: 0)",
    )
    render_p.set_defaults(func=_cmd_render)

    # run
    run_p = subparsers.add_parser(
        "run",
        help="Run project in directory containing game.toml or script.",
    )
    run_p.add_argument("project_dir", nargs="?", default=".", help="Project directory (default: current directory)")
    run_p.add_argument("--backend", choices=["pyglet", "pil"], default="pil", help="Rendering backend")
    run_p.add_argument("--skip-title", action="store_true", help="Bypass title screen and start story immediately.")
    run_p.add_argument("--no-audio", action="store_true", help="Disable audio playback (use NullAudioBackend).")
    run_p.add_argument("--watch", "--hot-reload", dest="watch", action="store_true", help="Automatically hot-reload when script changes on disk.")
    run_p.add_argument("--warp", default=None, help="Fast-forward / jump directly to scene label.")
    run_p.add_argument("--no-warp-sim", action="store_true", help="Bypass state simulation and jump directly when warping.")
    run_p.add_argument("--lang", "--locale", default=None, help="Language locale for translations (e.g. 'vi').")
    run_p.set_defaults(func=_cmd_run)

    for p in (play_p, run_p):
        p.add_argument(
            "--scale-mode",
            choices=["letterbox", "stretch", "crop", "fit_width", "fit_height"],
            default=None,
            help="Stage viewport scaling mode.",
        )
        p.add_argument(
            "--show-fps",
            dest="show_fps",
            action="store_true",
            default=None,
            help="Display real-time performance FPS overlay.",
        )
        p.add_argument(
            "--uncapped",
            action="store_true",
            default=False,
            help="Run without frame-rate cap / vsync.",
        )
        p.add_argument(
            "--render-preset",
            choices=["performance", "balanced", "quality", "debug"],
            default=None,
            help="Renderer pipeline optimization preset.",
        )

    # new
    new_p = subparsers.add_parser(
        "new",
        help="Scaffold a new Eager visual novel project structure.",
    )
    new_p.add_argument("name", help="Name of project directory to create")
    new_p.add_argument(
        "--demo",
        action="store_true",
        help="Scaffold project using the full showcase demo story and assets instead of the starter template.",
    )
    new_p.set_defaults(func=_cmd_new)

    # build
    build_p = subparsers.add_parser(
        "build",
        help="Bundle an Eager project into a distributable .zip archive (see packaging/build_export.py for standalone executables).",
    )
    build_p.add_argument("project_dir", nargs="?", default=".", help="Project directory (default: current directory)")
    build_p.add_argument("-o", "--output", default=None, help="Output zip archive path")
    build_p.add_argument("--no-check", action="store_true", help="Skip script and asset validation before packaging.")
    build_p.set_defaults(func=_cmd_build)

    # doctor
    doctor_p = subparsers.add_parser(
        "doctor",
        help="Check installed Eager packages, graphical/audio backends, and export tools.",
    )
    doctor_p.set_defaults(func=_cmd_doctor)

    # parse
    parse_p = subparsers.add_parser("parse", help="Parse screenplay into JSON AST.")
    parse_p.add_argument("file", help="Path to .es screenplay file")
    parse_p.add_argument("-o", "--output", help="Path to write JSON output (default: stdout)")
    parse_p.add_argument("--indent", type=int, default=2, help="JSON indentation spaces (default: 2)")
    parse_p.set_defaults(func=_cmd_parse)

    # graph
    graph_p = subparsers.add_parser("graph", help="Export screenplay as a directed scene graph.")
    graph_p.add_argument("file", help="Path to .es screenplay file")
    graph_p.add_argument("-o", "--output", help="Path to write graph output (default: stdout)")
    graph_p.add_argument(
        "--format",
        choices=["json", "dot", "mermaid"],
        default="json",
        help="Graph output format: json, dot, or mermaid (default: json)",
    )
    graph_p.add_argument("--no-body", action="store_true", help="Exclude AST body items from JSON output")
    graph_p.add_argument("--indent", type=int, default=2, help="JSON indentation spaces (default: 2)")
    graph_p.set_defaults(func=_cmd_graph)

    # i18n
    _add_i18n_subparser(subparsers)

    return parser



def run_play(args: argparse.Namespace) -> int:
    """Execute interactive playthrough (PIL graphical by default, or terminal/pyglet via --backend)."""
    backend = getattr(args, "backend", "pil")
    if backend != "terminal":
        return _cmd_play(args)
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Screenplay file '{script_path}' not found.", file=sys.stderr)
        return 1

    graph = load_project_graph(script_path)

    if not graph.nodes:
        print("Warning: Script contains no scenes.", file=sys.stderr)
        return 0

    from eager.core.i18n import TranslationManager

    tm = TranslationManager()
    locales_dir = (script_path if script_path.is_dir() else script_path.resolve().parent) / "locales"
    if locales_dir.is_dir():
        tm.load_directory(locales_dir)
    if getattr(args, "lang", None):
        tm.set_locale(args.lang)

    vm = StoryVM(graph, translation_manager=tm)
    if getattr(args, "warp", None):
        target_scene = args.warp
        if target_scene in vm.graph.nodes:
            vm.jump(target_scene)
            sys.stderr.write(f"Warped directly to scene '{target_scene}'.\n")
        else:
            sys.stderr.write(f"Warning: Warp target '{target_scene}' not found in script.\n")
    player = TerminalPlayer(vm, use_colors=not args.no_color)
    player.play()
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    """Inspect screenplay structure."""
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Screenplay file '{script_path}' not found.", file=sys.stderr)
        return 1

    graph = load_project_graph(script_path)

    print(f"File: {script_path.name}")
    print(f"Entry Scene: {graph.entry or '(None)'}")
    print(f"Total Scenes: {len(graph.nodes)}")
    print(f"Total Transitions: {len(graph.edges)}")
    print(f"Branching Points: {len(graph.branching_points())}")
    print(f"Hubs (in-degree >= 2): {len(graph.hubs())}")
    print(f"Terminal Scenes: {graph.terminal_scenes()}")
    print(f"Dead Ends: {graph.dead_ends()}")
    return 0


def run_test_run(args: argparse.Namespace) -> int:
    """Perform headless test run, optionally exploring all branching paths."""
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Screenplay file '{script_path}' not found.", file=sys.stderr)
        return 1

    graph = load_project_graph(script_path)

    from eager.core.i18n import TranslationManager

    tm = TranslationManager()
    locales_dir = (script_path if script_path.is_dir() else script_path.resolve().parent) / "locales"
    if locales_dir.is_dir():
        tm.load_directory(locales_dir)
    if getattr(args, "lang", None):
        tm.set_locale(args.lang)

    if getattr(args, "all_paths", False):
        # Exhaustive branch exploration: find all terminal paths
        # We model paths as choice index decisions at each choice prompt encountered
        paths_completed = 0
        total_steps = 0
        total_events = 0

        # Stack of choice sequences to explore: [[]] initially
        frontier: list[list[int]] = [[]]
        visited_choice_sequences: set[tuple[int, ...]] = set()

        while frontier:
            decision_path = frontier.pop()
            vm = StoryVM(graph, translation_manager=tm)
            steps = 0
            decision_idx = 0
            current_decisions: list[int] = []

            while not vm.is_ended and steps < args.max_steps:
                event = vm.step()
                if event is None:
                    break
                total_events += 1
                steps += 1
                total_steps += 1

                if vm.pending_choice is not None:
                    prompt = vm.pending_choice
                    enabled_indices = [opt.index for opt in prompt.options if opt.enabled]
                    if not enabled_indices:
                        break

                    if decision_idx < len(decision_path):
                        chosen = decision_path[decision_idx]
                        decision_idx += 1
                        current_decisions.append(chosen)
                        vm.choose(chosen)
                    else:
                        first_opt = enabled_indices[0]
                        for alt in enabled_indices[1:]:
                            alt_seq = tuple(current_decisions + [alt])
                            if alt_seq not in visited_choice_sequences:
                                visited_choice_sequences.add(alt_seq)
                                frontier.append(list(alt_seq))
                        current_decisions.append(first_opt)
                        decision_idx += 1
                        vm.choose(first_opt)

                if vm.pending_input is not None:
                    vm.submit_input(vm.pending_input.default or "Player")

            paths_completed += 1

        print(
            f"All-paths exploration completed: {paths_completed} paths explored, "
            f"{total_steps} steps, {total_events} events dispatched."
        )
        return 0


    vm = StoryVM(graph, translation_manager=tm)
    steps = 0
    events_count = 0

    while not vm.is_ended and steps < args.max_steps:
        event = vm.step()
        if event is None:
            break
        events_count += 1
        steps += 1

        if vm.pending_choice is not None:
            first_enabled = next((opt.index for opt in vm.pending_choice.options if opt.enabled), None)
            if first_enabled is not None:
                vm.choose(first_enabled)
            else:
                break

        if vm.pending_input is not None:
            # Default to placeholder input in headless mode
            vm.submit_input(vm.pending_input.default or "Player")

    print(f"Test run completed: {steps} steps, {events_count} events dispatched, ended: {vm.is_ended}.")
    return 0



# ── eager CLI (unified, graphics optional) ────────────────────────────────


def _create_audio_backend(backend: str, *, no_audio: bool = False) -> Any:
    """Instantiate the matching audio backend for the given render backend."""
    from eager.backends.audio.null import NullAudioBackend

    if no_audio:
        return NullAudioBackend()

    try:
        if backend == "pyglet":
            from eager.backends.audio.pyglet import PygletAudioBackend

            return PygletAudioBackend()
        if backend in ("pil", "miniaudio"):
            from eager.backends.audio.miniaudio import MiniaudioAudioBackend

            return MiniaudioAudioBackend()
    except Exception:  # noqa: BLE001
        return NullAudioBackend()

    return NullAudioBackend()


def _resolve_asset_dir(
    script_path: str | Path | None,
    asset_dir: str | Path | None,
) -> str | None:
    """Resolve the asset directory, falling back to ``assets/`` beside the script."""
    if asset_dir is not None:
        return str(asset_dir)
    if script_path is None:
        return None
    candidate = Path(script_path).resolve().parent / "assets"
    return str(candidate) if candidate.is_dir() else None


def _run_headless(
    session: Any,
    renderer: Any,
    *,
    dt: float = 1.0 / 60.0,
    max_steps: int | None = None,
    auto_choose: int | str | None = None,
) -> dict[str, Any]:
    """Drive a :class:`GameSession` to completion without a window.

    Advances to each interactive point, auto-selecting *auto_choose* when a
    choice prompt is reached, and renders every beat through *renderer*.
    Returns a summary dict with the step/render counts and whether the story
    ended.
    """
    steps = 0
    render_frames = 0

    while not session.vm.is_ended and not session.is_finished:
        if max_steps is not None and steps >= max_steps:
            break

        event = session.advance()
        steps += 1

        if event is not None and event.type == "choice_prompt":
            if auto_choose is not None:
                session.choose(auto_choose)
                continue
            first_enabled = next((opt.index for opt in event.options if opt.enabled), None)
            if first_enabled is not None:
                session.choose(first_enabled)
                continue
            break

        if event is not None and event.type == "input_prompt":
            session.submit_input(getattr(event, "default", "") or "Player")
            continue

        if event is None:
            break

        session.update(dt)
        renderer.render_compositor(session.compositor, 1280, 720)
        render_frames += 1

    return {
        "steps": steps,
        "ended": session.vm.is_ended or session.is_finished,
        "render_frames": render_frames,
        "final_ui_state": session.director.ui_state,
    }


def _cmd_play(args: argparse.Namespace) -> int:
    """Launch an interactive visual novel via the selected backend."""
    # Verify backend availability before constructing the session.
    if args.backend == "pyglet":
        try:
            import pyglet  # noqa: F401
        except ImportError:
            sys.stderr.write(
                "Error: Pyglet is required for --backend pyglet.\n"
                "Install it with: pip install eager[pyglet]\n"
            )
            return 1
    elif args.backend == "pil":
        try:
            import PIL  # noqa: F401
        except ImportError:
            sys.stderr.write(
                "Error: Pillow is required for --backend pil.\n"
                "Install it with: pip install eager[pil]\n"
            )
            return 1

    from eager.session import GameSession

    audio_backend = _create_audio_backend(
        args.backend,
        no_audio=getattr(args, "no_audio", False),
    )

    session = GameSession(
        args.script,
        backend=args.backend,
        audio_backend=audio_backend,
        asset_dir=_resolve_asset_dir(args.script, args.asset_dir),
        auto_reload=getattr(args, "watch", False),
    )

    if getattr(args, "lang", None):
        session.set_language(args.lang)

    if getattr(args, "warp", None):
        target_scene = args.warp
        if target_scene in session.vm.graph.nodes:
            simulate = not getattr(args, "no_warp_sim", False)
            session.warp(target_scene, simulate=simulate)
            sys.stderr.write(f"Warped directly to scene '{target_scene}'.\n")
        else:
            sys.stderr.write(f"Warning: Warp target '{target_scene}' not found in script.\n")
    elif not getattr(args, "skip_title", False) and hasattr(session.screens, "show"):
        session.screens.show("title", session)
        session.mode = "title"

    sys.stderr.write(f"Launching Eager visual novel ({args.backend})...\n")
    session._cli_args = args
    _run_interactive_player(session, backend=args.backend)
    return 0



def _cmd_render(args: argparse.Namespace) -> int:
    """Run a story to completion in headless mode (NullRenderer)."""
    from eager.backends.renderers.null import NullRenderer
    from eager.session import GameSession

    session = GameSession(
        args.script,
        backend="null",
        asset_dir=_resolve_asset_dir(args.script, args.asset_dir),
    )

    if getattr(args, "lang", None):
        session.set_language(args.lang)

    sys.stderr.write(f"Rendering '{args.script}' headlessly...\n")

    renderer = NullRenderer()

    result = _run_headless(
        session,
        renderer,
        dt=args.dt,
        max_steps=args.max_steps,
        auto_choose=args.auto_choose,
    )

    sys.stderr.write(
        f"Render complete: {result['steps']} steps, "
        f"{result['render_frames']} frames rendered, "
        f"story ended={result['ended']}.\n"
    )
    return 0 if result["ended"] else 1


# ── Interactive player loop ────────────────────────────────────────────


def _run_interactive_player(session: Any, *, backend: str) -> None:
    """Run the interactive player loop for the given backend.

    All interactive players (PygletPlayer and PILPlayer) share a
    common interface and run their own event loops via ``run()``.
    """
    args = getattr(session, "_cli_args", None)
    if backend == "pil":
        from eager.ui.pil_player import PILPlayer as player_cls
    elif backend == "pyglet":
        from eager.ui.pyglet_player import PygletPlayer as player_cls
    else:
        raise ValueError(
            f"Unknown player backend '{backend}'. Available backends: pil, pyglet."
        )

    asset_dir = str(session.asset_dir) if getattr(session, "asset_dir", None) else None
    cfg_title = getattr(getattr(session, "config", None), "title", None)
    title = cfg_title if cfg_title else f"Eager Visual Novel ({backend.upper()})"
    width = getattr(session, "virtual_width", 1280) or 1280
    height = getattr(session, "virtual_height", 720) or 720

    player_kwargs: dict[str, Any] = {
        "session": session,
        "width": width,
        "height": height,
        "title": title,
        "asset_dir": asset_dir,
    }

    scale_arg = getattr(args, "scale_mode", None) or getattr(getattr(session, "config", None), "scale_mode", None)
    if scale_arg:
        from eager.core.types import ScaleMode
        try:
            player_kwargs["scale_mode"] = ScaleMode(scale_arg.lower())
        except (ValueError, KeyError):
            pass

    show_fps_arg = getattr(args, "show_fps", None)
    if show_fps_arg is not None:
        player_kwargs["show_fps"] = show_fps_arg
    elif hasattr(getattr(session, "config", None), "show_fps"):
        player_kwargs["show_fps"] = session.config.show_fps

    uncapped_arg = getattr(args, "uncapped", False)
    if uncapped_arg:
        player_kwargs["uncapped"] = True

    preset_arg = getattr(args, "render_preset", None) or getattr(getattr(session, "config", None), "render_preset", None)
    if preset_arg and backend == "pil":
        player_kwargs["preset"] = str(preset_arg).lower()

    player: Any = player_cls(**player_kwargs)
    if (
        getattr(getattr(session, "preferences", None), "fullscreen", False)
        and hasattr(player, "toggle_fullscreen")
        and not getattr(player, "fullscreen", False)
    ):
        try:
            player.toggle_fullscreen()
        except Exception:  # noqa: BLE001, S110
            pass
    player.run()


def _cmd_run(args: argparse.Namespace) -> int:
    """Run an Eager visual novel project directory."""
    from eager.script.project import ProjectConfig
    from eager.session import GameSession

    proj_dir = Path(args.project_dir)
    toml_path = proj_dir / "game.toml"
    cfg = ProjectConfig.load(toml_path) if toml_path.exists() else ProjectConfig()

    script_path = proj_dir / cfg.entry_script
    if not script_path.exists():
        # Fallback to any .es script found in directory
        es_files = list(proj_dir.glob("*.es"))
        if not es_files:
            sys.stderr.write(f"Error: No script found in '{proj_dir}'.\n")
            return 1
        script_path = es_files[0]

    asset_dir = proj_dir / "assets" if (proj_dir / "assets").exists() else None

    audio_backend = _create_audio_backend(
        args.backend,
        no_audio=getattr(args, "no_audio", False),
    )

    session = GameSession(
        str(script_path),
        backend=args.backend,
        audio_backend=audio_backend,
        asset_dir=_resolve_asset_dir(script_path, asset_dir),
        auto_reload=getattr(args, "watch", False),
        config=cfg,
    )
    if getattr(args, "lang", None):
        session.set_language(args.lang)

    if getattr(args, "warp", None):
        target_scene = args.warp
        if target_scene in session.vm.graph.nodes:
            simulate = not getattr(args, "no_warp_sim", False)
            session.warp(target_scene, simulate=simulate)
            sys.stderr.write(f"Warped directly to scene '{target_scene}'.\n")
        else:
            sys.stderr.write(f"Warning: Warp target '{target_scene}' not found in script.\n")
    elif not getattr(args, "skip_title", False) and hasattr(session.screens, "show"):
        session.screens.show("title", session)
        session.mode = "title"

    session._cli_args = args
    _run_interactive_player(session, backend=args.backend)
    return 0


def _cmd_new(args: argparse.Namespace) -> int:
    """Scaffold a new Eager project."""
    target_dir = Path(args.name)
    if target_dir.exists():
        sys.stderr.write(f"Error: Directory '{target_dir}' already exists.\n")
        return 1

    is_demo = getattr(args, "demo", False)
    title = Path(args.name).name.replace("_", " ").replace("-", " ").title()

    if is_demo:
        # Search for showcase demo directory in workspace or parent paths
        repo_examples = None
        for candidate in (
            Path("examples"),
            Path(__file__).resolve().parents[4] / "examples",
            Path(__file__).resolve().parents[3] / "examples",
        ):
            if candidate.is_dir() and (candidate / "demo_story.es").exists():
                repo_examples = candidate
                break

        if repo_examples is None:
            sys.stderr.write("Error: Showcase demo assets not found. Creating standard starter project instead.\n")
            is_demo = False
        else:
            target_dir.mkdir(parents=True)
            import shutil

            # Copy demo script as main.es
            shutil.copy2(repo_examples / "demo_story.es", target_dir / "main.es")

            # Copy assets
            if (repo_examples / "assets").is_dir():
                shutil.copytree(repo_examples / "assets", target_dir / "assets")

            # Copy locales if present
            if (repo_examples / "locales").is_dir():
                shutil.copytree(repo_examples / "locales", target_dir / "locales")

            # Write game.toml
            toml_content = f"""[game]
title = "{title} (Demo Showcase)"
version = "0.1.0"
author = "Your Name"
entry_script = "main.es"

[window]
width = 1920
height = 1080
"""
            (target_dir / "game.toml").write_text(toml_content, encoding="utf-8")

            print(f"Created new Eager demo showcase project in '{target_dir}'.")
            print("Next steps:")
            print(f"  eager run {target_dir} --watch     # Launch with live hot-reload")
            print(f"  eager check {target_dir} --assets  # Validate script & assets")
            return 0

    # Default: scaffold from starter template
    template_dir = Path(__file__).resolve().parent.parent / "template"
    if template_dir.is_dir():
        import shutil

        shutil.copytree(template_dir, target_dir)
        # Customize game.toml title
        cfg_path = target_dir / "game.toml"
        if cfg_path.exists():
            cfg_text = cfg_path.read_text(encoding="utf-8")
            cfg_text = cfg_text.replace('title = "My First Visual Novel"', f'title = "{title}"')
            cfg_path.write_text(cfg_text, encoding="utf-8")
    else:
        # Fallback minimal scaffolding
        target_dir.mkdir(parents=True)
        (target_dir / "assets").mkdir()
        (target_dir / "assets" / "characters").mkdir()
        (target_dir / "assets" / "bg").mkdir()
        (target_dir / "assets" / "audio").mkdir()

        toml_content = f"""[game]
title = "{title}"
version = "0.1.0"
author = "Your Name"
entry_script = "main.es"

[window]
width = 1920
height = 1080
"""
        (target_dir / "game.toml").write_text(toml_content, encoding="utf-8")

        es_content = """## Start --- start
Narrator: Welcome to your new visual novel!
Narrator: Create characters, dialogue, and choices here.
"""
        (target_dir / "main.es").write_text(es_content, encoding="utf-8")

    print(f"Created new Eager project in '{target_dir}'.")
    print("Next steps:")
    print(f"  eager run {target_dir} --watch     # Launch with live hot-reload")
    print(f"  eager check {target_dir} --assets  # Validate script & assets")
    print(f"  eager play {target_dir}/main.es --backend terminal  # Terminal mode")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Validate screenplay script or project directory."""
    target_path = Path(args.script)
    if not target_path.exists():
        sys.stderr.write(f"Error: Path '{target_path}' not found.\n")
        return 1

    es_files = resolve_project_scripts(target_path)
    if not es_files:
        sys.stderr.write(f"Error: No .es scripts found in '{target_path}'.\n")
        return 1

    script_file = es_files[0]  # Used for asset dir resolution later

    try:
        items = []
        for f in es_files:
            text = f.read_text(encoding="utf-8")
            items.extend(eager.script.parse(text))
        result = eager.script.validate(items)
    except (eager.script.ParseError, OSError, ValueError, TypeError) as err:
        sys.stderr.write(f"Check failed with error: {err}\n")
        return 1

    has_errors = False
    if result.errors:
        has_errors = True
        print(f"Validation FAILED with {len(result.errors)} error(s):")
        for err in result.errors:
            print(f"  Line {err.line_number}: {err.message}")
    elif result.warnings:
        print(f"Validation passed with {len(result.warnings)} warning(s):")
        for warn in result.warnings:
            print(f"  Line {warn.line_number}: {warn.message}")
    else:
        print("Script validation PASSED (0 errors, 0 warnings).")

    # Asset verification check
    explicit_assets = getattr(args, "assets", False)
    asset_dir_arg = getattr(args, "asset_dir", None)
    should_check_assets = explicit_assets or asset_dir_arg is not None

    resolved_asset_dir: Path | None = None
    if asset_dir_arg is not None:
        resolved_asset_dir = Path(asset_dir_arg)
    elif target_path.is_dir() and (target_path / "assets").is_dir():
        resolved_asset_dir = target_path / "assets"
    elif script_file.resolve().parent.joinpath("assets").is_dir():
        resolved_asset_dir = script_file.resolve().parent.joinpath("assets")

    if should_check_assets or (resolved_asset_dir is not None and target_path.is_dir()):
        if resolved_asset_dir is None:
            sys.stderr.write("Error: Asset directory not found. Specify --asset-dir <path>.\n")
            return 1

        from eager.core.assets import check_assets

        graph = load_project_graph(target_path)
        report = check_assets(graph, resolved_asset_dir)

        print(f"\nAsset Consistency Check: '{resolved_asset_dir}'")
        print(f"  Total references: {report.total_references}")
        print(f"  Resolved assets:  {report.resolved_count}")

        if report.missing:
            has_errors = True
            print(f"  Missing assets:   {len(report.missing)}")
            for issue in report.missing:
                cand_str = ", ".join(issue.expected_paths[:2])
                print(
                    f"    Line {issue.reference.line_number}: [{issue.reference.kind}] "
                    f"'{issue.reference.identifier}' (expected e.g. {cand_str})"
                )
        else:
            print("  All referenced assets resolved successfully.")

    return 1 if has_errors else 0


def _cmd_build(args: argparse.Namespace) -> int:
    """Bundle an Eager visual novel project into a distribution zip archive."""
    import zipfile

    proj_dir = Path(args.project_dir).resolve()
    if not proj_dir.is_dir():
        sys.stderr.write(f"Error: Project directory '{proj_dir}' not found.\n")
        return 1

    if not getattr(args, "no_check", False):
        check_args = argparse.Namespace(
            script=str(proj_dir),
            assets=(proj_dir / "assets").is_dir(),
            asset_dir=None,
        )
        rc = _cmd_check(check_args)
        if rc != 0:
            sys.stderr.write("Build aborted: project check failed. Use --no-check to bypass.\n")
            return 1

    out_name = args.output or f"{proj_dir.name}_dist.zip"
    out_path = Path(out_name).resolve()

    print(f"Packaging '{proj_dir}' into '{out_path}'...")
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in proj_dir.rglob("*"):
            if file.is_file():
                resolved_file = file.resolve()
                if resolved_file == out_path:
                    continue
                if not resolved_file.is_relative_to(proj_dir):
                    continue
                rel = file.relative_to(proj_dir)
                # Skip venv, cache, git directories, dist and build
                if any(part.startswith((".", "__pycache__", "venv")) or part in ("dist", "build") for part in rel.parts):
                    continue
                zf.write(file, rel)

    print(f"Build complete: project archive created at '{out_path}'.")
    print("Note: For standalone executables or OS installers, use 'python packaging/build_export.py'.")
    return 0


def _cmd_i18n_extract(args: argparse.Namespace) -> int:
    """Extract translatable screenplay strings into a catalog JSON file."""
    target = Path(args.script)
    try:
        graph = load_project_graph(target)
    except OSError as e:
        sys.stderr.write(f"Error: failed to load project graph for '{target}': {e}\n")
        return 1

    from eager.core.i18n import TranslationCatalog
    from eager.vm.i18n import extract_catalog, merge_catalog

    catalog = extract_catalog(graph, locale=args.locale)

    out_path: Path
    if args.output:
        out_path = Path(args.output)
    else:
        locales_dir = (target if target.is_dir() else target.resolve().parent) / "locales"
        out_path = locales_dir / f"{args.locale}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.merge and out_path.exists():
        existing = TranslationCatalog.load_json(out_path)
        merged, stats = merge_catalog(catalog, existing)
        merged.save_json(out_path)
        print(f"Merged catalog saved to '{out_path}':")
        print(f"  Total strings:      {stats['total']}")
        print(f"  Existing preserved: {stats['translated']}")
        print(f"  New strings added:  {stats['new']}")
        if stats["obsolete"] > 0:
            print(f"  Obsolete strings:   {stats['obsolete']}")
    else:
        catalog.save_json(out_path)
        print(f"Extracted catalog saved to '{out_path}':")
        print(f"  Total strings:      {len(catalog.strings)}")
        print(f"  Unique speakers:    {len(catalog.speakers)}")

    return 0


def _cmd_i18n_check(args: argparse.Namespace) -> int:
    """Check translation coverage and missing strings for catalog(s)."""
    target = Path(args.script)
    try:
        graph = load_project_graph(target)
    except OSError as e:
        sys.stderr.write(f"Error: failed to load project graph for '{target}': {e}\n")
        return 1

    from eager.core.i18n import TranslationCatalog
    from eager.vm.i18n import validate_catalog

    cat_path = Path(args.catalog)
    catalogs_to_check: list[Path] = []
    if cat_path.is_dir():
        catalogs_to_check = sorted(p for p in cat_path.glob("*.json") if not p.name.startswith((".", "template")))
        if not catalogs_to_check:
            sys.stderr.write(f"Error: No translation catalogs found in directory '{cat_path}'.\n")
            return 1
    elif cat_path.is_file():
        catalogs_to_check = [cat_path]
    else:
        sys.stderr.write(f"Error: Catalog path '{cat_path}' not found.\n")
        return 1

    has_incomplete = False
    for p in catalogs_to_check:
        cat = TranslationCatalog.load_json(p)
        result = validate_catalog(cat, graph)
        print(f"Locale '{result['locale']}' ({p.name}):")
        print(f"  Coverage:     {result['coverage_percent']}% ({result['translated']}/{result['total']} strings)")
        if result["untranslated"] > 0:
            has_incomplete = True
            print(f"  Untranslated: {result['untranslated']}")
            for k in result["missing_keys"][:5]:
                print(f"    Missing: {k}")
            if len(result["missing_keys"]) > 5:
                print(f"    ... and {len(result['missing_keys']) - 5} more")
        if result["obsolete"] > 0:
            print(f"  Obsolete:     {result['obsolete']} keys in catalog not in script")

    if args.strict and has_incomplete:
        return 1
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    """Parse an .es screenplay file into JSON AST."""
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        items = eager.script.parse_file(path)
        json_output = eager.script.to_json(items, indent=args.indent)
        if args.output:
            Path(args.output).write_text(json_output, encoding="utf-8")
        else:
            sys.stdout.write(json_output + "\n")
        return 0
    except (eager.script.ParseError, eager.script.IncludeError) as exc:
        sys.stderr.write(f"Parse error: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Error: {exc}\n")
        return 1


def _cmd_graph(args: argparse.Namespace) -> int:
    """Export an .es screenplay file as a directed scene graph."""
    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"Error: File not found: {path}\n")
        return 1

    try:
        items = eager.script.parse_file(path)
        graph = eager.script.to_graph(items)

        if args.format == "dot":
            output_text = graph.to_dot()
        elif args.format == "mermaid":
            output_text = graph.to_mermaid()
        else:
            include_body = not args.no_body
            output_text = graph.to_json(include_body=include_body, indent=args.indent)

        if args.output:
            Path(args.output).write_text(output_text + "\n", encoding="utf-8")
        else:
            sys.stdout.write(output_text + "\n")
        return 0
    except (eager.script.ParseError, eager.script.IncludeError) as exc:
        sys.stderr.write(f"Parse error: {exc}\n")
        return 1
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Error: {exc}\n")
        return 1


def _cmd_doctor(_args: argparse.Namespace) -> int:
    """Report availability of Eager packages, rendering/audio backends, and export tools."""
    import importlib.metadata
    import importlib.util

    checks: list[tuple[str, str, str]] = [
        ("eager", "eager", "Unified Eager engine, DSL, VM, and CLI"),
        ("PIL", "pillow (or pillow-simd)", "Software renderer (--backend pil)"),
        ("pyglet", "pyglet", "Hardware OpenGL renderer (--backend pyglet)"),
        ("miniaudio", "miniaudio", "Audio playback backend"),
        ("eager_script_lsp", "eager-script-lsp", "Language Server Protocol (LSP) for editors"),
        ("PyInstaller", "pyinstaller", "Standalone executable builds (packaging/build_export.py)"),
    ]

    print("Eager Environment Check:")
    for mod_name, pkg_label, purpose in checks:
        spec = importlib.util.find_spec(mod_name)
        if spec is not None:
            version_str = ""
            if mod_name == "PIL":
                try:
                    import PIL
                    import PIL.features  # type: ignore[import-untyped]

                    supported = getattr(PIL.features, "get_supported_features", list)()
                    simd = "simd" in supported
                    pil_ver = getattr(PIL, "__version__", "")
                    tag = "pillow-simd" if simd else "pillow"
                    version_str = f" ({tag} {pil_ver})" if pil_ver else f" ({tag})"
                except (ImportError, AttributeError, ValueError):
                    version_str = ""
            else:
                try:
                    version_str = f" ({importlib.metadata.version(pkg_label.split()[0])})"
                except importlib.metadata.PackageNotFoundError:
                    version_str = ""
            print(f"  [OK]      {pkg_label}{version_str} — {purpose}")
        else:
            print(f"  [MISSING] {pkg_label} — {purpose}")

    return 0



# ── Entry points ────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``eager`` CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
