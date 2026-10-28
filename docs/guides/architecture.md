# Architecture

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

## Invariants & boundaries

### Leaf independence
`eager-core` and `eager-script` are 100% dependency-free and headless.

### Headless runtime
`eager-runtime` contains zero GUI, graphics, or windowing dependencies.

### Direct submodule imports
All primitives are imported directly from submodules (`from eager_core.<module> import ...`); root re-export shims are strictly forbidden.

### Safe expressions
Expression compilation (`compile_expr`) uses whitelisted AST evaluation with zero calls to Python's `eval()` or `exec()`.

## Script lowering

`@if` blocks are flattened into local-jump nodes. Inline choices are lowered into anonymous scenes formatted as `<scene_id>__anon_<line>` with `SceneNode.is_anonymous = True`. `StoryVM.choose` pushes an `inline` `CallFrame`; jumping out of an anonymous scene discards this frame instead of returning.

## State and persistence

Rollback must restore story and UI/choice states together. `PersistentData` tracks global unlock/read states across runs and is never rolled back with normal checkpoints.

## Graphics layers

Stage elements render in virtual coordinates; UI elements draw in window pixels. Backends are optional lazy imports. Pillow-SIMD and regular Pillow are mutually exclusive; install the former via `scripts/install_pillow_simd.py`.
