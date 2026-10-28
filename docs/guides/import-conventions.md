# Import Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims do not exist and are forbidden.

## Correct: direct submodule imports

```python
# eager-core
from eager_core.events import DialogueEvent, ChoicePromptEvent, ChoiceOption
from eager_core.types import Color, Vec2
from eager_core.audio import AudioMixer, NullAudioBackend
from eager_core.text import parse_text_tags, TextReveal

# eager-script
from eager_script.expr import compile_expr
from eager_script import parse_hook_args

# eager-runtime
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.saves import SaveManager

# eager-graphics
from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector

# Avoid: non-existent shims or missing root exports
from eager_runtime.events import DialogueEvent       # Fails: no shim in runtime
from eager_script import evaluate_expression         # Fails: no such function
```
