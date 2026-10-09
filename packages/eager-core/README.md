# Eager-Core

Shared, dependency-free subsystems for the Eager narrative engine.

`eager-core` sits at the bottom of the Eager dependency DAG alongside
`eager-script`. It hosts cross-cutting leaf subsystems consumed by more
than one higher layer (`eager-runtime` and `eager-graphics`) with zero external
dependencies (standard library only).

## Subsystems

1. **Audio Mixing** (`eager_core.audio`):
   - `AudioBackend` — protocol for low-level playback (`play`, `stop`, `set_volume`, `pause`, `resume`, `is_playing`).
   - `NullAudioBackend` — headless no-op backend recording calls.
   - `ChannelState` — per-channel volume, looping, and fade state.
   - `AudioMixer` — channel routing (`music`, `ambient`, `sound`, `voice`, custom), volume hierarchy, fade interpolation ramps, and state serialization.

2. **Core Types & Geometry** (`eager_core.types`):
   - `Vec2` — immutable 2D vector with arithmetic, distance, and `lerp`.
   - `Rect` — axis-aligned 2D rectangle with bounds, center, `contains`, and intersection tests.
   - `Color` — immutable RGBA float color with hex parsing (`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`), `lerp`, clamping, and byte conversions.

3. **Easing Curves** (`eager_core.easing`):
   - Easing functions: `linear`, quadratic, cubic, quartic, sine, exponential, back (overshoot), and bounce.
   - `get_easing(name_or_func)` lookup and normalization.

4. **Frame Timing & Clock** (`eager_core.timing`):
   - `FrameClock` — wall-clock delta-time (`dt`) measurement, instantaneous FPS, rolling average FPS, and elapsed time tracking.

5. **Input Abstractions** (`eager_core.input`):
   - `InputAction` — 21 backend-neutral semantic actions (`ADVANCE`, `ROLLBACK`, `CHOOSE`, `GAME_MENU`, `SKIP_TOGGLE`, etc.).
   - `Keymap` — configurable mapping of normalized key names to semantic actions.

6. **Filesystem Storage Helpers** (`eager_core.storage`):
   - `get_default_save_dir(game_name)` — standard XDG / OS app data path resolution.
   - `atomic_write_json(path, data)` — crash-safe temporary file swap.
   - `safe_read_json(path, default)` — fault-tolerant JSON reader.

7. **Narrative Events & Branching** (`eager_core.events`):
   - `ChoiceOption` — discrete option for branching dialogue prompts.
   - `StoryEvent` union & event dataclasses: `SceneEnterEvent`, `DialogueEvent`, `AppendEvent`, `FreshBoxEvent`, `NarrationEvent`, `ChoicePromptEvent`, `HookEvent`, `SceneExitEvent`, `StoryEndEvent`, `InputPromptEvent`.

8. **Rich Text Formatting & Pacing** (`eager_core.text`):
   - `parse_text_tags(raw)` — parse inline markup tags (`{b}`, `{i}`, `{color=#hex}`, `{size=N}`, `{w=0.5}`, `{p}`, `{fast}`).
   - `TextSegment`, `PausePoint`, `FormattedText`.
   - `TextReveal` — typewriter text pacing controller with pause timers and instant skip.

## Installation

```bash
pip install eager-core
```

## Usage

```python
from eager_core import (
    AudioMixer,
    Color,
    FrameClock,
    InputAction,
    Vec2,
    parse_text_tags,
)

# Geometry & Color
pos = Vec2(100.0, 200.0)
tint = Color.from_hex("#ff9900")

# Text markup parsing
formatted = parse_text_tags("Hello {b}world{/b}!{w=0.5}")

# Frame timing
clock = FrameClock()
dt = clock.tick()
```

## License

MIT
