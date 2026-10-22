# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/CooperElektrik/Eager/releases/tag/v0.4.0
