"""Raylib rendering backend and interactive player for Eager-Graphics.

This module provides three classes that mirror the surface area of the Pyglet
and PIL backends:

* :class:`RaylibAssetResolver` — loads textures from disk or generates
  procedural placeholders (mirrors :class:`PygletAssetResolver`).
* :class:`RaylibRenderer` — implements both the
  :class:`~eager_graphics.protocol.RenderBackend` and
  :class:`~eager_graphics.protocol.UIDrawBackend` protocols using Raylib's
  2D drawing primitives.
* :class:`RaylibPlayer` — an interactive visual-novel window that runs its own
  event loop (mirrors :class:`PygletPlayer`).

The ``pyray`` module (provided by the ``raylib`` PyPI package) must be
installed.  All drawing calls require an active Raylib drawing context
(``pyray.begin_drawing`` / ``pyray.end_drawing``), which is created either by
the :class:`RaylibPlayer` or explicitly by the caller before invoking
:meth:`RaylibRenderer.render_compositor`.

Raylib's 2D coordinate system uses a **top-left origin** (``y`` increases
downward), identical to PIL — no vertical flip is required for UI primitives,
unlike the Pyglet backend.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import pyray

    RAYLIB_AVAILABLE = True
except ImportError as err:
    RAYLIB_AVAILABLE = False
    _raylib_import_error: Any = err

from eager_core.input import InputAction, Keymap

from eager_graphics.layout import ViewportTransform

# Protocol import is always available (RenderBackend is a typing.Protocol)
from eager_graphics.protocol import RenderBackend, RenderItem, UIDrawBackend
from eager_graphics.timing import FrameClock
from eager_graphics.types import BLACK, WHITE, Color, ScaleMode
from eager_graphics.ui_components import UIOverlay

if TYPE_CHECKING:
    from eager_core.audio import AudioMixer
    from eager_runtime import ChoicePromptEvent, EventDispatcher, StoryVM

    from eager_graphics.compositor import StageCompositor
    from eager_graphics.director import StageDirector


_EXTENSIONS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")


def _check_raylib_available() -> None:
    """Raise a helpful ``ImportError`` if pyray is not installed."""
    if not RAYLIB_AVAILABLE:
        msg = (
            "Raylib (pyray) is not installed. Install with "
            "'pip install eager-graphics[raylib]' or 'pip install raylib'."
        )
        raise ImportError(msg) from _raylib_import_error


def _to_pyray_color(color: Color) -> Any:
    """Convert an Eager :class:`~eager_graphics.types.Color` to a ``pyray.Color``.

    Eager colors use normalised floats [0.0, 1.0]; Raylib colours use 0–255
    integers.
    """
    r, g, b, a = color.to_rgba_bytes()
    return pyray.Color(r, g, b, a)


class RaylibAssetResolver:
    """Loads and caches textures from disk, generating procedural placeholders when missing.

    Mirrors :class:`~eager_graphics.renderers.pyglet.PygletAssetResolver` and
    :class:`~eager_graphics.renderers.pil.PILAssetResolver` but returns
    ``pyray.Texture2D`` objects.

    Texture creation requires an active OpenGL context (``pyray.init_window``
    must have been called), so :meth:`get_texture` should only be invoked
    after a window has been created.
    """

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        _check_raylib_available()
        self.asset_dir = Path(asset_dir) if asset_dir is not None else None
        self._texture_cache: dict[str, Any] = {}

    def get_texture(
        self,
        asset_id: str,
        default_width: int = 400,
        default_height: int = 800,
    ) -> Any:
        """Retrieve a cached texture, load from disk, or generate a placeholder.

        Parameters
        ----------
        asset_id
            Identifier of the asset (e.g. ``"bg/castle"`` or ``"alice/happy"``).
        default_width, default_height
            Dimensions for procedurally generated placeholders when the asset
            file is not found on disk.

        Returns
        -------
        pyray.Texture2D
            A GPU texture ready for ``pyray.draw_texture_pro``.
        """
        tex = self._texture_cache.get(asset_id)
        if tex is not None:
            return tex

        # Built-in 1×1 white-pixel texture used for fades / flashes.
        if asset_id == "__builtin_color_rect__":
            img = pyray.gen_image_color(1, 1, pyray.WHITE)
            tex = pyray.load_texture_from_image(img)
            pyray.unload_image(img)
            self._texture_cache[asset_id] = tex
            return tex

        # 1. Attempt loading from disk if asset_dir is configured
        if self.asset_dir is not None:
            for ext in _EXTENSIONS:
                file_path = self.asset_dir / f"{asset_id}{ext}"
                if file_path.is_file():
                    try:
                        tex = pyray.load_texture(str(file_path))
                        self._texture_cache[asset_id] = tex
                        return tex
                    except (OSError, RuntimeError):
                        pass

        # 2. Generate procedural placeholder
        tex = self._generate_placeholder(asset_id, default_width, default_height)
        self._texture_cache[asset_id] = tex
        return tex

    # ``get_image`` is an alias used by renderer-agnostic callers that expect
    # this method name (mirrors the PIL backend's interface).
    get_image = get_texture

    def unload_all(self) -> None:
        """Unload all cached GPU textures and clear the cache.

        Call this before :func:`pyray.close_window` to avoid Wayland segfaults
        caused by releasing the OpenGL context while textures are still bound.
        """
        for tex in self._texture_cache.values():
            try:
                pyray.unload_texture(tex)
            except (AttributeError, RuntimeError, TypeError, OSError):
                pass
        self._texture_cache.clear()

    def _generate_placeholder(
        self,
        asset_id: str,
        width: int,
        height: int,
    ) -> Any:
        """Procedurally generate a solid-color placeholder texture.

        Produces a deterministic colour (derived from an MD5 hash of
        *asset_id*) matching the visual style of the Pyglet and PIL backends.
        """
        is_bg = asset_id.startswith("bg/") or "background" in asset_id
        w = 1920 if is_bg else width
        h = 1080 if is_bg else height

        # Deterministic colour derivation from asset_id string hash
        h_val = int(hashlib.md5(asset_id.encode("utf-8")).hexdigest()[:8], 16)
        r = h_val & 0xFF
        g = (h_val >> 8) & 0xFF
        b = (h_val >> 16) & 0xFF

        if is_bg:
            r = 30 + (r % 60)
            g = 35 + (g % 60)
            b = 45 + (b % 70)
        else:
            r = 100 + (r % 120)
            g = 100 + (g % 120)
            b = 100 + (b % 120)

        img = pyray.gen_image_color(w, h, pyray.Color(r, g, b, 255))
        tex = pyray.load_texture_from_image(img)
        pyray.unload_image(img)
        return tex


class RaylibRenderer(RenderBackend, UIDrawBackend):
    """Raylib 2D stage renderer.

    Implements the full :class:`~eager_graphics.protocol.RenderBackend` and
    :class:`~eager_graphics.protocol.UIDrawBackend` protocol using Raylib's
    immediate-mode 2D drawing API.

    Like :class:`PygletRenderer`, ``begin_frame`` / ``end_frame`` perform only
    internal bookkeeping — the caller is responsible for wrapping rendering
    in ``pyray.begin_drawing()`` / ``pyray.end_drawing()`` (typically done by
    :meth:`RaylibPlayer.on_draw` or by tests with a window fixture).
    """

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        *,
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
    ) -> None:
        _check_raylib_available()
        self.asset_resolver = RaylibAssetResolver(asset_dir)
        self.scale_mode = scale_mode
        self.width = width
        self.height = height
        self.clear_color: Color = BLACK
        self._in_frame: bool = False
        self._frame_buffer: list[RenderItem] = []
        self.last_frame: list[RenderItem] = []
        self.frame_count: int = 0
        self._current_transform: ViewportTransform | None = None
        self.clock: FrameClock = FrameClock()
        self._font: Any | None = None

    # ------------------------------------------------------------------ #
    # RenderBackend protocol
    # ------------------------------------------------------------------ #

    def begin_frame(self) -> None:
        """Begin a new frame — clears internal state.

        Does **not** call ``pyray.begin_drawing()`` — the caller must do that
        to establish a GPU drawing context.
        """
        if self._in_frame:
            msg = "begin_frame called without matching end_frame"
            raise RuntimeError(msg)
        self._frame_buffer = []
        self._in_frame = True

    def clear(self, color: Color = BLACK) -> None:
        """Store the framebuffer clear color.

        Like :meth:`NullRenderer.clear`, this does **not** immediately issue a
        GPU clear.  The actual ``pyray.clear_background()`` call is performed by
        :meth:`render_compositor` (or by the caller) inside an active drawing
        context.
        """
        self.clear_color = color

    def draw_item(self, item: RenderItem) -> None:
        """Render a single compositor :class:`~eager_graphics.protocol.RenderItem`."""
        if not self._in_frame:
            msg = "draw_item called outside of begin_frame/end_frame block"
            raise RuntimeError(msg)

        self._frame_buffer.append(item)

        # Early discard: invisible or degenerate items.
        if item.opacity <= 0.0 or not (item.scale_x and item.scale_y) or item.tint.a <= 0.0:
            return

        if self._current_transform is None:
            msg = "draw_item called before render_compositor set the viewport transform"
            raise RuntimeError(msg)

        # Resolve the texture from the asset resolver.
        is_bg = item.layer == "background" or item.asset_id.startswith("bg/")
        def_w = 1920 if is_bg else 400
        def_h = 1080 if is_bg else 800
        texture = self.asset_resolver.get_texture(item.asset_id, def_w, def_h)

        # --- dimensions in virtual coordinates ---
        tex_w = texture.width
        tex_h = texture.height
        eff_w = tex_w * abs(item.scale_x)
        eff_h = tex_h * abs(item.scale_y)

        # --- anchor offset factor ---
        fx, fy = item.anchor.get_offset_factor()

        # --- project dimensions to physical screen coordinates ---
        draw_w = max(1, eff_w * self._current_transform.scale_x)
        draw_h = max(1, eff_h * self._current_transform.scale_y)

        # --- anchor screen position (top-left origin, no flip needed) ---
        anchor_s_x, anchor_s_y = self._current_transform.to_screen(item.x, item.y)

        # --- source rectangle (handles horizontal / vertical flips) ---
        # When the net flip is active (flip_h XOR scale_x < 0), we set a
        # negative source width/height and offset the source origin so that
        # raylib mirrors the texture correctly.
        scale_x_neg = item.scale_x < 0
        scale_y_neg = item.scale_y < 0
        flip_h = item.flip_h ^ scale_x_neg  # XOR: double-flip cancels out
        flip_v = item.flip_v ^ scale_y_neg

        if flip_h:
            src_x = float(tex_w)
            src_w = float(-tex_w)
        else:
            src_x = 0.0
            src_w = float(tex_w)

        if flip_v:
            src_y = float(tex_h)
            src_h = float(-tex_h)
        else:
            src_y = 0.0
            src_h = float(tex_h)

        source = pyray.Rectangle(src_x, src_y, src_w, src_h)

        # --- destination rectangle and origin (rotation pivot) ---
        origin_x = draw_w * fx
        origin_y = draw_h * fy

        dest = pyray.Rectangle(anchor_s_x, anchor_s_y, draw_w, draw_h)
        origin = pyray.Vector2(origin_x, origin_y)

        # --- combined tint + opacity ---
        final_alpha = max(0.0, min(1.0, item.opacity * item.tint.a))
        tr, tg, tb = item.tint.to_rgba_bytes()[:3]
        tint_color = pyray.Color(tr, tg, tb, round(final_alpha * 255))

        # --- rotation (raylib rotates clockwise; negate to match the
        #     counter-clockwise convention used by Pyglet / PIL) ---
        rotation = -item.rotation

        pyray.draw_texture_pro(texture, source, dest, origin, rotation, tint_color)

    def end_frame(self) -> None:
        """Conclude the frame.

        Publishes :attr:`last_frame`, draws letterbox bars, and ticks the FPS
        clock.  Does **not** call ``pyray.end_drawing()`` — the caller owns
        the drawing context.
        """
        if not self._in_frame:
            msg = "end_frame called without matching begin_frame"
            raise RuntimeError(msg)

        self.last_frame = self._frame_buffer
        self._frame_buffer = []
        self._in_frame = False

        self.frame_count += 1
        self.clock.tick()

    # ------------------------------------------------------------------ #
    # FPS properties (delegate to the FrameClock)
    # ------------------------------------------------------------------ #

    @property
    def fps(self) -> float:
        return self.clock.fps

    @property
    def fps_avg(self) -> float:
        return self.clock.fps_avg

    @property
    def fps_overall(self) -> float:
        return self.clock.fps_overall

    # ------------------------------------------------------------------ #
    # Convenience: render a full compositor frame
    # ------------------------------------------------------------------ #

    def render_compositor(
        self,
        compositor: StageCompositor,
        window_width: int,
        window_height: int,
    ) -> None:
        """Render all active compositor layers to the window.

        Caller must wrap the call in ``pyray.begin_drawing()`` /
        ``pyray.end_drawing()``.
        """
        self.width = window_width
        self.height = window_height
        self._current_transform = compositor.layout.compute_viewport_transform(
            window_width,
            window_height,
            mode=self.scale_mode,
        )

        self.begin_frame()
        pyray.clear_background(_to_pyray_color(self.clear_color))

        items = compositor.render_list()
        for item in items:
            self.draw_item(item)

        self.end_frame()

        # Draw letterbox / pillarbox bars (after end_frame so they appear
        # on top of transparent gaps around the stage layer).
        trans = self._current_transform
        bar_color = _to_pyray_color(BLACK)
        win_w, win_h = self.width, self.height
        if trans.offset_x > 0:
            ox = int(trans.offset_x)
            pyray.draw_rectangle(0, 0, ox, win_h, bar_color)
            pyray.draw_rectangle(win_w - ox, 0, ox, win_h, bar_color)
        if trans.offset_y > 0:
            oy = int(trans.offset_y)
            pyray.draw_rectangle(0, 0, win_w, oy, bar_color)
            pyray.draw_rectangle(0, win_h - oy, win_w, oy, bar_color)

    # ------------------------------------------------------------------ #
    # UIDrawBackend primitives
    #
    # All coordinates arrive in window pixels with a top-left origin, which
    # matches Raylib's native 2D coordinate system — no Y-flip is required.
    # ------------------------------------------------------------------ #

    def _get_font(self) -> Any:
        """Return (and cache) Raylib's default font."""
        if self._font is None:
            self._font = pyray.get_font_default()
        return self._font

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
        col = _to_pyray_color(color)
        pyray.draw_rectangle(int(x), int(y), int(width), int(height), col)

        if border_color is not None and border_width > 0.0:
            rec = pyray.Rectangle(float(x), float(y), float(width), float(height))
            pyray.draw_rectangle_lines_ex(rec, float(border_width), _to_pyray_color(border_color))

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
        font = self._get_font()
        col = _to_pyray_color(color)

        # If the anchor is anything other than top-left, measure the text and
        # adjust the position so the anchor point lands at (x, y).
        need_measure = anchor_x != "left" or anchor_y != "top"
        if need_measure and text:
            measures = pyray.measure_text_ex(font, text, font_size, 0.0)
            tw, th = float(measures.x), float(measures.y)
            if anchor_x == "center":
                x -= tw / 2.0
            elif anchor_x == "right":
                x -= tw
            if anchor_y == "middle":
                y -= th / 2.0
            elif anchor_y == "bottom":
                y -= th

        pyray.draw_text_ex(font, text, pyray.Vector2(float(x), float(y)), font_size, 0.0, col)

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
        """Draw a resolved asset scaled into the given box, with optional tint."""
        tex = self.asset_resolver.get_texture(
            asset_id, max(1, round(width)), max(1, round(height))
        )
        tex_w, tex_h = tex.width, tex.height

        # Adjust position for anchors (default: top-left).
        dest_x = float(x)
        dest_y = float(y)
        if anchor_x == "center":
            dest_x -= width / 2.0
        elif anchor_x == "right":
            dest_x -= width
        if anchor_y == "middle":
            dest_y -= height / 2.0
        elif anchor_y == "bottom":
            dest_y -= height

        dest = pyray.Rectangle(dest_x, dest_y, float(width), float(height))
        source = pyray.Rectangle(0, 0, float(tex_w), float(tex_h))
        origin = pyray.Vector2(0.0, 0.0)

        pyray.draw_texture_pro(tex, source, dest, origin, 0.0, _to_pyray_color(tint))

    def measure_text(self, text: str, *, font_size: int = 14) -> tuple[float, float]:
        """Return the ``(width, height)`` the given text would occupy."""
        font = self._get_font()
        measures = pyray.measure_text_ex(font, text, font_size, 0.0)
        return (float(measures.x), float(measures.y))

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self.last_frame)

    def __repr__(self) -> str:
        return (
            f"RaylibRenderer(width={self.width}, height={self.height}, "
            f"frame_count={self.frame_count}, last_frame_items={len(self.last_frame)}, "
            f"fps={self.clock.fps:.1f})"
        )


class RaylibAudioBackend:
    """Raylib audio backend using LoadMusicStream and UpdateAudioStream.

    Manages audio devices via pyray.init_audio_device/close_audio_device and
    streams per-channel audio using Raylib's Music streams.
    """

    def __init__(self) -> None:
        _check_raylib_available()
        self._device_initialized = False
        if not pyray.is_audio_device_ready():
            pyray.init_audio_device()
            self._device_initialized = True
        self._streams: dict[str, Any] = {}
        self._loop_points: dict[str, tuple[float | None, float | None]] = {}
        self._paused: set[str] = set()

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
        if channel in self._streams:
            old_stream = self._streams[channel]
            try:
                pyray.stop_music_stream(old_stream)
                pyray.unload_music_stream(old_stream)
            except Exception:  # noqa: BLE001, S110
                pass

        try:
            stream = pyray.load_music_stream(path_str)
        except Exception:  # noqa: BLE001
            return

        stream.looping = loop
        # Check for raylib SetMusicLoopPoints / set_music_loop_points if available
        if hasattr(pyray, "set_music_loop_points") and loop_start is not None and loop_end is not None:
            try:
                pyray.set_music_loop_points(stream, float(loop_start), float(loop_end))
            except Exception:  # noqa: BLE001, S110
                pass
        elif hasattr(pyray, "SetMusicLoopPoints") and loop_start is not None and loop_end is not None:
            try:
                pyray.SetMusicLoopPoints(stream, float(loop_start), float(loop_end))
            except Exception:  # noqa: BLE001, S110
                pass

        pyray.set_music_volume(stream, max(0.0, min(1.0, volume)))
        pyray.play_music_stream(stream)
        self._streams[channel] = stream
        self._loop_points[channel] = (loop_start, loop_end)
        self._paused.discard(channel)

    def stop(self, channel: str, *, fade_out: float = 0.0) -> None:
        stream = self._streams.get(channel)
        if stream is not None:
            try:
                pyray.stop_music_stream(stream)
                pyray.unload_music_stream(stream)
            except Exception:  # noqa: BLE001, S110
                pass
            del self._streams[channel]
            self._loop_points.pop(channel, None)
            self._paused.discard(channel)

    def set_volume(self, channel: str, volume: float) -> None:
        stream = self._streams.get(channel)
        if stream is not None:
            pyray.set_music_volume(stream, max(0.0, min(1.0, volume)))

    def pause(self, channel: str) -> None:
        stream = self._streams.get(channel)
        if stream is not None:
            pyray.pause_music_stream(stream)
            self._paused.add(channel)

    def resume(self, channel: str) -> None:
        stream = self._streams.get(channel)
        if stream is not None:
            pyray.resume_music_stream(stream)
            self._paused.discard(channel)

    def is_playing(self, channel: str) -> bool:
        stream = self._streams.get(channel)
        if stream is None or channel in self._paused:
            return False
        return bool(pyray.is_music_stream_playing(stream))

    def update(self, dt: float) -> None:
        for ch, stream in list(self._streams.items()):
            if ch not in self._paused:
                pyray.update_music_stream(stream)
                loop_start, loop_end = self._loop_points.get(ch, (None, None))
                if loop_end is not None:
                    time_played = pyray.get_music_time_played(stream)
                    if time_played >= loop_end:
                        seek_pos = loop_start if loop_start is not None else 0.0
                        pyray.seek_music_stream(stream, float(seek_pos))

    def shutdown(self) -> None:
        for stream in list(self._streams.values()):
            try:
                pyray.stop_music_stream(stream)
                pyray.unload_music_stream(stream)
            except Exception:  # noqa: BLE001, S110
                pass
        self._streams.clear()
        self._loop_points.clear()
        self._paused.clear()
        if self._device_initialized and pyray.is_audio_device_ready():
            pyray.close_audio_device()
            self._device_initialized = False


# ---------------------------------------------------------------------- #
# Interactive Player
# ---------------------------------------------------------------------- #


class RaylibPlayer:
    """Full-featured interactive visual-novel player powered by Raylib.

    Creates its own window via ``pyray.init_window`` and runs the main loop
    in :meth:`run`.  Shares the same narrative-interface as
    :class:`~eager_graphics.renderers.pyglet.PygletPlayer`:
    ``advance_story()``, ``make_choice(idx)``, ``rollback()``,
    ``on_draw()``, ``active_choice_prompt``, ``is_finished``, ``close()``.
    """

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
        title: str = "Eager Visual Novel (Raylib)",
        asset_dir: str | Path | None = None,
        scale_mode: ScaleMode = ScaleMode.LETTERBOX,
        vsync: bool = True,
        visible: bool = True,
        show_fps: bool = True,
    ) -> None:
        _check_raylib_available()
        pyray.set_trace_log_level(pyray.LOG_WARNING)
        if vsync:
            pyray.set_config_flags(pyray.FLAG_VSYNC_HINT)
        pyray.init_window(width, height, title)
        pyray.set_target_fps(60)

        self.session = session
        if session is not None:
            self.vm = session.vm
            self.compositor = session.compositor
            self.director = session.director
            self.dispatcher = session.dispatcher
            self.audio = getattr(session, "audio", audio)
            self.keymap = getattr(session, "keymap", None) or Keymap()
            self.overlay = getattr(session, "overlay", None) or UIOverlay(width=width, height=height)
        else:
            self.vm = vm  # type: ignore[assignment]
            self.compositor = compositor  # type: ignore[assignment]
            self.director = director  # type: ignore[assignment]
            self.dispatcher = dispatcher  # type: ignore[assignment]
            self.audio = audio
            self.keymap = Keymap()
            self.overlay = UIOverlay(width=width, height=height)

        self.width = width
        self.height = height
        self.active_choice_prompt: ChoicePromptEvent | None = None
        self.is_finished: bool = False
        self.current_speaker: str | None = None
        self.current_text: str = ""
        self.current_emotion: str | None = None
        self.show_fps: bool = show_fps

        # Renderer-agnostic stage renderer
        self.renderer = RaylibRenderer(
            asset_dir=asset_dir,
            scale_mode=scale_mode,
            width=width,
            height=height,
        )

        # Enable visual history rollback on director
        self.director.enable_visual_history()

        # Step first beat if not starting in active menu
        has_active_screen = getattr(getattr(self.session, "screens", None), "is_active", False)
        if not has_active_screen:
            self.advance_story()

    # ------------------------------------------------------------------ #
    # Narrative control (identical interface to PygletPlayer)
    # ------------------------------------------------------------------ #

    def _sync_overlay(self) -> None:
        """Mirror current narrative state onto the UI components."""
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
            self._sync_overlay()
            return

        # Snapshot visual and UI state before advancing to the next narrative beat
        self.director.snapshot_visual_state()

        while not self.vm.is_ended:
            event = self.vm.step()
            if event is None:
                self.is_finished = True
                break

            self.dispatcher.dispatch(event)

            if event.type == "dialogue":
                diag = event  # type: ignore[attr-defined]
                self.current_speaker = diag.speaker
                self.current_text = diag.text
                self.current_emotion = diag.emotion
                break

            if event.type == "narration":
                narr = event  # type: ignore[attr-defined]
                self.current_speaker = None
                self.current_text = narr.text
                self.current_emotion = None
                break

            if event.type == "append":
                self.current_text += f" {event.text}"  # type: ignore[attr-defined]
                break

            if event.type == "fresh_box":
                self.current_text = event.text  # type: ignore[attr-defined]
                break

            if event.type == "choice_prompt":
                self.active_choice_prompt = event  # type: ignore[assignment]
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

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def on_draw(self) -> None:
        """Render one frame: stage graphics followed by UI textbox, choices, screens, and FPS."""
        pyray.begin_drawing()
        pyray.clear_background(pyray.BLACK)

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
        if self.show_fps:
            fps = self.renderer.fps
            fps_avg = self.renderer.fps_avg
            frames = self.renderer.frame_count
            pyray.draw_text(
                f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})",
                10,
                10,
                20,
                pyray.Color(230, 230, 230, 200),
            )

        pyray.end_drawing()

    # ------------------------------------------------------------------ #
    # Input handling (integrated into the main loop)
    # ------------------------------------------------------------------ #

    def _handle_input(self) -> None:
        """Process keyboard and mouse input for advancing, choices, rollback, exit."""
        mx = float(pyray.get_mouse_x())
        my = float(pyray.get_mouse_y())

        if self.session is not None:
            self.session.handle_input(InputAction.POINTER_MOVE, x=mx, y=my)

            if pyray.is_mouse_button_pressed(pyray.MOUSE_LEFT_BUTTON):
                self.session.handle_input(InputAction.POINTER_CLICK, x=mx, y=my)
                self.active_choice_prompt = self.session.active_choice_prompt
                self.is_finished = self.session.is_finished
                self._sync_overlay()

            # Mouse wheel scrolling
            wheel_move = pyray.get_mouse_wheel_move()
            if wheel_move > 0:
                self.session.handle_input(InputAction.ROLLBACK)
                self.active_choice_prompt = self.session.active_choice_prompt
                self.is_finished = self.session.is_finished
                self._sync_overlay()
            elif wheel_move < 0:
                self.session.handle_input(InputAction.ROLL_FORWARD)
                self.active_choice_prompt = self.session.active_choice_prompt
                self.is_finished = self.session.is_finished
                self._sync_overlay()

            # Key release (Ctrl skip release)
            if pyray.is_key_released(pyray.KEY_LEFT_CONTROL) or pyray.is_key_released(pyray.KEY_RIGHT_CONTROL):
                self.session.handle_input(InputAction.SKIP_RELEASE)

            # Check 1-9 choice keys
            if self.active_choice_prompt is not None:
                num_keys = [
                    pyray.KEY_ONE, pyray.KEY_TWO, pyray.KEY_THREE,
                    pyray.KEY_FOUR, pyray.KEY_FIVE, pyray.KEY_SIX,
                    pyray.KEY_SEVEN, pyray.KEY_EIGHT, pyray.KEY_NINE,
                ]
                for idx, k in enumerate(num_keys):
                    if pyray.is_key_pressed(k) and idx < len(self.active_choice_prompt.options):
                        self.session.handle_input(InputAction.CHOOSE, index=idx)
                        self.active_choice_prompt = self.session.active_choice_prompt
                        self.is_finished = self.session.is_finished
                        self._sync_overlay()
                        return

            # Key mappings
            ray_key_map = [
                (pyray.KEY_SPACE, "space"),
                (pyray.KEY_ENTER, "enter"),
                (pyray.KEY_UP, "up"),
                (pyray.KEY_DOWN, "down"),
                (pyray.KEY_BACKSPACE, "backspace"),
                (pyray.KEY_PAGE_UP, "pageup"),
                (pyray.KEY_PAGE_DOWN, "pagedown"),
                (pyray.KEY_TAB, "tab"),
                (pyray.KEY_LEFT_CONTROL, "ctrl"),
                (pyray.KEY_RIGHT_CONTROL, "ctrl"),
                (pyray.KEY_A, "a"),
                (pyray.KEY_H, "h"),
                (pyray.KEY_V, "v"),
                (pyray.KEY_F5, "f5"),
                (pyray.KEY_F9, "f9"),
                (pyray.KEY_ESCAPE, "escape"),
                (pyray.KEY_F3, "f3"),
                (pyray.KEY_Q, "q"),
            ]
            for rk, key_name in ray_key_map:
                if pyray.is_key_pressed(rk):
                    action = self.keymap.map_key(key_name)
                    if action == InputAction.QUIT:
                        pyray.close_window()
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
            return

        # Fallback if running without session
        if pyray.is_key_pressed(pyray.KEY_SPACE) or pyray.is_key_pressed(pyray.KEY_ENTER):
            if self.active_choice_prompt is None:
                self.advance_story()
        elif self.active_choice_prompt is not None:
            num_keys = [
                pyray.KEY_ONE, pyray.KEY_TWO, pyray.KEY_THREE,
                pyray.KEY_FOUR, pyray.KEY_FIVE, pyray.KEY_SIX,
                pyray.KEY_SEVEN, pyray.KEY_EIGHT, pyray.KEY_NINE,
            ]
            for idx, k in enumerate(num_keys):
                if pyray.is_key_pressed(k) and idx < len(
                    self.active_choice_prompt.options
                ):
                    self.make_choice(idx)
                    break
        elif pyray.is_key_pressed(pyray.KEY_BACKSPACE):
            self.rollback()
        elif pyray.is_key_pressed(pyray.KEY_F3):
            self.show_fps = not self.show_fps

        if pyray.is_key_pressed(pyray.KEY_ESCAPE) or pyray.is_key_pressed(pyray.KEY_Q):
            pyray.close_window()

        if pyray.is_mouse_button_pressed(pyray.MOUSE_LEFT_BUTTON):
            if self.active_choice_prompt is not None:
                index = self.overlay.hit_test_choice(mx, my)
                if index is not None:
                    self.make_choice(index)
            else:
                self.advance_story()

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """Run the interactive visual-novel main loop (blocks until window closes)."""
        while not pyray.window_should_close():
            dt = pyray.get_frame_time()
            self.tick(dt)
            self._handle_input()
            self.on_draw()

        self.close()

    def close(self) -> None:
        """Close the Raylib window and free resources."""
        if self.audio is not None:
            self.audio.shutdown()
        pyray.close_window()
