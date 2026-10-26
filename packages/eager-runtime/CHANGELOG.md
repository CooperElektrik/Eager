# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-10-26

### Added

- Stream-aware input handling in `TerminalPlayer`: caught `(EOFError, KeyboardInterrupt, OSError, ValueError)` on choice and text prompt inputs.
- Resilient save file recovery: `SaveManager.load_slot()` detects non-dict roots, missing checkpoints, or malformed JSON payloads and safely archives corrupted files to `<slot>.json.corrupt.bak` while returning `None`.
- Sealed all 15 submodules with explicit ASCII-sorted `__all__` lists.

### Fixed

- Resolved infinite loop on `InputPromptEvent` in `EventDispatcher.run_until_pause()` by including input prompts in the pause boundary condition.
- Direct submodule import in `cli.py:405` (`from eager_core.audio import NullAudioBackend`).

## [0.6.0] - 2026-10-24

### Added

- **Save Slot Thumbnails:** `SaveMetadata` carries a `thumbnail_path` field (schema v1→v2 with automatic migration). `GameSession.save_game()` captures a thumbnail screenshot to `save_dir/screenshots/thumbs/` and stores the path in slot metadata.
- **Autosave:** New `Preferences.autosave_enabled` flag (default `true`). `GameSession.advance()` automatically saves to circular autosave slots at each narrative interaction boundary, respecting `skip_mode` and `max_autosaves`.
- **Quicksave/Quickload Toast:** Transient toast confirmation ("Saved to quickslot" / "Loaded quickslot") shown via `UIOverlay.show_toast()` when using F5/F9 or the quick menu.

### Changed

- `SaveMetadata` schema bumped from v1 to v2; v1 saves are automatically migrated on load.
- `SaveManager.save_slot()` accepts `thumbnail_path` via `metadata_extra`.

## [0.5.0] - 2026-10-24

### Added

- `GameSession` session playtime accumulation (`_playtime` and `playtime` property) tracked in `update(dt)`, persisted via `save_slot()` and `quicksave()`, and restored upon `load_game()` and `quickload()`.
- `SaveMetadata.playtime_formatted` property formatting playtime as `HH:MM:SS` or `MM:SS`.
- `GameSession.take_screenshot()` and input routing for `InputAction.SCREENSHOT` to save timestamped PNG screenshots to `save_dir / "screenshots"` (using `renderer.save_frame()` when available).
- `ProjectConfig.load()` support for `theme` and custom `[theme]` color overrides (`theme_overrides`), passed as `config=cfg` into `GameSession` in `cli.py:_cmd_run`.

### Changed

- Headless theme decoupling: `_resolve_theme` in `session.py` resolves theme configurations via `get_theme_factory()` provider registry (or falls back to raw option dictionaries) instead of importing `eager_graphics.theme.Theme` directly.
- Script discovery ordering: `resolve_project_scripts` deterministically sorts discovered screenplay files and prioritizes the configured `entry_script` from `game.toml` as index 0; excludes `build` and `dist` directories.
- Relaxed `eager-script` dependency specification in `pyproject.toml` from `== 0.4.0` to `>= 0.4.0`.

### Fixed

- **Persistent Variables:** Routed in-script `$ persistent.<key> = ...` and compound assignments (`+=`, `-=`, etc.), `StoryVM.set_variable` / `get_variable`, and dialogue text interpolation `[persistent.<key>]` directly to the injected `PersistentData` instance; accepted `persistent` and `initial_variables` in `StoryVM.__init__`; excluded `persistent` variables from `StorySnapshot` and save states to ensure persistence state is never rolled back during undo/rewind.
- **Initialization Order:** Initialized `PersistentData` before `StoryVM` creation in `GameSession.__init__`, allowing top-level `@default` expressions referencing `persistent.<var>` to resolve against persistent data.
- **NullStage Dialogue Append:** `NullStage._on_append` now appends dialogue text with whitespace separation matching interactive renderers and clears active choice selections.
- **Snapshot Migrations:** Guarded `StorySnapshot.from_dict` migration loop to require strict monotonic version advancement, preventing infinite loops on buggy migration handlers.

### Security

- Path traversal guards in `resolve_project_scripts` preventing script inclusion or traversal outside the project directory via symlinks or parent references (`..`) in `@include` directives.
- Project export safety in `_cmd_build` excluding target zip files and build artifacts (`dist`, `build`) from recursively bundling into the archive.

## [0.4.0] - 2026-10-21

### Added

- Reusable `Checkpoint` and `CheckpointHistory` models in `eager_runtime.state`, providing bounded checkpoint stacks with redo/roll-forward support at narrative interaction points.

### Changed

- `TerminalPlayer` captures interaction checkpoints (`DialogueEvent`, `NarrationEvent`, `ChoicePromptEvent`) using `CheckpointHistory` and rewinds via checkpoint restoration.
- `NullStage.save_visual_state()` only serializes stage compositor state, avoiding duplicate UI state persistence.
- `StoryVM` now builds every `~ input` prompt through a shared `_build_input_prompt()` helper backed by `eager_script.hooks.parse_input_hook`, removing duplicated parsing between normal playback and save/load restoration.
- `eager` CLI and `GameSession` now resolve stage, UI, screen-manager, player, audio, and renderer providers through `eager_core.protocols` entry points instead of importing `eager-graphics` directly.
- `GameSession` mutates choice menus, input boxes, dialogue reveal state, and quick-menu hover state through `UIProtocol` methods, with compatibility fallbacks for custom overlay implementations.
- `GameSession.advance()` completes active stage animations before stepping, and `NullStage`/`NullCompositor` implement `finish_animations()`.
- Tightened `GameSession` to rely on declared stage, director, and audio contracts instead of redundant `hasattr` guards.
- `i18n.compute_beat_id()` honors explicit `{id=...}` markers on hook beats, and catalog extraction and validation share `parse_input_hook`.

### Fixed

- Input prompts are translated and interpolated consistently in both normal playback and save/load restoration paths, including prompts with `default=` values and unquoted multi-word text.

### Removed

- `HistoryManager` class in `eager_runtime.state`.
- Beat-level history tracking and rollback methods (`_history`, `history_enabled`, `enable_history()`, `disable_history()`, `can_rollback`, `rollback()`) from `StoryVM`.

## [0.3.0] - 2026-10-21

### Added

- Headless protocol stubs (`NullStage`, `NullUI`, `NullScreenManager`, `HeadlessUIState`) in `eager_runtime.headless` implementing core protocols.
- `enable_history()`, `disable_history()`, and `history_enabled` properties on `StoryVM` to control internal beat-level history recording.

### Changed

- Injected stage/UI architecture: `GameSession` now accepts injected `stage`, `ui`, and `screens` conforming to `eager_core.protocols`, fully decoupling `eager-runtime` from `eager-graphics`.
- Unified rollback: `GameSession` manages unified story and visual checkpoints, disabling redundant `StoryVM` beat-level snapshots by default.
- Propagated viewport resize events from `GameSession` to registered screens and UI.
- `GameSession.handle_input(InputAction.POINTER_MOVE, ...)` returns a boolean indicating whether the pointer move changed any UI hover state across screens, choice menus, or quick menus.

### Fixed

- Serialized `active_input_prompt` in `SaveData` so pending text input modal prompts round-trip correctly across save/load cycles.
- Quoted argument parsing for `~ input` hook commands in `StoryVM`, preserving spaces within prompt strings and default values.
- Registered `@character` metadata (name, display name, color) from `SceneGraph` into `stage` and `ui_state` on story load.
- Resolved all basedpyright type errors and warnings across the package.

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

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/CooperElektrik/Eager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
