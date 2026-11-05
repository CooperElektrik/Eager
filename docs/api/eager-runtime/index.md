# eager-runtime

Lightweight, headless narrative runtime, story virtual machine, and session controller for Eager-Script screenplays. Completely headless: zero GUI or graphics dependencies.

## Architecture & Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_core.dispatcher import EventDispatcher
from eager_core.saves import SaveManager
from eager_core.persistent import PersistentData
```

## Modules

| Module | Description |
|--------|-------------|
| [runtime](runtime.md) | Story virtual machine (`StoryVM`), instruction pointer, step execution, and call frames. |
| [session](session.md) | High-level session controller (`GameSession`), life-cycle state, choices, and rollback. |
| [assets](assets.md) | Asset resolution (`AssetResolver`) and directory-based resource management. |
| [player](player.md) | Interactive terminal player (`TerminalPlayer`) for text-only CLI play. |
| [project](project.md) | Project manifest loader (`ProjectConfig`) and multi-file screenplay graph construction. |
| [i18n](i18n.md) | Runtime internationalization and localization manager. |
| [cli](cli.md) | Command-line interface for executing and inspecting narrative sessions. |
