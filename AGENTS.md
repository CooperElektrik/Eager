# AGENTS.md — Eager Monorepo

Operational guidelines and constraints for autonomous agents in `eager-mono`.

---

## 1. Operational boundaries

### Always do
- Use `.venv/` at the root or prefix commands with `uv run`.
- Import primitives directly from `eager.<layer>.<module>` (e.g., `eager.core.events`); do not create or use re-export shims.
- Keep `eager.core` and `eager.script` dependency-free, and keep `eager.vm` and `eager.session` runnable headlessly (with `NullRenderer` / `NullAudioBackend`).
- Check constructor signatures, protocols, and existing call sites before writing code.
- Keep random state deterministic and save serialization atomic via `eager.core.saves`.
- Run tests, linter, and type checks before completing any task.

### Ask first
- Adding or updating dependencies in any `pyproject.toml`.
- Modifying `.es` screenplay syntax or public AST definitions.
- Changing save/checkpoint serialization schemas or `PersistentData` structures.
- Adding renderer backends or modifying native window bindings.

### Never do
- Use `eval()`, `exec()`, or widen AST whitelists in `eager.script.expr`.
- Touch the legacy stub `venv/`.
- Import `eager.vm`, `eager.stage`, `eager.ui`, `eager.session`, `eager.backends`, or `eager.cli` inside `eager.core`, `eager.script`, or `eager-script-lsp`.
- Implement narrative branching, rollback, or save logic in render players (`PILPlayer`, `PygletPlayer`)—keep that state machine in `GameSession`.
- Run `git commit` (delegated subagents).

---

## 2. Architecture and dependencies

```text
eager.core ──▶ eager.script ──▶ eager.vm ──▶ eager.stage ──▶ eager.ui ──▶ eager.session ──▶ eager.cli
     │               │                                           ▲              ▲
     │               └───────────────────────────────────────────┴──────────────┘
     │
     ├──▶ eager.backends (independent of vm, stage, ui, session, cli)
     │
     └──▶ eager-script-lsp (depends only on eager.core and eager.script)
```

### Invariants
- **Script lowering:** Flatten `@if` blocks into local-jump nodes. Lower inline choices into anonymous scenes formatted as `<scene_id>__anon_<line>` with `SceneNode.is_anonymous = True`. `StoryVM.choose` pushes an `inline` `CallFrame`; jumping out of an anonymous scene discards this frame instead of returning.
- **State and persistence:** Rollback must restore story and UI/choice states together. `PersistentData` tracks global unlock/read states across runs and is never rolled back with normal checkpoints.
- **Graphics layers:** Stage elements render in virtual coordinates; UI elements draw in window pixels. Keep `pil`, `pyglet`, and `miniaudio` backends as optional lazy imports. Pillow-SIMD and regular Pillow are mutually exclusive; install the former via `scripts/install_pillow_simd.py`.

---

## 3. Code patterns

### Import conventions

```python
# Direct submodule imports
from eager.core.events import DialogueEvent, ChoicePromptEvent
from eager.core.types import Color, Vec2
from eager.script.expr import compile_expr
from eager.script import parse_hook_args
from eager.session import GameSession

# Avoid: non-existent legacy package names
from eager_core.events import DialogueEvent        # Fails: removed in 0.9+
from eager_runtime.session import GameSession      # Fails: removed in 0.9+
```

### Expression evaluation

```python
# Whitelisted AST parsing & compilation
from eager.script.expr import compile_expr

expr = compile_expr(expr_string)
result = expr.evaluate(context_variables)

# Avoid: arbitrary evaluation
result = eval(expr_string, {}, context_variables)    # Prohibited
```

### Hook parsing

```python
# Parse in script, handle in stage
from eager.script import parse_hook_args

args = parse_hook_args(raw_hook_string)
# Hook handlers are registered on the runtime event dispatcher
# (StageDirector.bind wires them to stage compositor actions).
```

---

## 4. Verification checklist

A task is complete only when all steps pass:

1. **Focused tests:**
   ```bash
   uv run pytest packages/ -q --tb=short -x
   ```
2. **Linting and contracts:**
   ```bash
   uv run ruff check packages/
   uv run lint-imports
   ```
3. **Type checking:**
   ```bash
   (cd packages/eager && uv run basedpyright)
   (cd packages/eager-script-lsp && uv run basedpyright)
   ```
4. **Docs build:**
   ```bash
   uv run mkdocs build
   ```
5. **Git review:**
   ```bash
   git status
   git diff --stat
   ```

6. **Output reporting:** Report actual terminal outputs. Do not claim tests pass without running them.

---

## 5. Commands

Run from the monorepo root.

### Setup
```bash
uv sync            # Sync workspace dependencies
uv lock            # Update lockfile after pyproject.toml changes
```

### Testing
```bash
uv run pytest packages/ -q --tb=short -x                  # Run all tests
uv run pytest packages/eager -q --tb=short -x             # Run eager package tests
uv run pytest packages/eager-script-lsp -q --tb=short -x  # Run LSP tests
```

### Lint and format
```bash
uv run ruff check packages/
uv run ruff check --fix packages/
```

### Search
```bash
rg -C 10 "PatternName" packages/ --glob "!**/__pycache__/**"
```

### Documentation
```bash
uv run mkdocs build          # Build the docs site
uv run mkdocs serve          # Serve docs locally (http://127.0.0.1:8000)
```

---

## 6. Version bump protocol

When performing a version bump (e.g. from `0.9.0` to `0.10.0`), all of the following components must be updated atomically:

1. **Package & Root Manifests (`version = "X.Y.Z"`):**
   - Root `pyproject.toml`
   - `packages/eager/pyproject.toml`
   - `packages/eager-script-lsp/pyproject.toml`

2. **Intra-monorepo Minimum Dependency Bounds (`eager >= X.Y.Z`):**
   - `packages/eager-script-lsp/pyproject.toml` (`dependencies`)

3. **Runtime `__version__` Attributes (`__version__ = "X.Y.Z"`):**
   - `packages/eager/src/eager/__init__.py`
   - `packages/eager-script-lsp/src/eager_script_lsp/__init__.py`

4. **Packaging & Editor Extension Manifests:**
   - `editors/vscode/package.json` and `editors/vscode/package-lock.json` (`"version": "X.Y.Z"`)
   - `editors/vscode/README.md` (VSIX install command version)
   - `packaging/debian/DEBIAN/control` (`Version: X.Y.Z`)
   - `packaging/windows/eager.iss` (`#define AppVersion "X.Y.Z"`)

5. **Changelogs Synchronization:**
   - Convert `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` and add a fresh `## [Unreleased]` in root `CHANGELOG.md` and `packages/*/CHANGELOG.md`.
   - Update comparison links at the footer (`[Unreleased]`: `vX.Y.Z...HEAD`, `[X.Y.Z]`: `vPREV...vX.Y.Z`).

6. **Lockfile & Verification:**
   - Run `uv lock` followed by `uv sync`.
   - Run the full verification checklist (Section 4): `pytest`, `ruff check`, `lint-imports`, `basedpyright` across both packages, and `mkdocs build`.
