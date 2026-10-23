# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `eager_graphics.fonts` module providing canonical typeface extraction and dynamic registration into `pyglet.font` (`register_pyglet_default_font`, `get_default_font_data`).
- Automated pixel parity test suite (`tests/test_backend_parity.py`) verifying rendering equivalence, typographic extents, and transition blending between PIL and Pyglet.

### Changed

- `PygletRenderer` now configures `dpi=72` on `Label` and `font.load` so `font_size` maps 1:1 to window pixels matching `PILRenderer`.
- `PygletRenderer.draw_rect`, `draw_rect_outline`, and `draw_gradient_rect` now snap coordinates to integer pixels, matching PIL and preventing subpixel hairline seams between adjacent UI panels.
- `PygletAssetResolver` now indexes and resolves `.bmp` and `.gif` formats matching `PILAssetResolver`.

### Fixed

- **Background Crossfade Blending:** `StageCompositor.set_background` maintains the outgoing background at full opacity (`1.0`) during crossfade/dissolve transitions while the incoming background fades in on top, avoiding the 25% midpoint luminance dip to black under standard Porter-Duff alpha blending.
- **Typographic Metrics & Anchors:** `PILRenderer.measure_text` now computes typographic line heights (`ascent + descent`) and advance widths (`font.getlength`) matching Pyglet's text metrics and line-wrapping behavior; fixed `_PIL_ANCHOR_Y["bottom"] = "b"` to align with text bounds instead of baseline.
- **Texture Bleeding:** Applied `GL_CLAMP_TO_EDGE` wrap mode to textures in `PygletAssetResolver` to prevent edge texels from filtering with opposing borders on transparent stage sprites.
- **Gradient Rounding:** `PILRenderer.draw_gradient_rect` now rounds color interpolation values to the nearest integer byte instead of truncating, matching OpenGL GPU vertex color interpolation.

## [0.4.0] - 2026-10-21

### Added

- `roll_forward()` method on `BasePlayer` for stepping forward along `GameSession`'s redo stack.
- `finish_animations()` on `StageCompositor` and `StageDirector`, plus `Tween.finish()` and `Timeline.finish_all()` / `flush()`, to snap active tweens to their end values.
- `Theme` at the package root (`eager_graphics.theme`) with `TextboxStyle.from_theme()`, `ChoiceMenuStyle.from_theme()`, `UIOverlay(theme=...)`, and theme propagation across `DialogueBox`, `ChoiceMenu`, `QuickMenu`, `Screen`, and `ScreenManager`.
- `UIOverlay` protocol-mutation helpers (`get_selected_choice`, `set_selected_choice`, `set_choice_options`, `set_input_text`, `update_input`, `set_dialogue_visible_chars`, `complete_dialogue_reveal`, `get_hovered_quick_action`, `set_hovered_quick_action`).
- Provider registration through the `eager.providers` entry point for stage, UI, screen-manager, player, audio, and renderer factories.

### Changed

- `StageDirector.save_visual_state()` now exclusively serializes stage compositor state, delegating UI state persistence to `save_ui_state()` and eliminating state duplication in checkpoints.
- Split the monolithic `renderers/pil.py` into the `eager_graphics.renderers.pil` subpackage (`_compat`, `_constants`, `_imaging`, `_cache`, `assets`, `renderer`, `player`), with the package `__init__` re-exporting the previous public and private names.
- Moved `Theme` from `eager_graphics.screens.theme` to `eager_graphics.theme`; screens and overlay components now share one theme definition.
- Font sizes in `DialogueBox`, `ChoiceMenu`, `InputBox`, `EndNotice`, `QuickMenu`, `UIOverlay`, and built-in screens now scale with viewport height (720p reference).
- `StageDirector` event handlers, `BasePlayer`, and screen widgets now consume concrete protocol attributes instead of defensive `getattr`/`hasattr` fallbacks.
- `StageCompositor.save_state()` flushes active tweens before serialization to avoid persisting intermediate opacity values.

### Fixed

- Prevented 0-opacity and mid-transition sprite states after save and rollback by completing active tweens before snapshots and narrative advancement.
- Removed duplicate field resets in `DialogueBox.clear()`.

### Removed

- `VisualHistoryManager` and `eager_graphics.history` module.
- `enable_visual_history()`, `snapshot_visual_state()`, `rollback_visual_state()`, and `on_beat_step()` on `StageDirector`.
- `eager_graphics.screens.theme` module (moved to `eager_graphics.theme`).

## [0.3.0] - 2026-10-21

### Added

- `BasePlayer` in `eager_graphics.player`, abstracting shared session management, event dispatching, and hotkeys for window player implementations (`PILPlayer`, `PygletPlayer`).
- `StageProtocol` implementation methods on `StageDirector`.
- Viewport resize handling (`on_resize` / `handle_resize`) across `Screen` and `ScreenManager`.
- Background audio streaming in `MiniaudioAudioBackend` using `miniaudio.stream_file` for music and ambient channels to eliminate main thread loading hitches.
- `draw_rect_outline` and `_blend_rect` helpers on `PILRenderer` for drawing bordered and translucent shapes.

### Changed

- Proportional screen layout: `SaveScreen`, `LoadScreen`, `PreferencesScreen`, and `HistoryScreen` dynamically adapt positions, margins, font sizes, and card dimensions to viewport dimensions.
- Deduplicated `PILPlayer` and `PygletPlayer` into `BasePlayer`.
- `Screen.handle_mouse_move` and `ScreenManager.handle_mouse_move` return a boolean indicating whether a hover state actually changed.
- `wrap_text` returns character span tuples `(line_str, start_char_idx, end_char_idx)` instead of plain strings.
- `wrap_text` cache key includes backend type and font family to prevent cross-backend/font cache collisions.

### Fixed

- Alpha transparency handling in `PILRenderer` for translucent rectangle shapes, borders, and text glyphs.
- Formatted text line-finding in `DialogueBox.draw`, preventing text style/typewriter offset corruption on repeated words.
- Guarded against uninitialized sessions in `HistoryScreen.draw`.
- Forwarded character display name and color metadata to `StageDirector` and `DialogueBox`.
- Telemetry now correctly reports `Tier 3 (Stage Cache / UI Only)` when `PILRenderer` restores the stage from `_stage_cache`.
- Resolved all basedpyright type errors and warnings across the package.

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

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/CooperElektrik/Eager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
