# eager-script-lsp

Full-featured Language Server Protocol (LSP) server for Eager-Script (`.es`) screenplays.

## Features

- **Real-Time Diagnostics**: Resilient parsing, AST validation, broken jump/call target checks, asset linter, and i18n checks.
- **Auto-Completion**: Context-aware completions for scenes, characters, asset-derived emotion sprites, hooks and keywords, variables, and inline text tags.
- **Navigation**: Go-to-definition, find-references, document/workspace symbols, and narrative call hierarchy.
- **Hover Previews**: Rich Markdown tooltips for scene topologies, character sheets, asset previews, and multi-locale i18n translation tables.
- **Refactoring & Actions**: Multi-file rename for scene labels, characters, and variables; quick fixes to generate missing scenes and pin beat IDs.
- **Semantic Highlighting & Lenses**: Semantic tokens, folding ranges, document links, color pickers, and Code Lenses ("Warp & Play").
