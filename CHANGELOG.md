# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-10-21

### Added

- **Plugins:** Provider registry and `eager.providers` entry-point discovery in `eager-core`, letting `eager-graphics` register stage, UI, screen-manager, player, audio, and renderer factories without `eager-runtime` importing it.
- **Script:** Unified input-hook parsing (`InputHookArgs`, `is_input_hook`, `parse_input_args`, `parse_input_hook`) shared by `StoryVM` and localization extraction.
- **UI:** Unified `Theme` styling for overlays, menus, and built-in screens, with viewport-relative font scaling for all HUD and screen text.

### Changed

- **Rollback:** Fully unified state rollback around atomic `Checkpoint` and `CheckpointHistory`, capturing snapshots at narrative interaction boundaries (`DialogueEvent`, `NarrationEvent`, `AppendEvent`, `FreshBoxEvent`, `ChoicePromptEvent`, `InputPromptEvent`, and `StoryEndEvent`).
- **Save & Checkpoint schema:** Eliminated redundant duplicate `ui_state` serialization inside stage visual states (`save_visual_state`), cleanly isolating compositor stage state in `visual` and dialogue/UI state in `ui`.
- **Runtime:** `TerminalPlayer` now uses `CheckpointHistory` to capture interaction points and rewind state on `:undo` / `:rollback`.
- **Graphics:** Added `roll_forward()` to `BasePlayer` for redo traversal across rolled-back checkpoints.
- **Graphics:** Split the monolithic Pillow backend (`renderers/pil.py`) into the `renderers/pil` subpackage (`_compat`, `_constants`, `_imaging`, `_cache`, `assets`, `renderer`, `player`) while preserving the public re-exports.
- **Graphics:** Moved `Theme` from `eager_graphics.screens.theme` to `eager_graphics.theme` and applied it consistently to `UIOverlay`, dialogue/choice/quick-menu components, and built-in screens.
- **Runtime & graphics:** `GameSession` now mutates UI overlays through `UIProtocol` mutation methods, with matching implementations in the headless `NullUI`.
- **Graphics:** Stage timelines now expose `finish_animations()` / `finish_all()` and flush active tweens before snapshots and narrative advances.
- **Maintenance:** Removed redundant defensive `hasattr` checks across the workspace in favor of declared protocol contracts.
- **Tooling:** Added `import-linter` contracts enforcing package boundaries (headless runtime, dependency-free core/script, renderer independence, and screen/director separation).

### Fixed

- **Graphics & runtime:** Prevented saves and rollbacks from capturing mid-transition or 0-opacity stage states by completing active tweens before serialization and advancement.
- **Localization:** Input-hook beats with explicit `{id=...}` markers now reuse that ID when computing translation keys.

### Removed

- **Legacy rollback:** Removed `HistoryManager` and beat-level history recording (`_history`, `history_enabled`, `enable_history()`, `disable_history()`, `can_rollback`, `rollback()`) from `StoryVM`.
- **Visual history:** Removed `VisualHistoryManager` (`eager_graphics/history.py`) and legacy director rollback methods (`enable_visual_history()`, `snapshot_visual_state()`, `rollback_visual_state()`, `on_beat_step()`).
- **Graphics:** Removed the `eager_graphics.screens.theme` module; import `Theme` from `eager_graphics.theme` (or the package root) instead.

## [0.3.0] - 2026-10-21

### Added

- **Architecture:** `StageProtocol`, `UIProtocol`, `UIStateProtocol`, and `ScreenManagerProtocol` defined in `eager-core` and injected into `GameSession`, completely decoupling `eager-runtime` from `eager-graphics`.
- **Runtime:** Headless protocol stubs (`NullStage`, `NullUI`, `NullScreenManager`, `HeadlessUIState`) in `eager_runtime.headless`.
- **Audio:** Audio streaming in `MiniaudioAudioBackend` for long-running tracks (BGM/ambient) using `miniaudio.stream_file` to eliminate main thread loading hitches.
- **Graphics:** `BasePlayer` class deduplicating common session handling, screen management, and input loops between `PILPlayer` and `PygletPlayer`.

### Changed

- **Screens:** Dynamic viewport scaling for built-in screens (`SaveScreen`, `LoadScreen`, `PreferencesScreen`, `HistoryScreen`) adapting layout geometries, fonts, and card dimensions proportionally.
- **Rollback:** Unified rollback systems in `GameSession`, disabling redundant beat-level history snapshots in `StoryVM` by default.
- **Text:** `wrap_text` returns `(line, start, end)` character spans for reliable formatting/reveal offset calculation, and caches results by backend type and font family.
- **Input:** `GameSession.handle_input` and `ScreenManager.handle_mouse_move` return whether hover states changed to gate UI redraws.

### Fixed

- **PIL backend:** Fixed translucent rendering for rectangles, borders, and text glyphs.
- **Saves:** Serialized `active_input_prompt` in `SaveData` to persist active text input dialogs across saves and loads.
- **Script runtime:** Parse `~ input` hook arguments with quote awareness to support multi-word prompts and defaults.
- **Dialogue:** Forward `@character` definitions into `StageDirector` and `UIState` so character colors and display names render correctly.
- **Screens:** Guarded against uninitialized session references in `HistoryScreen.draw`.
- **Type safety:** Resolved all basedpyright type errors and strict type warnings across `eager-core`, `eager-runtime`, and `eager-graphics`.

### Performance

- **PIL backend & GameSession:** Hit-test gating on pointer motion to avoid spurious UI invalidation and stay in Tier 0 (Idle Skip) at 60+ Hz.
- **PIL backend:** Guaranteed clean stage buffer snapshots into `_stage_cache` for settled frames to accelerate UI-only repaints (Tier 3).
- **Audio:** Streaming audio playback avoids blocking the main thread when loading large music files.

## [0.2.0] - 2026-10-19

Consolidates all changes after the v0.1.0 release (initial commit `97609c1`, 2026-10-09). Eager is a `uv` workspace of four packages: `eager-script` (DSL parser), `eager-core` (shared dependency-free leaf), `eager-runtime` (headless VM, `GameSession`, saves, CLI), and `eager-graphics` (compositor and Null/Pyglet/PIL backends). See individual package changelogs for package-specific details:

- [`packages/eager-core/CHANGELOG.md`](file:///home/cooper/DevThings/eager-mono/packages/eager-core/CHANGELOG.md)
- [`packages/eager-graphics/CHANGELOG.md`](file:///home/cooper/DevThings/eager-mono/packages/eager-graphics/CHANGELOG.md)
- [`packages/eager-runtime/CHANGELOG.md`](file:///home/cooper/DevThings/eager-mono/packages/eager-runtime/CHANGELOG.md)
- [`packages/eager-script/CHANGELOG.md`](file:///home/cooper/DevThings/eager-mono/packages/eager-script/CHANGELOG.md)

### Added

- **Tooling/examples:** `scripts/analyze_deps.py` module-dependency reporter, `scripts/concat_py.py`, render and PIL benchmarks, and a reworked Hoshiko-asset demo with credits.
- **Project:** Root `README.md`, MIT `LICENSE` mirrored into all four packages, and a CI workflow (ruff + pytest matrix on Python 3.11/3.14).

### Changed

- **Build:** Graphics dependencies became lazy/optional imports; Pillow-SIMD and regular Pillow remain mutually exclusive. The root project now depends on workspace members and `requires-python` was bumped to `>=3.11`.
- **Docs:** `AGENTS.md` was rewritten as operational guidelines, and package READMEs and graphics/script docs were brought in line with the code.

### Fixed

- Corrected artist credits and asset naming in the demo.

## [0.1.0] - 2026-10-09

- Initial release.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/CooperElektrik/Eager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
