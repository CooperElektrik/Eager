# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-10-19

### Added

- Inline choice menu blocks — indented reactions and mutations directly under `?` options without target labels, lowered into anonymous scenes (`SceneNode.is_anonymous`) that return to the caller via inline call frames, with tab/space normalization and comment support.
- Expanded parser/validator coverage and DSL documentation (`docs/syntax.md`, `docs/validation.md`, `docs/scene-graph.md`).

### Removed

- The terminal editor (`eager_script.editor`) and its docs/tests.

## [0.1.0] - 2026-10-09

- Initial release.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
