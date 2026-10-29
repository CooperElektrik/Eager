# Eager

A modern, high-performance Python engine and tooling ecosystem for visual novels and interactive narrative games.

## Architecture

Eager is organized as a monorepo with strict architectural boundaries:

```text
eager-script ──┐
               ├── eager-graphics (presentation, renderer backends)
 eager-core ───┤
      │        ├── eager-script-lsp (LSP server, language tooling)
      │        │
      └──────── eager-runtime (headless story VM, sessions)
                       │ (optional extras)
                       ├── eager-graphics
                       └── eager-script-lsp
```

### Key invariants

| Boundary | Rule |
|----------|------|
| **Leaf independence** | `eager-core` and `eager-script` are 100% dependency-free and headless. |
| **Headless runtime** | `eager-runtime` contains zero GUI, graphics, or windowing dependencies. |
| **Direct submodule imports** | All primitives are imported directly from submodules (`from eager_core.<module> import ...`); root re-export shims are forbidden. |
| **Safe expressions** | Expression compilation (`compile_expr`) uses whitelisted AST evaluation with zero calls to `eval()` or `exec()`. |

## Packages

| Package | Import path | Role |
|---------|-------------|------|
| [`eager-core`](api/eager-core/index.md) | `eager_core` | Shared leaf foundation: audio mixing, geometry (`Vec2`, `Rect`), `Color`, easing, timing, input semantics, storage, text pacing (`{fast}`). |
| [`eager-script`](api/eager-script/index.md) | `eager_script` | Zero-dependency screenplay DSL parser: AST generation, stream parsing, directed scene graph, validator, and expression compiler (`compile_expr`). |
| [`eager-runtime`](api/eager-runtime/index.md) | `eager_runtime` | Headless story virtual machine (`StoryVM`), event dispatcher (`run_until_pause`), session controller (`GameSession`), save manager, and terminal player. |
| [`eager-graphics`](api/eager-graphics/index.md) | `eager_graphics` | Resolution-independent presentation layer: stage compositor, dialogue/choice UI, built-in screens, and pluggable backends (Null, PIL, Pyglet). |
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

- [eager-core](api/eager-core/index.md)
- [eager-script](api/eager-script/index.md)
- [eager-runtime](api/eager-runtime/index.md)
- [eager-graphics](api/eager-graphics/index.md)
- [eager-script-lsp](api/eager-script-lsp/index.md)
