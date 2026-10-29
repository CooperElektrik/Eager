# API Reference

Eager's API is modularly organized into five packages. Each package's public symbols are documented using [mkdocstrings](https://mkdocstrings.github.io/), reflecting the source docstrings directly to ensure accurate, up-to-date documentation.

## Packages

| Package | Import Root | Description |
|---------|-------------|-------------|
| [**eager-core**](eager-core/index.md) | `eager_core` | Leaf foundation: types, events, audio, text pacing, timing, easing, input, storage, i18n, protocols, exceptions. |
| [**eager-script**](eager-script/index.md) | `eager_script` | Zero-dependency screenplay DSL parser: tokenization, AST, expression compiler, scene graph, hooks, and validator. |
| [**eager-runtime**](eager-runtime/index.md) | `eager_runtime` | Headless story virtual machine, session controller, event dispatcher, save manager, and terminal player. |
| [**eager-graphics**](eager-graphics/index.md) | `eager_graphics` | Presentation layer: compositor, stage layers, timeline, screens, and renderers (Null, PIL, Pyglet, Miniaudio). |
| [**eager-script-lsp**](eager-script-lsp/index.md) | `eager_script_lsp` | Language Server Protocol (LSP 3.17+) server: autocompletion, diagnostics, hover, navigation, and CLI diagnostics. |

## Import Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
# eager-core
from eager_core.types import Vec2, Color
from eager_core.events import DialogueEvent, ChoicePromptEvent

# eager-script
from eager_script.expr import compile_expr
from eager_script import parse_hook_args

# eager-runtime
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession

# eager-graphics
from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector

# eager-script-lsp
from eager_script_lsp.server import EagerLanguageServer
```
