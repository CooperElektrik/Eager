# AGENTS.md — Eager Monorepo

Operational guidelines and constraints for autonomous agents in `eager-mono`.

---

## 1. Operational boundaries

### Always do
- Use `.venv/` at the root or prefix commands with `uv run`.
- Import primitives directly from `eager_core.<module>` (e.g., `eager_core.events`); do not create or use re-export shims.
- Keep `eager-script` and `eager-core` dependency-free, and keep `eager-runtime` fully headless.
- Check constructor signatures, protocols, and existing call sites before writing code.
- Keep random state deterministic and save serialization atomic via `eager_runtime.saves`.
- Run tests, linter, and type checks before completing any task.

### Ask first
- Adding or updating dependencies in any `pyproject.toml`.
- Modifying `.es` screenplay syntax or public AST definitions.
- Changing save/checkpoint serialization schemas or `PersistentData` structures.
- Adding renderer backends or modifying native window bindings.

### Never do
- Use `eval()`, `exec()`, or widen AST whitelists in `eager_script.expr`.
- Touch the legacy stub `venv/`.
- Import `eager-runtime` or `eager-graphics` inside `eager-script` or `eager-core`.
- Implement narrative branching, rollback, or save logic in render players (`PILPlayer`, `PygletPlayer`)—keep that state machine in `GameSession`.
- Run `git commit` (delegated subagents).

---

## 2. Architecture and dependencies

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

### Invariants
- **Script lowering:** Flatten `@if` blocks into local-jump nodes. Lower inline choices into anonymous scenes formatted as `<scene_id>__anon_<line>` with `SceneNode.is_anonymous = True`. `StoryVM.choose` pushes an `inline` `CallFrame`; jumping out of an anonymous scene discards this frame instead of returning.
- **State and persistence:** Rollback must restore story and UI/choice states together. `PersistentData` tracks global unlock/read states across runs and is never rolled back with normal checkpoints.
- **Graphics layers:** Stage elements render in virtual coordinates; UI elements draw in window pixels. Keep backends as optional lazy imports. Pillow-SIMD and regular Pillow are mutually exclusive; install the former via `scripts/install_pillow_simd.py`.

---

## 3. Code patterns

### Import conventions

```python
# Direct submodule imports
from eager_core.events import DialogueEvent, ChoicePromptEvent
from eager_core.types import Color, Vec2
from eager_script.expr import compile_expr
from eager_script import parse_hook_args

# Avoid: non-existent shims or missing root exports
from eager_runtime.events import DialogueEvent       # Fails: no shim in runtime
from eager_script import evaluate_expression         # Fails: no such function
```

### Expression evaluation

```python
# Whitelisted AST parsing & compilation
from eager_script.expr import compile_expr

expr = compile_expr(expr_string)
result = expr.evaluate(context_variables)

# Avoid: arbitrary evaluation
result = eval(expr_string, {}, context_variables)    # Prohibited
```

### Hook parsing

```python
# Parse in script, handle in graphics
from eager_script import parse_hook_args

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
   (cd packages/eager-core && uv run basedpyright)
   (cd packages/eager-script && uv run basedpyright)
   (cd packages/eager-runtime && uv run basedpyright)
   (cd packages/eager-graphics && uv run basedpyright src)
   (cd packages/eager-script-lsp && uv run basedpyright)
   ```
4. **Git review:**
   ```bash
   git status
   git diff --stat
   ```
5. **Output reporting:** Report actual terminal outputs. Do not claim tests pass without running them.

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
uv run pytest packages/eager-script -q --tb=short -x      # Run package tests
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