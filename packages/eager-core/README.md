# Eager-Core

Shared, dependency-free subsystems for the Eager narrative engine.

`eager-core` sits at the bottom of the Eager dependency DAG alongside `eager-script`. It hosts cross-cutting leaf subsystems consumed by higher layers (`eager-runtime` and `eager-graphics`) with zero external runtime dependencies (standard library only).

---

## Direct Submodule Import Convention

To maintain clean module boundaries and avoid circular import chains, **primitives must be imported directly from their respective submodules**:

```python
# Correct: Direct submodule imports
from eager_core.types import Vec2, Color
from eager_core.events import DialogueEvent, ChoicePromptEvent, ChoiceOption
from eager_core.exceptions import EagerCoreError, AudioError, ColorParseError
from eager_core.text import parse_text_tags, TextReveal
from eager_core.audio import AudioMixer, NullAudioBackend

# Prohibited: Root re-export shims
from eager_core import Vec2, Color  # Avoid root imports
```

---

## Subsystems

### 1. Domain Exceptions (`eager_core.exceptions`)
Hierarchical, informative domain exceptions with backward-compatible multiple inheritance:
- `EagerCoreError(Exception)` — Base class for all core domain exceptions. Accepts arbitrary keyword arguments stored as attributes on the instance for rich forensic diagnostics.
- `AudioError(EagerCoreError, ValueError)` — Audio decoding, playback, channel, or path traversal failures.
- `ColorParseError(EagerCoreError, ValueError)` — Invalid hex color string syntax or boundary violations.
- `StorageError(EagerCoreError, OSError)` — Filesystem persistence, atomic write, or serialization errors.
- `I18nError(EagerCoreError, ValueError)` — Translation catalog schema, missing mapping, or invalid locale errors.

### 2. Audio Mixing (`eager_core.audio`)
- `AudioBackend` — Protocol for low-level audio playback (`play`, `stop`, `set_volume`, `pause`, `resume`, `is_playing`, `update`, `shutdown`).
- `BaseAudioBackend` — Abstract base providing no-op default implementations.
- `NullAudioBackend` — Headless no-op backend recording calls and loop points for testing.
- `ChannelState` — Per-channel volume, looping, loop points (`loop_start`, `loop_end`), and fade state.
- `AudioMixer` — Multi-channel routing (`music`, `ambient`, `sound`, `voice`, custom), loop points forwarding, volume hierarchy, fade interpolation ramps, path traversal security checks, and state serialization.

### 3. Core Types & Geometry (`eager_core.types`)
- `Vec2` — Immutable 2D vector with vector arithmetic (`+`, `-`, `*`), `lerp`, scalar division with zero-division protection, and boundary validation. Returns `NotImplemented` on incompatible types to preserve Python standard operator semantics.
- `Rect` — Axis-aligned 2D rectangle with bounds, center, `contains`, and `intersects` methods.
- `Color` — Immutable RGBA float color with hex parsing (`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`), `lerp`, clamping, and byte conversions. Raises `ColorParseError` on invalid hex syntax.

### 4. Easing Curves (`eager_core.easing`)
- Parametric easing functions: `linear`, quadratic, cubic, quartic, sine, exponential, back (overshoot), and bounce (in, out, and in-out variants).
- `get_easing(name_or_func)` lookup and normalization.

### 5. Frame Timing & Clock (`eager_core.timing`)
- `FrameClock` — Wall-clock delta-time (`dt`) measurement, instantaneous FPS, rolling average FPS, and elapsed time tracking.

### 6. Input Abstractions (`eager_core.input`)
- `InputAction` — 29 backend-neutral semantic actions (`ADVANCE`, `ROLLBACK`, `CHOOSE`, `GAME_MENU`, `SKIP_TOGGLE`, `SCREENSHOT`, etc.).
- `Keymap` — Configurable mapping of normalized key names to semantic actions.

### 7. Filesystem Storage Helpers (`eager_core.storage`)
- `get_default_save_dir(game_name)` — Standard XDG / OS app data path resolution.
- `atomic_write_json(path, data)` — Crash-safe temporary file swap wrapping I/O errors in `StorageError`.
- `safe_read_json(path, default=None, *, backup_corrupt=False)` — Fault-tolerant JSON reader. When `backup_corrupt=True`, automatically backs up corrupted files to `<filename>.corrupt.bak`.

### 8. Narrative Events & Branching (`eager_core.events`)
- `ChoiceOption` — Canonical dataclass for narrative choice options (`index`, `text`, `target`, `condition`).
- `StoryEvent` union & event dataclasses: `SceneEnterEvent`, `DialogueEvent`, `AppendEvent`, `FreshBoxEvent`, `NarrationEvent`, `ChoicePromptEvent`, `HookEvent`, `SceneExitEvent`, `StoryEndEvent`, `InputPromptEvent`.

### 9. Protocols & Architectural Decoupling (`eager_core.protocols`)
- Structural protocols decoupling presentation, audio, UI, and storage from the headless runtime: `StageProtocol`, `UIProtocol`, `ScreenManagerProtocol`, `AudioBackendProtocol`, `UIDrawBackendProtocol`, `ThemeFactory`.

### 10. Rich Text Formatting & Typewriter Pacing (`eager_core.text`)
- Inline tag parser supporting `{b}`, `{i}`, `{color=#hex}`, `{size=N}`, `{w=0.5}`, `{p}`, and `{fast}`:
  - `{fast}`: Designates instant reveal for preceding text. Text before `{fast}` appears immediately without typewriter animation, while text following `{fast}` types out normally.
- `FormattedText` — Container for stripped plain text, style segments, pause points, and `fast_index: int`.
- `TextReveal` — Typewriter pacing controller with pause timers, instant skip, and automatic initialization to `fast_index`.

---

## Installation

```bash
pip install eager-core
```

---

## Usage Example

```python
from eager_core.types import Vec2, Color
from eager_core.text import parse_text_tags, TextReveal
from eager_core.timing import FrameClock
from eager_core.storage import safe_read_json, atomic_write_json
from eager_core.exceptions import ColorParseError

# Geometry & Color
pos = Vec2(100.0, 200.0)
try:
    tint = Color.from_hex("#ff9900")
except ColorParseError as err:
    print(f"Invalid color: {err}")

# Rich text markup with instant pacing prefix
formatted = parse_text_tags("Previously seen dialogue.{fast} New typewriter text!{w=0.5}")
print(f"Fast reveal index: {formatted.fast_index}")

# Typewriter controller
reveal = TextReveal(formatted, chars_per_second=30.0)
print(f"Initial visible characters: {reveal.visible_chars}")

# Frame timing
clock = FrameClock()
dt = clock.tick()
reveal.update(dt)
```

---

## License

MIT
