"""Pyglet rendering backend and interactive player for Eager-Graphics."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import pyglet
    from pyglet.graphics import Batch, Group
    from pyglet.shapes import Rectangle
    from pyglet.text import Label
except ImportError as err:
    msg = "Pyglet is not installed. Install with 'pip install eager-graphics[pyglet]' or 'pip install pyglet'."
    raise ImportError(msg) from err

from eager_graphics.layout import ViewportTransform
from eager_graphics.protocol import RenderBackend, RenderItem
from eager_graphics.timing import FrameClock
from eager_graphics.types import BLACK, WHITE, Color, ScaleMode
from eager_graphics.ui_components import UIOverlay

if TYPE_CHECKING:
    from eager_runtime import ChoicePromptEvent, EventDispatcher, StoryVM

    from eager_graphics.compositor import StageCompositor
    from eager_graphics.director import StageDirector


class PygletAssetResolver:
    """Loads and caches textures from disk, generating procedural placeholders when missing."""

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self._cache: dict[str, pyglet.image.AbstractImage] = {}

    def get_texture(
        self,
        asset_id: str,
        default_width: int = 400,
        default_height: int = 800,
    ) -> pyglet.image.AbstractImage:
        """Retrieve texture from cache, load from disk, or generate fallback."""
        if asset_id in self._cache:
            return self._cache[asset_id]

        if asset_id == "__builtin_color_rect__":
            tex = pyglet.image.ImageData(1, 1, "RGBA", bytes([255, 255, 255, 255]))
            self._cache[asset_id] = tex
            return tex

        # 1. Attempt loading from disk if asset_dir configured
        if self.asset_dir is not None:
            extensions = [".png", ".jpg", ".jpeg", ".webp"]
            for ext in extensions:
                file_path = self.asset_dir / f"{asset_id}{ext}"
                if file_path.is_file():
                    try:
                        tex = pyglet.image.load(str(file_path))
                        self._cache[asset_id] = tex
                        return tex
                    except (OSError, pyglet.image.ImageDecodeException):
                        pass

        # 2. Generate placeholder texture
        tex = self._generate_placeholder(asset_id, default_width, default_height)
        self._cache[asset_id] = tex
        return tex

    def _generate_placeholder(
        self,
        asset_id: str,
        width: int,
        height: int,
    ) -> pyglet.image.AbstractImage:
        """Procedurally generate a solid/gradient patterned placeholder texture."""
        is_bg = asset_id.startswith("bg/") or "background" in asset_id
        w = 1920 if is_bg else width
        h = 1080 if is_bg else height

        # Deterministic color derivation from asset_id string hash
        h_val = int(hashlib.md5(asset_id.encode("utf-8")).hexdigest()[:8], 16)
        r = (h_val & 0xFF)
        g = ((h_val >> 8) & 0xFF)
        b = ((h_val >> 16) & 0xFF)

        if is_bg:
            # Darker, muted tone for backgrounds
            r = 30 + (r % 60)
            g = 35 + (g % 60)
            b = 45 + (b % 70)
        else:
            # Vibrant, pastel tone for characters
            r = 100 + (r % 120)
            g = 100 + (g % 120)
            b = 100 + (b % 120)

        # 1. Attempt high-quality procedural generation via Pillow if available
        try:
            from PIL import Image, ImageChops, ImageDraw

            tw = min(w, 256)
            th = min(h, 256)
            base = Image.new("RGBA", (tw, th), (r, g, b, 255))
            grad_l = Image.linear_gradient("L").resize((tw, th), resample=Image.Resampling.BILINEAR)
            grad_mask = grad_l.point(lambda p: int(200 + p * 0.21))
            base = ImageChops.multiply(
                base,
                Image.merge(
                    "RGBA",
                    (grad_mask, grad_mask, grad_mask, Image.new("L", (tw, th), 255)),
                ),
            )
            draw = ImageDraw.Draw(base)
            draw.rectangle((0, 0, tw - 1, th - 1), outline=(255, 255, 255, 255), width=2)
            if (tw, th) != (w, h):
                base = base.resize((w, h), resample=Image.Resampling.BILINEAR)

            return pyglet.image.ImageData(w, h, "RGBA", base.tobytes(), pitch=-w * 4)
        except ImportError:
            pass

        # 2. Fast pure-Python gradient generation fallback
        num_bands = 32
        border_thickness = 4
        white4 = b"\xff\xff\xff\xff"
        w_mid = max(0, w - border_thickness * 2)

        parts: list[bytes] = []
        border_row = white4 * w
        parts.append(border_row * border_thickness)

        body_h = max(0, h - border_thickness * 2)
        band_h = body_h // num_bands
        rem = body_h % num_bands

        for i in range(num_bands):
            grad = 1.0 - (i / num_bands) * 0.25
            cr, cg, cb = int(r * grad), int(g * grad), int(b * grad)
            row = (
                (white4 * border_thickness)
                + (bytes([cr, cg, cb, 255]) * w_mid)
                + (white4 * border_thickness)
            )
            count = band_h + (1 if i < rem else 0)
            parts.append(row * count)

        parts.append(border_row * border_thickness)
        buf = b"".join(parts)
        return pyglet.image.ImageData(w, h, "RGBA", buf)


class PygletRenderer(RenderBackend):
    """Pyglet 2D stage renderer implementing RenderBackend protocol."""

    def __init__(
        self,
        *,
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        window: pyglet.window.Window | None = None,
    ) -> None:
        self.asset_resolver = PygletAssetResolver(asset_dir)
        self.scale_mode = scale_mode
        self.window = window
        self.width: int = window.width if window is not None else 1920
        self.height: int = window.height if window is not None else 1080
        self._current_transform: ViewportTransform | None = None
        self._active_sprites: list[pyglet.sprite.Sprite] = []
        self._letterbox_bars: list[Rectangle] = []
        self.clock: FrameClock = FrameClock()
        self.frame_count: int = 0

    def set_window(self, window: pyglet.window.Window) -> None:
        """Associate renderer with an active Pyglet Window."""
        self.window = window
        self.width = window.width
        self.height = window.height

    def begin_frame(self) -> None:
        """Prepare for new frame rendering pass."""
        self._active_sprites.clear()
        self._letterbox_bars.clear()

    def clear(self, color: Color = BLACK) -> None:
        """Clear OpenGL framebuffer with color."""
        r, g, b, a = color.r, color.g, color.b, color.a
        pyglet.gl.glClearColor(r, g, b, a)
        if self.window is not None:
            self.window.clear()

    def draw_item(self, item: RenderItem) -> None:
        """Render a single compositor item."""
        if self._current_transform is None:
            msg = "draw_item called before render_compositor set the viewport transform"
            raise RuntimeError(msg)

        if item.opacity <= 0.0 or not (item.scale_x and item.scale_y):
            return

        win_h = self.window.height if self.window is not None else self.height
        transform = self._current_transform

        # Load / resolve texture
        is_bg = item.layer == "background" or item.asset_id.startswith("bg/")
        def_w = 1920 if is_bg else 400
        def_h = 1080 if is_bg else 800
        texture = self.asset_resolver.get_texture(item.asset_id, def_w, def_h)

        # Compute effective element dimension in virtual coordinates
        eff_w = texture.width * abs(item.scale_x)
        eff_h = texture.height * abs(item.scale_y)

        # Anchor offset in virtual space
        fx, fy = item.anchor.get_offset_factor()

        # Project dimensions to physical screen coordinates
        draw_w = eff_w * transform.scale_x
        draw_h = eff_h * transform.scale_y

        # Anchor screen position in Pyglet coordinates (bottom-left origin, Y goes UP)
        anchor_s_x, anchor_s_y = transform.to_screen(item.x, item.y)
        pyglet_anchor_x = anchor_s_x
        pyglet_anchor_y = win_h - anchor_s_y

        # Configure texture region with anchor matching item.anchor
        tex = texture.get_texture()
        region = tex.get_region(0, 0, tex.width, tex.height)
        region.anchor_x = texture.width * fx
        region.anchor_y = texture.height * (1.0 - fy)

        # Create and configure Pyglet sprite
        sprite = pyglet.sprite.Sprite(
            region,
            x=pyglet_anchor_x,
            y=pyglet_anchor_y,
            group=Group(order=item.z_order),
            subpixel=True,
        )

        scale_x_dir = -1.0 if item.flip_h else 1.0
        if item.scale_x < 0:
            scale_x_dir = -scale_x_dir
        scale_y_dir = -1.0 if item.flip_v else 1.0
        if item.scale_y < 0:
            scale_y_dir = -scale_y_dir

        sprite.scale_x = scale_x_dir * (draw_w / texture.width)
        sprite.scale_y = scale_y_dir * (draw_h / texture.height)
        sprite.rotation = item.rotation

        # Opacity & Tint
        final_alpha = max(0.0, min(1.0, item.opacity * item.tint.a))
        sprite.color = (
            round(item.tint.r * 255),
            round(item.tint.g * 255),
            round(item.tint.b * 255),
            round(final_alpha * 255),
        )

        sprite.draw()
        self._active_sprites.append(sprite)

    def end_frame(self) -> None:
        """Conclude frame render pass, drawing letterbox black bars if necessary."""
        if self.window is None or self._current_transform is None:
            return

        win_w, win_h = self.window.width, self.window.height
        trans = self._current_transform

        # Draw letterbox/pillarbox borders if window exceeds virtual aspect ratio
        if trans.offset_x > 0:
            # Left & right pillarbox bars
            left_bar = Rectangle(0, 0, trans.offset_x, win_h, color=(0, 0, 0, 255))
            right_bar = Rectangle(
                win_w - trans.offset_x, 0, trans.offset_x, win_h, color=(0, 0, 0, 255)
            )
            left_bar.draw()
            right_bar.draw()
            self._letterbox_bars.extend([left_bar, right_bar])

        if trans.offset_y > 0:
            # Top & bottom letterbox bars
            bottom_bar = Rectangle(0, 0, win_w, trans.offset_y, color=(0, 0, 0, 255))
            top_bar = Rectangle(
                0, win_h - trans.offset_y, win_w, trans.offset_y, color=(0, 0, 0, 255)
            )
            bottom_bar.draw()
            top_bar.draw()
            self._letterbox_bars.extend([bottom_bar, top_bar])

        self.frame_count += 1
        self.clock.tick()

    # ------------------------------------------------------------------ #
    # FPS properties (delegate to the FrameClock for a uniform API)
    # ------------------------------------------------------------------ #

    @property
    def fps(self) -> float:
        """Instantaneous frames-per-second (1 / last frame interval)."""
        return self.clock.fps

    @property
    def fps_avg(self) -> float:
        """Rolling-average FPS over the last 60 rendered frames."""
        return self.clock.fps_avg

    @property
    def fps_overall(self) -> float:
        """Average FPS across all frames rendered since the renderer was created."""
        return self.clock.fps_overall

    def render_compositor(
        self,
        compositor: StageCompositor,
        window_width: int,
        window_height: int,
    ) -> None:
        """Render all active compositor layers to the window."""
        self.width = window_width
        self.height = window_height
        self._current_transform = compositor.layout.compute_viewport_transform(
            window_width,
            window_height,
            mode=self.scale_mode,
        )

        self.begin_frame()
        self.clear(BLACK)

        items = compositor.render_list()
        for item in items:
            self.draw_item(item)

        self.end_frame()

    # ------------------------------------------------------------------ #
    # UIDrawBackend primitives
    #
    # Immediate-mode primitives consumed by the renderer-agnostic components
    # in eager_graphics.ui_components.  Those components work in window
    # pixels with a TOP-LEFT origin; Pyglet is natively bottom-left, so every
    # y coordinate is flipped through _flip_y before being issued.
    # ------------------------------------------------------------------ #

    def _flip_y(self, y: float, extent: float = 0.0) -> float:
        """Convert a top-left-origin *y* (optionally spanning *extent*) to Pyglet space."""
        return float(self.height) - y - extent

    def draw_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: Color,
        *,
        border_color: Color | None = None,
        border_width: float = 0.0,
    ) -> None:
        """Draw a filled rectangle, optionally stroked with a top border."""
        rect = pyglet.shapes.Rectangle(
            x=float(x) + width / 2.0,
            y=self._flip_y(y, height) + height / 2.0,
            width=float(width),
            height=float(height),
            color=color.to_rgba_bytes(),
        )
        rect.draw()

        if border_color is not None and border_width > 0.0:
            border = pyglet.shapes.Rectangle(
                x=float(x) + width / 2.0,
                y=self._flip_y(y, border_width) + border_width / 2.0,
                width=float(width),
                height=float(border_width),
                color=border_color.to_rgba_bytes(),
            )
            border.draw()

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: int = 14,
        color: Color = WHITE,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        """Draw a single line of text at the requested anchor point."""
        pyglet_anchor_x = {"left": "left", "center": "center", "right": "right"}.get(
            anchor_x, "left"
        )

        # Map the top-left convention onto Pyglet's vertical anchors.  Because
        # the y coordinate has already been flipped, "top" in our space is the
        # higher of the two Pyglet anchors.
        pyglet_anchor_y = {
            "top": "top",
            "middle": "center",
            "bottom": "bottom",
        }.get(anchor_y, "top")

        label = pyglet.text.Label(
            text,
            font_name=self._ui_font_name(),
            font_size=font_size,
            x=float(x),
            y=self._flip_y(y),
            anchor_x=pyglet_anchor_x,
            anchor_y=pyglet_anchor_y,
            color=color.to_rgba_bytes(),
        )
        label.draw()

    def draw_image(
        self,
        asset_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        tint: Color = WHITE,
        anchor_x: str = "left",
        anchor_y: str = "top",
    ) -> None:
        """Draw a resolved asset scaled into the given box."""
        texture = self.asset_resolver.get_texture(
            asset_id, max(1, round(width)), max(1, round(height))
        )
        if texture is None:
            return

        target_w = max(1, round(width))
        target_h = max(1, round(height))

        # Sprites are anchored at their centre by default, which keeps the
        # bottom-left conversion below straightforward.
        sprite = pyglet.sprite.Sprite(
            texture,
            x=float(x) + target_w / 2.0,
            y=self._flip_y(y, target_h) + target_h / 2.0,
            scale=(target_w / max(1, texture.width), target_h / max(1, texture.height)),
        )

        if anchor_x == "left":
            sprite.anchor_x = 0.0
        elif anchor_x == "right":
            sprite.anchor_x = float(target_w)
        if anchor_y == "top":
            sprite.anchor_y = 0.0
        elif anchor_y == "bottom":
            sprite.anchor_y = float(target_h)

        if tint != WHITE:
            sprite.color = tint.to_rgba_bytes()
        sprite.draw()

    def _ui_font_name(self) -> str:
        """Return the font family used for UI text."""
        return "sans-serif"

    def measure_text(self, text: str, *, font_size: int = 14) -> tuple[float, float]:
        """Measure the pixel extents *text* would occupy at *font_size*.

        Reads the label's ``content_width`` / ``content_height`` rather than
        ``width`` / ``height``: the latter are only populated once the label has
        been laid out in a draw pass, and report ``None`` beforehand.
        """
        try:
            label = pyglet.text.Label(
                text, font_name=self._ui_font_name(), font_size=font_size
            )
            width = float(label.content_width)
            height = float(label.content_height)
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return (float(font_size) * 0.5 * len(text), float(font_size) * 1.2)
        return (width, height)


class PygletPlayer(pyglet.window.Window):
    """Full-featured interactive Visual Novel window player powered by Eager and Eager-Graphics."""

    def __init__(
        self,
        vm: StoryVM,
        compositor: StageCompositor,
        director: StageDirector,
        dispatcher: EventDispatcher,
        *,
        width: int = 1280,
        height: int = 720,
        title: str = "Eager-Graphics Visual Novel",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        vsync: bool = True,
        visible: bool = True,
        show_fps: bool = True,
    ) -> None:
        super().__init__(
            width=width,
            height=height,
            caption=title,
            resizable=True,
            vsync=vsync,
            visible=visible,
        )
        self.vm = vm
        self.compositor = compositor
        self.director = director
        self.dispatcher = dispatcher

        self.renderer = PygletRenderer(
            asset_dir=asset_dir,
            scale_mode=scale_mode,
            window=self,
        )

        # Narrative UI State
        self.current_speaker: str | None = None
        self.current_text: str = ""
        self.current_emotion: str | None = None
        self.active_choice_prompt: ChoicePromptEvent | None = None
        self.is_finished: bool = False

        # Renderer-agnostic UI components (textbox, choice menu, end notice).
        # These own all layout maths and draw through the renderer's
        # UIDrawBackend primitives.
        self.overlay = UIOverlay(width=width, height=height)

        # UI elements batch
        self._ui_batch = Batch()

        # On-screen FPS debug overlay
        self.show_fps: bool = show_fps
        self._fps_label: Label | None = None
        if show_fps:
            self._fps_label = Label(
                "",
                font_name="sans-serif",
                font_size=11,
                x=10,
                y=10,
                anchor_x="left",
                anchor_y="bottom",
                color=(230, 230, 230, 200),
            )
        # Enable visual history rollback on director
        self.director.enable_visual_history()

        self.advance_story()

        # Schedule animation tick at 60 FPS
        pyglet.clock.schedule_interval(self.tick, 1.0 / 60.0)

    def on_resize(self, width: int, height: int) -> None:
        """Keep the UI components laid out against the new window size."""
        self.overlay.set_viewport(width, height)

    def _sync_overlay(self) -> None:
        """Mirror current narrative state onto the UI components.

        Called whenever the active choice prompt or dialogue changes so that
        input handling sees up-to-date layout even before the next draw.
        """
        self.overlay.sync(self.director.ui_state, self.active_choice_prompt)

    def advance_story(self) -> None:
        """Advance the story by one dialogue beat or hook."""
        if self.is_finished or self.vm.is_ended:
            self.is_finished = True
            self._sync_overlay()
            return

        if self.active_choice_prompt is not None:
            # Cannot advance while awaiting branch choice selection
            self._sync_overlay()
            return

        # Snapshot visual and UI state before advancing to the next narrative beat
        self.director.snapshot_visual_state()

        # Advance VM until next interactive beat (dialogue, choice, or end)
        while not self.vm.is_ended:
            event = self.vm.step()
            if event is None:
                self.is_finished = True
                break

            self.dispatcher.dispatch(event)

            if event.type == "dialogue":
                diag = event  # type: DialogueEvent
                self.current_speaker = diag.speaker
                self.current_text = diag.text
                self.current_emotion = diag.emotion
                break

            if event.type == "narration":
                narr = event  # type: NarrationEvent
                self.current_speaker = None
                self.current_text = narr.text
                self.current_emotion = None
                break

            if event.type == "append":
                self.current_text += f" {event.text}"
                break

            if event.type == "fresh_box":
                self.current_text = event.text
                break

            if event.type == "choice_prompt":
                self.active_choice_prompt = event
                break

            if event.type == "story_end":
                self.is_finished = True
                break

        self._sync_overlay()

    def make_choice(self, choice_index: int) -> None:
        """Select a branching choice option and continue execution."""
        if self.active_choice_prompt is None:
            return

        if 0 <= choice_index < len(self.active_choice_prompt.options):
            self.active_choice_prompt = None
            self.vm.choose(choice_index)
            self.advance_story()

    def rollback(self) -> bool:
        """Rollback narrative and stage state by one beat."""
        if not self.vm.can_rollback:
            return False

        success = self.vm.rollback()
        if success:
            self.director.rollback_visual_state()
            self.active_choice_prompt = None
            self.current_speaker = self.director.ui_state.speaker
            self.current_text = self.director.ui_state.text
            self.current_emotion = self.director.ui_state.emotion
            self.is_finished = self.director.ui_state.is_finished
            self._sync_overlay()
        return success

    def tick(self, dt: float) -> None:
        """Advance compositor animations by dt (delegates to step() so the FPS clock ticks)."""
        self.compositor.step(dt)

    def on_draw(self) -> None:
        """Render frame: stage graphics followed by UI textbox and choices."""
        self.clear()

        # 1. Render Stage Elements
        self.renderer.render_compositor(self.compositor, self.width, self.height)

        # 2-4. Dialogue textbox, branching choices, and story-end notice,
        #      all delegated to the renderer-agnostic UI components.
        self.overlay.draw(
            self.renderer,
            self.director.ui_state,
            self.active_choice_prompt,
            is_finished=self.is_finished,
        )

        # 5. Render FPS counter
        if self._fps_label is not None:
            self._draw_fps()

    def _draw_fps(self) -> None:
        """Update and draw the on-screen FPS counter overlay."""
        if self._fps_label is None:
            return
        fps = self.renderer.fps
        fps_avg = self.renderer.fps_avg
        # Use compositor clock for overall frame count context
        frames = self.compositor.clock.frame_count
        self._fps_label.text = f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})"
        self._fps_label.draw()

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Handle mouse clicks for advancement or choice selection."""
        if button != pyglet.window.mouse.LEFT:
            return

        # If choices are presented, check button click bounds
        if self.active_choice_prompt is not None:
            # Pyglet reports y in bottom-left space; the components lay out in
            # top-left space, so flip before hit testing.
            flipped_y = self.height - y
            index = self.overlay.hit_test_choice(x, flipped_y)
            if index is not None:
                self.make_choice(index)
            return

        # Otherwise click advances story
        self.advance_story()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        """Handle keyboard input for advancing, choices, rollback, and save/load."""
        key = pyglet.window.key

        if symbol in (key.SPACE, key.RETURN):
            if self.active_choice_prompt is None:
                self.advance_story()

        elif self.active_choice_prompt is not None:
            # 1-9 keys to pick choice
            num_keys = [key._1, key._2, key._3, key._4, key._5, key._6, key._7, key._8, key._9]
            for idx, k in enumerate(num_keys):
                if symbol == k and idx < len(self.active_choice_prompt.options):
                    self.make_choice(idx)
                    break

        elif symbol == key.BACKSPACE:
            self.rollback()

        elif symbol == key.ESCAPE or symbol == key.Q:
            self.close()
