"""Pyglet rendering backend and interactive player for Eager-Graphics."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import pyglet
    from pyglet.graphics import Batch, Group
    from pyglet.shapes import Box, Rectangle
    from pyglet.text import Label
    from pyglet.window import key, mouse
except ImportError as err:
    msg = "Pyglet is not installed. Install with 'pip install eager-graphics[pyglet]' or 'pip install pyglet'."
    raise ImportError(msg) from err

from eager_core.input import InputAction, Keymap

from eager_graphics.layout import ViewportTransform
from eager_graphics.protocol import RenderBackend, RenderItem
from eager_graphics.timing import FrameClock
from eager_graphics.types import BLACK, WHITE, Color, ScaleMode
from eager_graphics.ui_components import UIOverlay

if TYPE_CHECKING:
    from eager_core.audio import AudioMixer
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
            candidate_ids = [asset_id]
            if not asset_id.startswith("characters/"):
                candidate_ids.append(f"characters/{asset_id}")
            if asset_id.startswith("bg/"):
                candidate_ids.append(f"backgrounds/{asset_id[3:]}")
            elif asset_id.startswith("backgrounds/"):
                candidate_ids.append(f"bg/{asset_id[12:]}")

            extensions = [".png", ".jpg", ".jpeg", ".webp"]
            for cid in candidate_ids:
                for ext in extensions:
                    file_path = self.asset_dir / f"{cid}{ext}"
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

    # Alias matching PIL and Raylib resolvers
    get_image = get_texture

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
        width: int = 1920,
        height: int = 1080,
        *,
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        window: pyglet.window.Window | None = None,
    ) -> None:
        self.asset_resolver = PygletAssetResolver(asset_dir)
        self.scale_mode = scale_mode
        self.window = window
        self.width: int = window.width if window is not None else width
        self.height: int = window.height if window is not None else height
        self._current_transform: ViewportTransform | None = None
        self._active_sprites: list[pyglet.sprite.Sprite] = []
        self._letterbox_bars: list[Rectangle] = []
        self.clock: FrameClock = FrameClock()
        self.frame_count: int = 0
        self.last_frame: list[RenderItem] = []

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
        self.frame_count += 1
        self.clock.tick()

        if self.window is None or self._current_transform is None:
            return

        win_w, win_h = self.width, self.height
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
        self.last_frame = items
        for item in items:
            self.draw_item(item)

        self.end_frame()

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"PygletRenderer(width={self.width}, height={self.height}, "
            f"frame_count={self.frame_count}, last_frame_items={len(self.last_frame)}, "
            f"fps={self.clock.fps:.1f})"
        )

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
        """Draw a filled rectangle, optionally stroked with a border."""
        rect = pyglet.shapes.Rectangle(
            x=float(x),
            y=self._flip_y(y, height),
            width=float(width),
            height=float(height),
            color=color.to_rgba_bytes(),
        )
        rect.draw()

        if border_color is not None and border_width > 0.0:
            box = Box(
                x=float(x),
                y=self._flip_y(y, height),
                width=float(width),
                height=float(height),
                thickness=float(border_width),
                color=border_color.to_rgba_bytes(),
            )
            box.draw()

    def draw_rect_outline(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        color: Color,
        *,
        line_width: float = 1.0,
    ) -> None:
        """Draw an unfilled rectangle outline with thickness *line_width*."""
        box = Box(
            x=float(x),
            y=self._flip_y(y, height),
            width=float(width),
            height=float(height),
            thickness=float(line_width),
            color=color.to_rgba_bytes(),
        )
        box.draw()

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        """Draw a rectangle filled with a vertical linear gradient."""
        w = max(1.0, float(width))
        h = max(1.0, float(height))
        flipped_y = self._flip_y(y, h)

        rect = pyglet.shapes.Rectangle(
            x=float(x),
            y=flipped_y,
            width=w,
            height=h,
            color=bottom_color.to_rgba_bytes(),
        )
        bot = list(bottom_color.to_rgba_bytes())
        top = list(top_color.to_rgba_bytes())
        rect._vertex_list.colors[:] = bot + bot + top + bot + top + top
        rect.draw()

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

        dest_x = float(x)
        dest_y = float(y)
        if anchor_x == "center":
            dest_x -= target_w / 2.0
        elif anchor_x == "right":
            dest_x -= target_w
        if anchor_y == "middle":
            dest_y -= target_h / 2.0
        elif anchor_y == "bottom":
            dest_y -= target_h

        sprite = pyglet.sprite.Sprite(
            texture,
            x=dest_x,
            y=self._flip_y(dest_y, target_h),
        )
        sprite.scale_x = target_w / max(1, texture.width)
        sprite.scale_y = target_h / max(1, texture.height)

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


class PygletAudioBackend:
    """Pyglet-based audio backend implementing AudioBackend protocol.

    Uses a `pyglet.media.Player` per channel for playback, volume, and looping.
    Supports whole-file looping and seamless loop points (loop_start/loop_end).
    """

    def __init__(self) -> None:
        self._players: dict[str, pyglet.media.Player] = {}
        self._loop_points: dict[str, tuple[float | None, float | None]] = {}

    def play(
        self,
        channel: str,
        asset_path: str | Path,
        *,
        loop: bool = False,
        volume: float = 1.0,
        fade_in: float = 0.0,
        loop_start: float | None = None,
        loop_end: float | None = None,
    ) -> None:
        path_str = str(asset_path)
        if channel in self._players:
            old_player = self._players[channel]
            try:
                old_player.pause()
                old_player.delete()
            except Exception:  # noqa: BLE001, S110
                pass

        try:
            source = pyglet.media.load(path_str, streaming=True)
        except Exception:  # noqa: BLE001
            try:
                source = pyglet.media.load(path_str, streaming=False)
            except Exception:  # noqa: BLE001
                return

        player = pyglet.media.Player()
        player.queue(source)
        player.volume = max(0.0, min(1.0, volume))
        self._loop_points[channel] = (loop_start, loop_end)

        if loop:
            if loop_start is None and loop_end is None:
                player.loop = True
            else:
                player.loop = False

                @player.event
                def on_player_eos() -> None:
                    seek_pos = loop_start if loop_start is not None else 0.0
                    try:
                        player.seek(seek_pos)
                        player.play()
                    except Exception:  # noqa: BLE001, S110
                        pass
        else:
            player.loop = False

        self._players[channel] = player
        player.play()

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        player = self._players.get(channel)
        if player is not None:
            try:
                player.pause()
                player.delete()
            except Exception:  # noqa: BLE001, S110
                pass
            del self._players[channel]
            self._loop_points.pop(channel, None)

    def set_volume(self, channel: str, volume: float) -> None:
        player = self._players.get(channel)
        if player is not None:
            player.volume = max(0.0, min(1.0, volume))

    def pause(self, channel: str) -> None:
        player = self._players.get(channel)
        if player is not None:
            player.pause()

    def resume(self, channel: str) -> None:
        player = self._players.get(channel)
        if player is not None:
            player.play()

    def is_playing(self, channel: str) -> bool:
        player = self._players.get(channel)
        return bool(player is not None and player.playing)

    def update(self, dt: float) -> None:
        for ch, player in list(self._players.items()):
            if not player.playing:
                continue
            loop_start, loop_end = self._loop_points.get(ch, (None, None))
            if loop_end is not None and player.time >= loop_end:
                seek_pos = loop_start if loop_start is not None else 0.0
                try:
                    player.seek(seek_pos)
                    player.play()
                except Exception:  # noqa: BLE001, S110
                    pass

    def shutdown(self) -> None:
        for player in list(self._players.values()):
            try:
                player.pause()
                player.delete()
            except Exception:  # noqa: BLE001, S110
                pass
        self._players.clear()
        self._loop_points.clear()


class PygletPlayer(pyglet.window.Window):
    """Full-featured interactive Visual Novel window player powered by Eager and Eager-Graphics."""

    def __init__(
        self,
        vm: StoryVM | None = None,
        compositor: StageCompositor | None = None,
        director: StageDirector | None = None,
        dispatcher: EventDispatcher | None = None,
        *,
        session: Any | None = None,
        audio: AudioMixer | None = None,
        width: int = 1280,
        height: int = 720,
        title: str = "Eager-Graphics Visual Novel (Pyglet)",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        vsync: bool = True,
        visible: bool = True,
        show_fps: bool = True,
        uncapped: bool = False,
    ) -> None:
        if uncapped:
            vsync = False
        self.uncapped: bool = uncapped
        super().__init__(
            width=width,
            height=height,
            caption=title,
            resizable=True,
            vsync=vsync,
            visible=visible,
        )
        self.width = width
        self.height = height
        self.session = session
        if session is not None:
            self.vm = session.vm
            self.compositor = session.compositor
            self.director = session.director
            self.dispatcher = session.dispatcher
            self.audio = getattr(session, "audio", audio)
            self.keymap = getattr(session, "keymap", None) or Keymap()
            self.overlay = getattr(session, "overlay", None) or UIOverlay(width=width, height=height)
            self.overlay.set_viewport(width, height)
            if hasattr(session, "overlay"):
                session.overlay.set_viewport(width, height)
        else:
            self.vm = vm  # type: ignore[assignment]
            self.compositor = compositor  # type: ignore[assignment]
            self.director = director  # type: ignore[assignment]
            self.dispatcher = dispatcher  # type: ignore[assignment]
            self.audio = audio
            self.keymap = Keymap()
            self.overlay = UIOverlay(width=width, height=height)

        self.renderer = PygletRenderer(
            width=width,
            height=height,
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

        # UI elements batch
        self._ui_batch = Batch()

        # On-screen FPS debug overlay
        self.show_fps: bool = show_fps
        self._fps_label: Label = Label(
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

        # Step first beat if not starting in active menu
        has_active_screen = getattr(getattr(self.session, "screens", None), "is_active", False)
        if not has_active_screen:
            self.advance_story()

        # Schedule animation tick at 60 FPS
        pyglet.clock.schedule_interval(self.tick, 1.0 / 60.0)

    def on_resize(self, width: int, height: int) -> None:
        """Keep the UI components laid out against the new window size."""
        super().on_resize(width, height)
        self.overlay.set_viewport(width, height)
        if self.session is not None and hasattr(self.session, "overlay"):
            self.session.overlay.set_viewport(width, height)
        self.renderer.width = width
        self.renderer.height = height

    def _sync_overlay(self) -> None:
        """Mirror current narrative state onto the UI components.

        Called whenever the active choice prompt or dialogue changes so that
        input handling sees up-to-date layout even before the next draw.
        """
        self.current_speaker = self.director.ui_state.speaker
        self.current_text = self.director.ui_state.text
        self.current_emotion = self.director.ui_state.emotion
        self.overlay.sync(self.director.ui_state, self.active_choice_prompt)

    def advance_story(self) -> None:
        """Advance the story by one dialogue beat or hook."""
        if self.session is not None:
            self.session.advance()
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()
            return

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
        if self.session is not None:
            self.session.choose(choice_index)
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()
            return

        if self.active_choice_prompt is None:
            return

        if 0 <= choice_index < len(self.active_choice_prompt.options):
            self.active_choice_prompt = None
            self.vm.choose(choice_index)
            self.advance_story()

    def rollback(self) -> bool:
        """Rollback narrative and stage state by one beat."""
        if self.session is not None:
            success = self.session.rollback()
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()
            return success

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
        """Advance animations and pump audio mixer / session logic."""
        if self.session is not None:
            self.session.update(dt)
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            return

        self.compositor.step(dt)
        if self.audio is not None:
            self.audio.update(dt)

    def close(self) -> None:
        """Close window and release audio mixer resources."""
        if self.audio is not None:
            self.audio.shutdown()
        super().close()

    def run(self) -> None:
        """Run the interactive visual-novel main loop (blocks until window closes)."""
        pyglet.app.run()

    def on_draw(self) -> None:
        """Render frame: stage graphics followed by UI textbox, choices, screens, and FPS."""
        self.clear()

        if self.session is not None:
            self.session.draw(self.renderer, self.width, self.height)
        else:
            # 1. Render Stage Elements
            self.renderer.render_compositor(self.compositor, self.width, self.height)

            # 2-4. Dialogue textbox, branching choices, and story-end notice
            self.overlay.draw(
                self.renderer,
                self.director.ui_state,
                self.active_choice_prompt,
                is_finished=self.is_finished,
            )

        # 5. Render FPS counter
        if self.show_fps and self._fps_label is not None:
            self._draw_fps()

    def _draw_fps(self) -> None:
        """Update and draw the on-screen FPS counter overlay."""
        if self._fps_label is None:
            return
        fps = self.renderer.fps
        fps_avg = self.renderer.fps_avg
        frames = self.renderer.frame_count
        self._fps_label.text = f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})"
        self._fps_label.draw()

    def on_mouse_motion(self, x: int, y: int, dx: int, dy: int) -> None:
        """Handle mouse movement for screen and button hover states."""
        flipped_y = self.height - y
        if self.session is not None:
            self.session.handle_input(InputAction.POINTER_MOVE, x=x, y=flipped_y)

    def on_mouse_drag(
        self, x: int, y: int, dx: int, dy: int, buttons: int, modifiers: int
    ) -> None:
        """Handle mouse drag for sliders and interactive UI elements."""
        flipped_y = self.height - y
        if self.session is not None:
            self.session.handle_input(InputAction.POINTER_MOVE, x=x, y=flipped_y)
            if buttons & mouse.LEFT:
                self.session.handle_input(InputAction.POINTER_CLICK, x=x, y=flipped_y)
                self.active_choice_prompt = self.session.active_choice_prompt
                self.is_finished = self.session.is_finished
                self._sync_overlay()

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        """Handle mouse clicks for advancement, screens, or choice selection."""
        if button == mouse.RIGHT:
            if self.session is not None:
                self.session.handle_input(InputAction.GAME_MENU)
                self.active_choice_prompt = self.session.active_choice_prompt
                self.is_finished = self.session.is_finished
                self._sync_overlay()
            return

        if button != mouse.LEFT:
            return

        flipped_y = self.height - y
        if self.session is not None:
            self.session.handle_input(InputAction.POINTER_CLICK, x=x, y=flipped_y)
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()
            return

        # Fallback if running without session
        if self.active_choice_prompt is not None:
            index = self.overlay.hit_test_choice(x, flipped_y)
            if index is not None:
                self.make_choice(index)
            return

        self.advance_story()

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        """Handle keyboard input for advancing, choices, rollback, save/load, and menus."""
        sym_str = key.symbol_string(symbol).lower()
        if sym_str.startswith("_") and len(sym_str) == 2 and sym_str[1].isdigit():
            sym_str = sym_str[1]
        elif sym_str.startswith("num_") and len(sym_str) == 5 and sym_str[4].isdigit():
            sym_str = sym_str[4]
        elif sym_str == "num_enter":
            sym_str = "enter"

        if self.session is not None:
            # 1-9 choice keys
            if self.active_choice_prompt is not None and sym_str in "123456789":
                idx = int(sym_str) - 1
                if idx < len(self.active_choice_prompt.options):
                    self.session.handle_input(InputAction.CHOOSE, index=idx)
                    self.active_choice_prompt = self.session.active_choice_prompt
                    self.is_finished = self.session.is_finished
                    self._sync_overlay()
                    return

            action = self.keymap.map_key(sym_str)
            if action == InputAction.QUIT:
                self.close()
                return
            elif action == InputAction.DEBUG_OVERLAY:
                self.show_fps = not self.show_fps
                return
            elif action:
                self.session.handle_input(action)
                self.active_choice_prompt = self.session.active_choice_prompt
                self.is_finished = self.session.is_finished
                self._sync_overlay()
                return

        # Fallback if running without session
        if symbol in (key.SPACE, key.RETURN) or sym_str in ("space", "enter"):
            if self.active_choice_prompt is None:
                self.advance_story()
        elif self.active_choice_prompt is not None:
            if len(sym_str) == 1 and sym_str in "123456789":
                idx = int(sym_str) - 1
                if idx < len(self.active_choice_prompt.options):
                    self.make_choice(idx)
        elif symbol == key.BACKSPACE or sym_str == "backspace":
            self.rollback()
        elif symbol == key.F3 or sym_str == "f3":
            self.show_fps = not self.show_fps
        elif symbol in (key.ESCAPE, key.Q) or sym_str in ("escape", "q"):
            self.close()

    def on_key_release(self, symbol: int, modifiers: int) -> None:
        """Handle key releases (e.g. releasing Ctrl stops fast-forward skip)."""
        sym_str = key.symbol_string(symbol).lower()
        if sym_str in ("ctrl", "lctrl", "rctrl") and self.session is not None:
            self.session.handle_input(InputAction.SKIP_RELEASE)

    def on_mouse_scroll(self, x: int, y: int, scroll_x: float, scroll_y: float) -> None:
        """Handle mouse wheel scrolling for rollback, roll-forward, or screen scrolling."""
        if self.session is not None:
            if scroll_y > 0:
                self.session.handle_input(InputAction.ROLLBACK)
            elif scroll_y < 0:
                self.session.handle_input(InputAction.ROLL_FORWARD)
            self.active_choice_prompt = self.session.active_choice_prompt
            self.is_finished = self.session.is_finished
            self._sync_overlay()
