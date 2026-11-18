# Import Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims do not exist and are forbidden.

## Correct: direct submodule imports

```python
# eager.core
from eager.core.events import DialogueEvent, ChoicePromptEvent, ChoiceOption
from eager.core.types import Color, Vec2
from eager.core.audio import AudioMixer, NullAudioBackend
from eager.core.text import parse_text_tags, TextReveal
from eager.core.dispatcher import EventDispatcher
from eager.core.saves import SaveManager

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

# Avoid: legacy package names
from eager_core.events import DialogueEvent       # Fails: removed in 0.9+
from eager_runtime.session import GameSession     # Fails: removed in 0.9+
```
