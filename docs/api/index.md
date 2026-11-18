# API Reference

Eager's API is organized into two packages: **`eager`** (the unified visual novel engine) and **`eager-script-lsp`** (the Language Server Protocol tooling). Public symbols are documented using [mkdocstrings](https://mkdocstrings.github.io/).

## Packages

| Package | Import Root | Description |
|---------|-------------|-------------|
| [**eager**](eager/index.md) | `eager` | Unified engine: `eager.core`, `eager.script`, `eager.vm`, `eager.stage`, `eager.ui`, `eager.session`, `eager.backends`, and `eager.cli`. |
| [**eager-script-lsp**](eager-script-lsp/index.md) | `eager_script_lsp` | Language Server Protocol (LSP 3.17+) server: autocompletion, diagnostics, hover, navigation, and CLI diagnostics. |

## Import Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
# eager.core
from eager.core.types import Vec2, Color
from eager.core.events import DialogueEvent, ChoicePromptEvent

# eager.script
from eager.script.expr import compile_expr
from eager.script import parse_hook_args

# eager.vm & eager.session
from eager.vm.runtime import StoryVM
from eager.session import GameSession

# eager.stage & eager.ui
from eager.stage.compositor import StageCompositor
from eager.stage.director import StageDirector
from eager.ui.player import BasePlayer

# eager-script-lsp
from eager_script_lsp.server import EagerLanguageServer
```
