# Eager-Graphics Architecture

Eager-Graphics is a **headless, renderer-agnostic, resolution-independent Graphics & Stage Compositor** designed for the [Eager](https://github.com/CooperElektrik/Eager) visual novel engine ecosystem.

- **FPS monitoring**: Every render backend and the `StageCompositor` itself own a `FrameClock` (`eager_graphics.timing`) that tracks real wall-clock frame intervals, computing instantaneous, rolling-average, and overall FPS for debug HUDs and headless benchmarks.

---

## 1. Design Philosophy

| Pillar | Description |
|---|---|
| **Headless & Render-Agnostic** | Eager-Graphics computes *what* should appear on screen (sprites, backgrounds, overlays, transitions) and yields an ordered render list (`RenderItem`). It never calls drawing APIs or touches GPU pixels directly. |
| **Resolution-Independent** | All stage elements live in a virtual reference coordinate system (default `1920x1080`). Backends scale to physical screen sizes using viewport transformers. |
| **Zero Bloat & Fast** | Pure Python with zero heavy dependencies (no Pygame, no SDL, no image decoders in core). Timeline updates and render list compilation execute in microseconds. |
| **Deterministic State** | Visual state serializes to plain JSON-compatible dictionaries, enabling infallible quicksave and time-travel rollback alongside Eager's narrative snapshots. |
| **Writer-Centric Contracts** | Integrates cleanly with Eager's `EventDispatcher`. Writers use clean engine hooks (`~ bg`, `~ show`, `~ move`, etc.) without touching Python code. |

---

## 2. Rendering Pipeline

```
  Eager-Script Screenplay (.es)
            │
            ▼
    [ StoryVM (Eager) ] ──── emits StoryEvents ────► [ EventDispatcher ]
                                                              │
                                                              ▼
                                                      [ StageDirector ]
                                                              │
                                    ┌─────────────────────────┴─────────────────────────┐
                                    ▼                                                   ▼
                        mutates stage & timeline                            updates UIState
                        (via screenplay hooks)                            (speaker/text/choices)
                                    │                                                   │
                                    ▼                                                   ▼
                    [ StageCompositor ]                                       [ UIOverlay ]
                    (ticks FrameClock → fps/clock)                    (DialogueBox · ChoiceMenu · EndNotice)
                                    │                                                   │
                                    │                                          immediate-mode
                                    │                                          UIDrawBackend
                                    │                                          primitives
                                    ▼                                                   ▼
                             list[RenderItem] ──────────────────────────►  same RenderBackend
                                    │                                                   ▲
                    ┌─────────────────┼───────────────────────┼───────────────────────┘
                    ▼                 ▼                       ▼                      ▼
              Pygame Backend     Raylib Backend          Godot Engine            Web / Canvas
```

### Two layers, two draw-command styles

Eager-Graphics draws in two distinct passes, and it is worth keeping them apart:

| | **Stage layer** | **UI layer** |
|---|---|---|
| Owner | `StageCompositor` | `UIOverlay` and its components |
| Produces | `list[RenderItem]` (pre-transformed, batched) | Immediate-mode primitives (`draw_rect`, `draw_text`, `draw_image`) |
| Protocol | `RenderBackend` | `UIDrawBackend` |
| Coordinate space | Virtual stage (1920×1080), then viewport-transformed | Window pixels, top-left origin |
| Content | Backgrounds, sprites, fades, flashes, shake | Dialogue box, speaker nameplate, choice buttons, end notice |

Because the two layers use different protocols, the compositor stays completely
unaware of narrative chrome, and the UI components stay unaware of virtual-stage
scaling. Backends implement both protocols; `NullRenderer` records either kind of
call, which makes the whole UI layer assertable in headless tests.

---

## 2a. Narrative UI Components

`eager_graphics.ui_components` holds the front-end chrome:

| Component | Responsibility |
|---|---|
| `DialogueBox` | Bottom-docked textbox, speaker nameplate, dialogue text, advance cue. |
| `ChoiceMenu` | Centre-aligned branch buttons; `hit_test()` for mouse input. |
| `EndNotice` | Bottom banner shown once the story concludes. |
| `UIOverlay` | Container that owns the three above and draws them in order. |

Each component owns its own layout maths and exposes it via `layout()`, so the
geometry that is *drawn* is the same geometry that is *hit-tested*. Styling is
configurable through frozen style dataclasses (`TextboxStyle`, `ChoiceMenuStyle`).

Coordinate convention: components lay out in **window pixels with a top-left
origin**. Backends whose native origin differs — Pyglet uses bottom-left — flip
`y` when issuing primitives, so components never need to know which backend they
are talking to.

Players (`PILPlayer`, `PygletPlayer`) hold a `UIOverlay` and delegate:

```python
def on_draw(self):
    self.clear()
    self.renderer.render_compositor(self.compositor, self.width, self.height)
    self.overlay.draw(
        self.renderer,
        self.director.ui_state,
        self.active_choice_prompt,
        is_finished=self.is_finished,
    )
```

---

## 3. Virtual Stage & Viewport Transformation

### Virtual Coordinate System
- Reference resolution: **1920 × 1080** (customizable via `virtual_width` and `virtual_height`).
- Origin `(0, 0)` is top-left.
- Default character ground line is at `ground_y = 1080.0` (screen bottom).

### Viewport Scaling Modes (`ScaleMode`)
When rendering to a physical display of different dimensions, `LayoutResolver.compute_viewport_transform()` provides exact scaling and positioning:

- **`LETTERBOX`**: Preserves virtual aspect ratio, centering the stage and letterboxing/pillarboxing excess space.
- **`STRETCH`**: Stretches the virtual stage to fill the entire physical window (aspect ratio may distort).
- **`CROP`**: Scales to fill the entire physical window, cropping overflowing content.
- **`FIT_WIDTH`**: Scales uniformly so virtual width matches window width.
- **`FIT_HEIGHT`**: Scales uniformly so virtual height matches window height.

`ViewportTransform.to_screen(x, y)` converts virtual stage coordinates to actual physical pixel coordinates.

---

## 4. Layer Hierarchy & Stacking Order

Eager-Graphics maintains an ordered layer stack. Higher `z_order` renders on top:

1. **`background`** (`z_order=0`): Environment art and CG backgrounds. Automatically manages crossfades between incoming and outgoing scenes.
2. **`characters`** (`z_order=100`): Character sprites with horizontal positioning, expressions, and enter/exit transitions.
3. **`foreground`** (`z_order=200`): Foreground props and overlays. Use `compositor.show_element("foreground", ...)` to add content. *(Particle effects and weather systems are not yet implemented.)*
4. **`ui`** (`z_order=300`): Dialogue textbox, speaker nameplate, choice menus. Exempt from camera shake.
5. **`overlay`** (`z_order=400`): Full-screen color washes, flashes, and fades. Exempt from camera shake.

Custom layers can be added at any time via `compositor.stage.get_or_create_layer(name, z_order)`.

---

## 5. Camera Shake

Screen shake is applied non-destructively:
- Element base positions are **never modified or corrupted** by shake.
- An offset vector `shake_offset: Vec2` is dynamically computed and applied to non-exempt layers during `render_list()` generation.
- Layers listed in `compositor.shake_exempt_layers` (default `{"ui", "overlay"}`) remain steady.

---

## 6. Backend Integration Protocol

Backends implement the lightweight `RenderBackend` protocol:

```python
from typing import Protocol
from eager_graphics.protocol import RenderItem
from eager_graphics.types import Color

class RenderBackend(Protocol):
    def begin_frame(self) -> None: ...
    def clear(self, color: Color) -> None: ...
    def draw_item(self, item: RenderItem) -> None: ...
    def end_frame(self) -> None: ...
```

Each `RenderItem` supplies all information needed to draw:
- `asset_id`: String identifier (e.g. `bg/castle`, `alice/happy`).
- `x`, `y`: Virtual stage coordinates (incorporating camera shake).
- `opacity`: Float from `0.0` (invisible) to `1.0` (opaque).
- `scale_x`, `scale_y`: Horizontal and vertical scaling multipliers.
- `rotation`: Clockwise rotation in degrees.
- `anchor`: Alignment anchor point (e.g. `Anchor.BOTTOM_CENTER`).
- `tint`: Color multiply tint (`Color`).
- `flip_h`, `flip_v`: Mirror flags.
- `layer`: Name of the parent layer.
- `z_order`: Global render sort key.

### UI Draw Protocol

Backends additionally implement `UIDrawBackend`, used by the components in
`ui_components` for the narrative chrome layer:

```python
from typing import Protocol
from eager_graphics.protocol import UIDrawBackend

class UIDrawBackend(Protocol):
    def draw_rect(self, x, y, width, height, color, *,
                  border_color=None, border_width=0.0) -> None: ...
    def draw_text(self, x, y, text, *, font_size=14, color=WHITE,
                  anchor_x="left", anchor_y="top") -> None: ...
    def draw_image(self, asset_id, x, y, width, height, *,
                   tint=WHITE, anchor_x="left", anchor_y="top") -> None: ...
    def measure_text(self, text, *, font_size=14) -> tuple[float, float]: ...
```

Coordinates are window pixels with a **top-left origin**; backends with a
different native origin flip `y` themselves. Anchors are strings:
`anchor_x` ∈ `{left, center, right}`, `anchor_y` ∈ `{top, middle, bottom}`.

---

## 7. First-Party Renderers

### NullRenderer (`eager_graphics.renderers.null`)
Always available — no optional dependencies.

- Pure-Python, zero-GPU/headless rendering backend.
- Implements `RenderBackend` and records draw calls into `last_frame` for inspection/testing.
- Also implements `UIDrawBackend`, recording UI primitives into `ui_calls` — this makes the dialogue box and choice menu assertable in headless tests.
- **FPS monitoring**: Owns a `FrameClock` (ticked per `end_frame`), exposing `fps`, `fps_avg`, `fps_overall`, `frame_count`, and `dt` properties.
- Ideal for CI, automated testing, and headless game loops.

```python
from eager_graphics import NullRenderer, StageCompositor

comp = StageCompositor(1920, 1080)
backend = NullRenderer()
for _ in range(120):
    comp.step(dt=1/60)
    backend.render_compositor(comp, 1280, 720)
print(f"FPS: {backend.fps:.1f}  (overall: {backend.fps_overall:.1f})")
```

Inspecting the UI layer headlessly:

```python
from eager_graphics import NullRenderer, UIOverlay, UIState

backend = NullRenderer()
UIOverlay(1280, 720).draw(backend, UIState(speaker="Meris", text="Choose."), prompt)

for call in backend.ui_calls:
    print(call["kind"], call.get("text") or call.get("color"))
```

### Pyglet (`eager_graphics.renderers.pyglet`)
Install via `pip install eager-graphics[hardware]`.

- Hardware-accelerated OpenGL 2D rendering.
- `PygletRenderer`: Implements `RenderBackend`, handles viewport scaling, letterbox borders, flips, and tinting.
- `PygletPlayer`: Ready-to-use interactive game window supporting dialogue, choices, rollback, and custom assets.
- Built-in procedural placeholder generator for zero-asset prototyping.

### PIL / Pillow (`eager_graphics.renderers.pil`)
Install via `pip install eager-graphics[software]` or `pip install pillow`. (Player windows additionally need Tk bindings in your Python, e.g. `apt install python3-tk`.)

- High-performance software rendering backend with all optimizations.
- `PILRenderer`: Implements `RenderBackend`, viewport scaling (`LETTERBOX`, `STRETCH`, etc.), LRU sprite transform caching, opaque direct-blit fast-path (13x speedup), and precomputed LUT tinting.
- `PILPlayer`: Interactive game window supporting dialogue, choices, rollback, and custom assets. Frames are rendered in software via PIL and presented in a tkinter window (`run()`); story logic works headless, so only Pillow is required unless a window is opened.
- Procedural placeholder generator for zero-asset prototyping.

```python
from eager_graphics.renderers.pil import PILRenderer
renderer = PILRenderer(1280, 720)
image = renderer.render_compositor(compositor, 1280, 720)
renderer.save_frame("screenshot.png")
```

