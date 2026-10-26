# Eager-Graphics

A lightweight, renderer-agnostic, resolution-independent Graphics & Stage Compositor with pluggable backends for the Eager narrative engine.

Eager-Graphics is the **presentation layer** of the Eager visual novel engine. It provides stage compositing, scene layers, tweens, camera shake, UI overlays, dialogue boxes, choice menus, built-in screens, NVL mode, and pluggable rendering backends.

---

## Features

- **Pluggable Render Backends**:
  - `NullRenderer`: Headless frame recorder for continuous integration and deterministic tests.
  - `PILRenderer`: High-performance CPU software rendering with LRU texture caching and direct-blit compositing (`pip install 'eager-graphics[software]'` or optional SIMD acceleration via `'eager-graphics[software-simd]'`).
  - `PygletRenderer`: Hardware-accelerated OpenGL 2D backend for high-framerate visual novel execution (`pip install 'eager-graphics[hardware]'`).
- **Resilient Audio Backends**:
  - `PygletAudioBackend`: Per-channel audio playback and looping via Pyglet Media. Emits structured warning logs on unreadable files or player failures without terminating the session.
  - `MiniaudioAudioBackend`: Low-latency streaming and soft-mixing via `miniaudio` (`pip install 'eager-graphics[audio]'`). Resilient to uninitialized audio output devices and corrupt sound files.
  - `NullAudioBackend`: Headless no-op audio backend recording calls for testing (from `eager_core.audio`).
- **Stage Compositor & Transitions**: Backgrounds, character sprites, z-ordering, viewport scaling and letterboxing, camera shake, and crossfades.
- **UI Chrome & Components**: Bottom-docked dialogue boxes, speaker nameplates, side emotion portraits, choice selection menus, text input boxes, and full-screen NVL mode.
- **Built-in Screen System**: Modular `ScreenManager` driving Title, Save/Load, Preferences, and History backlog screens with responsive viewport layout adaptation.

---

## Installation & Extras

Choose the appropriate extra for your deployment target:

```bash
# Hardware-accelerated Pyglet OpenGL backend
pip install 'eager-graphics[hardware]'

# Software rendering with Pillow
pip install 'eager-graphics[software]'

# High-performance software rendering with Pillow-SIMD (source build, x86)
pip install 'eager-graphics[software-simd]'

# Miniaudio low-latency PCM audio backend
pip install 'eager-graphics[audio]'
```

> **Note**: For Pyglet rendering, ensure you install `eager-graphics[hardware]`. Attempting to initialize `PygletRenderer` without the hardware extra installed will emit an informative error pointing to `pip install 'eager-graphics[hardware]'`.

---

## Direct Submodule Import Convention

In accordance with monorepo guidelines, import UI state types and core events from their canonical locations:

```python
# UI state and presentation
from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector, CharacterConfig
from eager_graphics.renderers.pyglet import PygletRenderer, PygletPlayer
from eager_graphics.renderers.pil.renderer import PILRenderer

# Events and primitives from eager-core
from eager_core.events import ChoiceOption, DialogueEvent, InputPromptEvent
from eager_core.types import Color, Vec2
```

---

## Quickstart: Stage Compositor & Director

```python
from eager_core.events import DialogueEvent
from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector, CharacterConfig

# 1. Setup compositor with virtual canvas resolution
compositor = StageCompositor(virtual_size=(1920, 1080))

# 2. Setup stage director and register characters
director = StageDirector(compositor)
director.register_character("guard", CharacterConfig(
    display_name="Town Guard",
    color="#e74c3c",
    default_side_image="assets/guard_neutral.png"
))

# 3. Handle dialogue events
dialogue = DialogueEvent(speaker="guard", text="Welcome to the gates.")
director.handle_dialogue_event(dialogue)
```

---

## Audio Failure Resilience

Both `PygletAudioBackend` and `MiniaudioAudioBackend` are engineered to guarantee that audio hardware errors, missing audio assets, or corrupt media files do not crash game sessions:

- Device initialization errors are caught and logged as warnings via standard `logging.getLogger("eager_graphics.renderers.*")`.
- Playback falls back gracefully, allowing story progression even when audio devices are unavailable.
- Audio streaming decoding errors in background threads are logged without aborting main rendering loops.

---

## CLI Integration

`eager-graphics` provides the visual rendering players invoked through the `eager` CLI:

```bash
# Play visual novel using hardware OpenGL backend
eager play examples/demo_story.es --backend pyglet

# Play visual novel using CPU software renderer (silent mode)
eager play examples/demo_story.es --backend pil --no-audio

# Run project defined in game.toml
eager run
```

---

## License

MIT
