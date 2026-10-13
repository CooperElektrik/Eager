"""Command-line interfaces for the Eager runtime.

Two entry points are provided:

* ``eager``       — headless / text-only commands (``play``, ``inspect``,
  ``test-run``).  No graphics dependency required.
* ``eager-x``     — visual-novel commands (``play`` with a rendering backend,
  ``render`` in headless mode).  Requires ``eager_graphics`` to be installed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import eager_script

from eager_runtime.player import TerminalPlayer
from eager_runtime.runtime import StoryVM

# ── shared helpers ────────────────────────────────────────────────────


def _build_common_script_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("script", help="Path to the .es screenplay script file.")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Parse script using Eager-SP mode.",
    )


def _ensure_graphics() -> None:
    """Raise a helpful error if eager_graphics is not installed."""
    try:
        import eager_graphics  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "eager_graphics is required for visual-novel commands.\n"
            "Install it with: pip install eager-graphics[all]"
        ) from exc


def _version_string() -> str:
    try:
        import eager_graphics

        return f"eager-x {eager_graphics.__version__}"
    except ImportError:
        import eager_runtime

        return f"eager {eager_runtime.__version__}"


# ── eager CLI (text-only, no graphics) ────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``eager`` CLI."""
    parser = argparse.ArgumentParser(
        prog="eager",
        description="Eager narrative runtime and player for Eager-S screenplay scripts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # play
    play_p = subparsers.add_parser(
        "play", help="Play an Eager-S screenplay interactively in the terminal."
    )
    _build_common_script_args(play_p)
    play_p.add_argument("--no-color", action="store_true", help="Disable colored terminal output.")
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

    return parser



def run_play(args: argparse.Namespace) -> int:
    """Execute interactive terminal playthrough."""
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Screenplay file '{script_path}' not found.", file=sys.stderr)
        return 1

    text = script_path.read_text(encoding="utf-8")
    graph = eager_script.parse_graph(text, plain=args.plain)

    if not graph.nodes:
        print("Warning: Script contains no scenes.", file=sys.stderr)
        return 0

    vm = StoryVM(graph)
    player = TerminalPlayer(vm, use_colors=not args.no_color)
    player.play()
    return 0


def run_inspect(args: argparse.Namespace) -> int:
    """Inspect screenplay structure."""
    script_path = Path(args.script)
    if not script_path.exists():
        print(f"Error: Screenplay file '{script_path}' not found.", file=sys.stderr)
        return 1

    text = script_path.read_text(encoding="utf-8")
    graph = eager_script.parse_graph(text, plain=args.plain)

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

    text = script_path.read_text(encoding="utf-8")
    graph = eager_script.parse_graph(text, plain=args.plain)

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
            vm = StoryVM(graph)
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


    vm = StoryVM(graph)
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



# ── eager-x CLI (visual novel with graphics) ────────────────────────────


def build_x_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``eager-x`` CLI."""
    parser = argparse.ArgumentParser(
        prog="eager-x",
        description="Eager-Graphics: unified visual novel engine CLI.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=_version_string(),
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # play
    play_p = subparsers.add_parser(
        "play",
        help="Launch an interactive visual novel window.",
    )
    play_p.add_argument("script", help="Path to .es screenplay file")
    play_p.add_argument(
        "--backend",
        choices=["pyglet", "pil", "raylib"],
        default="pil",
        help="Rendering backend (default: pil)",
    )
    play_p.add_argument("--asset-dir", default=None, help="Directory containing sprite/background assets.")
    play_p.add_argument("--plain", action="store_true", help="Parse script in Eager-SP plain mode.")
    play_p.add_argument("--warp", default=None, help="Fast-forward / jump directly to scene label.")
    play_p.add_argument("--no-audio", action="store_true", help="Disable audio playback (use NullAudioBackend).")
    play_p.set_defaults(func=_cmd_play)

    # render
    render_p = subparsers.add_parser(
        "render",
        help="Run a story to completion in headless mode (NullRenderer, no window).",
    )
    render_p.add_argument("script", help="Path to .es screenplay file")
    render_p.add_argument("--asset-dir", default=None, help="Directory containing sprite/background assets.")
    render_p.add_argument("--plain", action="store_true", help="Parse script in Eager-SP plain mode.")
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
    run_p.add_argument("--backend", choices=["pyglet", "pil", "raylib"], default="pil", help="Rendering backend")
    run_p.add_argument("--no-audio", action="store_true", help="Disable audio playback (use NullAudioBackend).")
    run_p.set_defaults(func=_cmd_run)

    # new
    new_p = subparsers.add_parser(
        "new",
        help="Scaffold a new Eager visual novel project structure.",
    )
    new_p.add_argument("name", help="Name of project directory to create")
    new_p.set_defaults(func=_cmd_new)

    # check
    check_p = subparsers.add_parser(
        "check",
        help="Validate script syntax, logic, and scene graph integrity.",
    )
    check_p.add_argument("script", help="Path to .es screenplay file or project directory")
    check_p.add_argument("--plain", action="store_true", help="Validate in Eager-SP plain mode.")
    check_p.set_defaults(func=_cmd_check)

    # build
    build_p = subparsers.add_parser(
        "build",
        help="Package and bundle an Eager project into a standalone distribution archive.",
    )
    build_p.add_argument("project_dir", nargs="?", default=".", help="Project directory (default: current directory)")
    build_p.add_argument("-o", "--output", default=None, help="Output zip archive path")
    build_p.set_defaults(func=_cmd_build)

    return parser



def _create_audio_backend(backend: str, *, no_audio: bool = False) -> Any:
    """Instantiate the matching audio backend for the given render backend."""
    from eager_core import NullAudioBackend

    if no_audio:
        return NullAudioBackend()

    if backend == "pyglet":
        try:
            from eager_graphics.renderers.pyglet import PygletAudioBackend

            return PygletAudioBackend()
        except Exception:  # noqa: BLE001
            return NullAudioBackend()
    if backend == "raylib":
        try:
            from eager_graphics.renderers.raylib import RaylibAudioBackend

            return RaylibAudioBackend()
        except Exception:  # noqa: BLE001
            return NullAudioBackend()
    if backend == "pil":
        try:
            from eager_graphics.renderers.miniaudio import MiniaudioAudioBackend

            return MiniaudioAudioBackend()
        except Exception:  # noqa: BLE001
            return NullAudioBackend()

    return NullAudioBackend()


def _cmd_play(args: argparse.Namespace) -> int:
    """Launch an interactive visual novel via the selected backend."""
    _ensure_graphics()

    # Verify backend availability before constructing the engine.
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
            )
            return 1
    elif args.backend == "raylib":
        try:
            import pyray  # noqa: F401
        except ImportError:
            sys.stderr.write(
                "Error: Raylib (pyray) is required for --backend raylib.\n"
                "Install it with: pip install eager-graphics[raylib]\n"
            )
            return 1

    from eager_runtime.engine import VisualEngine

    audio_backend = _create_audio_backend(
        args.backend,
        no_audio=getattr(args, "no_audio", False),
    )

    engine = VisualEngine(
        script_path=args.script,
        backend=args.backend,
        audio_backend=audio_backend,
        asset_dir=args.asset_dir,
        plain=args.plain,
    )

    if getattr(args, "warp", None):
        target_scene = args.warp
        if target_scene in engine.vm.graph.nodes:
            engine.vm.jump(target_scene)
            sys.stderr.write(f"Warped directly to scene '{target_scene}'.\n")
        else:
            sys.stderr.write(f"Warning: Warp target '{target_scene}' not found in script.\n")

    sys.stderr.write(f"Launching Eager visual novel ({args.backend})...\n")
    _run_interactive_player(engine, backend=args.backend)
    return 0



def _cmd_render(args: argparse.Namespace) -> int:
    """Run a story to completion in headless mode (NullRenderer)."""
    _ensure_graphics()

    from eager_runtime.engine import VisualEngine

    engine = VisualEngine(
        script_path=args.script,
        backend="null",
        asset_dir=args.asset_dir,
        plain=args.plain,
    )

    sys.stderr.write(f"Rendering '{args.script}' headlessly...\n")

    result = engine.run_headless(
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


def _run_interactive_player(engine: Any, *, backend: str) -> None:
    """Run the interactive player loop for the given backend.

    Both PygletPlayer and PILPlayer share a common interface:
    ``advance_story()``, ``make_choice(idx)``, ``on_draw()``,
    ``active_choice_prompt``, ``is_finished``, and ``close()``.
    RaylibPlayer and PILPlayer run their own event loops (``run()``);
    PygletPlayer is driven by ``pyglet.app.run()``.
    """
    session = getattr(engine, "session", engine)
    asset_dir = str(engine.asset_dir) if getattr(engine, "asset_dir", None) else None

    if backend == "raylib":
        from eager_graphics.renderers.raylib import RaylibPlayer

        player = RaylibPlayer(
            session=session,
            width=1280,
            height=720,
            title="Eager Visual Novel (Raylib)",
            asset_dir=asset_dir,
        )
        player.run()
        return

    if backend == "pil":
        from eager_graphics.renderers.pil import PILPlayer

        player = PILPlayer(
            session=session,
            width=1280,
            height=720,
            title="Eager Visual Novel (PIL)",
            asset_dir=asset_dir,
        )
        player.run()
        return

    if backend == "pyglet":
        from eager_graphics.renderers.pyglet import PygletPlayer

        PygletPlayer(
            session=session,
            width=getattr(engine.renderer, "width", 1280) if hasattr(engine, "renderer") else 1280,
            height=720,
            title="Eager Visual Novel",
            asset_dir=asset_dir,
        )
    else:
        return

    import pyglet

    pyglet.app.run()


def _cmd_run(args: argparse.Namespace) -> int:
    """Run an Eager visual novel project directory."""
    _ensure_graphics()
    from eager_runtime.engine import VisualEngine
    from eager_runtime.project import ProjectConfig

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

    engine = VisualEngine(
        str(script_path),
        backend=args.backend,
        audio_backend=audio_backend,
        asset_dir=str(asset_dir) if asset_dir else None,
    )
    _run_interactive_player(engine, backend=args.backend)
    return 0


def _cmd_new(args: argparse.Namespace) -> int:
    """Scaffold a new Eager project."""
    target_dir = Path(args.name)
    if target_dir.exists():
        sys.stderr.write(f"Error: Directory '{target_dir}' already exists.\n")
        return 1

    target_dir.mkdir(parents=True)
    (target_dir / "assets").mkdir()
    (target_dir / "assets" / "characters").mkdir()
    (target_dir / "assets" / "backgrounds").mkdir()
    (target_dir / "assets" / "audio").mkdir()

    # game.toml
    toml_content = f"""[game]
title = "{args.name.replace('_', ' ').title()}"
version = "0.1.0"
author = "Your Name"
entry_script = "main.es"

[window]
width = 1920
height = 1080
"""
    (target_dir / "game.toml").write_text(toml_content, encoding="utf-8")

    # main.es
    es_content = """## Start --- start
Narrator: Welcome to your new visual novel!
Narrator: Create characters, dialogue, and choices here.
"""
    (target_dir / "main.es").write_text(es_content, encoding="utf-8")

    print(f"Created new Eager project in '{target_dir}'.")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Validate screenplay script or project directory."""
    target_path = Path(args.script)
    if not target_path.exists():
        sys.stderr.write(f"Error: Path '{target_path}' not found.\n")
        return 1

    if target_path.is_dir():
        from eager_runtime.project import ProjectConfig

        cfg_path = target_path / "game.toml"
        cfg = ProjectConfig.load(cfg_path) if cfg_path.exists() else ProjectConfig()
        script_file = target_path / cfg.entry_script
        if not script_file.exists():
            es_files = list(target_path.glob("*.es"))
            if not es_files:
                sys.stderr.write(f"Error: No .es scripts found in '{target_path}'.\n")
                return 1
            script_file = es_files[0]
    else:
        script_file = target_path

    try:
        text = script_file.read_text(encoding="utf-8")
        items = eager_script.parse(text, plain=args.plain)
        result = eager_script.validate(items, plain=args.plain)
    except (eager_script.ParseError, OSError, ValueError, TypeError) as err:
        sys.stderr.write(f"Check failed with error: {err}\n")
        return 1

    if result.errors:
        print(f"Validation FAILED with {len(result.errors)} error(s):")
        for err in result.errors:
            print(f"  Line {err.line_number}: {err.message}")
        return 1

    if result.warnings:
        print(f"Validation passed with {len(result.warnings)} warning(s):")
        for warn in result.warnings:
            print(f"  Line {warn.line_number}: {warn.message}")
    else:
        print("Validation PASSED (0 errors, 0 warnings).")
    return 0


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
                rel = file.relative_to(proj_dir)
                # Skip venv, cache, git directories
                if any(part.startswith((".", "__pycache__", "venv")) for part in rel.parts):
                    continue
                zf.write(file, rel)

    print(f"Build complete: archive created at '{out_path}'.")
    return 0



# ── Entry points ────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``eager`` CLI (text-only)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def main_x(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``eager-x`` CLI (visual novel with graphics)."""
    parser = build_x_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
