# eager-core

Shared, dependency-free subsystems for the Eager narrative engine. `eager-core` sits at the bottom of the dependency DAG alongside `eager-script` with zero external runtime dependencies (standard library only).

## Architecture & Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
from eager_core.types import Vec2, Color, Rect
from eager_core.events import DialogueEvent, ChoicePromptEvent
from eager_core.audio import AudioMixer, Sound
from eager_core.text import parse_text_tags, TextReveal
```

## Modules

| Module | Description |
|--------|-------------|
| [types](types.md) | Fundamental geometry primitives (`Vec2`, `Rect`, `Size`), colors (`Color`), and enums. |
| [events](events.md) | Narrative and presentation event dataclasses (`DialogueEvent`, `ChoicePromptEvent`, etc.). |
| [audio](audio.md) | Audio mixing, channel management, volume attenuation, and playback protocols. |
| [text](text.md) | Text formatting, tag parsing (`{fast}`, `{w=0.5}`), and character pacing/reveal timing. |
| [timing](timing.md) | Delta timing, clocks, and frame step tracking. |
| [easing](easing.md) | Mathematical interpolation curves and easing functions (linear, ease-in, cubic, etc.). |
| [input](input.md) | Semantic input actions, keycodes, and input events. |
| [storage](storage.md) | Abstract storage backends and file/memory persistence providers. |
| [i18n](i18n.md) | Internationalization, translation catalogs, and string localization. |
| [protocols](protocols.md) | Core protocols for renderers, audio backends, and engine lifecycles. |
| [exceptions](exceptions.md) | Base exception hierarchy for all Eager subsystems. |
| [dispatcher](dispatcher.md) | Event dispatcher (`EventDispatcher`), hook routing, and execution loop (`run_until_pause`). |
| [saves](saves.md) | Save manager (`SaveManager`), atomic checkpointing, save slots, and state serialization. |
| [state](state.md) | Runtime execution state, checkpoints, and call frames. |
| [persistent](persistent.md) | Cross-session persistent data (`PersistentData`) for global unlocks and seen flags. |
| [preferences](preferences.md) | User preferences (`Preferences`) for audio volume, text speed, and auto-forwarding. |
| [headless](headless.md) | Headless runner stubs and mocks for automated playthroughs, scripting, and CI tests. |
| [backlog](backlog.md) | Dialogue history backlog (`Backlog`) and rewind state tracking. |
| [layout](layout.md) | Virtual coordinate layout system, relative positioning, and anchor alignment. |
| [timeline](timeline.md) | Animation timeline, tweens, keyframes, and camera shake effects. |
| [theme](theme.md) | Theme definitions, UI styling, and aesthetic presets. |
| [watcher](watcher.md) | File watcher (`FileWatcher`) for hot reloading screenplay changes during development. |
