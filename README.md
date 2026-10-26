# Eager

A modern, high-performance Python engine and tooling ecosystem for visual novels and interactive narrative games.

---

## Architecture & Layer Isolation

Eager is organized as a monorepo with strict architectural boundaries enforced by 16 `import-linter` contracts:

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

### Invariants & Boundaries
- **Leaf Independence**: `eager-core` and `eager-script` are 100% dependency-free and headless.
- **Headless Runtime**: `eager-runtime` contains zero GUI, graphics, or windowing dependencies.
- **Direct Submodule Imports**: All primitives are imported directly from submodules (`from eager_core.<module> import ...`); root re-export shims are strictly forbidden.
- **Safe Expressions**: Expression compilation (`compile_expr`) uses whitelisted AST evaluation with zero calls to Python's `eval()` or `exec()`.

---

## Packages

| Package | Import Path | Role & Description |
|---|---|---|
| [`eager-core`](packages/eager-core/) | `eager_core` | Shared leaf foundation: audio mixing, geometry (`Vec2`, `Rect`), `Color`, easing, timing, input semantics, storage, and text pacing (`{fast}`). |
| [`eager-script`](packages/eager-script/) | `eager_script` | Zero-dependency screenplay DSL parser: AST generation, stream parsing, directed scene graph, validator, and expression compiler (`compile_expr`). |
| [`eager-runtime`](packages/eager-runtime/) | `eager_runtime` | Headless story virtual machine (`StoryVM`), event dispatcher (`run_until_pause`), session controller (`GameSession`), save manager (`.corrupt.bak`), and terminal player. |
| [`eager-graphics`](packages/eager-graphics/) | `eager_graphics` | Resolution-independent presentation layer: stage compositor, dialogue/choice UI, built-in screens, and pluggable backends (Null, PIL, Pyglet). |
| [`eager-script-lsp`](packages/eager-script-lsp/) | `eager_script_lsp` | Language Server Protocol (LSP 3.17+) server: real-time diagnostics, autocompletion, hover previews, navigation, and `--check` CLI. |

---

## v1.0.0 Release Readiness

The codebase has undergone a comprehensive stabilization sprint across 6 hardening tracks:
- **Track R1 (Syntax & AST Lowering)**: Hardened screenplay parser boundaries, inline choice lowering, and `{fast}` instant typewriter text reveal.
- **Track R2 (Core Primitives)**: Sealed 100% of submodules with explicit `__all__`, established `EagerCoreError` hierarchy, and hardened `Vec2`/`Color` arithmetic.
- **Track R3 (Headless Runtime)**: Resolved `InputPromptEvent` pausing in `run_until_pause()`, added stream-aware terminal input handling, and implemented forensic `.corrupt.bak` save backups.
- **Track R4 (Presentation & Backends)**: Audio failure logging and resilience across Pyglet/Miniaudio, eliminated 124 basedpyright diagnostics, and disambiguated `ChoiceOption`.
- **Track R5 (Language Server Protocol)**: Resilient AST recovery preserving indentation, partial filter completion, character hovers, and clean buffer closure.
- **Track R6 (Monorepo Integrity)**: 936 passing tests (including a 58-test opaque-box E2E suite), 0 basedpyright diagnostics, clean ruff linting, and 16/16 import contracts kept.

---

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
# Run full monorepo test suite (936 tests)
uv run pytest packages/ -q --tb=short -x

# Run code linter
uv run ruff check packages/

# Run type checker across all packages
(cd packages/eager-script && uv run basedpyright)
(cd packages/eager-runtime && uv run basedpyright src)
(cd packages/eager-graphics && uv run basedpyright src)
(cd packages/eager-script-lsp && uv run basedpyright)

# Verify architectural layer boundaries
uv run lint-imports
```

---

## Repository Layout

```text
.
├── packages/
│   ├── eager-core/         # Shared leaf primitives, types, audio, text tags
│   ├── eager-script/       # Screenplay DSL parser & expression compiler
│   ├── eager-runtime/      # Headless story VM, session controller, saves
│   ├── eager-graphics/     # Stage compositor, UI chrome, rendering backends
│   └── eager-script-lsp/   # Language Server Protocol daemon & CLI
├── editors/
│   └── vscode/             # VS Code extension for Eager-Script
├── examples/               # Demo stories and scripts
├── docs/                   # Migration guides and architectural specifications
└── scripts/                # Development and benchmarking utilities
```

---

## License

MIT — see [LICENSE](LICENSE).
