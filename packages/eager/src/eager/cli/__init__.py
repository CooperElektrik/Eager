"""Command-line interface for the Eager runtime.

Single entry point is provided: ``eager`` with subcommands ``run``, ``check``,
``test-run``, and ``new``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import eager.script
from eager.script.graph import to_graph
from eager.script.includes import resolve_includes
from eager.script.project import ProjectConfig
from eager.vm.runtime import StoryVM

logger = logging.getLogger(__name__)

__all__ = [
    "build_parser",
    "main",
    "run_test_run",
]


def _version_string() -> str:
    """Return formatted Eager CLI version string."""
    from eager import __version__

    return f"eager {__version__}"


def _resolve_entry_script(target: Path) -> tuple[Path, ProjectConfig]:
    """Resolve an entry .es script and ProjectConfig from a file or project directory."""
    if target.is_dir():
        toml_path = target / "game.toml"
        cfg = ProjectConfig.load(toml_path) if toml_path.exists() else ProjectConfig()
        script_path = target / cfg.entry_script
        if not script_path.exists():
            es_files = sorted(target.glob("*.es"))
            if not es_files:
                msg = f"No .es script found in '{target}'."
                raise FileNotFoundError(msg)
            script_path = es_files[0]
        return script_path, cfg

    toml_path = target.resolve().parent / "game.toml"
    cfg = ProjectConfig.load(toml_path) if toml_path.exists() else ProjectConfig()
    return target, cfg


def _resolve_asset_dir(
    script_path: Path,
    asset_dir: str | Path | None,
) -> str | None:
    """Resolve the asset directory, falling back to ``assets/`` beside the script."""
    if asset_dir is not None:
        return str(asset_dir)
    candidate = script_path.resolve().parent / "assets"
    return str(candidate) if candidate.is_dir() else None


def _create_audio_backend(backend: str, *, no_audio: bool = False) -> Any:
    """Instantiate the matching audio backend for the given render backend."""
    from eager.core.audio import NullAudioBackend

    if no_audio or backend != "pyglet":
        return NullAudioBackend()
    try:
        from eager.backends.audio.pyglet import PygletAudioBackend

        return PygletAudioBackend()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to initialize PygletAudioBackend, falling back to NullAudioBackend: %s", exc)
        return NullAudioBackend()


def build_parser() -> argparse.ArgumentParser:
    """Build the unified CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="eager",
        description="Eager Visual Novel Engine CLI",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=_version_string(),
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Set logging verbosity (default: WARNING)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging (shorthand for --log-level DEBUG)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── run ───────────────────────────────────────────────────────────
    run_p = subparsers.add_parser(
        "run",
        help="Run an Eager visual novel (.es script or project directory).",
    )
    run_p.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Path to a .es screenplay file or project directory (default: '.').",
    )
    run_p.add_argument(
        "--backend",
        choices=("pyglet", "null"),
        default="pyglet",
        help="Rendering backend (default: pyglet).",
    )
    run_p.add_argument("--asset-dir", help="Asset directory path (default: <script_dir>/assets).")
    run_p.add_argument("--no-audio", action="store_true", help="Disable audio playback.")
    run_p.add_argument(
        "--scale-mode",
        choices=("letterbox", "stretch", "cover"),
        help="Viewport scaling mode.",
    )
    run_p.add_argument("--skip-title", action="store_true", help="Jump directly into the story.")
    run_p.add_argument("--uncapped", action="store_true", help="Disable 60 FPS cap / VSync.")
    run_p.add_argument("--max-steps", type=int, default=2000, help="Max steps for null backend.")
    run_p.add_argument("--choice", type=int, default=0, help="Auto-choice index for null backend.")
    run_p.set_defaults(func=_cmd_run)

    # ── check ─────────────────────────────────────────────────────────
    check_p = subparsers.add_parser(
        "check",
        help="Validate screenplay syntax, reachability, and assets.",
    )
    check_p.add_argument("script", help="Path to the .es screenplay file or project directory.")
    check_p.add_argument("--assets", action="store_true", help="Verify referenced asset files.")
    check_p.add_argument("--asset-dir", help="Asset directory path for --assets check.")
    check_p.set_defaults(func=_cmd_check)

    # ── test-run ──────────────────────────────────────────────────────
    test_p = subparsers.add_parser(
        "test-run",
        help="Simulate a headless playthrough of the screenplay.",
    )
    test_p.add_argument("script", help="Path to the .es screenplay file or project directory.")
    test_p.add_argument("--max-steps", type=int, default=5000, help="Maximum VM steps per path.")
    test_p.add_argument(
        "--all-paths",
        action="store_true",
        help="Exhaustively explore all branching choice paths.",
    )
    test_p.set_defaults(func=run_test_run)

    # ── new ───────────────────────────────────────────────────────────
    new_p = subparsers.add_parser("new", help="Create a new Eager visual novel project.")
    new_p.add_argument("name", help="Project directory name.")
    new_p.set_defaults(func=_cmd_new)

    return parser


def _run_headless(
    session: Any,
    renderer: Any,
    *,
    max_steps: int = 2000,
    auto_choice: int = 0,
) -> int:
    """Drive a GameSession headlessly using NullRenderBackend."""
    steps = 0
    while not session.is_finished and steps < max_steps:
        if session.active_choice_prompt is not None:
            opts = session.active_choice_prompt.options
            enabled = [o.index for o in opts if o.enabled]
            idx = auto_choice if auto_choice in enabled else (enabled[0] if enabled else 0)
            session.choose(idx)
        else:
            session.advance()
        session.update(1.0 / 60.0)
        session.draw(renderer, session.virtual_width, session.virtual_height)
        steps += 1
    print(f"Headless run completed: {steps} steps, ended={session.is_finished}.")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Run an Eager screenplay or project directory."""
    from eager.session import GameSession

    target = Path(args.target)
    if not target.exists():
        sys.stderr.write(f"Error: Path '{target}' not found.\n")
        return 1

    try:
        script_path, cfg = _resolve_entry_script(target)
    except FileNotFoundError as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1

    asset_dir = _resolve_asset_dir(script_path, getattr(args, "asset_dir", None))
    audio_backend = _create_audio_backend(
        args.backend,
        no_audio=getattr(args, "no_audio", False),
    )

    session = GameSession(
        str(script_path),
        backend=args.backend,
        audio_backend=audio_backend,
        asset_dir=asset_dir,
        config=cfg,
    )

    if args.backend == "null":
        from eager.backends.renderers.null import NullRenderBackend

        renderer = NullRenderBackend()
        return _run_headless(
            session,
            renderer,
            max_steps=args.max_steps,
            auto_choice=args.choice,
        )

    if not getattr(args, "skip_title", False) and hasattr(session.screens, "show"):
        session.screens.show("title", session)
        session.mode = "title"

    from eager.ui.pyglet_player import PygletPlayer

    player_kwargs: dict[str, Any] = {
        "session": session,
        "width": getattr(session, "virtual_width", 1280) or 1280,
        "height": getattr(session, "virtual_height", 720) or 720,
        "title": cfg.title or "Eager Visual Novel",
        "asset_dir": asset_dir,
    }
    scale_arg = getattr(args, "scale_mode", None) or getattr(cfg, "scale_mode", None)
    if scale_arg:
        from eager.core.types import ScaleMode

        try:
            player_kwargs["scale_mode"] = ScaleMode(scale_arg.lower())
        except (ValueError, KeyError):
            pass
    if getattr(args, "uncapped", False):
        player_kwargs["uncapped"] = True

    player = PygletPlayer(**player_kwargs)
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
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    """Validate screenplay script or project directory."""
    target_path = Path(args.script)
    if not target_path.exists():
        sys.stderr.write(f"Error: Path '{target_path}' not found.\n")
        return 1

    try:
        script_file, _ = _resolve_entry_script(target_path)
        raw_items = eager.script.parse(script_file.read_text(encoding="utf-8"))
        items = resolve_includes(raw_items, base_dir=script_file.parent, visited={script_file.resolve()})
        result = eager.script.validate(items)
    except (eager.script.EagerScriptError, FileNotFoundError, OSError, ValueError, TypeError) as err:
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

        graph = to_graph(items)
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


def run_test_run(args: argparse.Namespace) -> int:
    """Perform headless test run, optionally exploring all branching paths."""
    target_path = Path(args.script)
    if not target_path.exists():
        print(f"Error: Screenplay file '{target_path}' not found.", file=sys.stderr)
        return 1

    script_file, _ = _resolve_entry_script(target_path)
    raw_items = eager.script.parse(script_file.read_text(encoding="utf-8"))
    graph = to_graph(resolve_includes(raw_items, base_dir=script_file.parent, visited={script_file.resolve()}))

    if getattr(args, "all_paths", False):
        paths_completed = 0
        total_steps = 0
        total_events = 0
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
            first_enabled = next((opt.index for opt in vm.pending_choice.options if opt.enabled), None)
            if first_enabled is not None:
                vm.choose(first_enabled)
            else:
                break

    print(f"Test run completed: {steps} steps, {events_count} events dispatched, ended: {vm.is_ended}.")
    return 0


def _cmd_new(args: argparse.Namespace) -> int:
    """Scaffold a new Eager project."""
    target_dir = Path(args.name)
    if target_dir.exists():
        sys.stderr.write(f"Error: Directory '{target_dir}' already exists.\n")
        return 1

    title = Path(args.name).name.replace("_", " ").replace("-", " ").title()
    template_dir = Path(__file__).resolve().parent.parent / "template"
    if template_dir.is_dir():
        import shutil

        shutil.copytree(template_dir, target_dir)
        cfg_path = target_dir / "game.toml"
        if cfg_path.exists():
            cfg_text = cfg_path.read_text(encoding="utf-8")
            cfg_text = cfg_text.replace('title = "My First Visual Novel"', f'title = "{title}"')
            cfg_path.write_text(cfg_text, encoding="utf-8")
    else:
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
    print(f"  eager run {target_dir}               # Launch the game")
    print(f"  eager check {target_dir} --assets    # Validate script & assets")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    level_name = "DEBUG" if getattr(args, "verbose", False) else getattr(args, "log_level", "WARNING")
    logging.basicConfig(
        level=getattr(logging, level_name, logging.WARNING),
        format="%(levelname)s %(name)s: %(message)s",
    )
    logger.debug("Executing CLI command %r", getattr(args, "command", None))
    return int(args.func(args))
