# API Overview

Eager's API is organized into five packages. Each package's public symbols are documented below via [mkdocstrings](https://mkdocstrings.github.io/), which reads directly from the source docstrings. This keeps the reference in sync with the code.

## Package index

| Package | Description |
|---------|-------------|
| [eager-core](eager-core.md) | Core primitives: types, events, exceptions, audio, text, timing, input, storage. |
| [eager-script](eager-script.md) | Screenplay DSL parser, expression compiler, scene graph, hooks, validator. |
| [eager-runtime](eager-runtime.md) | Headless story VM, session controller, event dispatcher, save manager. |
| [eager-graphics](eager-graphics.md) | Stage compositor, UI components, render backends (Null, PIL, Pyglet). |
| [eager-script-lsp](eager-script-lsp.md) | Language Server Protocol server for `.es` screenplays. |

## Import convention

All primitives must be imported directly from their defining submodule:

```python
from eager_core.types import Vec2, Color
from eager_core.events import DialogueEvent, ChoicePromptEvent
from eager_script.expr import compile_expr
from eager_script import parse_hook_args
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_graphics.compositor import StageCompositor
```

Root re-export shims are strictly forbidden.
