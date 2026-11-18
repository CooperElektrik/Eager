# Eager

A modern, high-performance Python engine and tooling ecosystem for visual novels and interactive narrative games.

## User Guide (For Creators)

New to Eager? Start here to write, stage, and package your visual novel:

- [Getting Started](user-guide/getting-started.md) — Create, run, and validate your first project (`eager new`, `eager run`, `eager doctor`)
- [Screenplay Syntax (`.es`)](user-guide/screenplay-syntax.md) — Scenes, dialogue, choices, variables, and conditionals
- [Staging, Visuals & Audio](user-guide/staging-and-effects.md) — Stage hooks (`~ bg`, `~ show`, `~ move`, `~ flash`, `~ play_bgm`) and asset layout
- [Project, i18n & Distribution](user-guide/project-and-distribution.md) — `game.toml`, translations (`eager i18n`), `.zip` bundles, and standalone exports
- [IDE & Debugging Workflow](user-guide/ide-and-debugging.md) — VS Code extension, LSP, `--watch`, `--warp`, and headless testing

## Architecture

Eager is organized as a monorepo with strict architectural boundaries:

```text
eager.core ──▶ eager.script ──▶ eager.vm ──▶ eager.stage ──▶ eager.ui ──▶ eager.session ──▶ eager.cli
     │               │                                           ▲              ▲
     │               └───────────────────────────────────────────┴──────────────┘
     │
     ├──▶ eager.backends (independent of vm, stage, ui, session, cli)
     │
     └──▶ eager-script-lsp (depends only on eager.core and eager.script)
```

### Key invariants

| Boundary | Rule |
|----------|------|
| **Leaf independence** | `eager.core` and `eager.script` are 100% dependency-free and headless. |
| **Headless VM & session** | `eager.vm` and `eager.session` run headlessly with `NullRenderer` / `NullAudioBackend`. |
| **Direct submodule imports** | All primitives are imported directly from submodules (`from eager.core.<module> import ...`); root re-export shims are forbidden. |
| **Safe expressions** | Expression compilation (`compile_expr`) uses whitelisted AST evaluation with zero calls to `eval()` or `exec()`. |

## Packages

| Package | Import path | Role |
|---------|-------------|------|
| [`eager`](api/eager/index.md) | `eager` | Unified visual novel engine: `eager.core`, `eager.script`, `eager.vm`, `eager.stage`, `eager.ui`, `eager.session`, `eager.backends`, and `eager.cli`. |
| [`eager-script-lsp`](api/eager-script-lsp/index.md) | `eager_script_lsp` | Language Server Protocol (LSP 3.17+) server: real-time diagnostics, autocompletion, hover previews, navigation, and `--check` CLI. |

## Installation

```bash
# Clone the repo
git clone https://github.com/CooperElektrik/Eager.git
cd Eager

# Sync workspace dependencies
uv sync
```

## Development

All commands run from the monorepo root using `uv run`:

```bash
# Run the full test suite
uv run pytest packages/ -q --tb=short -x

# Lint
uv run ruff check packages/

# Verify architectural import boundaries
uv run lint-imports

# Build the docs site
uv run mkdocs build

# Serve the docs locally
uv run mkdocs serve
```

## API Reference

Browse the auto-generated API reference for each package:

- [eager](api/eager/index.md)
- [eager-script-lsp](api/eager-script-lsp/index.md)
