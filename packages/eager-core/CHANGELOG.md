# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.8.0] - 2026-11-05

### Added

- Storage and narrative state subsystems:
  - Extracted `eager_core.state` (`CallFrame`, `StorySnapshot`) for immutable narrative checkpoints and call stack serialization.
  - Extracted `eager_core.saves` (`SaveMetadata`, `SaveData`, `SaveManager`) providing save/load slot management, autosaves, and automated forensic corrupted save backup.
  - Extracted `eager_core.persistent` (`PersistentData`) for cross-playthrough global state persistence.
  - Extracted `eager_core.preferences` (`Preferences`) managing audio volume, text display speeds, and window presentation settings.
- Presentation, character, and layout subsystems:
  - Extracted `eager_core.characters` (`CharacterConfig`) supporting character display names, color styling, voice configuration, side image mapping, and recursive composite expression resolution (`resolve_expression`).
  - Extracted `eager_core.layout` (`LayoutBox`, `Anchor`, `Alignment`) for coordinate calculations and UI positioning algebra.
  - Extracted `eager_core.lighting` (`LightSource`, `AmbientLight`, `LightmapConfig`) defining 2D lighting models.
  - Extracted `eager_core.theme` (`Theme`, `ThemeStyle`, `ThemePreset`) for UI component theming.
  - Extracted `eager_core.timeline` (`Timeline`, `Keyframe`, `Interpolation`) for keyframed parameter transitions.
  - Extracted `eager_core.types` (`ScaleMode`, `BlendMode`, `TransitionType`, `Transform`, `Box`, `Rect`).
  - Extracted `eager_core.ui_state` (`UIState`, `DialogueBoxState`, `ChoiceBoxState`, `InputPromptState`).
- Headless execution and decoupled host protocols:
  - Extracted `eager_core.headless` (`HeadlessPlayer`) for headless screenplay execution, CI test automation, and CLI script evaluation.
  - Extracted `eager_core.backlog` (`BacklogEntry`, `BacklogManager`) for dialogue history tracking.
  - Extracted `eager_core.dispatcher` (`ActionDispatcher`) for decoupled event dispatching.
  - Extracted `eager_core.watcher` (`FileWatcher`, `FileChangeHandler`) for filesystem change monitoring and live reloading.
  - Added `PlayerHostProtocol`, `StageDirectorProtocol`, and UI presentation protocols in `eager_core.protocols` for decoupled host lifecycle communication.
- Multi-line text measurement helpers in `eager_core.text` (`measure_text_lines`) supporting dynamic UI layouts.

### Changed

- Tightened method signatures and type annotations across protocol interfaces.

### Removed

- Removed duplicate `eager_core.hooks`, consolidating hook parsing in canonical `eager_script.hooks`.
- Removed legacy migration hooks from `SaveManager` and `StorySnapshot`.

## [0.7.0] - 2026-10-30

### Added

- Domain exception hierarchy in `src/eager_core/exceptions.py` defining `EagerCoreError(Exception)` and subclasses `AudioError`, `ColorParseError`, `StorageError`, and `I18nError`.
- `{fast}` typewriter text reveal tag support in `eager_core.text` (`FormattedText.fast_index`, `TextReveal`).
- `Vec2` arithmetic safety: operations on incompatible types return `NotImplemented` and division by zero raises `ZeroDivisionError`.
- Hex syntax validation in `Color.from_hex` raising `ColorParseError`.
- Sealed all 10 submodules with explicit ASCII-sorted `__all__` lists.
- Complete Google-style docstring coverage across all 10 submodules for automated MkDocs API reference generation.

## [0.5.0] - 2026-10-24

### Added

- `ThemeFactory` protocol type and `register_theme_factory` / `get_theme_factory` provider registry functions in `eager_core.protocols` for decoupled theme factory registration without graphics dependencies (with reset support in `reset_providers()`).

### Security

- Path traversal guard in `AudioMixer._resolve_asset` ensuring resolved audio asset paths remain strictly within the configured `asset_dir`.

## [0.4.0] - 2026-10-21

### Added

- Provider registry and `eager.providers` entry-point discovery in `eager_core.protocols`: stage/UI/screen-manager factory registration, player/audio/renderer registries (`register_player`, `get_player`, `list_players`, etc.), `load_providers()`, and `reset_providers()`.
- `StageProtocol.finish_animations()` for immediately completing active stage animations.
- `UIProtocol` overlay mutation methods (`get_selected_choice`, `set_selected_choice`, `set_choice_options`, `set_input_text`, `update_input`, `set_dialogue_visible_chars`, `complete_dialogue_reveal`, `get_hovered_quick_action`, `set_hovered_quick_action`).

### Changed

- `AudioMixer` now calls `AudioBackend.update()` and `shutdown()` directly instead of guarding them with `hasattr`, enforcing the protocol contract for custom backends.

## [0.3.0] - 2026-10-21

### Added

- Runtime-checkable `StageProtocol`, `UIProtocol`, `UIStateProtocol`, and `ScreenManagerProtocol` in `eager_core.protocols` and re-exported in root `eager_core`.

### Fixed

- Strict type annotations, TypedDict definitions (`AudioMixerSaveState`), and resolved all basedpyright type errors and warnings across the package.

## [0.2.0] - 2026-10-19

### Added

- Extended `AudioBackend` protocol with `loop_start`/`loop_end`, `update(dt)`, and `shutdown()`, plus a `BaseAudioBackend` with lifecycle no-ops; `ChannelState` now round-trips loop points through save/load.
- Polyphonic `AudioMixer` using dynamic channel pools for sound effects, plus asset-serial tracking for seamless audio rollback continuity.
- New `eager_core.i18n` module providing `TranslationCatalog` and `TranslationManager`, alongside text-tag parsing and measurement improvements.

## [0.1.0] - 2026-10-09

- Initial release.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.8.0...HEAD
[0.8.0]: https://github.com/CooperElektrik/Eager/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/CooperElektrik/Eager/compare/v0.5.0...v0.7.0
[0.5.0]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/CooperElektrik/Eager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
