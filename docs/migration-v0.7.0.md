# Eager v0.7.0 Upgrade & Migration Guide

This guide details all architectural updates, interface migrations, breaking changes, and operational enhancements introduced in the Eager v0.7.0 release.

---

## Executive Summary of Changes

| Area | Prior Pattern (v0.x) | v1.0.0 Standard | Impact |
|---|---|---|---|
| **Core Imports** | `from eager_core import Vec2, Color` | `from eager_core.types import Vec2, Color` | Mandatory direct submodule imports |
| **Exceptions** | Generic `ValueError`, `OSError` | `from eager_core.exceptions import EagerCoreError, ...` | Structured domain exceptions (backward compatible) |
| **Expressions** | `evaluate_safe_expression(ast, env)` | `from eager_script.expr import compile_expr; expr.evaluate(env)` | Expression AST compilation and error wrapping |
| **Choice Option** | `from eager_graphics.ui_state import ChoiceOption` | `from eager_core.events import ChoiceOption` | Disambiguated canonical import |
| **Corrupt Saves** | Uncaught exceptions or silent loss | `.corrupt.bak` forensic backup creation; returns `None` | Automated recovery and disk protection |
| **Pyglet Extra** | `pip install eager-graphics[pyglet]` | `pip install 'eager-graphics[hardware]'` | Corrected packaging extra specification |
| **Text Reveal** | Manual offset calculation | `{fast}` tag with `FormattedText.fast_index` | Built-in instant typewriter skip marker |

---

## 1. Direct Submodule Imports

### The Change
To enforce strict architectural boundaries, eliminate circular import hazards, and support efficient lazy loading, package root re-export shims have been sealed. All primitives and utilities must now be imported directly from their defining submodules.

### Migration Examples

#### Leaf Primitives (`eager-core`)
```python
# Legacy (Deprecated / Disallowed)
from eager_core import Vec2, Color, AudioMixer, FrameClock, InputAction, parse_text_tags

# v1.0.0 (Required)
from eager_core.types import Vec2, Color
from eager_core.audio import AudioMixer, NullAudioBackend
from eager_core.timing import FrameClock
from eager_core.input import InputAction, Keymap
from eager_core.text import parse_text_tags, TextReveal
from eager_core.events import DialogueEvent, ChoicePromptEvent, ChoiceOption
from eager_core.exceptions import EagerCoreError, AudioError, ColorParseError
```

#### Screenplay Script Tooling (`eager-script`)
```python
# Legacy
from eager_script import evaluate_expression

# v1.0.0
from eager_script import parse, parse_iter, parse_graph, to_graph, validate, ScreenplayParser
from eager_script.expr import compile_expr, CompiledExpr, ExprError
from eager_script.hooks import parse_hook_args, is_input_hook, parse_input_args
```

#### Runtime Subsystems (`eager-runtime`)
```python
# Legacy
from eager_runtime import StoryVM, GameSession, DialogueEvent  # DialogueEvent moved to eager-core

# v1.0.0
from eager_runtime.runtime import StoryVM
from eager_runtime.session import GameSession
from eager_runtime.dispatcher import EventDispatcher
from eager_runtime.saves import SaveManager
from eager_core.events import DialogueEvent, ChoicePromptEvent, InputPromptEvent
```

#### Graphics & UI Components (`eager-graphics`)
```python
# Legacy
from eager_graphics.ui_state import ChoiceOption  # Spurious re-export removed

# v1.0.0
from eager_core.events import ChoiceOption
from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector, CharacterConfig
from eager_graphics.renderers.pyglet import PygletRenderer, PygletPlayer
from eager_graphics.renderers.pil.renderer import PILRenderer
```

---

## 2. Domain Exception Hierarchy (`eager_core.exceptions`)

### The Change
Eager v1.0.0 introduces a centralized domain exception hierarchy rooted at `EagerCoreError`. To guarantee backward compatibility with existing codebases, domain exceptions inherit from both `EagerCoreError` and standard library exception classes.

```text
Exception
 └── EagerCoreError
      ├── AudioError (also inherits ValueError)
      ├── ColorParseError (also inherits ValueError)
      ├── StorageError (also inherits OSError)
      └── I18nError (also inherits ValueError)
```

### Forensic Context Attributes
`EagerCoreError` accepts arbitrary keyword arguments that are attached to the exception instance:

```python
from eager_core.exceptions import AudioError

try:
    mixer.play("music", "unauthorized/../../escape.ogg")
except AudioError as err:
    print(f"Failed audio path: {err.path}")
    print(f"Error channel: {err.channel}")
```

### Updating Existing Catch Blocks
Existing `except (ValueError, OSError):` handlers will continue to catch these exceptions without code changes. However, it is recommended to migrate to explicit domain catches:

```python
# Recommended v1.0.0 pattern
from eager_core.exceptions import EagerCoreError, AudioError, ColorParseError, StorageError

try:
    color = Color.from_hex(user_hex)
    audio.play("sound", sound_asset)
except ColorParseError as err:
    logger.warning("Invalid theme color: %s", err)
except AudioError as err:
    logger.warning("Audio playback unavailable: %s", err)
except EagerCoreError as err:
    logger.error("Core engine fault: %s", err)
```

---

## 3. Expression Compilation Pattern

### The Change
Legacy helper functions such as `evaluate_safe_expression` or direct AST execution functions have been replaced by the `compile_expr` compiler pipeline.

### Migration Example

```python
# Legacy Pattern (Prohibited in v1.0.0)
from eager_script.expr import evaluate_safe_expression
result = evaluate_safe_expression(expr_ast, context)

# Also Prohibited (Security Violation)
result = eval(expr_string, {}, context)

# v1.0.0 Standard Pattern
from eager_script.expr import compile_expr, ExprError

try:
    expr = compile_expr("reputation >= 50 and not visited('dungeon')")
    result = expr.evaluate(context)
except ExprError as err:
    logger.error("Expression evaluation error: %s", err)
```

### Zero-Division & Arithmetic Error Wrapping
In v1.0.0, runtime arithmetic errors (such as `100 / 0` or invalid operand types) inside script expressions are automatically caught and wrapped in `ExprError` rather than crashing the virtual machine.

---

## 4. Disambiguation of `ChoiceOption`

### The Change
In v0.x, `ChoiceOption` was erroneously re-exported from `eager_graphics.ui_state`, leading to confusing import paths between the runtime event system and UI presentation widgets. In v1.0.0, `ChoiceOption` is defined exclusively in `eager_core.events`.

### Migration Example

```python
# Legacy
from eager_graphics.ui_state import ChoiceOption  # REMOVED

# v1.0.0
from eager_core.events import ChoiceOption
```

---

## 5. Save Management & Forensic Corruption Backups

### The Change
In v0.x, corrupted save files (such as truncated JSON, non-dictionary root payloads, or missing checkpoints) could raise unhandled `AttributeError` or `ValueError` inside `SaveManager.load_slot()` or during `SaveManager.list_slots()`.

In v1.0.0:
1. `SaveManager.load_slot(slot_name)` validates that the payload is a dictionary containing a valid checkpoint dictionary.
2. If the file is unreadable, invalid JSON, or structurally corrupt, `SaveManager` automatically copies the file to `<slot_name>.json.corrupt.bak` and returns `None`.
3. `SaveManager.list_slots()` and `SaveManager.get_slot_metadata()` catch corrupted metadata safely and skip corrupted slots, preventing inventory/menu crashes.

### Migration Example

```python
# v1.0.0 Recommended save loading pattern
from eager_runtime.saves import SaveManager

save_mgr = SaveManager(save_dir)

save_data = save_mgr.load_slot("slot_1")
if save_data is None:
    # A corrupt file was detected and backed up to slot_1.json.corrupt.bak
    display_toast("Save slot could not be read; backup preserved.")
else:
    session.restore_from_save(save_data)
```

---

## 6. Pyglet Packaging Extra Correction

### The Change
The documentation in previous versions occasionally referenced `pip install eager-graphics[pyglet]`. The canonical optional extra defined in `pyproject.toml` is `hardware`:

```bash
# Correct v1.0.0 hardware installation
pip install 'eager-graphics[hardware]'
```

---

## 7. Typewriter Text Pacing with `{fast}`

### The Change
To support visual novel typewriter effects where previously read dialogue lines or appends should appear immediately without re-triggering typewriter animations, v1.0.0 introduces the `{fast}` tag.

```python
from eager_core.text import parse_text_tags, TextReveal

# In screenplay scripts or UI strings:
script_line = "Previously read text.{fast} Newly revealed text!"

formatted = parse_text_tags(script_line)
# formatted.fast_index contains the character boundary offset

reveal = TextReveal(formatted, chars_per_second=30.0)
# reveal.visible_chars is initialized to fast_index immediately
```

---

## 8. Upgrade Verification Checklist

Before deploying applications or game distributions on Eager v1.0.0, verify the following:

- [ ] All imports from `eager_core` reference specific submodules (e.g., `eager_core.types`, `eager_core.events`).
- [ ] No occurrences of `from eager_graphics.ui_state import ChoiceOption` remain; updated to `eager_core.events`.
- [ ] Expression evaluation uses `compile_expr(expr).evaluate(context)`.
- [ ] Catch blocks handling engine errors catch `EagerCoreError` or specific domain subclasses (`AudioError`, etc.).
- [ ] Hardware rendering installs specify `'eager-graphics[hardware]'`.
- [ ] Save loading code safely handles `None` returns from `load_slot()`.
