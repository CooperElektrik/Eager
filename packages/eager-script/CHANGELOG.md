# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-10-30

### Added

- Streaming AST generator `parse_iter` and stateful `ScreenplayParser`.
- AST nodes `ParsedSet`, `ParsedDefault`, `ParsedCharacter`, `ParsedIf`, `ParsedElif`, `ParsedElse`, `ParsedEnd`, `ParsedCondJump`, and `ParsedLocalJump`.
- Automatic flushing of unclosed `@if` blocks on script EOF in screenplay parser.
- Boundary test coverage covering empty scripts, unclosed tags, and unicode integrity across CJK/emoji.
- Sealed all 5 submodules with explicit ASCII-sorted `__all__` lists.
- Complete Google-style docstring coverage across all 5 submodules for automated MkDocs API reference generation.

### Fixed

- Safe expression evaluator catches and wraps all runtime arithmetic, type, and value errors (`ZeroDivisionError`, `ArithmeticError`, `TypeError`, `ValueError`) into `ExprError`.
- Fixed `@if/@elif/@else` unreachable code and cycle false positive warnings in `SceneGraph` analysis and validator.
- Refactored `test_parser.py` with explicit type narrowing, resolving 922 basedpyright errors and enabling removal of `ignore = ["tests/test_parser.py"]`.
- Standardized test naming to 1:1 submodule mirroring (`test_graph.py`, `test_parser.py`, `test_expr.py`, `test_validator.py`, `test_cli.py`) and modernized to native pytest.

### Removed

- Removed dead code in `eager-script` (`VOICE_PATTERN`, `_strip_line_comment`, `_slugify`).

## [0.5.0] - 2026-10-24

### Fixed

- **Character Attribute Parsing:** Parse `@character` attributes using `shlex.split` so quoted values containing spaces (e.g. `title="The Great Magician"`) are parsed without truncation, falling back safely to whitespace splitting if quotes are malformed.
- **Graph Branch Condition Accumulation:** Fixed branch condition accumulation in `_process_scene_body` (`eager_script.graph`) so `@elif` edges negate all prior sibling conditions (`(not (a)) and (b)`), and `@else` edges negate all preceding conditions (`(not (a)) and (not (b))`), correctly preserving nested conditional jump logic in `SceneGraph`.

## [0.4.0] - 2026-10-21

### Added

- `InputHookArgs`, `is_input_hook()`, `parse_input_args()`, and `parse_input_hook()` in `eager_script.hooks`, re-exported from `eager_script`, for structured parsing of `~ input` hooks.

### Changed

- `~ input` argument parsing now consistently supports `prompt=`/`default=` keywords in any order alongside quoted or unquoted positional prompt text.
- `parse_hook_args()` now treats only `identifier=value` tokens as keyword arguments, preserving `=` inside unquoted prompts and defaults.
- Removed redundant guards in expression evaluation, relying on AST validation to restrict attribute access to `persistent`.

## [0.3.0] - 2026-10-21

- No changes since 0.2.0.

## [0.2.0] - 2026-10-19

### Added

- Inline choice menu blocks — indented reactions and mutations directly under `?` options without target labels, lowered into anonymous scenes (`SceneNode.is_anonymous`) that return to the caller via inline call frames, with tab/space normalization and comment support.
- Expanded parser/validator coverage and DSL documentation (`docs/syntax.md`, `docs/validation.md`, `docs/scene-graph.md`).

### Removed

- The terminal editor (`eager_script.editor`) and its docs/tests.

## [0.1.0] - 2026-10-09

- Initial release.

[Unreleased]: https://github.com/CooperElektrik/Eager/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/CooperElektrik/Eager/compare/v0.5.0...v0.7.0
[0.5.0]: https://github.com/CooperElektrik/Eager/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/CooperElektrik/Eager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/CooperElektrik/Eager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/CooperElektrik/Eager/compare/97609c1...v0.2.0
[0.1.0]: https://github.com/CooperElektrik/Eager/commit/97609c1
