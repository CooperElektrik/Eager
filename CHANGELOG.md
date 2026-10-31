# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-10-30

### Added

- **Track R1: Syntax & AST Lowering**:
  - Added `{fast}` typewriter text reveal tag support in `eager_core.text` (`FormattedText.fast_index`, `TextReveal`). Dialogue preceding `{fast}` is revealed instantly on the initial frame while subsequent text animates at normal typewriter speed.
  - Added streaming AST generator `parse_iter` and stateful `ScreenplayParser` in `eager-script`.
  - Added `ParsedSet`, `ParsedDefault`, `ParsedCharacter`, `ParsedIf`, `ParsedElif`, `ParsedElse`, `ParsedEnd`, `ParsedCondJump`, and `ParsedLocalJump` AST node definitions.
  - Expanded boundary tests for screenplay syntax covering empty scripts, consecutive blank lines, unclosed voice/formatting tags, bare jumps/calls/hooks, and unicode integrity across CJK and emoji.
  - Added automatic flushing of unclosed `@if` blocks on script EOF in screenplay parser.
- **Track R2: Core Primitives & Safety**:
  - Established custom domain exception hierarchy in `src/eager_core/exceptions.py` defining `EagerCoreError(Exception)`, `AudioError(EagerCoreError, ValueError)`, `ColorParseError(EagerCoreError, ValueError)`, `StorageError(EagerCoreError, OSError)`, and `I18nError(EagerCoreError, ValueError)` with arbitrary forensic keyword context attributes.
  - Added `Vec2` arithmetic safety: operations on incompatible types return `NotImplemented` and division by zero raises an informative `ZeroDivisionError`.
  - Added hex syntax validation in `Color.from_hex` raising `ColorParseError`.
  - Sealed 100% of public submodules across `eager-core` (10 submodules) and `eager-script` (5 submodules) with explicit ASCII-sorted `__all__` lists.
- **Track R3: Headless Runtime & Fault-Tolerant Persistence**:
  - Stream-aware input handling in `TerminalPlayer`: caught `(EOFError, KeyboardInterrupt, OSError, ValueError)` on choice and text prompt inputs, providing graceful fallback when streams are closed or redirected.
  - Automatic forensic save backup: `SaveManager.load_slot()` detects non-dict roots, missing checkpoints, or malformed JSON payloads and automatically creates `<slot>.json.corrupt.bak` while returning `None`.
  - Resilient slot metadata handling: `SaveMetadata.from_dict()` and `SaveManager.list_slots()` gracefully skip corrupted save slots without aborting directory listing.
  - Aligned `SaveData.CURRENT_VERSION` with `SaveMetadata` v2 and added automatic fallback migration for unversioned/legacy saves.
  - Enhanced asset integrity checker (`check_assets()`): extracted character attributes and recursively descended into inline choice bodies.
  - Robust project graph loading: re-raised parse errors in `load_project_graph()` during `hot_reload`, and synchronized declared characters and default variables.
  - Live localization hot-reloading: dynamically reloaded locale catalogs and preserved translation and character styling during presentation refresh.
  - Translation fallback: added raw speaker identifier fallback when display name has no matching translation key in catalog.
  - Session navigation safety: ensured clean dialogue clearing and `is_finished` flag reset on `GameSession.warp()`.
  - Configured project directory resolution for localization catalogs and viewport dimensions.
  - Sealed all 15 submodules in `eager-runtime` with explicit ASCII-sorted `__all__` lists.
- **Track R4: Presentation & Backends Resilience**:
  - Structured audio error logging: added `logger.warning(...)` diagnostics to `PygletAudioBackend` and `MiniaudioAudioBackend` when encountering uninitialized audio devices, missing media assets, or streaming decode failures.
  - Bound `InputPromptEvent` in `StageDirector.bind()` and wired `active_input_prompt` into `UIState` and `clear_dialogue()`.
  - Preserved live timeline during `StageCompositor.save_state()`: settled stage values are snapshotted without terminating active timeline animations or screen fade overlays mid-beat.
  - Custom fade-in color: added optional `color` parameter to `StageCompositor.fade_in()` and wired parameter parsing in `StageDirector.handle_fade_in()`.
  - Pyglet screenshot export: implemented `PygletRenderer.save_frame()` screenshot capture.
  - Unified fullscreen handling: wired `InputAction.FULLSCREEN` toggling across both `PygletPlayer` and `PILPlayer`.
  - NVL mode enhancements in `UIOverlay.draw_nvl`: added inline text tag parsing, font size scaling, and tail-fit overflowing dialogue entries.
  - Renderer introspection and parity: implemented `PygletRenderer.debug_info()` / `__repr__` and PygletPlayer F3 debug overlay cycling parity with `PILPlayer`.
  - Dynamic element mapping: resolved character element IDs via character display names, and translated speakers after character name resolution.
  - State snapshotting: included `ui_state` inside `save_visual_state` snapshots.
  - Added stage composition boundary tests (`test_composition_edge_cases.py`) verifying offscreen coordinates, negative scale, rotation beyond 360°, zero opacity culling, and layer z-order sorting.
  - Sealed all 17 submodules in `eager-graphics` with explicit ASCII-sorted `__all__` lists.
- **Track R5: Language Server Protocol Intelligence**:
  - Recognized and masked `@include` directives in `ScriptDocument`, wiring definition navigation and document links.
  - Partial filter autocompletion: regex-based filtering for scene targets (e.g., `> s` or `visited('s')`), directives, and built-in functions.
  - Character documentation on hover: hovering character tokens inside engine hooks (e.g., `~ show <char>`) displays character sheets with display names, colors, and asset references.
  - Function documentation tooltips: added full parameter and return type hover docstrings for all 11 DSL expression functions.
  - Definition lookup fallback: variable definition navigation falls back to the first mutation site when an explicit `@default` declaration is absent.
  - Dotted persistent variables: full support for `persistent.<var>` in expressions, hover tooltips, and completions.
  - Choice inline spans scanning and recursive inline choice AST lookup.
  - Anonymous scene resolution and prefix variants for append (`+`) and fresh-box (`=`) dialogue tags.
  - Dynamic beat occurrence computation across document edits.
  - Preserved indentation during AST error recovery: `_recover_ast` retains leading whitespace to prevent indentation truncation inside nested choice blocks.
  - Buffer synchronization diagnostics clearing: publishing empty diagnostics when untracked or deleted files are closed.
  - CLI capabilities: added `--version` flag and validated that target files end in `.es`.
  - Sealed all 14 submodules in `eager-script-lsp` with explicit ASCII-sorted `__all__` lists.
- **Track R6: Monorepo Modernization & Testing**:
  - Authored comprehensive 58-test opaque-box E2E test suite in `packages/eager-runtime/tests/test_scenarios.py` across 4 systematic tiers (Feature Coverage, Boundary & Corner Cases, Cross-Feature Combinations, Real-World Application Scenarios) and published `TEST_READY.md`.
  - Standardized test file naming to mirror source submodules 1:1 across all packages (`test_graph.py`, `test_parser.py`, `test_runtime.py`, `test_saves.py`, `test_renderer_pyglet.py`, etc.).
  - Modernized the entire monorepo test suite to native pytest assertions, eliminating legacy `unittest.TestCase` inheritance and slow allocations.
  - Consolidated redundant and slow test suites, slashing test suite execution time to ~4.5 seconds across 833 passing tests with zero flakiness.
  - Migrated deprecated `tool.uv.dev-dependencies` to `dependency-groups.dev` in root `pyproject.toml`.
  - Synchronized `>= 0.7.0` intra-monorepo minimum version dependencies across packaging manifests (`debian/DEBIAN/control`, `windows/eager.iss`, `editors/vscode/package.json`, `editors/vscode/package-lock.json`).
- **Track R7: Documentation & Ecosystem**:
  - Complete documentation overhaul using Material for MkDocs (`mkdocs.yml`), building in ~4.7s with zero warnings.
  - 100% Google-style docstring coverage across all submodules in all 5 packages, validated by `mkdocstrings[python]` autodoc.
  - Restructured API reference documentation into dedicated per-module documentation pages under `docs/api/`.
  - Authored developer guides under `docs/guides/` covering monorepo architecture, import conventions, expression evaluation, and engine hook parsing.

### Changed

- **Track R1**: Removed dead code in `eager-script` (`VOICE_PATTERN`, `_strip_line_comment`, `_slugify`).
- **Track R2**: Removed obsolete `"Programming Language :: Python :: 3.10"` classifier across all `pyproject.toml` files, aligning with Python `>=3.11` runtime requirements.
- **Track R4**: Corrected `pyglet.py` error message to recommend `pip install 'eager-graphics[hardware]'`.
- **Track R4**: Disambiguated `ChoiceOption`: removed re-export from `ui_state.py` and consolidated canonical imports directly to `from eager_core.events import ChoiceOption`.

### Fixed

- **Track R1**: Safe expression evaluator catches and wraps all runtime arithmetic, type, and value errors (`ZeroDivisionError`, `ArithmeticError`, `TypeError`, `ValueError`) into `ExprError`.
- **Track R1**: Refactored `test_parser.py` with explicit type narrowing, resolving 922 basedpyright errors and enabling permanent removal of `ignore = ["tests/test_parser.py"]`.
- **Track R1**: Fixed `@if/@elif/@else` unreachable code and cycle false positive warnings in `SceneGraph` analysis and validator.
- **Track R3**: Fixed infinite loop bug on `InputPromptEvent` in `EventDispatcher.run_until_pause()` by adding `InputPromptEvent` to the pause boundary condition.
- **Track R3**: Fixed non-canonical direct submodule import in `cli.py:405` (`from eager_core.audio import NullAudioBackend`).
- **Track R4**: Resolved 124 basedpyright diagnostics across `packages/eager-graphics/tests/` (MockUIDrawBackend method signatures, PIL getpixel narrowing, Pyglet window fixtures).
- **Track R4**: Fixed non-canonical import in `test_director.py:5` (`from eager_core.audio import AudioMixer, NullAudioBackend`).
- **Track R5**: Suppressed single-file false positive diagnostics for subroutine returns, external scene labels, and entry point reachability in multi-file projects.
- **Track R5**: Filtered out `persistent.*` variables from preamble `@default` declaration quick fixes.

## [0.6.0] - 2026-10-24

### Added

- **Save Slot Thumbnails:** `SaveMetadata` carries a `thumbnail_path` field (schema v1→v2 with automatic migration). `GameSession.save_game()` captures a thumbnail screenshot to `save_dir/screenshots/thumbs/` and stores the path in slot metadata. Save schema migrations are supported for existing v1 saves.
- **Autosave:** New `Preferences.autosave_enabled` flag (default `true`). `GameSession.advance()` automatically saves to circular autosave slots at each narrative interaction boundary (dialogue, narration, choice, input, story end), respecting `skip_mode` and `max_autosaves`.
- **Quicksave/Quickload Toast:** `UIOverlay` shows a transient toast confirmation ("Saved to quickslot" / "Loaded quickslot") when using F5/F9 or the quick menu, driven by `update_toast(dt)` each frame.

### Changed

- `SaveMetadata` schema bumped from v1 to v2; v1 saves are automatically migrated on load (adds `thumbnail_path: null`).

### Fixed

- `SaveManager.save_slot()` now accepts `thumbnail_path` via `metadata_extra`.

## [0.5.0] - 2026-10-24

### Added

- **Graphics Parity:** Added `eager_graphics.fonts` and automated cross-backend rendering parity tests (`test_backend_parity.py`) asserting typographic metrics, UI primitive rasterization, stage composition, and crossfade blending equivalence between PIL and Pyglet.
- **Playtime Tracking & Screenshots:** Added session playtime accumulation (`_playtime`, `playtime_formatted`) to `GameSession` and `SaveMetadata`, and wired `InputAction.SCREENSHOT` to capture timestamped frame screenshots to `save_dir / "screenshots"`.
- **Project Configuration & Themes:** Added theme name and custom `[theme]` color overrides parsing in `ProjectConfig.load()`, propagating configured theme styling into `GameSession` via `eager run`.
- **Decoupled Theme Provider:** Added `ThemeFactory` protocol type and `register_theme_factory` / `get_theme_factory` in `eager_core.protocols`, allowing runtime theme resolution without importing `eager-graphics` in headless environments.
- **Language Server:** Added inlay hints for character display names on speaker tokens when using short character identifiers.
- **Language Server:** Added the `eager-script-lsp` package providing full LSP 3.17+ server support for Eager-Script screenplays, featuring resilient document scanning, workspace symbol indexing, real-time diagnostics (syntax, dead targets, asset checks, i18n keys), context-aware completions, hover previews, go-to-definition, reference search, call hierarchies, multi-file rename, semantic tokens, inlay hints, color decorators, and "Warp & Play" code lenses.
- **CLI & Integration:** Added the `eager-script-lsp` standalone executable and the `eager lsp` runtime CLI subcommand supporting stdio, TCP, WebSocket, and headless batch diagnostics (`--check`). Added optional `lsp` extra to `eager-runtime`.
- **VS Code Extension:** Added VS Code extension in `editors/vscode` with full TextMate grammar and language server integration.

### Changed

- **Script Discovery:** `resolve_project_scripts` and `WorkspaceIndex` now sort screenplay files deterministically and prioritize the entry script specified in `game.toml` as index 0, while excluding `dist` and `build` directories.
- **Dependencies:** Relaxed `eager-runtime` dependency on `eager-script` from exact `== 0.4.0` to `>= 0.4.0`.

### Fixed

- **Graphics Parity:** Resolved cross-backend divergences between `PILRenderer` and `PygletRenderer`:
  - Maintained outgoing background opacity at `1.0` during crossfades to achieve mathematically linear blending ($OVER$) without midpoint luminance dips to black.
  - Aligned Pyglet font point sizing to 1:1 window pixels (`dpi=72`) and unified `measure_text` typographic metrics and anchor definitions with PIL.
  - Snapped Pyglet UI rectangle and gradient boundaries to integer pixels to eliminate subpixel hairline seams.
  - Clamped texture sampling (`GL_CLAMP_TO_EDGE`) in `PygletAssetResolver` to prevent edge texel bleeding on transparent sprites.
  - Rounded gradient color interpolation in PIL to match GPU hardware vertex color interpolation.
- **Persistent Variables:** In-script assignments to `$ persistent.<var>`, compound assignments, `StoryVM.set_variable` / `get_variable`, and dialogue text interpolation `[persistent.<var>]` now interact directly with `PersistentData`, and persistent variables are excluded from `StorySnapshot` and save states to prevent rollback on undo/rewind. Initialized `PersistentData` before `StoryVM` creation so top-level `@default` expressions can resolve persistent variables.
- **Audio Concurrency & Deadlocks:** In `MiniaudioAudioBackend`, released the backend lock during audio stream generator chunk reads (`track.stream.send`) to prevent worker thread deadlocks with audio control methods (`stop`, `set_volume`, `shutdown`). Fixed stream EOF handling on non-looping channels to cleanly update `is_playing = False`.
- **Character Attribute Parsing:** Used `shlex.split` in `ScreenplayParser` for `@character` declarations so quoted attribute values containing spaces are parsed without truncation.
- **Graph Branch Condition Accumulation:** Fixed branch condition accumulation in `_process_scene_body` (`eager_script.graph`) so `@elif` branches negate prior sibling conditions and `@else` branches negate all preceding conditions.
- **Language Server:** Fixed color normalization in `compute_document_colors` where normalized float color channels were erroneously divided by 255.0 a second time.
- **Headless Runtime:** `NullStage._on_append` now appends dialogue text with space separation and clears active choices; `StorySnapshot.from_dict` migration loop enforces strictly monotonic version progression.

### Security

- **Path Traversal Guards:** Added path traversal validation preventing directory traversal attacks across:
  - `AudioMixer._resolve_asset` for audio files.
  - `PILAssetResolver` and `PygletAssetResolver` for image and sprite textures.
  - `resolve_project_scripts` for screenplay includes (`@include`) and script discovery.
  - `WorkspaceIndex` for external symlink screening.
  - `_cmd_build` excluding target archives and build directories from recursive bundling.

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

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/CooperElektrik/Eager/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/CooperElektrik/Eager/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/CooperElektrik/Eager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
