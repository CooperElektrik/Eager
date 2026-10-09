# Eager-X API Reference

All primary classes, protocols, and data structures are exported from the top-level `eager_x` package.

```python
from eager_x import (
    StageCompositor,
    StageDirector,
    LayoutResolver,
    ViewportTransform,
    Timeline,
    Tween,
    Stage,
    Layer,
    StageElement,
    ElementState,
    RenderItem,
    RenderBackend,
    FrameClock,
    Vec2,
    Color,
    Anchor,
    ScaleMode,
    TransitionKind,
)
```

---

## 1. `StageCompositor`

The primary orchestrator managing stage layers, timeline updates, screen shake, and render list generation.

### Constructor
```python
StageCompositor(
    virtual_width: int = 1920,
    virtual_height: int = 1080,
    *,
    ground_y: float = 1080.0,
)
```

### Methods
- **`update(dt: float) -> None`**: Advance timeline tweens and decay screen shake by `dt` seconds.
- **`render_list() -> list[RenderItem]`**: Generate a sorted, z-ordered list of active render items.
- **`set_background(asset_id: str, *, transition: str | TransitionKind = "cut", duration: float = 0.5) -> None`**: Swap background with transition.
- **`clear_background(*, transition: str | TransitionKind = "cut", duration: float = 0.5) -> None`**: Clear background.
- **`show_character(character_id: str, expression: str = "default", *, position: str | Vec2 = "center", transition: str | TransitionKind = "fade", duration: float = 0.3, z_index: int = 0, flip_h: bool = False) -> None`**: Display or update a character sprite.
- **`hide_character(character_id: str, *, transition: str | TransitionKind = "fade", duration: float = 0.3) -> None`**: Hide a character sprite.
- **`move_character(character_id: str, position: str | Vec2, *, duration: float = 0.5, easing: str = "ease_in_out_quad") -> None`**: Tween character to a new position.
- **`set_expression(character_id: str, expression: str) -> None`**: Switch character expression texture immediately.
- **`shake(intensity: float = 1.0, duration: float = 0.3) -> None`**: Trigger camera shake.
- **`flash(*, duration: float = 0.15, color: Color | str | None = None) -> None`**: Flash overlay layer.
- **`fade_in(*, duration: float = 1.0) -> None`**: Fade overlay from solid to transparent.
- **`fade_out(*, duration: float = 1.0, color: Color | str | None = None) -> None`**: Fade overlay to solid color.
- **`save_state() -> dict[str, Any]`**: Snapshot complete visual stage state.
- **`load_state(state: dict[str, Any]) -> None`**: Restore visual stage state from snapshot.
- **`debug_info() -> dict[str, Any]`**: Return a JSON-serializable, structured snapshot of the compositor's full runtime state — virtual stage dimensions, **FPS statistics** (instantaneous, 60-frame rolling average, overall average, frame count, elapsed time), camera-shake status, active timeline tweens, every layer/element with position/opacity/z-order, and the current frame's computed render list. Ideal for debug overlays, logging, and test introspection.
- **`debug_repr(*, include_layers: bool = True) -> str`**: Render `debug_info()` as a multi-line, human-readable string report, ready to print to stdout or draw into an on-screen text overlay in any renderer (Pyglet `Label`, Raylib `draw_text`, etc.). Includes an FPS line. Pass `include_layers=False` for a compact single-frame status line.
- **`step(dt: float = 1.0 / 60.0) -> None`**: Advance the compositor by a single fixed-timestep frame (default ≈60 FPS). Convenience alias for `update()` intended for headless game loops. Also ticks the internal `FrameClock` so FPS is tracked.
- **`fps`**, **`fps_avg`**, **`fps_overall`** *(properties)*: Real-time frames-per-second measured by the compositor's internal `FrameClock`. `fps` is instantaneous (1/Δt of last step), `fps_avg` is a rolling 60-frame average, and `fps_overall` is the average since creation/reset. All return `0.0` until at least two `step()` calls have been made.
- **`run_headless(render_backend=None, *, dt=1/60, max_steps=None, until=None, render=False) -> int`**: Run a self-contained headless game loop with no window or GPU required. Advances the timeline frame-by-frame until `max_steps` is reached or `until()` returns `True`; optionally renders each frame through a `RenderBackend` (e.g. `NullRenderer`). Returns the number of frames stepped. FPS is tracked automatically during the loop.

### Example: on-screen debug overlay

```python
# Print a compact status line each frame.
print(compositor.debug_repr(include_layers=False))

# Or draw the full report into a Pyglet label as an on-screen HUD:
# debug_label.text = compositor.debug_repr()
# (render the label after drawing all backend items)

# Access individual FPS metrics programmatically:
print(f"FPS: {compositor.fps:.1f}  (overall: {compositor.fps_overall:.1f})")
```

### Example: headless FPS measurement

```python
from eager_x import StageCompositor, NullRenderer

comp = StageCompositor(1920, 1080)
comp.set_background("bg/demo", transition="cut")

# Run 300 frames and report real-time throughput
steps = comp.run_headless(dt=1/60, max_steps=300)
print(f"Ran {steps} steps in {comp.clock.elapsed:.2f}s → {comp.fps_overall:.1f} FPS")
```

---

## 2. `StageDirector`

Bridges Eager's narrative event loop to `StageCompositor`.

### Constructor
```python
StageDirector(compositor: StageCompositor)
```

### Methods
- **`bind(dispatcher: EventDispatcher) -> None`**: Register hook and event handlers onto Eager's `EventDispatcher`.
- **`register_character(character_id: str, *, asset_prefix: str | None = None, default_expression: str = "default", default_position: str = "center") -> None`**: Configure character default parameters.
- **`register_scene_bg(scene_id: str, asset_id: str, transition: str = "crossfade", duration: float = 0.8) -> None`**: Automatically trigger background change when entering a specific scene.

---

## 3. `LayoutResolver` & `ViewportTransform`

Handles stage position resolution and resolution-independent scaling.

### `LayoutResolver` Methods
- **`resolve_position(pos: str | Vec2 | tuple[float, float]) -> Vec2`**: Converts named positions (`"left"`, `"center"`, etc.) or coordinates into a virtual `Vec2`.
- **`register_named_position(name: str, x: float, y: float | None = None) -> None`**: Define custom named positions.
- **`compute_viewport_transform(window_width: float, window_height: float, mode: ScaleMode = ScaleMode.LETTERBOX) -> ViewportTransform`**: Compute viewport scaling and offset.

### `ViewportTransform`
- **`scale: float`**: Uniform scaling factor.
- **`offset_x: float`**, **`offset_y: float`**: Letterbox padding offset.
- **`dest_rect: Rect`**: Physical screen destination rectangle.
- **`to_screen(x: float, y: float) -> tuple[float, float]`**: Transform virtual coordinates to screen space.
- **`to_virtual(x: float, y: float) -> tuple[float, float]`**: Transform screen space to virtual coordinates.

---

## 4. `RenderItem` Output Data Structure

```python
@dataclass(frozen=True, slots=True)
class RenderItem:
    asset_id: str
    x: float
    y: float
    opacity: float
    scale_x: float
    scale_y: float
    rotation: float
    anchor: Anchor
    tint: Color
    flip_h: bool
    flip_v: bool
    layer: str
    z_order: int
```

Each backend iterates over `compositor.render_list()` and draws each `RenderItem` using its native graphics primitives.

---

## 4.1 `Timeline` & `Tween`

### `Timeline` Methods
- **`active_count`** *(property)*: Number of currently running tweens.
- **`active_tweens() -> list[dict[str, Any]]`**: Debug-friendly summary of every active tween — target identifier, property name, normalized progress `[0.0, 1.0]`, remaining time, and duration. Used by `StageCompositor.debug_info()` so callers never need to touch private tween state.

### `Tween` Fields
- `target`, `property_name`, `start_value`, `end_value`, `duration`, `easing`, `delay`, `elapsed`, `on_complete`, `on_update`, `finished`.

---

## 4.2 `FrameClock` — FPS Measurement

`FrameClock` is a lightweight, zero-dependency utility (`eager_x.timing`) that records wall-clock frame timestamps via `time.perf_counter()` and derives three FPS views:

| Property | Description |
|---|---|
| `fps` | Instantaneous FPS (1 / last frame interval). Jumps around but reacts immediately to hitches. |
| `fps_avg` | Rolling-average FPS over the last `rolling_window` frames (default 60). Smooth, ideal for HUD display. |
| `fps_overall` | Total frames / total elapsed wall-clock time since start or last `reset()`. |
| `dt` | Delta time (seconds) of the most recent frame. |
| `frame_count` | Total frames recorded. |
| `elapsed` | Total wall-clock seconds since the clock started or was reset. |

```python
from eager_x import FrameClock

clock = FrameClock(rolling_window=30)
clock.tick()       # first call returns dt=0.0
# ... render a frame ...
clock.tick()       # returns dt since last tick
print(f"FPS: {clock.fps:.1f} (avg: {clock.fps_avg:.1f})")
clock.reset()      # clear all history
```

`FrameClock` is integrated into every render backend and the `StageCompositor` itself:

- **`StageCompositor.step()`** ticks the compositor's internal clock, so `debug_info()` and `debug_repr()` automatically report FPS.
- **`NullRenderer`**, **`PygletRenderer`**, and **`PILRenderer`** each own a `FrameClock` ticked in `end_frame()`, exposing `fps`, `fps_avg`, and `fps_overall` as properties.

### Constructor

```python
FrameClock(rolling_window: int = 60)
```

### Methods
- **`tick(now: float | None = None) -> float`**: Record a frame boundary. Returns the delta time since the previous tick (`0.0` on the first call). Pass `now` for deterministic testing; otherwise `time.perf_counter()` is used.
- **`reset() -> None`**: Clear all timestamps and counters.

---

## 5. Pyglet Backend (`eager_x.renderers.pyglet`)

Provides hardware-accelerated 2D stage rendering and an interactive visual novel window runner using Pyglet.

### `PygletRenderer`
Implements `RenderBackend`:
```python
PygletRenderer(
    *,
    asset_dir: str | Path | None = None,
    scale_mode: ScaleMode = ScaleMode.LETTERBOX,
    window: pyglet.window.Window | None = None,
)
```
- **`render_compositor(compositor: StageCompositor, window_width: int, window_height: int) -> None`**: Computes resolution-independent viewport transforms, letterbox borders, and draws all active elements.
- **`asset_resolver`**: Automatically loads real images (`.png`, `.jpg`, `.webp`) or procedurally generates stylized placeholder textures with zero external art assets required.
- **`fps`**, **`fps_avg`**, **`fps_overall`** *(properties)*: Frame-rate statistics measured by an internal `FrameClock` (ticked once per `end_frame`).
- **`frame_count: int`**: Total frames rendered.

### `PygletPlayer`
An interactive visual novel window (`pyglet.window.Window`):
```python
PygletPlayer(
    vm: StoryVM,
    compositor: StageCompositor,
    director: StageDirector,
    dispatcher: EventDispatcher,
    *,
    width: int = 1280,
    height: int = 720,
    title: str = "Eager-X Visual Novel",
    asset_dir: str | Path | None = None,
    scale_mode: ScaleMode = ScaleMode.LETTERBOX,
    visible: bool = True,
    show_fps: bool = True,
)
```
- Interactive story advancement on Click, Space, or Enter.
- Built-in UI textbox, speaker nameplate, and clickable branching choices.
- Time-travel rollback on Backspace.
- **`show_fps`** *(constructor parameter)*: When `True` (default), renders an on-screen FPS counter in the top-left corner, sourced from `PygletRenderer.fps` / `PygletRenderer.fps_avg`. The counter can be toggled at runtime via `player._fps_label = None`.
- Runs with `pyglet.app.run()`.

---

## 6. Headless Backend (`eager_x.renderers.null`)

A pure-Python, zero-dependency renderer that implements the `RenderBackend` protocol without requiring a GPU, display server, or third-party graphics library. Instead of drawing pixels it records every `RenderItem` submitted during a frame for programmatic inspection — ideal for CI pipelines, headless game loops, automated testing, and debug snapshots.

### `NullRenderer`
```python
from eager_x.renderers.null import NullRenderer

backend = NullRenderer()
```

Implements the `RenderBackend` protocol (`begin_frame`, `clear`, `draw_item`, `end_frame`) plus a convenience `render_compositor()`:

- **`render_compositor(compositor: StageCompositor, window_width: int, window_height: int) -> None`**: Renders one frame from a `StageCompositor` without advancing it (call `compositor.update(dt)` yourself in your game loop). Mirrors `PygletRenderer.render_compositor` so backends are interchangeable.
- **`last_frame: list[RenderItem]`**: A copy of every draw call from the most recent completed frame.
- **`frame_count: int`**: Number of frames fully rendered.
- **`clear_color: Color`**: The color used to clear the (conceptual) framebuffer; defaults to `BLACK`.
- **`fps`**, **`fps_avg`**, **`fps_overall`** *(properties)*: Frame-rate statistics measured by an internal `FrameClock` (ticked once per `end_frame`).
- **`clock: FrameClock`**: Direct access to the internal clock for custom timing queries.

```python
# Headless render loop — no window, no GPU, no pyglet required.
comp = StageCompositor(1920, 1080)
backend = NullRenderer()

comp.set_background("bg/castle", transition="cut")
comp.update(0.016)  # advance animations
backend.render_compositor(comp, 1280, 720)

print(f"Rendered {len(backend)} items in {backend.frame_count} frame(s).")
for item in backend.last_frame:
    print(f"  [{item.layer}] {item.asset_id} @ ({item.x}, {item.y}) opacity={item.opacity:.2f}")
```

The `NullRenderer` is always available (imported unconditionally from `eager_x`), even when no graphical backend is installed. This makes Eager-X's full compositor logic testable and usable in pure-headless environments.
