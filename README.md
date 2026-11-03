# Eager

A modern, high-performance Python engine and tooling ecosystem for visual novels.


## Packages

| Package | Import Path | Role & Description |
|---|---|---|
| [`eager-core`](packages/eager-core/) | `eager_core` | Provides methods and classes/types for audio mixing, geometry, color, easing, timing, input semantics, storage, and text pacing. |
| [`eager-script`](packages/eager-script/) | `eager_script` | Screenplay DSL. |
| [`eager-runtime`](packages/eager-runtime/) | `eager_runtime` | Story virtual machine, event dispatcher, session controller, save manager, and terminal player. |
| [`eager-graphics`](packages/eager-graphics/) | `eager_graphics` | Presentation layer: stage compositor, dialogue/choice UI, built-in screens, and pluggable backends.|
| [`eager-script-lsp`](packages/eager-script-lsp/) | `eager_script_lsp` | Language Server Protocol (LSP 3.17+) server. |


## Quickstart

### Workspace Setup

```bash
git clone https://github.com/CooperElektrik/Eager.git
cd Eager

# Sync workspace dependencies using uv
uv sync
```

### Play the Demo

```bash
# Play interactive demo screenplay in the terminal
uv run eager play examples/demo_story.es

# Launch hardware-accelerated OpenGL player
uv run eager play examples/demo_story.es --backend pyglet

# Launch software-rendered player
uv run eager play examples/demo_story.es --backend pil
```

### Screenplay Tooling

```bash
# Validate screenplay syntax and link integrity
uv run eager-script check examples/demo_story.es

# Export directed scene graph as Mermaid markup
uv run eager-script graph examples/demo_story.es --format mermaid

# Headless batch diagnostic check via language server
uv run eager-script-lsp --check examples/demo_story.es
```

---

## Development & Verification

All commands are run using `uv run` from the monorepo root:

```bash
# Run full monorepo test suite (833 tests)
uv run pytest packages/ -q --tb=short -x

# Run code linter
uv run ruff check packages/

# Run type checker across all packages
(cd packages/eager-core && uv run basedpyright)
(cd packages/eager-script && uv run basedpyright)
(cd packages/eager-runtime && uv run basedpyright)
(cd packages/eager-graphics && uv run basedpyright src)
(cd packages/eager-script-lsp && uv run basedpyright)

# Verify architectural layer boundaries
uv run lint-imports

# Build documentation site
uv run mkdocs build
```

## License

MIT.