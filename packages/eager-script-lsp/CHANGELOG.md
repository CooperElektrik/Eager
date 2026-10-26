# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-10-26

### Added

- Context-aware autocompletion: identifier-aware filtering for scene targets (`> s`).
- Hover documentation for character tokens in engine hooks and parameter/return type docstrings for built-in functions.
- CLI capabilities: `--version` flag and `.es` file extension check.
- Expanded test suite covering syntax recovery, diagnostics clearing on file close, and multi-file projects.
- Sealed all 14 submodules with explicit ASCII-sorted `__all__` lists.

### Fixed

- Preserved leading whitespace during AST error recovery in nested choice blocks.
- Fixed identifier completion shadowing bug in `completion.py`.

## [0.5.0] - 2026-10-24

### Added

- Inlay hints for character display names on speaker tokens in `compute_inlay_hints()` when a speaker identifier has a declared character display name (e.g. `a: Hello` -> `a ("Alice"): Hello`).

### Changed

- Dynamically resolve package version via `importlib.metadata.version` in `EagerLanguageServer` with fallback to `0.4.0`.
- Deterministically sort discovered screenplay files in `WorkspaceIndex` and prioritize the project's configured `entry_script` from `game.toml`, while excluding `dist` and `build` directories.

### Fixed

- Color literal normalization in `compute_document_colors()`: removed redundant second division by 255.0, restoring proper RGB color preview channels.

### Security

- Ignored external symlinks and paths resolving outside the workspace directory during script discovery in `WorkspaceIndex`.

## [0.4.0] - 2026-10-22

### Added

- Initial release of `eager-script-lsp`: full-featured Language Server Protocol (LSP 3.17+) server for Eager-Script (`.es`) screenplays.
- **Resilient Scanner & AST Indexing**: Fault-tolerant incremental document parsing with exact source token spans (`ScriptDocument`) and cross-document workspace indexing (`WorkspaceIndex`).
- **Real-Time Diagnostics**: Screenplay syntax checks, broken jump/call target detection, unreferenced scene warnings, asset availability validation, and i18n translation key consistency.
- **Context-Aware Completion**: Auto-completion for scene labels, character identifiers, emotion sprites discovered from assets, engine hook directives and keyword arguments, variables, and inline text tags.
- **Rich Hover Previews**: Markdown documentation and metadata previews for scenes, character sheets, asset paths, engine hooks, built-in functions, and localization catalogs.
- **Navigation**: Definition provider, reference search, document symbol outline, workspace-wide symbol search, and narrative call hierarchy (incoming/outgoing calls and jumps).
- **Refactoring & Code Actions**: Project-wide rename refactoring across screenplay files, quick fixes to scaffold missing scene targets, and quick fixes to assign explicit beat IDs.
- **Semantic Highlighting & Lenses**: Semantic tokens provider, color picker/decorator provider for `{color=...}` tags, inlay hints for character display names, and "Warp & Play" code lenses.
- **CLI & Transport**: Standalone `eager-script-lsp` binary and `eager lsp` CLI integration supporting stdio, TCP socket, WebSocket, and a headless `--check` batch validator.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/CooperElektrik/Eager/releases/tag/v0.4.0
