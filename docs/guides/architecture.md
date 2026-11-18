# Architecture

Eager is organized as a monorepo with strict architectural boundaries enforced by `import-linter` contracts:

```text
eager.core ──▶ eager.script ──▶ eager.vm ──▶ eager.stage ──▶ eager.ui ──▶ eager.session ──▶ eager.cli
     │               │                                           ▲              ▲
     │               └───────────────────────────────────────────┴──────────────┘
     │
     ├──▶ eager.backends (independent of vm, stage, ui, session, cli)
     │
     └──▶ eager-script-lsp (depends only on eager.core and eager.script)
```

## Invariants & boundaries

### Leaf independence
`eager.core` and `eager.script` are 100% dependency-free and headless.

### Headless VM & session
`eager.vm` and `eager.session` run headlessly with `NullRenderer` / `NullAudioBackend`.

### Direct submodule imports
All primitives are imported directly from submodules (`from eager.core.<module> import ...`); root re-export shims are forbidden.

### Safe expressions
Expression compilation (`compile_expr`) uses whitelisted AST evaluation with zero calls to Python's `eval()` or `exec()`.

## Script lowering

`@if` blocks are flattened into local-jump nodes. Inline choices are lowered into anonymous scenes formatted as `<scene_id>__anon_<line>` with `SceneNode.is_anonymous = True`. `StoryVM.choose` pushes an `inline` `CallFrame`; jumping out of an anonymous scene discards this frame instead of returning.

## State and persistence

Rollback must restore story and UI/choice states together. `PersistentData` tracks global unlock/read states across runs and is never rolled back with normal checkpoints. Checkpoint serialization is standardized across `Checkpoint.to_dict()` and `Checkpoint.from_dict()`.

## Direct layer wiring & lifecycle notifications

`GameSession` wires `StageDirector`, `UIOverlay`, `ScreenManager`, and `AudioMixer` directly (using `NullRenderer` / `NullAudioBackend` when `headless=True` or `backend="null"`).
- When session state is restored (e.g. on save load or rollback), `GameSession.notify_state_restored()` invokes `on_state_restored()` on registered lifecycle listeners (such as `BasePlayer`) to synchronize visual presentation cleanly.

## Bidirectional AST serialization

All 22 AST nodes implement the runtime-checkable `AstNode` protocol and support bidirectional serialization via `to_dict()`, `from_dict()`, `to_json()`, and `from_json()`, tagged with the node's `type` discriminator.

## Exception hierarchies

Eager maintains clean domain exception hierarchies:
- `EagerCoreError` (`eager.core.exceptions`)
- `EagerScriptError` (`eager.script`)
- `EagerBackendError` (`eager.backends.exceptions`)

## Graphics layers

Stage elements render in virtual coordinates; UI elements draw in window pixels. Backends (`pil`, `pyglet`, `miniaudio`) are optional lazy imports. Pillow-SIMD and regular Pillow are mutually exclusive; install the former via `scripts/install_pillow_simd.py`.
