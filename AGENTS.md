# Eager-X — Agent Cheat Sheet (Monorepo)

> Quick-reference for navigating, testing, and extending the **Eager** monorepo —
> a dependency stack of four Python packages that together form a complete
> narrative-engine toolchain:
>
> 1. **eager-script** (`eager_script`) — zero-dependency screenplay DSL parser &
>    AST/scene-graph builder with safe expressions, conditionals, interpolation
>    and characters, plus screenplay hook-argument parsing and an optional
>    terminal editor.
> 2. **eager-core** (`eager_core`) — shared, dependency-free leaf subsystems
>    consumed by more than one layer: **AudioMixer**, core geometry & color types
>    (`Vec2`, `Rect`, `Color`), **easing** curves, **FrameClock**, **InputAction**
>    & **Keymap**, atomic **storage** helpers, narrative **StoryEvent**s &
>    **ChoiceOption**, and rich **text** tag parsing (`parse_text_tags`, `TextReveal`).
> 3. **eager-runtime** (`eager_runtime`) — headless story VM, event dispatcher,
>    **GameSession** central controller, save/load & rollback, text typewriter +
>    backlog, preferences/persistent data, terminal player, and the `eager` /
>    `eager-x` CLI façades.
> 4. **eager-graphics** (`eager_graphics`) — renderer-agnostic,
>    resolution-independent stage compositor & **presentation layer** with
>    pluggable backends (Null / Pyglet / PIL / Raylib), plus text tags, UI
>    screens and theme.
>
> Dependency DAG (bottom leaves → top): **eager-script** and **eager-core** are
> zero-dependency leaves; **eager-graphics** depends on both; **eager-runtime**
> depends on `eager-script` + `eager-core` and *optionally* on `eager-graphics`
> (the `graphics` extra) — the headless VM works without it.

---

## 1. Existing Agent Conventions

- When reading files, always prefer full file read (reading the whole file at once) over incremental reads (reading parts of the file only). Incremental reads are slow and extremely costly when compared to just reading the full file at once.
- When searching, always use ripgrep (`rg`) and exclude venv or extraneous directories.
- **Exploration via `pool exec`**: To locate the exact files and content relevant to a task,
  use `pool exec --unsafe-auto-allow -p "PUT YOUR PROMPT HERE"`. (`--unsafe-auto-allow` only
  skips the interactive confirmation prompt — the CLI itself is sandboxed.) Inspect only the
  files that the tool surfaces — do **not** waste time reading extraneous files that are not
  directly relevant to the task. This applies to both the main agent and every subagent (see §12).
- When benchmarking, create one reusable benchmark harness and use it instead of writing the benchmark inline every time.
- Always prefer to chain Bash commands together to run quickly and effectively. This will always save you time.
- Inspect signature or read the class' init before writing scripts.
- Use `pytest -q --tb=short -x`; use `git diff --stat`; print only summary metrics.
- Implement everything at once, test all, fix all, verify all, submit.
- The Python virtual environment is `.venv/` at the **monorepo root** (not `venv/`).
  **⚠ There is also a legacy `venv/` stub at the repo root — do not use it; it is empty.**
  Always target `.venv/`.
- **Python version**: `requires-python = ">=3.11"` in each package; the workspace
  `.venv/` is Python 3.14. Do not rely on 3.14-only syntax in library code — keep
  library code compatible with 3.11 so the packages remain installable.
- Install/activate once, then run everything from the package directory:
  `source .venv/bin/activate && cd packages/eager-graphics`
  (For tests of the whole tree you can also run from the monorepo root — see §5.)

---

## 2. Directory Map

```
eager-mono/                          # uv workspace root
├── pyproject.toml                   # [tool.uv.workspace], dev-dependencies
├── uv.lock
├── .venv/                           # Python 3.14 venv (the real env — use this)
├── venv/                            # (legacy stub — do not use; empty)
├── AGENTS.md                        # ← this file
├── examples/                        # root-level demos
│   ├── demo_story.es
│   └── run_demo.py
└── packages/
    ├── eager-script/                # ← Eager-S screenplay DSL parser (leaf)
    │   ├── pyproject.toml           # name = "eager-script", 0 runtime deps
    │   ├── README.md
    │   ├── src/eager_script/        # import: eager_script
    │   ├── tests/                   # 5 files, 100 tests
    │   ├── docs/                    # syntax.md, scene-graph.md, validation.md,
    │   │                              # api-reference.md, editor.md, benchmarks.md
    │   └── benchmarks/              # benchmark.py
    ├── eager-core/                  # ← shared leaf subsystems (audio, types, math, timing, events, text)
    │   ├── pyproject.toml           # name = "eager-core", 0 runtime deps
    │   ├── README.md
    │   ├── src/eager_core/          # import: eager_core
    │   └── tests/                   # 8 files, 26 tests
    ├── eager-runtime/               # ← Eager narrative runtime (VM + session)
    │   ├── pyproject.toml           # name = "eager-runtime", deps: eager-script, eager-core
    │   ├── README.md
    │   ├── src/eager_runtime/       # import: eager_runtime
    │   ├── tests/                   # 12 files, 70 tests
    │   └── (no docs/)               # docs live in eager-script + README
    └── eager-graphics/              # ← stage compositor + presentation layer
        ├── pyproject.toml           # name = "eager-graphics", deps: eager-core, eager-script
        ├── README.md
        ├── src/eager_graphics/      # import: eager_graphics
        │   ├── screens/             # Screen, ScreenManager, Theme, widgets,
        │   │                          #   builtin screens (Title, Save/Load, …)
        │   ├── renderers/           # NullRenderer + lazy Pyglet/PIL/Raylib
        │   └── ...                  # (text.py, compositor.py, director.py, …)
        ├── tests/                   # 23 files, 242 tests
        ├── docs/                    # architecture.md, api.md, hooks.md
        └── examples/                # stage_demo.py, pyglet_visual_novel.py,
                                     #               pil_visual_novel.py
```

### Package Summary

| Package | Import | Runtime Deps | Extras | Tests |
|---|---|---|---|---|
| `eager-script` | `eager_script` | none | `editor` (blessed), `dev` (pytest, ruff) | 100 in 5 files |
| `eager-core` | `eager_core` | none | `dev` (pytest, ruff) | 26 in 8 files |
| `eager-runtime` | `eager_runtime` | `eager-script`, `eager-core` | `graphics` (eager-graphics), `dev` (pytest, ruff, pyglet, blessed) | 70 in 12 files |
| `eager-graphics` | `eager_graphics` | `eager-core`, `eager-script` | `dev` (pytest, ruff, eager-runtime), `hardware` (pyglet), `software` (Pillow), `raylib` (raylib≥6.0.0), `all` (all three) | 242 in 23 files |

> **Counts drift.** The test counts above are accurate as of the last update but
> will rot as tests are added. Regenerate with:
> ```
> for p in eager-script eager-core eager-runtime eager-graphics; do
>   (cd packages/$p && pytest --collect-only -q 2>/dev/null | tail -1)
> done
> ```

---

## 3. Source Layout & Module Responsibilities

### 3.1 eager-script (`packages/eager-script/src/eager_script/`)

| Module | Key Exports | Purpose |
|---|---|---|
| `__init__.py` | `ScreenplayParser`, `PlainScreenplayParser`, `parse`, `parse_iter`, `to_dict`, `to_json`, `to_graph`, `parse_graph`, `validate`, `slugify`, `ParseError`, all `Parsed*` node classes (incl. `ParsedSet`, `ParsedDefault`, `ParsedCharacter`, `ParsedIf`/`ParsedElif`/`ParsedElse`/`ParsedEnd`, `ParsedCondJump`, `ParsedLocalJump`), `ParsedItem` union | Top-level re-exports. Defines all AST node dataclasses (`frozen=True, slots=True`), parsing patterns (`CHOICE_PATTERN`, `VOICE_PATTERN`, `SPEAKER_PATTERN`), the `ScreenplayParser` (standard mode with override hooks), `PlainScreenplayParser` (Eager-SP mode), and module-level convenience functions. `__version__ = "0.1.0"`. Lazy-imports `SceneGraph`/`SceneEdge`/`SceneNode`/`parse_graph`/`to_graph` from `graph.py` and `ValidationError`/`ValidationResult`/`validate` from `validator.py`. Adds `$`/`@`/`[...]` script-logic parsing, `[var]` interpolation, and `@if` lowering. |
| `expr.py` | `compile_expr`, `CompiledExpr`, `ExprError`, `_ALLOWED_FUNCTIONS`, `_ALLOWED_OPERATORS` | Zero-dependency safe-expression evaluator (`compile_expr(src) -> CompiledExpr`, `CompiledExpr.evaluate(env) -> Any`). Parses with `ast.parse(mode="eval")` and recursively whitelists nodes (Constant, Name, Attribute only on `persistent`, BoolOp, UnaryOp, BinOp, Compare, IfExp, whitelisted Calls, List/Tuple); normalizes `true`/`false`/`none` to Python constants. Whitelisted functions: `visited`, `seen`, `random`, `chance`, `min`, `max`, `abs`, `len`, `int`, `str`, `round`. Syntax/security violations raise `ExprError`. Import via `from eager_script.expr import …` (not re-exported at package top level). |
| `graph.py` | `SceneNode`, `SceneEdge`, `SceneGraph`, `to_graph`, `parse_graph` | Immutable directed scene graph from parsed AST. `SceneNode` has `id, display_name, line_number, body: tuple[ParsedItem,...], speakers, hooks`. `SceneEdge` has `source, target, kind ∈ {"jump","call","choice","return","fallthrough"}, label, line_number, `condition: str \| None`. `SceneGraph` has `entry, nodes: dict[str,SceneNode], edges: tuple[SceneEdge,...], preamble: tuple[ParsedItem,...], `characters: dict, `defaults: tuple[ParsedDefault,...]` plus queries: `successors`, `predecessors`, `reachable_from`, `is_reachable`, `dead_ends`, `hubs`, `branching_points`, `terminal_scenes`, `to_dict`, `to_json`, `to_dot`, `to_mermaid`. `_lower_scene_body()` flattens nested `@if`/`@elif`/`@else`/`@end` into `ParsedCondJump`/`ParsedLocalJump` so `beat_index` stays a flat int; edges inside conditional blocks are still extracted. |
| `validator.py` | `ValidationError`, `ValidationResult`, `validate` | Static validation. `ValidationError` (frozen slots: `message`, `line_number`, `level="error"`). `ValidationResult` (frozen slots: `errors`, `warnings`; `.is_valid` property). Checks: Undefined Target (error), Duplicate Label (error), Plain Mode Violations (error), unbalanced `@if`/`@end` (error), expression syntax errors in `$`/`@if`/`@elif`/choice conditions (error), `$`/`@`/`[` directives outside scenes (error). Warnings: Unreturned Subroutine, Dead Code/Unreachable, Orphan Scene Label, Unreachable From Entry, Cyclical Traversal, variable read without `@default`/`$` assignment, speaker not in `@character` defs when any are defined, unknown hook name. |
| `hooks.py` | `HookArgs`, `parse_hook_args` | Dependency-free parser for the argument tail of a screenplay hook (`~ name args`). Handles positional tokens, `at`/`with`/`to` keywords, `key=value` pairs, and quoted strings. `HookArgs` is frozen slots with typed string/number/bool getters; colour decoding lives in `eager_graphics.director` (moved here from eager-graphics in the presentation-layer split). |
| `cli.py` | `build_parser`, `main` | Argparse CLI with subcommands: `parse` (`-o`, `--indent`, `--plain`), `graph` (`-o`, `--format json|dot|mermaid`, `--no-body`, `--indent`, `--plain`), `check` (`--plain`), `edit` (`--read-only`, `--plain`). Entry point: `eager-script = "eager_script.cli:main"`. |
| `editor/__init__.py` | `is_editor_available`, `run_editor`, `Editor` (lazy `__getattr__`) | Optional terminal editor gate. `is_editor_available()` checks for `blessed`. `__getattr__` lazily loads `Editor` from `app.py`. |
| `editor/app.py` | `Editor` | Full-screen terminal editor with alternate screen buffer, raw/cbreak input mode (`editor_input_mode` context manager disables IXON/ISIG). Renders header bar, viewport (gutter with `!`/`W`/space markers + syntax highlighting), status bar, help bar. Keybindings: Ctrl+S save, Ctrl+Q/Ctrl+X/Ctrl+C quit, Ctrl+O outline, Ctrl+F/Ctrl+W find, Ctrl+G goto-line, Ctrl+Z undo, Ctrl+Y/Ctrl+R redo, Ctrl+K/Ctrl+D delete-line, F1/Ctrl+H help. |
| `editor/buffer.py` | `TextBuffer`, `BufferSnapshot` | Line storage, cursor, undo/redo (200-entry stacks), search. |
| `editor/highlighter.py` | `EagerSHighlighter` | `highlight_line(line)→str` applying ANSI styles to all DSL syntax categories. |
| `editor/ui.py` | `draw_box`, `prompt_input`, `confirm_dialog`, `outline_dialog`, `help_dialog` | Modal terminal dialogs. |
| `editor/outline.py` | `SceneEntry`, `extract_outline` | Scene outline extraction from source lines. |
| `editor/validator_cache.py` | `ValidatorCache` | Caches parse+validation results; `get_line_status(line_number)`, `summary()`. |
| `__main__.py` | — | `from eager_script.cli import main; sys.exit(main())` |

### 3.2 eager-core (`packages/eager-core/src/eager_core/`)

| Module | Key Exports | Purpose |
|---|---|---|
| `__init__.py` | All core public classes and functions | Top-level re-exports. Zero-dependency leaf package consumed by higher layers. `__version__ = "0.1.0"`. |
| `audio.py` | `AudioBackend`, `AudioMixer`, `ChannelState`, `NullAudioBackend` | Low-level audio provider protocol, channel management, volume hierarchy, and fade interpolation ramps. |
| `types.py` | `Vec2`, `Rect`, `Color`, `WHITE`, `BLACK`, `TRANSPARENT`, `RED`, `GREEN`, `BLUE` | Immutable 2D vectors, axis-aligned bounding rectangles, and RGBA float colors with hex parsing and byte conversions. |
| `easing.py` | `linear`, all `ease_in_*`/`ease_out_*`/`ease_in_out_*`, `get_easing`, `EASING_MAP`, `EasingFunc` | Mathematical easing curves for animations, audio fades, and transitions. |
| `timing.py` | `FrameClock` | Lightweight wall-clock delta-time (`dt`) measurement, instantaneous and rolling average FPS tracker. |
| `input.py` | `InputAction`, `Keymap` | Backend-neutral 29-action semantic input enum and key identifier mapping dictionary. |
| `storage.py` | `get_default_save_dir`, `atomic_write_json`, `safe_read_json` | Platform save directory resolution, crash-safe atomic JSON file writing and safe reading. |
| `events.py` | `StoryEvent`, `SceneEnterEvent`, `DialogueEvent`, `AppendEvent`, `FreshBoxEvent`, `NarrationEvent`, `ChoiceOption`, `ChoicePromptEvent`, `HookEvent`, `SceneExitEvent`, `StoryEndEvent`, `InputPromptEvent` | Discrete narrative engine events and choice option structures. |
| `text.py` | `parse_text_tags`, `FormattedText`, `TextSegment`, `PausePoint`, `TextReveal` | Inline dialogue text tag parser and typewriter reveal pacing controller. |

### 3.3 eager-runtime (`packages/eager-runtime/src/eager_runtime/`)

| Module | Key Exports | Purpose |
|---|---|---|
| `__init__.py` | `EventDispatcher`, all `StoryEvent` types (incl. `InputPromptEvent`), `ChoiceOption`, `TerminalPlayer`, `StoryVM`, `StoryRuntimeError`, `StorySnapshot`, `HistoryManager`, `CallFrame`, `InputAction`, `Keymap` (eager). Lazy: `VisualEngine`, `SaveSlot`, `StateCorruptionError` (`engine.py`); `GameSession`, `Checkpoint`, `CheckpointHistory` (`session.py`); `SaveManager`, `SaveMetadata`, `SaveData` (`saves.py`); `PersistentData` (`persistent.py`); `Preferences` (`preferences.py`); `Backlog`, `BacklogEntry` (`backlog.py`) via `_LAZY_EXPORTS` dict + `__getattr__`. `__version__ = "0.1.0"`. | Top-level re-exports. Bare `import eager_runtime` is headless-only (no graphics) — the graphics-dependent `GameSession`/`engine` modules are lazy-exported so the headless VM, dispatcher, events, state, input, and terminal player incur zero graphics import cost. |
| `runtime.py` | `StoryVM`, `StoryRuntimeError` | Headless story VM executing a `SceneGraph`. Properties: `graph`, `current_scene_id`, `beat_index`, `is_ended`, `pending_choice`, `variables`, `visited_scenes`, `can_rollback`. Methods: `set_variable`, `get_variable`, `save()→StorySnapshot`, `load(snapshot)`, `rollback()→bool`, `jump(scene_id)`, `call(scene_id)`, `choose(choice:int\|str)`, `step()→StoryEvent\|None`. Executes `ParsedSet` (`$`), `ParsedCondJump`/`ParsedLocalJump` (lowered `@if`) silently per beat; evaluates expressions via `compile_expr` against a per-VM `random.Random` (state persisted in `StorySnapshot.rng_state`); interpolates `[var]` with `[[`/`]]` literal escapes (missing var → leaves `[name]`, records runtime warning). Manages `_call_stack: list[CallFrame]`, `_visited_scenes: set[str]`, `_history: HistoryManager`. Emits `SceneEnterEvent` on entry, `SceneExitEvent` on transitions, `StoryEndEvent` (incl. `reason="no_entry"` for empty graphs) at termination. |
| `events.py` | `StoryEvent` (TypeAlias union of 10 frozen slots dataclasses), `SceneEnterEvent`, `DialogueEvent`, `AppendEvent`, `FreshBoxEvent`, `NarrationEvent`, `ChoiceOption`, `ChoicePromptEvent`, `HookEvent`, `SceneExitEvent`, `StoryEndEvent`, `InputPromptEvent` | Thin re-export of `eager_core.events` — the dataclasses are defined there (see §3.2), not here. Each has `.type: str` property and `.to_dict()`. `ChoiceOption` carries `condition: str \| None` + `enabled: bool`; `ChoicePromptEvent.options` is a `tuple`. `SceneExitEvent.transition_kind ∈ {"jump","call","choice","return","fallthrough"}`; `StoryEndEvent.reason ∈ {"terminal","dead_end","completed","interrupted"}`; new `InputPromptEvent` (`var_name`, `prompt`, `default`) emitted from `~ input`. |
| `dispatcher.py` | `EventDispatcher` | Bridges VM → callbacks. Registration: `on_hook(hook_name)` decorator (passes `event.args` to handler), `on_event(event_type)` decorator, `on_any_hook(func)`, `on_any_event(func)`. Dispatch: `dispatch(event)` fires global → type-specific → hook-specific listeners. `run_until_pause(vm)` steps VM and dispatches events, pausing on `ChoicePromptEvent` or `StoryEndEvent`. |
| `state.py` | `CallFrame`, `StorySnapshot`, `HistoryManager` | `CallFrame` (frozen slots: `scene_id`, `beat_index`; `to_dict`/`from_dict`). `StorySnapshot` (frozen slots: `current_scene, beat_index, call_stack, variables, visited_scenes, pending_choice_beat, next_transition_target, just_entered_scene, is_ended, rng_state`; `to_dict`/`to_json`/`from_dict`/`from_json` with `.get()` defaults for forward compatibility). `HistoryManager` — list-backed, `max_history=500`; `push`, `pop()→StorySnapshot\|None`, `clear`, `can_rollback`, `depth`. |
| `engine.py` | `VisualEngine`, `SaveSlot`, `StateCorruptionError` | Backward-compatible visual-novel façade. `VisualEngine` now **wraps a `GameSession`** (stored as `self.session`) while preserving its prior public API (`advance`, `step_frame`, `render`, `render_items`, `run_headless`, `make_choice`, `can_rollback`, `save_slot`, `load_save_slot`, `rollback`). Backend selection: `"null"` (NullRenderer, always), `"pyglet"`, `"pil"` (lazy import), `"raylib"` (lazy import). Params: `script_path, *, backend="null", asset_dir=None, virtual_width=1920, virtual_height=1080, plain=False, max_history=500`. `SaveSlot` is a frozen dataclass (`story_state: dict`, `visual_state: dict`). |
| `session.py` | `GameSession`, `Checkpoint`, `CheckpointHistory` | **Central controller** for interactive novels. Owns `vm`, `dispatcher`, `compositor`, `director`, `audio` (`AudioMixer` from `eager_core`), `backlog`, `screens`, `preferences`, `persistent`, `save_manager`, `keymap`, `overlay`. State flags: `mode ∈ {"title","game","menu","ended"}`, `skip_mode`, `auto_mode`, `ui_hidden`, `is_finished`, `active_choice_prompt`, `active_input_prompt`. Core API: `advance()` (runs VM to the next interaction, dispatches all events, then **checkpoints**), `choose(choice)`, `submit_input(value)`, `rollback()→bool`, `update(dt)`, `draw(ui_backend, width, height)`, `handle_input(action, **payload)`. `Checkpoint = {story, visual, audio, backlog_len, ui}`; `CheckpointHistory` is a bounded deque (default 100). Save/load: `save_game/load_game/quicksave/quickload` on `SaveManager`. `advance()` pushes a `Checkpoint` after each interaction; `rollback()` pops to the previous one and **re-materializes pending choices** so the menu reappears (fixes B4). Imports `eager_graphics` at module top — but it's lazy-exported from `__init__`, so bare `import eager_runtime` stays headless. |
| `input.py` | `InputAction`, `Keymap` | Backend-neutral input layer (zero graphics imports; re-exports `eager_core.input`). `InputAction` — 29-value `str, Enum` (`ADVANCE, ROLLBACK, ROLL_FORWARD, CHOOSE, POINTER_MOVE/CLICK, SCROLL, NAV_UP/DOWN/LEFT/RIGHT, CONFIRM, CANCEL, SKIP_TOGGLE/HOLD/RELEASE, AUTO_TOGGLE, QUICK_SAVE/LOAD, GAME_MENU, HISTORY, HIDE_UI, SCREENSHOT, FULLSCREEN, TEXT_CHAR/BACKSPACE, RELOAD, DEBUG_OVERLAY, QUIT`). `Keymap.DEFAULT_BINDINGS` maps Ren'Py-style key names (`space`, `enter`, `mouse_left`, `pageup`, `mouse_wheel_up`, `ctrl`, `tab`, `a`, `escape`, `f5`, `f9`, `s`, `f`, `shift+r`, `f3`, `q`) → `InputAction`; `map_key(name)→InputAction\|None`. |
| `backlog.py` | `Backlog`, `BacklogEntry` | Bounded chronological dialogue/narration log (`max_entries=200`): `add(speaker, text, voice, emotion)`, `append_to_last(text)` (for `-` continuations), `clear`, `to_list`/`from_list`. Truncated on rollback to the checkpoint's `backlog_len`. |
| `saves.py` | `SaveManager`, `SaveData`, `SaveMetadata` | On-disk save-slot system. `SaveManager(save_dir, max_autosaves=5, max_quicksaves=5)`: `save_slot/load_slot/get_slot_metadata/delete_slot/list_slots/quicksave/quickload/autosave/autoload`. Files are `<sanitized_slot>.json` of `{metadata, checkpoint}`; `SaveMetadata` (frozen: `slot_name, timestamp, scene_id, scene_name, dialogue_snippet, playtime_seconds`). Atomic via `storage.atomic_write_json` (tmp + `os.replace`); `safe_read_json` falls back on missing/corrupt. |
| `persistent.py` | `PersistentData` | `MutableMapping` for cross-playthrough state (`persistent.*`). Loads/saves `persistent.json` atomically; `unlock_gallery`/`is_gallery_unlocked`, `unlock_achievement`/`has_achievement`; attribute-style access. **Not** rolled back. |
| `preferences.py` | `Preferences` | `@dataclass`: `text_speed` (cps, 0=instant), `auto_forward_time`, `master_volume`, `music_volume`, `sfx_volume`, `voice_volume`, `skip_unseen`, `fullscreen`, `resolution_scale`; `load(file)`/`save(file)` atomic JSON with field filtering. |
| `project.py` | `ProjectConfig`, `merge_graphs` | `game.toml` loader via stdlib `tomllib` (`title/version/author/entry_script/virtual_width/virtual_height/theme`). `merge_graphs(graphs)` merges multi-file `SceneGraph`s (nodes/edges/preamble/characters/defaults; duplicate scene IDs flagged by validator). |
| `storage.py` | `get_default_save_dir`, `atomic_write_json`, `safe_read_json` | Re-export of `eager_core.storage` (see §3.2): platform save dir (`$EAGER_SAVE_DIR` → XDG `~/.local/share/eager/<id>` / macOS `~/Library/Application Support/eager/<id>` / Windows `%APPDATA%\eager\<id>`); `atomic_write_json` (tmp + `os.replace`); `safe_read_json` (returns default on missing/corrupt). Stdlib only. |
| `player.py` | `TerminalPlayer` | Interactive terminal runner. `TerminalPlayer(vm, *, input_stream, output_stream, use_colors)`. `play()` loops until `vm.is_ended`, printing SceneEnterEvent, DialogueEvent, NarrationEvent, AppendEvent, FreshBoxEvent, HookEvent, ChoicePromptEvent, StoryEndEvent. `_handle_choice_input` supports `:save`, `:load`, `:undo`/`:rollback`, `:vars`, `:q`/`:quit`, plus numeric and text choice matching. |
| `cli.py` | `build_parser`, `build_x_parser`, `main`, `main_x` | Two CLIs: `eager` (text-only: `play`, `inspect`, `test-run [--all-paths] [--max-steps]`) and `eager-x` (visual novel: `play [--backend pyglet\|pil\|raylib] [--warp scene] [--plain]`, `render [--auto-choose]`, `run <project_dir>`, `new <name>`, `check <script\|dir>`, `build [-o/--output]`). `_ensure_graphics()` raises a helpful `ImportError`. `_run_interactive_player` drives `GameSession`/`VisualEngine` through `PygletPlayer`/`PILPlayer`/`RaylibPlayer`. |
| `__main__.py` | — | `from eager_runtime.cli import main; sys.exit(main())` |

### 3.4 eager-graphics (`packages/eager-graphics/src/eager_graphics/`)

| Module | Key Exports | Purpose |
|---|---|---|
| `__init__.py` | All public classes & functions | Top-level package re-exports. Core API **including the text module** (`TextReveal`, `FormattedText`, `parse_text_tags`, `TextSegment`, `PausePoint`) is imported eagerly. Audio moved out to `eager_core` and screenplay hook-arg parsing to `eager_script` in the presentation-layer split. `NullRenderer` and `FrameClock` always available. Optional backends (Pyglet, PIL, Raylib) resolved lazily via `renderers.__getattr__` to avoid import side effects. `__version__ = "0.1.0"`. |
| `compositor.py` | `StageCompositor` | **Core orchestrator.** Manages layers, drives the `Timeline`, applies camera shake, generates the `RenderItem` list, tracks FPS via `FrameClock`, and provides `save_state`/`load_state`/`debug_info`/`debug_repr`/`step`/`run_headless`. |
| `director.py` | `StageDirector`, `CharacterConfig` | Bridges Eager's `EventDispatcher` to the compositor. Registers screenplay hooks via `bind()` (`~ bg`, `~ bg_clear`, `~ scene`, `~ image`, `~ show`, `~ hide`, `~ move`, `~ expr`, `~ fade_in`/`~ fade_out`, `~ flash`, `~ shake`, `~ play`/`~ stop`/`~ volume` for audio, `~ nvl`/`~ nvl_clear`). `bind()`'s `_wrap_hook` no longer auto-snapshots; visual history is driven explicitly via `snapshot_visual_state()`/`on_beat_step()` (the session calls it before advancing a beat) and `rollback_visual_state()`. The wildcard `on_any_event` listener translates narrative events (dialogue/append/fresh_box/narration, choices, scene enter/exit, story end) into `UIState` updates; auto-syncs character expressions from emotion tags, resolves side images (`<asset>_<emotion>`), and routes `~ play` to the `AudioMixer` (skipped in skip mode). Owns `UIState` and `VisualHistoryManager` for `save_visual_state`/`load_visual_state`. |
| `text.py` | `TextReveal`, `FormattedText`, `TextSegment`, `PausePoint`, `parse_text_tags` | Text tag parsing + typewriter reveal. `parse_text_tags(raw)` parses `{b}/{i}/{u}/{s}/{color=#hex}/{size=N}/{w}`/`{p}`/`{fast}`/`{{`-escape into `FormattedText` (plain text + `tuple[TextSegment]` + `tuple[PausePoint]`). `TextReveal(formatted, cps)`: `update(dt)`, `visible_chars`, `is_complete`, `complete_immediately()`, `{w}`/`{p}` pause points; cps=0 → instant. |
| `stage.py` | `Stage`, `Layer`, `StageElement`, `ElementState` | Visual hierarchy: ordered layers → named elements → mutable element state. All serializable via `to_dict`/`from_dict`. |
| `layout.py` | `LayoutResolver`, `ViewportTransform` | Virtual stage resolution, semantic position names (`left`, `center`, etc., custom), viewport scaling modes (`LETTERBOX`, `STRETCH`, `CROP`, `FIT_WIDTH`, `FIT_HEIGHT`). `compute_viewport()` is aliased as `compute_viewport_transform()`. |
| `timeline.py` | `Timeline`, `Tween` | Animation engine. `Tween` is a dataclass (`target, property_name, start_value, end_value, duration, easing, delay, elapsed, on_complete, on_update, finished`). `Timeline` provides `add_tween`, `cancel_tweens_for`, `has_tweens`, `active_tweens`, `active_count`, `update(dt)`, `clear()`. Interpolates `float`, `Vec2`, and `Color`. |
| `types.py` | `Vec2`, `Color`, `Rect`, `Anchor`, `ScaleMode`, `TransitionKind` | Immutable geometry, color, and coordinate types. Named color constants: `BLACK`, `BLUE`, `GREEN`, `RED`, `TRANSPARENT`, `WHITE`. |
| `easing.py` | `EasingFunc`, `linear`, all `ease_in_*`/`ease_out_*`/`ease_in_out_*`, `get_easing`, `EASING_MAP` | All easing curve functions + name lookup. `EasingFunc` is a `Callable[[float], float]` type alias. `EASING_MAP` registers every curve by name. |
| `history.py` | `VisualHistoryManager` | Bounded-stack (`collections.deque`) snapshot manager for visual state rollback. Deep-copies on push. |
| `ui_state.py` | `UIState`, `ChoiceOption`, `NVLEntry` | Dialogue textbox state (speaker, text, emotion, side_image, `nvl_mode`, `nvl_entries`), choices (with `enabled`/`condition`), and story-end tracking. `NVLEntry` records `(speaker, text, emotion)` for NVL mode. `clear_dialogue`/`clear_nvl`/`clear_choices` mutators; `to_dict`/`from_dict`. |
| `ui_components.py` | `UIOverlay`, `DialogueBox`, `ChoiceMenu`, `EndNotice`, `TextboxStyle`, `ChoiceMenuStyle`, `DialogueBoxLayout`, `TextAnchor`, `wrap_text` | Renderer-agnostic front-end UI chrome. Lays out in window pixels (top-left origin), draws via `UIDrawBackend`. `DialogueBox` (bottom-docked textbox + nameplate + advance cue + optional side-image slot) draws **word-wrapped** lines via `wrap_text`/`_get_wrapped_lines` (greedy wrap, respects `\n`, hard-breaks overlong words, cached); `ChoiceMenu` has `hit_test()`; `EndNotice` is a bottom banner; `UIOverlay` owns all three and delegates to a `UIDrawBackend` + `UIState`. |
| `timing.py` | `FrameClock` | Zero-dependency FPS tracker (instantaneous, rolling-60 average, overall). Tick once per frame. |
| `protocol.py` | `RenderItem`, `RenderBackend`, `UIDrawBackend` | `RenderItem` is a frozen, slots dataclass (the draw command) with `asset_id, x, y, opacity, scale_x, scale_y, rotation, anchor, tint, flip_h, flip_v, layer, z_order`, plus `to_dict`/`from_dict`. `RenderBackend` and `UIDrawBackend` are `Protocol`s backends implement. |
| `renderers/__init__.py` | `NullRenderer` (+ Pyglet/PIL/Raylib lazy via `__getattr__`) | Exports `NullRenderer` always. Optional backends (Pyglet, PIL, Raylib) are **not** eagerly imported — they are resolved lazily via `__getattr__` to avoid side effects (e.g. Pyglet initialises GTK/EGL on Wayland, which conflicts with other backends). `__all__` includes all backend names for type-checking; accessing a missing backend raises `ImportError` at access time. |
| `renderers/null.py` | `NullRenderer` | Headless, zero-dependency renderer. Records `RenderItem`s into `last_frame` and UI primitives into `ui_calls`. Implements both `RenderBackend` and `UIDrawBackend`. Also implements `render_compositor()` for API parity. |
| `renderers/pil.py` | `PILRenderer`, `PILPlayer`, `PILAssetResolver` | Software rendering backend with LRU sprite-transform caching, opaque direct-blit fast-path, precomputed LUT tinting, and `preload_assets`/`warm_sprite_cache`. |
| `renderers/pyglet.py` | `PygletRenderer`, `PygletPlayer`, `PygletAssetResolver` | Hardware-accelerated OpenGL 2D backend + interactive visual novel window. |
| `renderers/raylib.py` | `RaylibRenderer`, `RaylibPlayer`, `RaylibAssetResolver` | Hardware-accelerated OpenGL 2D backend (via `pyray`/raylib) + interactive visual novel window. |
| `screens/__init__.py` | `Screen`, `ScreenManager`, `Theme`, `Button`, `Label`, `Slider`, `TitleScreen`, `SaveLoadScreen` | Convenience re-exports for the built-in screens/widgets package. |
| `screens/screen.py` | `Screen`, `ScreenManager` | `Screen` base (rect, `build`, `handle_input`, `modal`, `visible`); `ScreenManager` stack (`register`/`show`/`hide`/`draw`, input routed to top; game input blocked under modal screens). |
| `screens/theme.py` | `Theme` | Frozen dataclass of palette colors + font sizes (textbox, nameplate, buttons, choices); defaults reproduce the legacy look. |
| `screens/widgets.py` | `Button`, `Label`, `Slider` | Immediate-mode renderer-agnostic widgets via `UIDrawBackend` (`hit_test`, hover/focus/disabled states, value-change callbacks). |
| `screens/builtin.py` | `TitleScreen`, `SaveLoadScreen` | Built-in screens: `TitleScreen` (Start Game / Load Game / Preferences / Quit) and `SaveLoadScreen` (paged 6-slot grid wired to `GameSession.save_game`/`load_game`). |

---

## 4. Key Architecture Concepts

### 4.1 Three-Tier Architecture

The Eager engine is structured as a three-layer stack:

```
┌─────────────────────────────────────────────────────┐
│  eager-graphics  (presentation layer)               │
│  StageCompositor • StageDirector                    │
│  TextReveal • ScreenManager • Theme • RenderBackends│
│  Computes *what* to draw; delegates drawing to      │
│  Null / Pyglet / PIL / Raylib backends.             │
└─────────────────────────▲───────────────────────────┘
                          │ (StoryEvent stream + ~ hook callbacks)
┌─────────────────────────┴───────────────────────────┐
│  eager-runtime   (session layer)                    │
│  GameSession (owns VM, dispatcher, compositor,      │
│  director, audio, screens, backlog, checkpoints,    │
│  prefs, persistent) • StoryVM • StorySnapshot       │
│  advance() runs VM → dispatches → checkpoints.      │
└─────────────────────────▲───────────────────────────┘
                          │ (SceneGraph)
┌─────────────────────────┴───────────────────────────┐
│  eager-script    (parsing layer)                    │
│  ScreenplayParser • expr • SceneGraph • Validator   │
│  Zero-dependency. Parses .es DSL into AST, lowers   │
│  @if blocks to CondJump/LocalJump, builds graph.    │
└─────────────────────────────────────────────────────┘
```

`eager-script` and `eager-core` are dependency-free leaves (the latter provides the `AudioMixer`); `eager-graphics` depends on both, and `eager-runtime` depends on `eager-script` + `eager-core` and optionally on `eager-graphics`.

### 4.2 eager-script — Parsing Layer

- **Eager-S DSL**: A line-oriented screenplay language with scene labels (`## Name --- id`), dialogue (`Speaker: text` or `Speaker (emotion): text`), narration (bare lines), append (`- text`), fresh box (`/ text`), choices (`? Text (target)`), jumps (`> target`), subroutine calls (`>> target`), returns (`<<`), hooks (`~ hook_name args`), and comments (`#`).
- **Two modes**: Standard mode (full DSL) via `ScreenplayParser`; Eager-SP plain mode (natural manuscript, no engine markup, auto-slugified targets, multi-line dialogue) via `PlainScreenplayParser`.
- **AST → Graph → Validation pipeline**: `parse()` → `ParsedItem[]` → `to_graph()` / `parse_graph()` → `SceneGraph` → `validate()` → `ValidationResult`. The `SceneGraph` supports topological queries (`successors`, `predecessors`, `reachable_from`, `dead_ends`, `hubs`, `branching_points`, `terminal_scenes`) and exports to JSON, Graphviz DOT, and Mermaid.
- **Script logic & expressions**: Standard mode adds `@default`/`$`/`@if`/`@elif`/`@else`/`@end` blocks, conditional choices (`? Text (target) if expr`), `[var]` interpolation (with `[[`/`]]` literal escapes), and `@character` definitions. `expr.py` provides a zero-dependency safe evaluator (`compile_expr` + whitelisted `ast` node walk; functions `visited`/`seen`/`random`/`chance`/`min`/`max`/`abs`/`len`/`int`/`str`/`round`). `@if` blocks are **lowered** in `graph.py` (`_lower_scene_body`) into flat `ParsedCondJump`/`ParsedLocalJump` so `beat_index` stays a flat int; `SceneGraph` gained `characters` and `defaults`, and `SceneEdge` gained `condition`. Plain (`--plain`) mode rejects `$`/`@`/`[` directives.
- **`sys.intern`** is used on all string identifiers (scene names, speaker names, emotion tags, hook names, targets) for memory efficiency and fast identity comparisons.
- **`parse_iter`** streams AST nodes with O(1) memory for large scripts.
- **Optional terminal editor** (`eager_script.editor`, requires `blessed`): full-screen editor with live diagnostics, syntax highlighting, and scene outline navigation.

### 4.3 eager-runtime — Session Layer

- **`GameSession`** is the backend-agnostic **central controller** for interactive novels. It owns the `StoryVM`, `EventDispatcher`, `StageCompositor`, `StageDirector`, `AudioMixer`, `Backlog`, `ScreenManager`, `Preferences`, `PersistentData`, `SaveManager`, `Keymap`, and `UIOverlay`. Its core loop `advance()` runs the VM to the next *interaction* (dialogue/narration/append/fresh_box/choice/input/stock_end), dispatches all intermediate events, records into the backlog, and then **pushes a `Checkpoint`**. `rollback()` pops the checkpoint history and restores story + visual + audio + UI + backlog atomically (re-materializing pending choices so the menu reappears — fixes B4). It also drives skip/auto-forward timers in `update(dt)` and draws stage + UI + active screen in `draw()`. Imported lazily from `eager_runtime.session` so bare `import eager_runtime` stays headless.
- **`StoryVM`**: The headless story virtual machine. It walks a `SceneGraph` node-by-node, beat-by-beat, emitting a `StoryEvent` for each narrative unit; executes `ParsedSet`/`ParsedCondJump`/`ParsedLocalJump` silently, evaluates `@`-expressions, interpolates `[var]`, and owns a `random.Random` (state persisted in `StorySnapshot.rng_state`). It maintains a call stack (`_call_stack: list[CallFrame]`) for `>>`/`<<` subroutines, a visited-scenes set, user variables (incl. a `persistent` proxy), and a `HistoryManager` for backward-compatible per-beat rollback. `step()` returns one `StoryEvent`; `is_ended` goes True at terminal/dead-end/completed/no_entry.
- **`EventDispatcher`**: Registers callbacks for specific hook names (`on_hook`), specific event types (`on_event`), or all events/hooks (`on_any_event` / `on_any_hook`). `run_until_pause(vm)` steps the VM and dispatches events, pausing on `ChoicePromptEvent`/`InputPromptEvent`/`StoryEndEvent`.
- **Event model**: 10 frozen, slots dataclasses, each with a `.type` string discriminator and `.to_dict()`. Events: `SceneEnterEvent`, `DialogueEvent`, `AppendEvent`, `FreshBoxEvent`, `NarrationEvent`, `ChoicePromptEvent` (+`ChoiceOption` with `condition`/`enabled`), `HookEvent`, `SceneExitEvent`, `StoryEndEvent`, `InputPromptEvent`.
- **`StorySnapshot` / `HistoryManager`**: Immutable snapshots (scene, beat index, call stack, variables, visited scenes, `pending_choice_beat`, `next_transition_target`, `just_entered_scene`, `is_ended`, `rng_state`) enable save/load and rollback; pending choices are re-materialized on load. `HistoryManager` is a bounded list (default 500).
- **Save/load stack**: `SaveManager` (atomic JSON slots, quicksave/autosave, thumbnails via backends), `PersistentData` (survives playthroughs; gallery/achievements), `Preferences` (text speed, volumes, skip/auto, fullscreen), `Checkpoint`/`CheckpointHistory` (session-level rollback deque, default 100).
- **`TerminalPlayer`** + **`InputAction`/`Keymap`**: `TerminalPlayer` consumes `StoryVM.step()` events and renders them to text; `InputAction`/`Keymap` (in `input.py`) give backend-neutral input mapping (Ren'Py-style defaults) for the graphical players.

### 4.4 eager-graphics — Graphics & Stage Compositor

- **Virtual stage**: 1920×1080 reference resolution, origin (0,0) at top-left. Characters anchored at `ground_y` (default 1080).
- **Two render layers**:
  - **Stage layer** — `StageCompositor` emits `list[RenderItem]` drawn by `RenderBackend` (Null/Pyglet/PIL/Raylib). Virtual coordinates → viewport-transformed. Content: backgrounds, sprites, fades, flashes, shake. Element IDs `__screen_fade__` (tint `BLACK`) and `__screen_flash__` (tint `WHITE`) live on the `overlay` layer for fades/flashes. The `__builtin_color_rect__` asset ID is a 1×1 white pixel.
  - **UI layer** — `UIOverlay` + components issue immediate-mode primitives (`draw_rect`, `draw_text`, `draw_image`) through `UIDrawBackend`. Window pixels, top-left origin. Content: dialogue box, nameplate, choice buttons, end notice. `NullRenderer` records these into `ui_calls` so the whole UI layer is assertable in headless tests.
- **Layer hierarchy** (z-order, ascending): `background` (0) → `characters` (100) → `foreground` (200) → `ui` (300) → `overlay` (400). Custom layers via `compositor.stage.get_or_create_layer()`.
- **Camera shake**: Non-destructive. `shake_offset` is computed in `update()` and applied during `render_list()` to non-exempt layers. Default exempt set: `{"ui", "overlay"}`. Element base positions are never modified.
- **Render items are frozen**: `RenderItem` is `@dataclass(frozen=True, slots=True)`. The compositor clones state into them at `render_list()` time. `global_z` sort key is computed as `layer.z_order * 1000 + elem.z_index` during `render_list()`; invisible layers and elements with `opacity <= 0` are skipped.
- **State snapshots**: `StageCompositor.save_state()` / `load_state()` serialize the entire stage hierarchy; `StageDirector.save_visual_state()` / `load_visual_state()` also capture `UIState` and the `VisualHistoryManager` stack.
- **Audio** (`eager_core.audio`): `AudioMixer` over a pluggable `AudioBackend` (default `NullAudioBackend` for headless tests) now lives in the shared leaf package **eager-core**, not in eager-graphics. Channels `music` (loop), `ambient` (loop), `sound` (polyphonic one-shot), `voice` (single) plus dynamic custom channels; per-call × channel-type × master volume; `fade_in`/`fade_out` ramps in `update(dt)`; `save_state`/`load_state` for save/resume. The runtime's `GameSession` constructs it; `StageDirector` receives it and wires `~ play`/`~ stop`/`~ volume`; skip mode suppresses `sound`/`voice`.
- **Text presentation** (`text.py`): `parse_text_tags` parses `{b}/{i}/{color=...}/{size=...}/{w}/{p}/{fast}` markup into `FormattedText` (segments + pause points); `TextReveal` does typewriter pacing driven by `Preferences.text_speed` (0 = instant) with click-to-complete to the next `{w}`/`{p}` boundary. `wrap_text` in `ui_components.py` performs greedy, cached word-wrap for multi-line dialogue (fixes B5).
- **Screens & theme** (`screens/`): `Screen` base + `ScreenManager` stack (modal input blocking); `Theme` (palette + fonts from `game.toml [theme]`); widgets `Button`/`Label`/`Slider`; built-in `TitleScreen` and `SaveLoadScreen` (wired to `SaveManager`). `GameSession.draw()` layers the active screen on top of the stage + UI.
- **NVL mode & side images**: `~ nvl on|off|clear` drives `UIState.nvl_mode`/`nvl_entries`; character `side=` side images render in the textbox (`<asset>_<emotion>`); `kind=nvl` characters always NVL.

### 4.5 `VisualEngine` — Compatibility Shim

> **New code should construct `GameSession` directly.** `VisualEngine` exists for backward compatibility only and is slated for eventual removal.

- **`VisualEngine`**: Lazily-imported (via `__getattr__`) backward-compatible façade. As of the Phase 1 refactor it **wraps a `GameSession`** (stored as `self.session`) while preserving its prior public API (`advance`, `step_frame`, `render`/`render_items`, `run_headless`, `make_choice`, `can_rollback`, `save_slot`, `load_save_slot`, `rollback`). Constructor takes a `.es` script path, backend name, optional asset dir, virtual resolution, and plain-mode flag.
- **Backend selection**: `"null"` (NullRenderer, always available), `"pyglet"` (hardware OpenGL), `"pil"` (software Pillow), `"raylib"` (hardware OpenGL via pyray). Unknown backends raise `ValueError`.
- **`SaveSlot`**: Frozen dataclass bundling `story_state` (VM snapshot dict) + `visual_state` (director's full visual state dict) for atomic save/load. `load_save_slot` wraps restore in try/except and rolls back to safety snapshots on failure, raising `StateCorruptionError`.
- **`run_headless`**: Runs the story to completion with `NullRenderer`, optionally auto-choosing a branch. Returns `dict(steps, ended, render_frames, final_ui_state)`.

---

## 5. Testing

Test counts and files per package (regenerate counts with the snippet in §2):

| Package | Files | Tests | Wall time |
|---|---|---|---|
| eager-graphics | 23 | 242 | ~5s |
| eager-runtime | 12 | 70 | — |
| eager-script | 5 | 100 | — |
| eager-core | 8 | 26 | — |

> **Optional-dependency guards.** `eager-runtime` tests that require
> `eager_graphics`, `pyglet`, or `Pillow` are guarded with `pytest.mark.skipif`.
> The workspace dev-dependencies include all of them, so `uv sync` from the repo
> root enables everything. `eager-script` tests requiring `blessed` (the editor
> tests) are similarly guarded — if `blessed` isn't installed, `test_editor.py`
> is skipped.

### Running tests

```bash
source .venv/bin/activate

# Per-package (recommended — matches §1 convention)
cd packages/eager-graphics && pytest -q --tb=short -x
cd packages/eager-runtime  && pytest -q --tb=short -x
cd packages/eager-script   && pytest -q --tb=short -x
cd packages/eager-core     && pytest -q --tb=short -x

# Whole tree from the monorepo root
pytest packages/ -q --tb=short -x

# Debugging
pytest -q --tb=long -s           # disable output capture
```

### Test File → Module Mapping

| Package | Test File | Covers |
|---|---|---|
| eager-core | `test_audio.py` | `AudioMixer`, `NullAudioBackend`, `AudioBackend` protocol, fades, save/load restores music |
| eager-core | `test_core_easing.py` | `eager_core.easing`: curve boundaries, `get_easing`, `EASING_MAP` |
| eager-core | `test_core_events.py` | `eager_core.events`: event dataclasses, `ChoiceOption`, `StoryEvent` union |
| eager-core | `test_core_input.py` | `eager_core.input`: `InputAction` members, `Keymap` bindings |
| eager-core | `test_core_storage.py` | `eager_core.storage`: save-dir resolution, atomic write, safe read |
| eager-core | `test_core_text.py` | `eager_core.text`: `parse_text_tags`, `TextReveal` pacing |
| eager-core | `test_core_timing.py` | `eager_core.timing`: `FrameClock` dt/FPS tracking |
| eager-core | `test_core_types.py` | `eager_core.types`: `Vec2`, `Rect`, `Color` |
| eager-graphics | `test_director_audio.py` | `StageDirector` audio-hook wiring (`~ play`/`~ stop`/`~ volume`) against an `eager_core` `AudioMixer` |
| eager-graphics | `test_compositor.py` | `StageCompositor`: backgrounds, characters, slides, save/load, shake, flash, fade |
| eager-graphics | `test_debug.py` | `StageCompositor` `debug_info`/`debug_repr` structure, JSON serializability, compact/full mode |
| eager-graphics | `test_director.py` | `StageDirector`: hook dispatch, emotion auto-sync, scene bg mapping, visual-state save/load |
| eager-graphics | `test_e2e_integration.py` | Full story flow: StoryVM + EventDispatcher + StageDirector + save/restore |
| eager-graphics | `test_easing.py` | Easing function boundaries, monotonicity, and `get_easing` lookups |
| eager-graphics | `test_fps_counter.py` | `FrameClock`, backend FPS integration, compositor `step`/debug FPS |
| eager-graphics | `test_headless_loop.py` | `step()` and `run_headless()` with/without backend |
| eager-graphics | `test_layout.py` | `LayoutResolver` positions, viewport transforms, scaling modes |
| eager-graphics | `test_null_renderer.py` | `NullRenderer` protocol compliance, frame lifecycle, copy isolation |
| eager-graphics | `test_overlay_rendering.py` | `__builtin_color_rect__`, flash/fade visuals, stage-sized coverage |
| eager-graphics | `test_phase7.py` | Phase 7 director hooks (`~ scene`/`~ image`/`~ show`/`~ hide`/`~ move`/`~ expr` transitions), side images, NVL mode, `~ input`, gallery/achievements |
| eager-graphics | `test_pil_optimizations.py` | putalpha fast-path, sprite/scaled cache, stage cache, preload/warm |
| eager-graphics | `test_pil_renderer.py` | `PILRenderer`, `PILAssetResolver`, `PILPlayer` (skipped if Pillow absent) |
| eager-graphics | `test_pyglet_renderer.py` | `PygletRenderer`, `PygletPlayer` (skipped if pyglet absent) |
| eager-graphics | `test_raylib_renderer.py` | `RaylibRenderer`, `RaylibAssetResolver`, `RaylibPlayer` (skipped if raylib absent) |
| eager-graphics | `test_screens.py` | Phase 6 `Screen`/`ScreenManager`, `Theme`, `Button`/`Label`/`Slider` widgets, `TitleScreen`/`SaveLoadScreen` (layout, hit-test, focus nav, modal, save grid) |
| eager-graphics | `test_stage.py` | `Stage`/`Layer`/`StageElement`/`ElementState` CRUD + serialization |
| eager-graphics | `test_text.py` | `parse_text_tags`, `TextReveal` typewriter pacing, `{w}`/`{p}` pauses, `complete()`, `wrap_text` word-wrap |
| eager-graphics | `test_timeline.py` | `Timeline` + `Tween` interpolation, cancellation, delay, immediate completion |
| eager-graphics | `test_types.py` | `Vec2`, `Color`, `Rect`, `Anchor`, `ScaleMode`, `TransitionKind` parsing |
| eager-graphics | `test_ui_components.py` | `UIOverlay`/`DialogueBox`/`ChoiceMenu`/`EndNotice` layout + `UIDrawBackend` conformance |
| eager-graphics | `test_visual_history.py` | `VisualHistoryManager` + director rollback + player rollback |
| eager-runtime | `test_cli_and_player.py` | CLI commands (`eager play`/`inspect`/`test-run`) + `TerminalPlayer` |
| eager-runtime | `test_engine.py` | `VisualEngine` façade (wraps `GameSession`): construction, backends, `advance`, `render`, `make_choice`, `rollback`, `save_slot`/`load_save_slot`, `run_headless` |
| eager-runtime | `test_hooks_and_dispatcher.py` | `EventDispatcher`: `on_hook`, `on_event`, `on_any_hook`, `on_any_event`, dispatch ordering |
| eager-runtime | `test_logic.py` | Phase 2 script logic: `$`/`@if`/`@elif`/`@else`/`@end`, `[var]` interpolation, choice conditions, rollback restores variables + RNG sequence |
| eager-runtime | `test_phase8.py` | Phase 8 tooling: `eager`/`eager-x` CLI (`check`, `build`, `run`, `warp`, `test-run --all-paths`), debug overlay, project config |
| eager-runtime | `test_rollback.py` | `StoryVM.rollback()` + `HistoryManager` across choice selections and step-by-step rewind |
| eager-runtime | `test_runtime_choices.py` | Choice branching: selection by index, by target ID, error cases |
| eager-runtime | `test_runtime_linear.py` | Linear story execution, empty graph handling, visited-scenes tracking |
| eager-runtime | `test_saves.py` | Phase 3 `SaveManager` CRUD, quicksave/autosave rotation, legacy slots, corrupt persistent-JSON backup, `PersistentData`, `Preferences`, session save/load |
| eager-runtime | `test_session.py` | Phase 1 `GameSession` advance/checkpoints, rollback restores sprites+text, rollback onto choice re-shows menu, `handle_input` |
| eager-runtime | `test_state_and_save.py` | `StorySnapshot`/`CallFrame` serialization round-trips, variable get/set, load-restore |
| eager-runtime | `test_subroutines.py` | `>>` / `<<` call stack: nested subroutine calls |
| eager-script | `test_parser.py` | `ScreenplayParser`/`PlainScreenplayParser`, `ParseError`, serialization, validators (ignored by basedpyright) |
| eager-script | `test_graph.py` | `SceneGraph`, `to_graph`, `parse_graph`, `SceneNode`/`SceneEdge` exports, CLI graph subcommands |
| eager-script | `test_editor.py` | `TextBuffer`, `Editor`, `EagerSHighlighter`, `extract_outline`, `ValidatorCache` (skipped if `blessed` absent) |
| eager-script | `test_expr.py` | `compile_expr` whitelist (rejects `__import__`, attribute access, lambdas, comprehensions), `CompiledExpr.evaluate`, `ExprError` |
| eager-script | `test_hooks.py` | `parse_hook_args` / `HookArgs` parsing (positional, `at`/`with`/`to`, `key=value`, quotes) |

---

## 6. Quick Start Commands

```bash
# 1. Activate the workspace venv (at monorepo root)
source .venv/bin/activate

# 2. Install all workspace deps (run once from the repo root)
uv sync

# 3. Tests — see §5 for the full testing reference
#    Quick version:
#      cd packages/<pkg> && pytest -q --tb=short -x

# 4. Run benchmarks (eager-script parser/validator/serializer)
cd packages/eager-script
PYTHONPATH=src python3 benchmarks/benchmark.py

# 5. CLI usage
eager-script parse script.es -o ast.json          # parse to JSON AST
eager-script graph script.es --format mermaid    # export scene graph to Mermaid
eager-script check script.es                     # validate script
eager-script edit script.es                      # open terminal editor (requires blessed)

eager play script.es                        # interactive terminal play
eager inspect script.es                     # inspect scene topology
eager test-run script.es                    # headless dry-run (auto-chooses 1st)
eager test-run script.es --all-paths        # exhaustively explore every branch
eager test-run script.es --max-steps 200      # cap total steps in a dry-run

eager-x play script.es --backend pil        # interactive visual novel (requires Pillow)
eager-x play script.es --backend pyglet     # interactive visual novel (requires pyglet)
eager-x play script.es --backend raylib     # interactive visual novel (requires pyray)
eager-x play script.es --warp intro         # jump directly to a scene label
eager-x render script.es --auto-choose 0    # headless render with NullRenderer
eager-x run <project_dir> --backend pil     # run a project dir (game.toml)
eager-x new myproject                       # scaffold game.toml + main.es + assets/
eager-x check script.es                     # validate script syntax + scene graph
eager-x build . --output dist.zip             # bundle project into a distribution archive

# 6. Type check (config in each package's pyproject.toml, basedpyright)
cd packages/eager-graphics && basedpyright
cd packages/eager-runtime && basedpyright
cd packages/eager-script && basedpyright

# 7. Lint
ruff check packages/                # lint library code (examples/ excluded)

# 8. Release / CI
#    CI workflows live in .github/workflows/ (lint → typecheck → test → build).
#    Version bumps happen per-package in each pyproject.toml + __init__.__version__.
#    Re-run `uv lock` from the repo root after any dependency change.
```

---

## 7. Documentation Reference

> Docs drift. Each row is accurate as of the package version shown; if you change
> a documented surface, update the doc and re-verify the row.

| Package | Version | Doc File | Covers |
|---|---|---|---|
| eager-script | 0.1.0 | `docs/syntax.md` | DSL syntax rules, Eager-SP plain mode, `$`/`@`/`[...]` script logic & interpolation, `@character`, escaping |
| eager-script | 0.1.0 | `docs/scene-graph.md` | Graph model, queries, DOT and Mermaid exports |
| eager-script | 0.1.0 | `docs/validation.md` | Validation checks, errors, warnings (incl. `@if`/`@end` balance, expression syntax, `$`/`@`/`[` outside scenes, unknown hooks) |
| eager-script | 0.1.0 | `docs/api-reference.md` | AST nodes (incl. `ParsedSet`/`ParsedDefault`/`ParsedCharacter`/`ParsedIf`-family/lowering nodes), `expr.py` API, core functions, exceptions |
| eager-script | 0.1.0 | `docs/editor.md` | Terminal editor features, keybindings, installation |
| eager-script | 0.1.0 | `docs/benchmarks.md` | Performance numbers across script sizes, streaming parser |
| eager-runtime | 0.1.0 | `README.md` | Features, quickstart, `GameSession`, save/load & rollback, `SaveManager` slots + thumbnails, `PersistentData`/`Preferences`, audio (from `eager-core`), `eager`/`eager-x` CLI (no `docs/` dir — runtime docs live in README; the Phase 8 plan's `docs/` was not materialized) |
| eager-core | 0.1.0 | `README.md` | Shared leaf package: audio mixing (`AudioBackend`/`NullAudioBackend`/`ChannelState`/`AudioMixer`) and the rationale for the layer split |
| eager-graphics | 0.1.0 | `docs/architecture.md` | Design pillars, rendering pipeline diagram, two-layer architecture, layer hierarchy, viewport scaling, camera shake, backend protocol, first-party renderers, UI components |
| eager-graphics | 0.1.0 | `docs/api.md` | Full API reference for `StageCompositor`, `StageDirector`, `LayoutResolver`/`ViewportTransform`, `RenderItem`, `Timeline`/`Tween`, `FrameClock`, `RenderBackend`, `UIDrawBackend`, first-party renderers |
| eager-graphics | 0.1.0 | `docs/hooks.md` | Screenplay hook syntax reference: `~ bg`, `~ bg_clear`, `~ show`, `~ hide`, `~ move`, `~ expr`, `~ fade_in`/`~ fade_out`, `~ flash`, `~ shake`, transitions & easing curves. Gaps (registered in `StageDirector.bind()` but undocumented): `~ scene`, `~ image`, `~ play`/`~ stop`/`~ volume` (audio), `~ nvl`/`~ nvl_clear` |

---

## 8. Recipes — Common Development Patterns

### 8.1 Extending the Eager-S DSL parser (eager-script)

1. Add a new AST node class in `__init__.py` as a `frozen=True, slots=True`
   dataclass with a `.type` property and `.to_dict()`.
2. Extend `_parse_prefixed` or the main `_parse` loop to emit the new node.
3. If the node is a new transition keyword, handle it in `graph.py`'s
   `to_graph()` edge construction and `SceneEdge.kind` (and `condition`).
4. Add a validation rule in `validator.py` if the new node can be statically
   checked; plain-mode (`--plain`) use of standard-only syntax must error.
5. Update `docs/syntax.md`, `docs/scene-graph.md`, `docs/validation.md`,
   `docs/api-reference.md`, and the editor highlighter.
6. Add tests to `tests/test_parser.py`, `tests/test_graph.py`, and
   (`tests/test_expr.py` for expressions).
7. For script-logic syntax (`$`/`@if`/`@character`/`[interp]`): the parser emits
   the high-level node, but `graph.py:_lower_scene_body` rewrites `@if` blocks to
   `ParsedCondJump`/`ParsedLocalJump` (keeping `beat_index` flat), expressions
   compile via `eager_script.expr.compile_expr`, and `StoryVM` executes the
   lowered nodes + interpolates `[var]`.

### 8.2 Adding a new screenplay hook handler (eager-graphics → eager-runtime bridge)

1. Add a handler method in `packages/eager-graphics/src/eager_graphics/director.py`
   (e.g. `handle_newhook(self, args: str) -> None`).
2. Register it in `StageDirector.bind()` via
   `dispatcher.on_hook("newhook")(_wrap_hook(self.handle_newhook))`.
   (`_wrap_hook` only forwards parsed args to the handler — visual-state
   snapshotting is driven explicitly by `GameSession` through
   `director.snapshot_visual_state()` / `on_beat_step()` before each interaction,
   **not** inside `bind()`.)
3. The handler parses args with `parse_hook_args(args)` (imported from
   `eager_script`) and calls the appropriate `StageCompositor` / `AudioMixer`
   (from `eager_core`) method.
4. Add docs to `packages/eager-graphics/docs/hooks.md`.

### 8.3 Adding a new easing function (eager-graphics)

1. Define the function in `packages/eager-graphics/src/eager_graphics/easing.py`.
2. Register it in the `EASING_MAP` dict.
3. It's immediately usable via `get_easing("your_name")` by name.
   Re-export from `__init__.py` if you want it in the top-level namespace.

### 8.4 Adding a new transition type (eager-graphics)

1. Add a member to `TransitionKind` in `packages/eager-graphics/src/eager_graphics/types.py`.
2. Implement the transition logic in `StageCompositor.set_background()` /
   `clear_background()` in `compositor.py`.
3. Document in `docs/hooks.md`.

### 8.5 Adding a new StoryEvent type (eager-runtime)

1. Add a `frozen=True, slots=True` dataclass in `eager_core/events.py` with a `.type`
   property and `.to_dict()` (re-export it from `eager_runtime/events.py`).
2. Add it to the `StoryEvent` TypeAlias union (in `eager_core/events.py`).
3. Emit it from `StoryVM.step()` in `runtime.py` where appropriate. If it is an
   *interaction* (pauses for the player, e.g. choices/input), add its `type`
   string to `GameSession.INTERACTION_TYPES` so `advance()` checkpoints & returns it.
4. Handle it in `GameSession` (e.g. add a branch to `handle_input`/`submit_input`)
   and, for UI-affecting events, in `TerminalPlayer.play()` (an `isinstance` branch).
5. Add tests to the relevant `test_runtime_*.py` file.

### 8.6 Adding a new CLI subcommand (eager-runtime)

1. Add a subparser in `build_parser()` or `build_x_parser()` in `cli.py`.
2. Implement the `run_*` handler function.
3. Wire it with `set_defaults(func=run_yourcmd)`.
4. If the command requires graphics, call `_ensure_graphics()` at the top.
5. Add tests to `tests/test_cli_and_player.py` and `tests/test_phase8.py`.
6. For `eager-x` commands, construct a `GameSession` (or the backward-compatible
   `VisualEngine`) and drive the player loop via `_run_interactive_player()`.

### 8.7 Adding a new renderer backend (eager-graphics)

Implement both protocols from `packages/eager-graphics/src/eager_graphics/protocol.py`:
- `RenderBackend` (`begin_frame`, `clear(color)`, `draw_item(item)`, `end_frame`) for the stage layer.
- `UIDrawBackend` (`draw_rect`, `draw_text`, `draw_image`, `measure_text`) for the UI layer.

Optionally provide a `render_compositor(compositor, window_width, window_height)` convenience method mirroring `NullRenderer`.

### 8.8 Wiring a new backend into the VisualEngine (eager-runtime → eager-graphics)

1. Add a `_BACKEND_*` constant and a branch in `VisualEngine._create_renderer()`.
2. Add CLI support in `cli.py`'s `_run_interactive_player()` if the backend has a player class.
3. The player class must implement: `advance_story()`, `make_choice(idx)`, `on_draw()`, `active_choice_prompt`, `is_finished`, `close()`.

### 8.9 Adding a new UI screen or widget (eager-graphics)

1. Subclass `Screen` in `packages/eager-graphics/src/eager_graphics/screens/` (e.g.
   `screens/my_screen.py`); implement `on_enter(session)` (build `self.buttons`),
   `draw(backend, w, h)`, and optional `handle_input(session, action, pressed)`.
2. Re-export it from `screens/__init__.py` and register it on the `ScreenManager`
   in `GameSession.__init__` (`self.screens`).
3. Route to it from a hook handler in `director.py` or an `InputAction` in
   `session.handle_input` (e.g. `GAME_MENU` → `session.screens.show("my_screen", session)`).
4. Widgets go in `screens/widgets.py` implementing `hit_test` + `draw(backend, ...)`
   over `UIDrawBackend`; theme colors/fonts come from `Theme` on the owning `Screen`.
5. Test layout/hit-testing with `NullRenderer` in `tests/test_screens.py`.

### 8.10 Adding a new package to the workspace

1. Create `packages/<name>/` with its own `pyproject.toml` (`name = "<name>"`,
   `version = "0.1.0"`, `requires-python = ">=3.11"`).
2. Add the package's source under `packages/<name>/src/<import_name>/` and its
   tests under `packages/<name>/tests/`.
3. Register the package path in the root `pyproject.toml`'s
   `[tool.uv.workspace].members` list (it may already be covered by the
   `packages/*` glob — verify).
4. Run `uv sync` from the repo root to materialize the new member in `.venv/`.
5. Add a row to §2's Directory Map and Package Summary; add rows to §3, §5, §7,
   and §10 as applicable.
6. If the new package should be optional to `eager-runtime`, add it as an extra
   in `packages/eager-runtime/pyproject.toml` and lazy-export from
   `eager_runtime/__init__.py`.

---

## 9. Search Cookbook

```bash
# ── eager-script ──────────────────────────────────────────────────────────
# Find all AST node class definitions
rg "^class Parsed" packages/eager-script/src/eager_script/

# Find where a DSL keyword is dispatched in the parser
rg "_parse_prefixed|ParsedJump|ParsedCall|ParsedReturn|ParsedHook" packages/eager-script/src/eager_script/__init__.py

# Find all SceneGraph query methods
rg "def (successors|predecessors|reachable|dead_ends|hubs|branching)" packages/eager-script/src/eager_script/graph.py

# Find validation checks
rg "def validate|Undefined Target|Duplicate Label|Cyclical" packages/eager-script/src/eager_script/validator.py

# ── eager-runtime ────────────────────────────────────────────────────────
# Find where a StoryEvent type is defined
rg "^class .*Event" packages/eager-runtime/src/eager_runtime/events.py

# Find all hooks registered in the dispatcher
rg "on_hook\(" packages/eager-runtime/src/eager_runtime/

# Find all VM step logic branches
rg "isinstance\(item," packages/eager-runtime/src/eager_runtime/runtime.py

# Find CLI subcommands
rg "add_parser\(" packages/eager-runtime/src/eager_runtime/cli.py

# Find where a GameSession method is defined
rg "def (advance|handle_input|submit_input|rollback|save_slot|load_save_slot|draw|run_headless)" packages/eager-runtime/src/eager_runtime/session.py

# Find the script-logic expression evaluator & whitelist
rg "def (compile_expr|_eval_|visit|ALLOWED_FUNCS|_EVAL)" packages/eager-script/src/eager_script/expr.py

# Find InputAction / Keymap definitions
rg "class InputAction|DEFAULT_BINDINGS|def from_key" packages/eager-runtime/src/eager_runtime/input.py

# Find SaveManager / PersistentData / Preferences
rg "^class (SaveManager|SaveData|SaveMetadata|PersistentData|Preferences)" packages/eager-runtime/src/eager_runtime/

# ── eager-graphics ───────────────────────────────────────────────────────
# Find where a method is defined
rg "def set_background" packages/eager-graphics/src/

# Find all references to a class across src + tests
rg "StageCompositor" packages/eager-graphics/src/ packages/eager-graphics/tests/

# Search hook names registered in the director
rg 'on_hook\(' packages/eager-graphics/src/eager_graphics/director.py

# Find all public class definitions across the package
rg "^class " packages/eager-graphics/src/eager_graphics/

# Check optional dependency guards
rg "try:" packages/eager-graphics/src/eager_graphics/__init__.py

# Find UIDrawBackend / RenderBackend implementations (stage vs UI protocols)
rg "class.*UIDrawBackend|class.*RenderBackend" packages/eager-graphics/src/

# List easing functions / EASING_MAP entries
rg "EASING_MAP|^def ease" packages/eager-graphics/src/eager_graphics/easing.py

# Find director hook handlers and audio/NVL wiring
rg "def handle_(bg|bg_clear|scene|image|show|hide|move|expr|fade|flash|shake|play|stop|volume|nvl|generic)" packages/eager-graphics/src/eager_graphics/director.py

# Find screen / widget definitions
rg "^class |def (on_enter|draw|hit_test)" packages/eager-graphics/src/eager_graphics/screens/

# Find TextReveal / parse_text_tags entry points
rg "def (parse_text_tags|complete|update)" packages/eager-graphics/src/eager_graphics/text.py

# Check which test files exist (all packages)
rg --files packages/*/tests/ | rg '^tests/test_'

# Find all three packages' __init__ exports
rg "^from eager_(script|runtime|graphics)" packages/ -r /dev/null
```

---

## 10. Quick Reference: Import Names

> Copy-paste blocks. Each name is documented in §3 — this section exists so you
> don't have to scroll up. **`expr.py` is NOT re-exported at the package top
> level** (see §3.1 and §11) — import it from `eager_script.expr` explicitly.

### eager-script (`eager_script`)

```python
import eager_script

# AST node classes
from eager_script import (
    ParsedLabel, ParsedDialogue, ParsedAppend, ParsedFreshBox,
    ParsedNarration, ParsedChoiceOption, ParsedChoiceSet,
    ParsedJump, ParsedCall, ParsedReturn, ParsedHook,
    # script-logic nodes (Phases 1-2)
    ParsedDefault, ParsedSet, ParsedCharacter,
    ParsedIf, ParsedElif, ParsedElse, ParsedEnd,
    ParsedCondJump, ParsedLocalJump,
    ParsedItem, ParseError,
    ScreenplayParser, PlainScreenplayParser,
)

# Core functions
from eager_script import parse, parse_iter, to_dict, to_json, validate, slugify

# Screenplay hook-argument parser (moved here from eager-graphics)
from eager_script import HookArgs, parse_hook_args

# Graph & validator (lazy-imported from submodules)
from eager_script import SceneGraph, SceneNode, SceneEdge, to_graph, parse_graph
from eager_script import ValidationError, ValidationResult

# Safe expression evaluator — its OWN submodule (NOT re-exported at top level)
from eager_script.expr import compile_expr, CompiledExpr, ExprError
```

### eager-core (`eager_core`)

```python
# Shared, zero-dependency leaf subsystems
from eager_core import (
    AudioBackend,       # Protocol
    AudioMixer,         # channel mixer (music/ambient/sound/voice)
    ChannelState,
    NullAudioBackend,   # headless default
)
```

### eager-runtime (`eager_runtime`)

```python
import eager_runtime

# Headless runtime — always available (no graphics dependency)
from eager_runtime import (
    StoryVM, StoryRuntimeError,
    EventDispatcher,
    StorySnapshot, HistoryManager, CallFrame,
    SceneEnterEvent, DialogueEvent, AppendEvent, FreshBoxEvent,
    NarrationEvent, ChoiceOption, ChoicePromptEvent,
    HookEvent, SceneExitEvent, StoryEndEvent,
    InputPromptEvent,           # 10th event type
    StoryEvent,                 # TypeAlias union of all 10 event types
    TerminalPlayer,             # interactive terminal runner
    InputAction, Keymap,        # backend-neutral input mapping
)

# Session & persistence — lazy-imported (game-session layer)
from eager_runtime import (
    GameSession, Checkpoint, CheckpointHistory,
    SaveManager, SaveData, SaveMetadata,
    PersistentData, Preferences,
    Backlog, BacklogEntry,
)

# Visual façade — lazy-imported (requires eager_graphics installed)
from eager_runtime import VisualEngine, SaveSlot, StateCorruptionError
```

### eager-graphics (`eager_graphics`)

```python
from eager_graphics import (
    StageCompositor,          # core orchestrator
    StageDirector, CharacterConfig,  # narrative bridge
    Stage,                    # visual hierarchy
    LayoutResolver, ViewportTransform,
    Timeline, Tween,
    FrameClock,
    RenderItem, RenderBackend, UIDrawBackend,
    Vec2, Color, Rect, Anchor, ScaleMode, TransitionKind,
    BLACK, BLUE, GREEN, RED, TRANSPARENT, WHITE,
    UIState, ChoiceOption,
    UIOverlay, DialogueBox, ChoiceMenu, EndNotice,
    TextboxStyle, ChoiceMenuStyle,
    get_easing, EasingFunc, linear, ease_in_out_quad,
    TextReveal, FormattedText, parse_text_tags, TextSegment, PausePoint,
    VisualHistoryManager,
    # always available:
    NullRenderer,
)

# NOT top-level — import from the defining submodule:
# from eager_graphics.ui_components import wrap_text
```

```
# Optional — only if a backend library is installed:
# PygletRenderer, PygletPlayer, PygletAssetResolver (requires pyglet)
# PILRenderer, PILPlayer, PILAssetResolver  (requires Pillow)
# RaylibRenderer, RaylibPlayer, RaylibAssetResolver  (requires pyray)

# Screens & widgets (Phase 8) — import from the screens subpackage:
# from eager_graphics.screens import (
#     Screen, ScreenManager, Theme, Button, Label, Slider,
#     TitleScreen, SaveLoadScreen,
# )
```

---

## 11. Gotchas & Tips

- **`eager-runtime` works headless** without `eager-graphics`. The graphics-dependent
  modules (`engine.py` → `VisualEngine`/`SaveSlot`/`StateCorruptionError`,
  `session.py` → `GameSession` + screens/audio) are **lazy-imported** via
  `__getattr__` (see `_LAZY_EXPORTS`), so a bare `import eager_runtime` gives you
  the VM, dispatcher, events, state, `InputAction`/`Keymap`, and terminal player
  with zero graphics import cost. `VisualEngine` still exists as a
  backward-compatible façade that wraps a `GameSession`.
- **`eager-script` and `eager-core` have zero runtime dependencies.** Everything
  else is optional (`blessed` for the editor, `pytest`/`ruff` for dev). Audio
  (`AudioMixer`) lives in `eager-core`, a shared leaf depended on by both
  `eager-runtime` and `eager-graphics`; screenplay hook-argument parsing
  (`parse_hook_args`/`HookArgs`) lives in `eager-script`.
- **The `eager-x` CLI** (`eager_runtime.cli:main_x`) is the entry point for
  visual-novel commands. It calls `_ensure_graphics()` before constructing
  `VisualEngine`, producing a helpful error message if `eager_graphics` isn't
  installed.
- **`StageDirector.bind(dispatcher)` is the integration point** — it registers
  the `~ hook` handlers on an `EventDispatcher` and wires up a wildcard
  `on_any_event` listener that translates narrative events into UI state
  updates, compositor actions (e.g. emotion auto-sync from
  `DialogueEvent.emotion`), audio (`HookEvent("play"/"stop"/"volume")`), and
  NVL buffer management. `bind()` itself does **not** snapshot — the session
  drives `snapshot_visual_state()` / `on_beat_step()` explicitly.
- **`sys.intern`** is used pervasively in `eager-script` for string
  identifiers — scene names, speaker names, emotion tags, hook names. This
  means identity comparisons (`is`) can be used in some contexts, and memory
  usage for large scripts is minimized.
- **`StorySnapshot` and `RenderItem` are both frozen + slots** — they are
  value objects designed for efficient serialization and comparison.
  `StorySnapshot` now also carries `pending_choice_beat`, `next_transition_target`,
  `just_entered_scene`, `is_ended`, and `rng_state` so rollback/restore is fully
  deterministic; pending choices are re-materialized on load. Saving bundles
  story (VM snapshot) + visual (director state) + persistent + preferences into
  one atomic `SaveSlot` / `SaveData`, with `SaveManager.load` rolling back to a
  safety snapshot on corruption (raising `StateCorruptionError`).
- **`GameSession` is the central controller** for interactive play — it owns
  the VM, dispatcher, compositor, director, `AudioMixer`, backlog, screen
  manager, preferences, `PersistentData`, `SaveManager`, `Keymap`, and
  `UIOverlay`. Drive it with `advance()` (runs to the next interaction) +
  `handle_input(action)`; restore with `rollback()`. `VisualEngine` delegates to
  the same session methods for backward compatibility.
- **Project config & input**: `eager-x run`/`new`/`build` use `ProjectConfig`
  (from `game.toml [game]` + `[window]` + `[theme]`, merged via
  `project.merge_graphs`). Input is backend-neutral through `InputAction` /
  `Keymap.DEFAULT_BINDINGS` (Ren'Py-style: `K_RETURN`, `K_SPACE`, `K_ESCAPE`,
  `choice_accept`/`choice_decline`, `window_toggle`, etc.).
- **`expr.py` is its own module** — do NOT `from eager_script import compile_expr`.
  Use `from eager_script.expr import compile_expr, CompiledExpr, ExprError`. It
  is the only `builtins`/`eval`-free evaluator, gated behind a strict whitelist
  (no attribute access, no lambdas, no comprehensions); functions available in
  expressions: `visited`, `seen`, `random`, `chance`, `min`, `max`, `abs`,
  `len`, `int`, `str`, `round`.
- **This file has a growth budget.** If a section starts exceeding ~50 lines or
  restating §3, move the detail into the relevant package's `docs/` and leave a
  short pointer here. The cheat sheet should remain skimmable in one sitting.

---

## 12. Subagent / Main Agent Workflow

This monorepo is maintained by a **main agent** that offloads bounded,
self-contained work to **subagents** using the `pool` CLI. The two tiers share
the same workspace, virtual environment (`../.venv` relative to the package
directory), and file system, so every subagent must follow the same
conventions laid out in this document.

### 12.1 Spawning a subagent

- The main agent spawns a subagent by running:
  ```
  pool exec --unsafe-auto-allow -p "PUT YOUR PROMPT HERE"
  ```
- **The main agent MUST explicitly tell the subagent that it is a subagent.**
  The assignment prompt must begin with a clear statement to that effect, for
  example: *"You are a subagent working under the main agent. Your task is …"*
  followed by complete, standalone instructions (relevant paths, expected
  outputs, and any constraints). A subagent that does not know it is a
  subagent cannot follow the wrapping-up protocol in §12.3.

### 12.2 Exploration protocol (main agent & subagents)

- When you need to locate the exact files and content relevant to a task, use
  `pool exec --unsafe-auto-allow -p "PUT YOUR PROMPT HERE"`.
- Read **only** the files that the tool identifies as relevant. Avoid reading
  extraneous files — this wastes time and context. Combine commands when
  possible, inspect signatures before writing scripts, and print only summary
  metrics.

### 12.3 Wrapping-up protocol (subagents only)

After finishing the assigned task, a subagent MUST follow this protocol before
returning control to the main agent:

1. **Check git changes** — run `git diff --stat` (and `git status`) to survey
   which files were added, modified, or deleted.
2. **Understand the changes** — review the diff and form a clear summary of
   what was implemented or changed and why.
3. **Update AGENTS.md as necessary** — if the changes alter the directory
   structure, rename/remove/reorganize modules, add or remove public exports,
   change test counts, or otherwise make any content in this document outdated,
   update the affected sections (e.g. §2 Directory Map, §3 Source Layout,
   §5 testing, §7 docs, §10 import names). If there is nothing to
   update, explicitly note that.
4. **Return to the main agent** — summarize, in a concise report, what the task
   was, what changes were made, which files were touched, and whether
   AGENTS.md was updated. Do not continue working after handing back control.

### 12.4 Failure protocol (subagents only)

If the task cannot be completed as specified, the subagent MUST NOT silently
return partial work as if it were done. Instead:

1. **Stop making changes** once it's clear the task cannot be completed.
2. **Leave the tree in a buildable state** — do not commit half-finished edits
   that break tests. If an in-progress change is irreversible, either complete
   it or revert it (`git checkout -- <path>`); do not leave the repo broken.
3. **Do not commit.** Subagents never `git commit`; the main agent reviews and
   commits.
4. **Report the failure clearly** using the §12.3 summary format, plus:
   - what was attempted,
   - the specific blocker (missing file, failing dependency, ambiguous spec),
   - what state the working tree is in (clean / dirty / reverted),
   - a suggested next step for the main agent.
5. **Return control.** Do not retry indefinitely or substitute a different task.

If the subagent succeeded but with caveats (e.g. tests pass for the new path
but an adjacent pre-existing failure was observed), report those caveats in the
§12.3 summary rather than silently ignoring them.