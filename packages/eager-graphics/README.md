# Eager-Graphics (Eager-X)

> A lightweight, renderer-agnostic, resolution-independent Graphics & Stage Compositor with pluggable backends for the Eager narrative engine.

Eager-Graphics is the **presentation layer** of the Eager visual novel engine. It provides stage compositing, scene layers, tweens and camera shake, UI overlays, dialogue boxes, choice menus, screens, NVL mode, and pluggable backends (Null, PIL, Pyglet, Raylib). Audio playback is driven through engine hooks, but the mixer itself lives in the sibling leaf package [`eager-core`](../eager-core/README.md).

---

## Features

- **Three Pluggable Backends**:
  - `NullRenderer`: Zero-dependency, headless frame recording for automated CI and tests.
  - `PILRenderer`: High-performance software rendering with LRU texture caching and direct-blit optimizations.
  - `PygletRenderer` / `RaylibRenderer`: Hardware-accelerated OpenGL 2D backends for high-framerate visual novel gaming.
- **Stage Compositor & Transitions**: Backgrounds, character sprites, z-ordering, viewport letterboxing/scaling, fades, and camera shake.
- **Renderer-Agnostic UI Chrome**: Bottom-docked dialogue boxes, speaker nameplates, side images, branch selection menus, and full-screen NVL novel mode.
- **Pluggable Audio Backends**:
  - `PygletAudioBackend`: Per-channel streaming and seamless looping via `pyglet.media.Player`.
  - `RaylibAudioBackend`: Low-level music stream playback and loop points via Raylib audio device.
  - `MiniaudioAudioBackend`: Low-latency PCM soft-mixing engine and loop points via `miniaudio` (`pip install eager-graphics[audio]`).
  - `NullAudioBackend`: Headless no-op audio backend recording calls for CI and tests.
- **Audio Hooks & Voice**: `~ play` / `~ stop` / `~ volume` with seamless intro/loop points (`loop_start`, `loop_end`), automatic dialogue voice playback and auto-stop, and skip-mode sound/voice suppression. Driven by `AudioMixer` from [`eager-core`](../eager-core/README.md).
- **UI Screen System & Themes**: Customizable ScreenManager with TitleScreen, Save/Load screen, backlog, and preferences.
- **CLI Commands (`eager-x`)**:
  - `eager-x new <project_name>` — Scaffolds a new visual novel project.
  - `eager-x run [project_dir]` — Runs a project directory using game.toml configuration.
  - `eager-x play <script.es>` — Launches an interactive player (`--backend pil|pyglet|raylib`, `--warp scene_id`).
  - `eager-x check <script_or_project>` — Validates script logic and graph integrity.
  - `eager-x build [project_dir]` — Bundles project into a standalone distribution archive.
  - `eager-x render <script.es>` — Headless render pass to completion.

---

## Quickstart

```bash
# Create a new visual novel project
eager-x new my_story

# Run the project
cd my_story
eager-x run
```

---

## License

MIT

