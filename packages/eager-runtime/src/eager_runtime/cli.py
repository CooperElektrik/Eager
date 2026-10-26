"""Command-line interface for the Eager runtime.

Single entry point is provided:

* ``eager`` — unified commands (``play``, ``inspect``,
  ``test-run``, ``render``, ``run``, ``new``, ``check``, ``build``,
  ``i18n``).  Graphical commands require ``eager_graphics`` to be installed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import eager_script
from eager_core.protocols import (
    get_audio_backend,
    get_player,
    get_renderer,
    get_stage_factory,
    list_players,
    load_providers,
)

from eager_runtime.player import TerminalPlayer
from eager_runtime.project import load_project_graph, mask_script_includes, resolve_project_scripts
from eager_runtime.runtime import StoryVM

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


def _ensure_graphics() -> None:
    """Raise a helpful error if eager_graphics is not installed."""
    load_providers()
    if get_stage_factory() is None:
        raise ImportError(
            "eager_graphics is required for visual-novel commands.\n"
            "Install it with: pip install eager-graphics[all]"
        )


def _version_string() -> str:
    import eager_runtime

    try:
        import importlib.metadata

        gfx_version = importlib.metadata.version("eager-graphics")
        return f"eager {gfx_version}"
    except Exception:  # noqa: BLE001
        return f"eager {eager_runtime.__version__}"


# ── eager CLI (text-only, no graphics) ────────────────────────────────


def _add_i18n_subparser(subparsers: Any) -> None:
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
        "play", help="Play an Eager-Script screenplay interactively in the terminal."
    )
    _build_common_script_args(play_p)
    play_p.add_argument("--no-color", action="store_true", help="Disable colored terminal output.")
    play_p.add_argument(
        "--backend",
        choices=["terminal", "pyglet", "pil"],
        default="terminal",
        help="Player backend (default: terminal). Graphical backends require eager-graphics.",
    )
    play_p.add_argument("--asset-dir", default=None, help="Directory containing sprite/background assets.")
    play_p.add_argument("--warp", default=None, help="Fast-forward / jump directly to scene label.")
    play_p.add_argument("--no-warp-sim", action="store_true", help="Bypass state simulation and jump directly when warping.")
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
    run_p.add_argument("--no-audio", action="store_true", help="Disable audio playback (use NullAudioBackend).")
    run_p.add_argument("--watch", "--hot-reload", dest="watch", action="store_true", help="Automatically hot-reload when script changes on disk.")
    run_p.set_defaults(func=_cmd_run)

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
        help="Package and bundle an Eager project into a standalone distribution archive.",
    )
    build_p.add_argument("project_dir", nargs="?", default=".", help="Project directory (default: current directory)")
    build_p.add_argument("-o", "--output", default=None, help="Output zip archive path")
    build_p.set_defaults(func=_cmd_build)

    # i18n
    _add_i18n_subparser(subparsers)

    # Optional LSP subcommand if eager_script_lsp is installed
    try:
        import eager_script_lsp.cli as lsp_cli
        lsp_p = subparsers.add_parser(
            "lsp",
            help="Run Language Server Protocol (LSP) server for Eager-Script screenplays.",
        )
        lsp_cli.add_arguments(lsp_p)
        lsp_p.set_defaults(func=lsp_cli.run_cli)
    except ImportError:
        pass

    return parser



def run_play(args: argparse.Namespace) -> int:
    """Execute interactive playthrough (terminal by default, graphical with --backend)."""
    backend = getattr(args, "backend", "terminal")
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

    from eager_core.i18n import TranslationManager

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

    from eager_core.i18n import TranslationManager

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
                    num_opts = len(prompt.options)

                    if decision_idx < len(decision_path):
                        chosen = decision_path[decision_idx]
                        decision_idx += 1
                        current_decisions.append(chosen)
                        vm.choose(chosen)
                    else:
                        # First time encountering this choice prompt in this path:
                        # Queue other alternatives (1 .. num_opts-1)
                        for alt in range(1, num_opts):
                            alt_seq = tuple(current_decisions + [alt])
                            if alt_seq not in visited_choice_sequences:
                                visited_choice_sequences.add(alt_seq)
                                frontier.append(list(alt_seq))
                        # Take choice 0 for current run
                        current_decisions.append(0)
                        decision_idx += 1
                        vm.choose(0)

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
            # Default to first choice in headless mode
            vm.choose(0)

    print(f"Test run completed: {steps} steps, {events_count} events dispatched, ended: {vm.is_ended}.")
    return 0



# ── eager CLI (unified, graphics optional) ────────────────────────────────


def _create_audio_backend(backend: str, *, no_audio: bool = False) -> Any:
    """Instantiate the matching audio backend for the given render backend."""
    from eager_core.audio import NullAudioBackend

    if no_audio:
        return NullAudioBackend()

    load_providers()
    backend_factory = get_audio_backend(backend)
    if backend_factory is not None:
        try:
            return backend_factory()
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
            break

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
    _ensure_graphics()

    # Verify backend availability before constructing the session.
    if args.backend == "pyglet":
        try:
            import pyglet  # noqa: F401
        except ImportError:
            sys.stderr.write(
                "Error: Pyglet is required for --backend pyglet.\n"
                "Install it with: pip install eager-graphics[hardware]\n"
            )
            return 1
    elif args.backend == "pil":
        try:
            import PIL  # noqa: F401
        except ImportError:
            sys.stderr.write(
                "Error: Pillow is required for --backend pil.\n"
                "Install it with: pip install eager-graphics[software]\n"
                "(or the SIMD build: pip install eager-graphics[software-simd])\n"
            )
            return 1

    from eager_runtime.session import GameSession

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

    sys.stderr.write(f"Launching Eager visual novel ({args.backend})...\n")
    _run_interactive_player(session, backend=args.backend)
    return 0



def _cmd_render(args: argparse.Namespace) -> int:
    """Run a story to completion in headless mode (NullRenderer)."""
    _ensure_graphics()

    from eager_runtime.session import GameSession

    session = GameSession(
        args.script,
        backend="null",
        asset_dir=_resolve_asset_dir(args.script, args.asset_dir),
    )

    if getattr(args, "lang", None):
        session.set_language(args.lang)

    sys.stderr.write(f"Rendering '{args.script}' headlessly...\n")

    renderer_factory = get_renderer("null")
    renderer = renderer_factory() if renderer_factory is not None else None
    if renderer is None:
        raise RuntimeError("No null renderer registered. Ensure eager-graphics is installed.")

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
    _ensure_graphics()
    player_cls = get_player(backend)
    if player_cls is None:
        raise ValueError(
            f"No player registered for backend '{backend}'. "
            f"Available backends: {', '.join(list_players()) or 'none'}. "
            f"Ensure eager-graphics is installed."
        )

    asset_dir = str(session.asset_dir) if getattr(session, "asset_dir", None) else None
    title = f"Eager Visual Novel ({backend.upper()})"
    player: Any = player_cls(
        session=session,
        width=1280,
        height=720,
        title=title,
        asset_dir=asset_dir,
    )
    player.run()


def _cmd_run(args: argparse.Namespace) -> int:
    """Run an Eager visual novel project directory."""
    _ensure_graphics()
    from eager_runtime.project import ProjectConfig
    from eager_runtime.session import GameSession

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
    _run_interactive_player(session, backend=args.backend)
    return 0


def _cmd_new(args: argparse.Namespace) -> int:
    """Scaffold a new Eager project."""
    target_dir = Path(args.name)
    if target_dir.exists():
        sys.stderr.write(f"Error: Directory '{target_dir}' already exists.\n")
        return 1

    is_demo = getattr(args, "demo", False)
    title = args.name.replace("_", " ").replace("-", " ").title()

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
            print("Run your game with:")
            print(f"  eager run {target_dir}")
            return 0

    # Default: scaffold from starter template
    template_dir = Path(__file__).resolve().parent / "template"
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
    print("Run your game with:")
    print(f"  eager run {target_dir}")
    print("Or play in the terminal:")
    print(f"  eager play {target_dir}/main.es")
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
            cleaned = mask_script_includes(text)
            items.extend(eager_script.parse(cleaned))
        result = eager_script.validate(items)
    except (eager_script.ParseError, OSError, ValueError, TypeError) as err:
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

        from eager_runtime.assets import check_assets

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

    print(f"Build complete: archive created at '{out_path}'.")
    return 0


def _resolve_script_file(target_path: Path) -> Path | None:
    if target_path.is_dir():
        from eager_runtime.project import resolve_project_scripts

        scripts = resolve_project_scripts(target_path)
        return scripts[0] if scripts else None
    elif target_path.is_file():
        return target_path
    return None


def _cmd_i18n_extract(args: argparse.Namespace) -> int:
    """Extract translatable screenplay strings into a catalog JSON file."""
    target = Path(args.script)
    try:
        graph = load_project_graph(target)
    except OSError as e:
        sys.stderr.write(f"Error: failed to load project graph for '{target}': {e}\n")
        return 1

    from eager_core.i18n import TranslationCatalog

    from eager_runtime.i18n import extract_catalog, merge_catalog

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

    from eager_core.i18n import TranslationCatalog

    from eager_runtime.i18n import validate_catalog

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



# ── Entry points ────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``eager`` CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
