# Eager

An engine for visual novels.

## Packages

| Package | Import | Description | Version |
|---|---|---|---|
| `eager-script` | `eager_script` | Zero-dependency screenplay DSL parser: AST, scene graph, validator, safe expressions, optional terminal editor | 0.1.0 |
| `eager-core` | `eager_core` | Shared dependency-free leaf: audio mixing, geometry/color types, easing, timing, input, storage, text tags | 0.1.0 |
| `eager-runtime` | `eager_runtime` | Headless story VM, event dispatcher, `GameSession` controller, saves/rollback, terminal player, `eager` / `eager-x` CLIs | 0.1.0 |
| `eager-graphics` | `eager_graphics` | Renderer-agnostic stage compositor & presentation layer (Null / Pyglet / PIL / Raylib backends), UI screens, themes | 0.1.0 |

Dependency DAG: `eager-script` and `eager-core` are zero-dependency leaves; `eager-graphics` depends on both; `eager-runtime` depends on `eager-script` + `eager-core` and optionally on `eager-graphics`.

## Quickstart

```bash
git clone https://github.com/CooperElektrik/Eager.git
cd Eager

# install the workspace + dev dependencies (creates .venv/)
uv sync
source .venv/bin/activate

# play the bundled demo in the terminal
eager play examples/demo_story.es

# parse / validate a screenplay
eager-script check examples/demo_story.es
eager-script graph examples/demo_story.es --format mermaid
```

## Layout

```
.
├── packages/
│   ├── eager-script/   # DSL parser (guides in docs/)
│   ├── eager-core/     # shared leaf subsystems
│   ├── eager-runtime/  # VM + session + CLIs
│   └── eager-graphics/ # compositor + backends (guides in docs/)
├── examples/           # demo_story.es + run_demo.py
└── .github/workflows/  # CI: lint + test
```

## Development

```bash
source .venv/bin/activate

pytest packages/ -q --tb=short -x   # full test suite
ruff check packages/                # lint (library code)
```

Per-package details live in each package's `README.md`; contributor conventions in `AGENTS.md`.

## License

MIT — see [LICENSE](LICENSE).
