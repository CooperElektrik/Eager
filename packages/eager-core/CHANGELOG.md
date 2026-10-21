# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
