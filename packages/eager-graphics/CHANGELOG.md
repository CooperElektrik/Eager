# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `Screen.handle_mouse_move` and `ScreenManager.handle_mouse_move` return a boolean indicating whether a hover state actually changed.

### Fixed

- Telemetry now correctly reports `Tier 3 (Stage Cache / UI Only)` when `PILRenderer` restores the stage from `_stage_cache`.

### Performance

- Hit-test gating on mouse motion: `PILPlayer._on_motion` only marks `_ui_dirty` if pointer input changed hover states, keeping the engine in Tier 0 (Idle Skip) at 60+ Hz over empty space.
- Guaranteed clean stage buffer snapshotting: `PILRenderer` caches the settled stage before drawing UI, allowing subsequent mouse moves to restore from `_stage_cache` without a full repaint.

## [0.2.0] - 2026-10-19

### Added

- Hardware audio backends — `PygletAudioBackend` (EOS-seek loop points) and `MiniaudioAudioBackend` (soft-mixing PCM callback, new `audio` extra), lazily imported beside their renderers, with seamless BGM looping and hook forwarding in `StageDirector`.
- Modernized UI — a two-stage cinematic gradient scrim in `DialogueBox`, a clean typographic `QuickMenu` toolbar, restyled `ChoiceMenu` cards with accent indicators, and an eye-friendly zinc/slate theme with amber accents.
- `draw_gradient_rect` on the `UIDrawBackend` protocol, implemented across Pyglet, PIL, and the Null renderer (Pyglet uses vertex-colored hardware shapes).
- Text-tag parser bridge to UI rendering, plus a graphical modal `InputPromptEvent` for `~ input`.
- `PreferencesScreen` and `HistoryScreen` with backlog voice replay via speaker buttons, `Bar`/`Grid` widgets, `ScreenManager` pointer/key dispatching, and rich save cards.
- Opt-in auto-highlight of the active speaker in `StageDirector`, with configurable dim color, highlight duration, pop scale, and hop tweening.
- `DebugOverlayMode` enum controlling debug overlay display.
- Opt-in `software-simd` extra for Pillow-SIMD rendering, with a `scripts/install_pillow_simd.py` swap helper.

### Changed

- Window players (`PILPlayer`, `PygletPlayer`) are now thin shells over `GameSession`, delegating story/state logic and wiring in quick save/load hotkeys, the QuickMenu, and the screen system.
- The PIL player keeps construction/story logic headless-safe and is driven by a non-blocking `root.update()` loop; the earlier tkinter port dropped the pyglet dependency from the software path.
- The Pyglet backend synced window sizing, public API, and input handling with the other backends; gradient alpha blending was fixed.
- Typewriter reveal continues from existing text on append beats and is synchronized with frame pacing; added a `cache` parameter to `draw_text`/`measure_text` so intermediate reveal states do not pollute the cache.

### Removed

- The Raylib render backend, its audio backend, tests, and dev dependency.
- `VisualEngine`, replaced by `GameSession`; legacy `classic()`/`cinematic()` theme factories; and the `eager_graphics.easing`, `eager_graphics.text`, and `eager_graphics.timing` re-export shims (import from `eager_core` instead).
- Generic event fallback handler in `StageDirector`.

### Fixed

- Corrected `draw_text` parameter order to `(x, y, text)` across screens to match `UIDrawBackend`.
- Resolved raylib sprite rendering, Pyglet UI layout, and PIL transition scaling issues.
- Added a thread-lock mutex to Miniaudio backend tracks.
- Fixed PIL adaptive-resampling cache poisoning and the stage freeze when idle.
- Fixed the Pyglet typewriter reveal animation and PIL frame pacing.

### Performance

- Pyglet backend optimizations yielded a ~10–36× FPS improvement.
- PIL renderer gained hierarchical caching, an RGB canvas, adaptive resampling, an alpha lookup table, a 1×1 fast path, cached zero-conversion UI gradients, and buffer pooling.
- PIL sprite compositing now crops to alpha bounding boxes, decomposes masked sprites into opaque interiors plus tiled fringe bands, and skips the gradient mask when ramp endpoints are fully opaque.
- Dirty-rectangle tracking in `render_compositor`, and a non-blocking frame loop reaching ~60 FPS (previously ~39–50 FPS) with truly uncapped runs, at essentially unchanged peak RSS.

## [0.1.0] - 2026-10-09

- Initial release.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
