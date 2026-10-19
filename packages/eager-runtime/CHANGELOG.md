# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `GameSession.handle_input(InputAction.POINTER_MOVE, ...)` returns a boolean indicating whether the pointer move changed any UI hover state across screens, choice menus, or quick menus.

## [0.2.0] - 2026-10-19

### Added

- `GameSession` controller — the central story/UI state machine connecting GUI players, screens, saves, and rollback.
- Duplicate-label detection and link-reachability validation in `merge_graphs` (`eager_runtime.project`).
- Script hot reloading via a `FileWatcher` and `GameSession.hot_reload` with state reconciliation and an error overlay, wired to `Shift+R` and `--watch`/`--hot-reload`.
- Project scaffolding with `eager new <name>` (a playable starter template) and a `--demo` flag that scaffolds from the full showcase.
- Candidate asset-path resolution (`characters/`, `backgrounds/`) across all resolvers, plus the `AssetChecker` consistency validator (`eager check --assets`).
- Localization pipeline with content-addressed translation IDs (`compute_beat_id`, `extract_catalog`, `merge_catalog`, `validate_catalog`), preference controls, CLI locale options, and a Vietnamese demo translation.
- Save/rollback features — parameterized `SaveManager.quicksave`/`quickload`, true skip-unseen protection with read-beat tracking, choice locking, roll-forward redo, and voice-aware auto-forward.

### Changed

- Interactive CLI maps the render backend to the matching audio backend, with `--no-audio` override and a Null fallback on construction failure; `StageDirector` auto-plays `DialogueEvent.voice` and manages voice lifecycle.

### Removed

- Obsolete "Eager-SP" mode, and the `eager_runtime.engine`/`eager_runtime.events` deprecated shims.

## [0.1.0] - 2026-10-09

- Initial release.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
