# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
