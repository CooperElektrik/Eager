# eager-graphics

Resolution-independent presentation layer for the Eager visual novel engine. Provides stage compositing, scene layers, tweens, camera shake, UI overlays, dialogue boxes, choice menus, built-in screens, NVL mode, and pluggable rendering backends.

## Architecture & Conventions

All primitives must be imported directly from their defining submodule. Root re-export shims are strictly forbidden:

```python
from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector
from eager_graphics.renderers.pil import PILRenderer
from eager_graphics.renderers.pyglet import PygletRenderer
```

## Modules

| Module | Description |
|--------|-------------|
| [compositor](compositor.md) | Stage compositing engine (`StageCompositor`) and render tree coordination. |
| [director](director.md) | Stage director (`StageDirector`) for wiring script hooks to stage compositor actions. |
| [stage](stage.md) | Stage display elements, scene layers, character sprites, and transitions. |
| [ui](ui.md) | Dialogue boxes, choice menus, NVL mode, and UI interaction states. |
| [fonts](fonts.md) | Font loader, glyph metrics caching, and typography management. |
| [player](player.md) | Interactive windowed player coordinator. |

## Subsystems

- [Screens](screens/index.md): Built-in game screens (title, settings, save/load, backlog) and widgets.
- [Renderers](renderers/index.md): Backend implementations (Null, PIL/Pillow-SIMD, Pyglet, Miniaudio).
