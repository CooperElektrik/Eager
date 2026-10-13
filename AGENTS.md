# Eager-X — Agent Guide

Eager-X is a Python monorepo for building interactive narrative games and visual novels. Four packages form a layered toolchain: screenplay parsing, shared primitives, story execution, and presentation.

This file records durable architecture and development conventions. It is not an exhaustive API reference or change log. Update it when package boundaries, core workflows, or important architectural invariants change—not for every ordinary implementation change. Put feature details in the relevant package README or docs.

## 1. Development conventions

- **Python compatibility:** library code must support Python 3.11+. The workspace currently uses a newer Python, so do not rely on version-specific syntax or APIs without checking compatibility.
- **Environment:** the real workspace environment is `.venv/` at the monorepo root. The root-level `venv/` is a legacy stub; do not use it.
- **Workspace:** run `uv sync` from the root after dependency changes, and run `uv lock` when dependency declarations change.
- **Explore narrowly:** use `rg` for searches and exclude `.venv/`, `venv/`, build outputs, and other generated directories. Read the complete relevant file when practical, and avoid inspecting unrelated files. Never do incremental reads, as it is wasteful and slow.
- **Inspect before implementing:** check existing class constructors, signatures, protocols, and call sites before writing code or scripts.
- **Verify changes:** add or update focused tests, run the relevant package suite, then run broader checks when practical. Prefer `pytest -q --tb=short -x`; use `git diff --stat` and `git status` before wrapping up. Report only checks actually run.
- **Documentation:** update package docs when public syntax, behavior, APIs, or architecture change. Do not expand this file with detailed feature documentation.

## 2. Workspace layout

```text
eager-mono/
├── pyproject.toml             # uv workspace configuration
├── uv.lock
├── .venv/                     # shared development environment
├── AGENTS.md                  # this guide
├── examples/                  # example scripts and runners
└── packages/
    ├── eager-script/          # screenplay DSL, AST, scene graph, validation
    ├── eager-core/            # shared dependency-free primitives
    ├── eager-runtime/         # story VM, events, sessions, persistence, CLIs
    └── eager-graphics/        # stage compositor, UI, render and audio backends
```

Each package has its own `pyproject.toml`, source tree under `src/`, tests, and README. Additional package documentation lives beside the relevant implementation.

## 3. Package boundaries and dependencies

```text
eager-script ─┐
              ├── eager-graphics
 eager-core ──┘
      │
      └──────── eager-runtime ── optional graphics extra ── eager-graphics
```

- **`eager-script` (`eager_script`)** — dependency-free screenplay language tooling. Parses `.es` scripts into AST nodes, builds a scene graph, validates scripts, supports plain-manuscript mode, and provides safe expression evaluation. The expression API is defined in `eager_script.expr`, not re-exported from the package root.
- **`eager-core` (`eager_core`)** — dependency-free shared primitives used by multiple layers: audio mixing protocols, geometry and color types, easing, timing, input mapping, storage helpers, narrative events, and text-tag/reveal utilities. Keep genuinely shared, lower-level implementations here rather than duplicating them in higher layers.
- **`eager-runtime` (`eager_runtime`)** — narrative execution and game-session logic. `StoryVM` is the headless story virtual machine; `EventDispatcher` routes its events; `GameSession` coordinates interactive play, presentation state, audio, UI, checkpoints, save/load, preferences, and persistent data. Graphics-dependent exports are lazy so a basic `import eager_runtime` remains headless-capable. `VisualEngine` is a compatibility façade around `GameSession`; new code should generally use `GameSession` directly.
- **`eager-graphics` (`eager_graphics`)** — renderer-agnostic presentation. It coordinates stage elements, animation, screenplay hooks, dialogue UI, screens, and rendering/audio backends. It depends on `eager-script` and `eager-core`, not on the runtime's implementation.

Keep these boundaries intact: `eager-script` and `eager-core` have no runtime dependencies; `eager-runtime` requires script and core, with graphics optional; `eager-graphics` uses script and core. Optional renderer libraries should remain optional and be imported lazily.

## 4. Core execution model

The main narrative path is:

```text
.es source → parser / AST → SceneGraph → validation → StoryVM
                                                   │
                                              StoryEvent stream
                                                   │
                                           EventDispatcher
                                                   │
                                      GameSession / StageDirector
                                                   │
                                  compositor + UI + selected backend
```

- The screenplay parser produces typed AST nodes. `to_graph()` / `parse_graph()` build the scene graph; validation checks targets, labels, syntax, and related static rules.
- The runtime executes a `SceneGraph` beat by beat. `StoryVM` evaluates script logic, manages variables and subroutine calls, and emits narrative events rather than depending on a renderer.
- `EventDispatcher` connects VM events and screenplay hooks to registered handlers.
- `GameSession` is the main controller for interactive play. `StageDirector` bridges runtime events/hooks to the compositor, UI state, and audio.
- Graphics are split between a **stage layer** (render items in virtual stage coordinates) and a **UI layer** (immediate-mode drawing in window pixels). Backends implement the renderer protocols rather than owning story logic.

## 5. Invariants to preserve

### Script and scene graph

- Standard DSL syntax and plain-manuscript mode are distinct; plain mode must reject standard-only directives where specified.
- Script expressions must use the whitelist-based evaluator. Do not replace it with Python `eval` or broaden allowed AST operations casually.
- Conditional `@if` blocks are lowered by the graph-building layer into flat conditional/local-jump nodes. Preserve the flat beat-index model used by the VM.
- If a language feature changes, consider parser/AST serialization, graph construction, validation, editor highlighting, tests, and syntax/API documentation—not only the parser branch.

### Runtime and state

- `StoryVM` must remain usable without graphics installed.
- `GameSession.advance()` runs execution to the next player interaction, dispatches intermediate events, and records a checkpoint. Rollback must keep story state and relevant presentation/UI state consistent, including restoring pending choices.
- Keep `PersistentData` distinct from rollback-managed per-session state: persistent progress is intended to survive playthroughs and is not rolled back with ordinary checkpoints.
- Save files use the shared atomic JSON storage helpers. Preserve safe handling of missing or corrupt save data.
- Random state is part of story snapshots; maintain deterministic save/restore and rollback behavior when changing execution state.

### Events, hooks, and presentation

- Narrative event dataclasses are defined in `eager_core.events`; runtime-facing modules re-export them. When adding an event, update the event union and every relevant producer/consumer, including pause/checkpoint behavior, terminal playback, UI handling, and tests.
- Screenplay hook argument parsing belongs to `eager_script`; presentation handlers belong in `eager_graphics` (principally `StageDirector`). Keep rendering-specific behavior out of the headless VM.
- Keep stage and UI rendering protocols separate. New backends should implement the relevant protocols and avoid making optional backend packages mandatory imports.
- Backend selection and interactive player integration also involve the runtime CLI; adding a renderer is more than adding a renderer class.

## 6. Where to start

Use these entry points as a guide; inspect their current signatures and implementation before relying on specific details.

| Concern | First places to inspect |
|---|---|
| DSL parsing and public AST | `packages/eager-script/src/eager_script/__init__.py` |
| Safe expressions | `packages/eager-script/src/eager_script/expr.py` |
| Scene graph and lowering | `packages/eager-script/src/eager_script/graph.py` |
| Static validation | `packages/eager-script/src/eager_script/validator.py` |
| Shared events/audio/types/storage/text/i18n | `packages/eager-core/src/eager_core/` |
| Story VM | `packages/eager-runtime/src/eager_runtime/runtime.py` |
| Event dispatch | `packages/eager-runtime/src/eager_runtime/dispatcher.py` |
| Session, checkpoints, input, UI coordination | `packages/eager-runtime/src/eager_runtime/session.py` |
| Save/load and project configuration | `packages/eager-runtime/src/eager_runtime/saves.py`, `project.py` |
| Translation catalog tooling | `packages/eager-runtime/src/eager_runtime/i18n.py` |
| CLI commands | `packages/eager-runtime/src/eager_runtime/cli.py` |
| Stage composition | `packages/eager-graphics/src/eager_graphics/compositor.py` |
| Hook and event bridge | `packages/eager-graphics/src/eager_graphics/director.py` |
| Renderer/UI protocols | `packages/eager-graphics/src/eager_graphics/protocol.py` |
| Screens and widgets | `packages/eager-graphics/src/eager_graphics/screens/` |

## 7. Common commands

Run commands from the monorepo root unless noted otherwise.

```bash
# Activate the shared environment and install workspace dependencies
source .venv/bin/activate
uv sync

# Run the complete test tree
pytest packages/ -q --tb=short -x

# Run one package's tests
(cd packages/eager-script && pytest -q --tb=short -x)
(cd packages/eager-core && pytest -q --tb=short -x)
(cd packages/eager-runtime && pytest -q --tb=short -x)
(cd packages/eager-graphics && pytest -q --tb=short -x)

# Lint
ruff check packages/

# Type-check packages with configured basedpyright settings
(cd packages/eager-script && basedpyright)
(cd packages/eager-runtime && basedpyright)
(cd packages/eager-graphics && basedpyright)
```

Optional-dependency tests may be skipped when their backend/editor libraries are unavailable. The workspace development setup is intended to install the full test toolchain.

Useful CLI entry points include `eager-script check`, `eager-script graph`, `eager play`, `eager inspect`, `eager test-run`, `eager i18n extract` / `check`, and `eager-x play` / `run` / `check` / `build` / `i18n`. Use each command's `--help` for its current arguments rather than maintaining an exhaustive command list here.

## 8. Common extension paths

- **New DSL syntax:** add or modify AST/parser behavior; update graph lowering or edges if needed; validate it; cover it with tests; update the relevant syntax/API docs and editor highlighting.
- **New script hook:** register the hook through `StageDirector`, parse its arguments with `eager_script.parse_hook_args`, and test its effect through event dispatch and presentation state.
- **New narrative event:** define the event in `eager_core.events`, update the `StoryEvent` union, emit it from the VM, and handle it at every relevant dispatcher/session/player/presentation boundary.
- **New renderer backend:** implement the stage and UI protocols as required, keep imports optional/lazy, wire backend selection and player/audio integration, and test protocol behavior without requiring a real window where possible.
- **New package:** add a package directory with its own `pyproject.toml`, source, and tests; verify workspace membership and dependency direction; run `uv sync`.

## 9. Subagent workflow

The main agent may delegate bounded tasks through the `pool` CLI. Exploration convention:

```bash
pool exec --unsafe-auto-allow -p "PUT YOUR PROMPT HERE"
```

- Delegated prompts must explicitly state that the worker is a subagent and include the scope, paths, constraints, and expected deliverable.
- Subagents work in the shared tree. They should inspect only task-relevant files and avoid overlapping edits where practical.
- Before returning, a subagent must inspect `git status`, `git diff --stat`, and the diff; update this guide only if durable architecture/workflow facts changed; then report the task, modified files, verification performed, caveats, and whether this guide changed.
- Subagents must not commit. If blocked, they should stop, leave the tree buildable (revert incomplete breaking changes when appropriate), and clearly report the blocker and working-tree state.