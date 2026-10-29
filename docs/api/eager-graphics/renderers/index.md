# eager_graphics Renderers

Pluggable rendering and audio backends for the Eager presentation layer.

| Backend | Description |
|---------|-------------|
| [null](null.md) | Headless dummy renderer (`NullRenderer`) for headless testing and CI verification. |
| [pil](pil.md) | Software rendering backend using Pillow or Pillow-SIMD for frame export and headless image generation. |
| [pyglet](pyglet.md) | Hardware-accelerated OpenGL rendering backend using Pyglet. |
| [miniaudio](miniaudio.md) | Cross-platform hardware audio playback backend using miniaudio. |
