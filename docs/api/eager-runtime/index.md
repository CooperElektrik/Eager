# eager-runtime

Lightweight, headless narrative runtime, story virtual machine, and session controller for Eager-Script screenplays. Completely headless: zero GUI or graphics dependencies.

## Architecture & Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.saves import SaveManager
from eager_runtime.persistent import PersistentData
```

## Modules

| Module | Description |
|--------|-------------|
| [runtime](runtime.md) | Story virtual machine (`StoryVM`), instruction pointer, step execution, and call frames. |
| [session](session.md) | High-level session controller (`GameSession`), life-cycle state, choices, and rollback. |
| [dispatcher](dispatcher.md) | Event dispatcher (`EventDispatcher`), hook routing, and execution loop (`run_until_pause`). |
| [saves](saves.md) | Save manager (`SaveManager`), atomic checkpointing, save slots, and state serialization. |
| [state](state.md) | Runtime execution state (`RuntimeState`), variable scoping, and call stack. |
| [persistent](persistent.md) | Cross-session persistent data (`PersistentData`) for global unlocks and seen flags. |
| [preferences](preferences.md) | User preferences (`Preferences`) for audio volume, text speed, and auto-forwarding. |
| [headless](headless.md) | Headless runner (`HeadlessRunner`) for automated playthroughs, scripting, and CI tests. |
| [assets](assets.md) | Asset resolution (`AssetResolver`) and directory-based resource management. |
| [backlog](backlog.md) | Dialogue history backlog (`DialogueBacklog`) and rewind state tracking. |
| [player](player.md) | Interactive terminal player (`TerminalPlayer`) for text-only CLI play. |
| [project](project.md) | Project manifest loader (`Project`) and multi-file screenplay graph construction. |
| [watcher](watcher.md) | File watcher (`ProjectWatcher`) for hot reloading screenplay changes during development. |
| [i18n](i18n.md) | Runtime internationalization and localization manager. |
| [cli](cli.md) | Command-line interface for executing and inspecting narrative sessions. |
