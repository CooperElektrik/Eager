# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Consolidates all changes after the v0.1.0 release (initial commit `97609c1`, 2026-10-09). Eager is a `uv` workspace of four packages: `eager-script` (DSL parser), `eager-core` (shared dependency-free leaf), `eager-runtime` (headless VM, `GameSession`, saves, CLI), and `eager-graphics` (compositor and Null/Pyglet/PIL backends).

### Added

- **eager-script:** Inline choice menu blocks — indented reactions and mutations directly under `?` options without target labels, lowered into anonymous scenes (`SceneNode.is_anonymous`) that return to the caller via inline call frames, with tab/space normalization and comment support.
- **eager-script:** Duplicate-label detection and link-reachability validation in `merge_graphs`, plus expanded parser/validator coverage and DSL documentation (`docs/syntax.md`, `docs/validation.md`, `docs/scene-graph.md`).
- **eager-core:** Extended `AudioBackend` protocol with `loop_start`/`loop_end`, `update(dt)`, and `shutdown()`, plus a `BaseAudioBackend` with lifecycle no-ops; `ChannelState` now round-trips loop points through save/load.
- **eager-core:** New `eager_core.i18n` module with stable, content-addressed translation IDs, and text-tag parsing/measurement improvements.
- **eager-runtime:** `GameSession` controller — the central story/UI state machine connecting GUI players, screens, saves, and rollback.
- **eager-runtime:** Script hot reloading via a `FileWatcher` and `GameSession.hot_reload` with state reconciliation and an error overlay, wired to `Shift+R` and `--watch`/`--hot-reload`.
- **eager-runtime:** Project scaffolding with `eager new <name>` (a playable starter template) and a `--demo` flag that scaffolds from the full showcase.
- **eager-runtime:** Candidate asset-path resolution (`characters/`, `backgrounds/`) across all resolvers.
- **eager-runtime:** Localization pipeline with translation catalogs, preference controls, CLI locale options, and a Vietnamese demo translation.
- **eager-runtime:** Save/rollback features — parameterized `SaveManager.quicksave`/`quickload`, true skip-unseen protection with read-beat tracking, choice locking, roll-forward redo, and voice-aware auto-forward.
- **eager-graphics:** Hardware audio backends — `PygletAudioBackend` (EOS-seek loop points) and `MiniaudioAudioBackend` (soft-mixing PCM callback, new `audio` extra), lazily imported beside their renderers, with seamless BGM looping.
- **eager-graphics:** Polyphonic audio mixer using dynamic channel pools for sound effects, plus asset-serial tracking for seamless audio rollback continuity.
- **eager-graphics:** Modernized UI — a two-stage cinematic gradient scrim in `DialogueBox`, a clean typographic `QuickMenu` toolbar, restyled `ChoiceMenu` cards with accent indicators, and an eye-friendly zinc/slate theme with amber accents.
- **eager-graphics:** `draw_gradient_rect` on the `UIDrawBackend` protocol, implemented across Pyglet, PIL, and the Null renderer (Pyglet uses vertex-colored hardware shapes).
- **eager-graphics:** Text-tag parser bridge to UI rendering, plus a graphical modal `InputPromptEvent` for `~ input`.
- **eager-graphics:** `PreferencesScreen` and `HistoryScreen` with backlog voice replay via speaker buttons, `Bar`/`Grid` widgets, `ScreenManager` pointer/key dispatching, and rich save cards.
- **eager-graphics:** Opt-in auto-highlight of the active speaker in `StageDirector`, with configurable dim color, highlight duration, pop scale, and hop tweening.
- **eager-graphics:** `DebugOverlayMode` enum controlling debug overlay display.
- **eager-graphics:** Opt-in `software-simd` extra for Pillow-SIMD rendering, with a `scripts/install_pillow_simd.py` swap helper.
- **Tooling/examples:** `scripts/analyze_deps.py` module-dependency reporter, `scripts/concat_py.py`, render and PIL benchmarks, a reworked Hoshiko-asset demo with credits, asset-consistency checker, and interactive HTML graph export (both later removed).
- **Project:** Root `README.md`, MIT `LICENSE` mirrored into all four packages, and a CI workflow (ruff + pytest matrix on Python 3.11/3.14).

### Changed

- **eager-graphics:** Window players (`PILPlayer`, `PygletPlayer`) are now thin shells over `GameSession`, delegating story/state logic and wiring in quick save/load hotkeys, the QuickMenu, and the screen system.
- **eager-graphics:** The PIL player keeps construction/story logic headless-safe and is driven by a non-blocking `root.update()` loop; the earlier tkinter port dropped the pyglet dependency from the software path.
- **eager-graphics:** The Pyglet backend synced window sizing, public API, and input handling with the other backends; gradient alpha blending was fixed.
- **eager-graphics:** Typewriter reveal continues from existing text on append beats and is synchronized with frame pacing; added a `cache` parameter to `draw_text`/`measure_text` so intermediate reveal states do not pollute the cache.
- **eager-runtime:** Interactive CLI maps the render backend to the matching audio backend, with `--no-audio` override and a Null fallback on construction failure; `StageDirector` auto-plays `DialogueEvent.voice` and manages voice lifecycle.
- **Build:** Graphics dependencies became lazy/optional imports; Pillow-SIMD and regular Pillow remain mutually exclusive. The root project now depends on workspace members and `requires-python` was bumped to `>=3.11`.
- **Docs:** `AGENTS.md` was rewritten as operational guidelines, and package READMEs and graphics/script docs were brought in line with the code.
- **Performance:** Pyglet backend optimizations yielded a ~10–36× FPS improvement.
- **Performance:** PIL renderer gained hierarchical caching, an RGB canvas, adaptive resampling, an alpha lookup table, a 1×1 fast path, cached zero-conversion UI gradients, and buffer pooling.
- **Performance:** PIL sprite compositing now crops to alpha bounding boxes, decomposes masked sprites into opaque interiors plus tiled fringe bands, and skips the gradient mask when ramp endpoints are fully opaque.
- **Performance:** Dirty-rectangle tracking in `render_compositor`, and a non-blocking frame loop reaching ~60 FPS (previously ~39–50 FPS) with truly uncapped runs, at essentially unchanged peak RSS.

### Removed

- **eager-graphics:** The Raylib render backend, its audio backend, tests, and dev dependency.
- **eager-graphics:** `VisualEngine`, replaced by `GameSession`; legacy `classic()`/`cinematic()` theme factories; and the `eager_graphics.easing`, `eager_graphics.text`, and `eager_graphics.timing` re-export shims (import from `eager_core` instead).
- **eager-graphics:** Generic event fallback handler in `StageDirector`.
- **eager-script:** The terminal editor (`eager_script.editor`) and its docs/tests.
- **eager-runtime:** Obsolete "Eager-SP" mode, and the `eager_runtime.engine`/`eager_runtime.events` deprecated shims.
- **Tooling:** The HTML graph debugger.
- **i18n:** Legacy positional translation keys, replaced by content-addressed hashes.

### Fixed

- Corrected `draw_text` parameter order to `(x, y, text)` across screens to match `UIDrawBackend`.
- Resolved raylib sprite rendering, Pyglet UI layout, and PIL transition scaling issues.
- Added a thread-lock mutex to Miniaudio backend tracks.
- Fixed PIL adaptive-resampling cache poisoning and the stage freeze when idle.
- Fixed the Pyglet typewriter reveal animation and PIL frame pacing.
- Corrected artist credits and asset naming in the demo.

## [0.1.0] - 2026-10-09

- Initial release.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/97609c1...HEAD
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
