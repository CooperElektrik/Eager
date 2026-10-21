"""Interactive Tkinter window shell and headless player driver for Pillow."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from eager_graphics.player import BasePlayer
from eager_graphics.types import DebugOverlayMode, ScaleMode

from ._compat import PIL_AVAILABLE, TKINTER_AVAILABLE, _TclError, tk
from .renderer import PILRenderer

if TYPE_CHECKING or PIL_AVAILABLE:

    class PILPlayer(BasePlayer):
        """Thin interactive window shell driving a :class:`GameSession` with Pillow frames.

        The player owns no narrative state: all story advancement, branching,
        rollback, typewriter reveal, and input semantics live in the injected
        :class:`~eager_runtime.session.GameSession`.  Window events are forwarded
        to ``session.handle_input(...)`` and frames are produced by
        ``session.draw(...)``.  Only Pillow is required to construct and drive
        the player headless; the tkinter window is created lazily by :meth:`run`,
        so only entering the event loop needs Tk bindings.
        """

        def __init__(
            self,
            *,
            session: Any,
            width: int = 1280,
            height: int = 720,
            title: str = "Eager-Graphics Visual Novel (PIL)",
            asset_dir: str | Path | None = None,
            scale_mode: ScaleMode = ScaleMode.LETTERBOX,
            vsync: bool = True,
            visible: bool = True,
            show_fps: bool | str | DebugOverlayMode = True,
            uncapped: bool = False,
        ) -> None:
            super().__init__(
                session=session,
                width=width,
                height=height,
                title=title,
                asset_dir=asset_dir,
                scale_mode=scale_mode,
                vsync=vsync,
                visible=visible,
                show_fps=show_fps,
                uncapped=uncapped,
            )
            self.vsync: bool = vsync and not uncapped
            self.visible: bool = visible

            self.renderer = PILRenderer(
                width=width,
                height=height,
                asset_dir=asset_dir,
                scale_mode=scale_mode,
            )

            self._fps_widget: Any = None
            self._last_debug_update: float = 0.0
            self._last_render_path: str = "None"

            self._photo: Any = None
            self._last_visible_chars: int | None = None
            self._last_input_cursor: bool | None = None

            # tkinter window objects — created lazily by run() so that
            # construction and story logic stay headless-safe.
            self._root: Any = None
            self._label: Any = None
            self._closed: bool = False
            self._last_tick: float = 0.0

            # Step first beat if not starting in active menu
            self.step_initial_beat()

            # Pre-load all assets and warm the sprite cache so the first
            # visible frame doesn't pay disk-I/O + resize costs (which would
            # cause a visible frame drop / hitch).
            self.renderer.preload_assets(self.compositor)
            self.renderer.warm_sprite_cache(
                self.compositor, self.width, self.height
            )

        def toggle_debug_overlay(self) -> None:
            """Cycle debug overlay mode for developer diagnostics."""
            _ = self.cycle_debug_overlay()

        def cycle_debug_overlay(self) -> DebugOverlayMode:
            """Cycle debug overlay mode: FPS -> DETAILED -> OFF -> FPS."""
            match self.debug_mode:
                case DebugOverlayMode.OFF:
                    self.debug_mode = DebugOverlayMode.FPS
                case DebugOverlayMode.FPS:
                    self.debug_mode = DebugOverlayMode.DETAILED
                case DebugOverlayMode.DETAILED:
                    self.debug_mode = DebugOverlayMode.OFF
            self._draw_debug_overlay(force=True)
            return self.debug_mode

        def tick(self, dt: float) -> None:
            """Advance compositor animations, audio, and session logic by dt."""
            super().tick(dt)
            if self.session.text_reveal is not None and not self.session.text_reveal.is_complete:
                self._ui_dirty = True
            cur_vc = getattr(getattr(self.director, "ui_state", None), "visible_chars", None)
            if cur_vc != self._last_visible_chars:
                self._last_visible_chars = cur_vc
                self._ui_dirty = True
            if self.active_input_prompt is not None:
                cur_cursor = getattr(getattr(self.overlay, "input_box", None), "cursor_visible", True)
                if cur_cursor != self._last_input_cursor:
                    self._last_input_cursor = cur_cursor
                    self._ui_dirty = True

        def on_draw(self) -> None:
            """Render frame: stage graphics followed by UI textbox and choices."""
            # Fast-path for completely static frames (idle scene & UI):
            # skip re-rendering and re-present the cached frame.
            stage_items = self.compositor.render_list()
            is_stage_static = (
                self.renderer._stage_cache is not None
                and self.renderer._last_stage_items == stage_items
                and self.renderer._last_transform == self.renderer._current_transform
                and self.renderer._stage_cache.size == (self.width, self.height)
            )
            is_text_revealing = bool(
                self.session.text_reveal is not None
                and not self.session.text_reveal.is_complete
            )
            is_screen_active = bool(
                getattr(getattr(self.session, "screens", None), "is_active", False)
            )
            is_input_active = self.active_input_prompt is not None

            if (
                is_stage_static
                and not self._ui_dirty
                and not is_text_revealing
                and not is_screen_active
                and not is_input_active
                and self._photo is not None
            ):
                self._last_render_path = "Tier 0 (Idle Skip)"
                self.renderer.frame_count += 1
                self.renderer.clock.tick()
                self._present_cached()
                self._draw_debug_overlay()
                return

            self.session.draw(self.renderer, self.width, self.height)
            self._last_render_path = self.renderer._last_render_path
            self._ui_dirty = False

            # Present the composited PIL frame to the tkinter window
            # (no-op when running headless).
            self._present()
            self._draw_debug_overlay()

        def _present(self) -> None:
            """Push the current PIL frame to the tkinter label (no-op headless)."""
            if self._root is None or self._label is None:
                return
            from PIL import ImageTk

            img = self.renderer.get_image()
            if self._photo is not None and hasattr(self._photo, "paste"):
                try:
                    self._photo.paste(img)
                    return
                except Exception:  # noqa: BLE001, S110
                    pass

            self._photo = ImageTk.PhotoImage(img)
            self._label.configure(image=self._photo)

        def _present_cached(self) -> None:
            """Re-display the cached frame without re-rendering (no-op headless)."""
            if self._root is None or self._label is None or self._photo is None:
                return
            self._label.configure(image=self._photo)

        def _draw_fps(self) -> None:
            """Update the on-screen debug overlay (no-op headless)."""
            self._draw_debug_overlay()

        def _draw_debug_overlay(self, force: bool = False) -> None:
            """Update the on-screen developer debug overlay (no-op headless)."""
            if self._root is None or tk is None:
                return
            if self._fps_widget is None:
                self._fps_widget = tk.Label(
                    self._root,
                    font=("TkDefaultFont", 9),
                    fg="#e6e6e6",
                    bg="#000000",
                    justify="left",
                    anchor="nw",
                    padx=6,
                    pady=4,
                )
            if self.debug_mode == DebugOverlayMode.OFF:
                self._fps_widget.place_forget()
                return

            now = time.monotonic()
            if not force and self._fps_widget.cget("text") and (now - self._last_debug_update) < 0.1:
                return
            self._last_debug_update = now

            if self.debug_mode == DebugOverlayMode.FPS:
                fps = self.renderer.fps
                fps_avg = self.renderer.fps_avg
                frames = self.renderer.frame_count
                self._fps_widget.configure(
                    font=("TkDefaultFont", 9),
                    text=f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})",
                )
                self._fps_widget.place(x=10, y=10)
            elif self.debug_mode == DebugOverlayMode.DETAILED:
                text = self.get_debug_overlay_text()
                try:
                    self._fps_widget.configure(
                        font=("TkFixedFont", 9),
                        text=text,
                    )
                except Exception:  # noqa: BLE001
                    self._fps_widget.configure(
                        font=("monospace", 9),
                        text=text,
                    )
                self._fps_widget.place(x=10, y=10)

        def get_debug_overlay_text(self) -> str:
            """Return the formatted debug overlay text for the current debug mode."""
            if self.debug_mode == DebugOverlayMode.OFF:
                return ""
            if self.debug_mode == DebugOverlayMode.FPS:
                fps = self.renderer.fps
                fps_avg = self.renderer.fps_avg
                frames = self.renderer.frame_count
                return f"FPS: {fps:.1f}  (avg: {fps_avg:.1f}, frames: {frames})"
            return self._format_detailed_debug()

        def _format_detailed_debug(self) -> str:
            """Format a rich multi-line diagnostic snapshot for PIL player & renderer."""
            info = self.renderer.debug_info()
            perf = info["performance"]
            stage = info["stage_caching"]
            motion = info["motion_resampling"]
            caches = info["caches"]
            backend = info["backend"]

            render_path = self._last_render_path or stage["last_render_path"]
            simd_str = backend["simd"]
            p_ver = backend["pillow_version"]
            fps = perf["fps"]
            fps_avg = perf["fps_avg"]
            frames = perf["frame_count"]
            dt = perf["dt_ms"]

            lines = [
                "── Eager Debug: PIL Backend ──────────────────────────",
                f"FPS: {fps:.1f} (avg: {fps_avg:.1f}) | Frame: {frames} | dt: {dt:.1f}ms",
                f"Pillow: {p_ver} ({simd_str}) | Mode: {backend['mode']} ({backend['dimensions'][0]}x{backend['dimensions'][1]}, {backend['scale_mode']})",
                "── Stage & Repaint ───────────────────────────────────",
                f"Render Path: {render_path}",
            ]

            if stage["last_dirty_bbox"] is not None:
                bb = stage["last_dirty_bbox"]
                lines.append(f"Dirty Rect: [{bb[0]},{bb[1]} -> {bb[2]},{bb[3]}] ({stage['dirty_area_pct']:.1f}% screen)")
            else:
                lines.append("Dirty Rect: None (full or cached)")

            m_count = motion["in_motion_count"]
            m_str = f"{m_count} asset(s)" if m_count > 0 else "None"
            lines.append(f"In-Motion: {m_str} | Resampling: {motion['active_filter']}")

            compositor = getattr(self.session, "compositor", None)
            if compositor is not None:
                stage_items = compositor.render_list()
                bg_c = sum(1 for it in stage_items if it.layer == "background")
                act_c = sum(1 for it in stage_items if it.layer not in ("background", "overlay"))
                ov_c = sum(1 for it in stage_items if it.layer == "overlay")
                active_tw = len(getattr(getattr(compositor, "timeline", None), "active_tweens", list)())
                lines.append(f"Stage Items: {len(stage_items)} (bg: {bg_c}, actors: {act_c}, overlay: {ov_c}) | Tweens: {active_tw}")

            sp = caches["sprite_lru"]
            sp_mb = sp["bytes"] / (1024 * 1024)
            sp_hr = sp["hit_ratio"] * 100.0
            tot_mb = caches["total_lru_bytes"] / (1024 * 1024)
            lines.extend([
                "── Cache Diagnostics ─────────────────────────────────",
                f"Sprite LRU: {sp['items']}/{sp['max_items']} ({sp_mb:.1f} MB) | Hit Rate: {sp_hr:.1f}% ({sp['hits']}H/{sp['misses']}M)",
                f"Total LRU: {caches['total_lru_items']} items ({tot_mb:.1f} MB)",
                f"Sub-caches: text: {caches['text_mask_lru']['items']}, scaled: {caches['scaled_lru']['items']}, ui: {caches['ui_image_lru']['items']}, geom: {caches['geom_lru']['items']}",
                f"LUTs: α:{caches['luts']['alpha']} rgba:{caches['luts']['rgba']} fade:{caches['luts']['fade']} | Fonts: {caches['fonts']} | Textures: {caches['loaded_assets']}",
            ])

            director = getattr(self.session, "director", None)
            if director is not None and hasattr(director, "ui_state"):
                speaker = director.ui_state.speaker or "None"
                rev = (
                    f"{self.session.text_reveal.visible_chars}/{self.session.text_reveal.total_chars}"
                    if (getattr(self.session, "text_reveal", None) and not self.session.text_reveal.is_complete)
                    else "complete"
                )
                choices_str = f"{len(self.active_choice_prompt.options)} choices" if self.active_choice_prompt else "None"
                lines.append(f"UI: speaker: {speaker} | reveal: {rev} | prompt: {choices_str}")

            return "\n".join(lines)

        def run(self) -> None:
            """Create the tkinter window and run the event loop (blocking).

            Requires Tk bindings in this Python (e.g. the ``python3-tk``
            system package on Debian/Ubuntu).  All story state prepared
            before this call is preserved.
            """
            if not TKINTER_AVAILABLE or tk is None:
                raise ImportError(
                    "tkinter is not available in this Python. "
                    "Install Tk bindings (e.g. 'apt install python3-tk') to use PILPlayer windows."
                )
            if self._root is not None:
                self._root.mainloop()
                return

            root = tk.Tk()
            root.title(self.title)
            root.geometry(f"{self.width}x{self.height}")
            root.resizable(True, True)
            root.protocol("WM_DELETE_WINDOW", self.close)

            label = tk.Label(root, borderwidth=0, highlightthickness=0)
            label.pack(fill="both", expand=True)

            root.bind("<Button-1>", self._on_click)
            root.bind("<Motion>", self._on_motion)
            root.bind("<Key>", self._on_key)
            root.bind("<Button-4>", self._on_scroll_up)
            root.bind("<Button-5>", self._on_scroll_down)
            root.bind("<MouseWheel>", self._on_mousewheel)
            root.bind("<KeyRelease-Control_L>", self._on_ctrl_release)
            root.bind("<KeyRelease-Control_R>", self._on_ctrl_release)
            root.bind("<Configure>", self._on_configure)

            self._root = root
            self._label = label
            if not self.visible:
                root.withdraw()

            # Present the already-stepped first beat, then enter the loop.
            self.on_draw()
            self._last_tick = time.perf_counter()
            self._run_loop()

        def _run_loop(self) -> None:
            """Drive the frame loop until the window closes (blocking).

            Tk's ``after(delay)`` timer has a coarse floor on many X11 setups
            (observed ~20 ms here), which hard-caps the whole loop near 50 FPS
            no matter what delay is requested -- including the ``uncapped``
            path, which only asks for ``after(1)``.  Instead we pump the event
            queue non-blockingly with ``update()`` and sleep out the remainder
            of the frame budget.  That keeps input responsive, honours the
            target cadence, and lets ``uncapped`` actually run unthrottled.
            """
            root = self._root
            period = (1.0 / 60.0) if (self.vsync and not self.uncapped) else 0.0
            while not self._closed and self._root is root:
                started = time.perf_counter()
                dt = started - self._last_tick if self._last_tick > 0.0 else (1.0 / 60.0)
                self._last_tick = started
                self.tick(dt)
                self.on_draw()
                try:
                    root.update()  # process pending input/window events
                except _TclError:  # window torn down from a callback
                    break
                if period:
                    remaining = period - (time.perf_counter() - started)
                    if remaining > 0.0:
                        time.sleep(remaining)

        def close(self) -> None:
            """Close the player window (marks closed when running headless)."""
            super().close()
            self._closed = True
            root, self._root = self._root, None
            self._label = None
            if root is None:
                return
            # Best-effort teardown: the window may already be half-destroyed
            # (e.g. close from inside an event callback).
            for op in (root.quit, root.destroy):
                try:
                    op()
                except Exception:  # noqa: BLE001, S110
                    pass

        def _on_scroll_up(self, event: Any) -> None:
            self.handle_scroll(1.0)

        def _on_scroll_down(self, event: Any) -> None:
            self.handle_scroll(-1.0)

        def _on_mousewheel(self, event: Any) -> None:
            delta = getattr(event, "delta", 0)
            self.handle_scroll(1.0 if delta > 0 else -1.0)

        def _on_ctrl_release(self, event: Any) -> None:
            self.handle_skip_release()

        def _on_motion(self, event: Any) -> None:
            """Handle mouse movement for screen and button hover states."""
            self.handle_pointer_move(float(event.x), float(event.y))

        def _on_click(self, event: Any) -> None:
            """Handle mouse clicks for advancement or choice selection."""
            self.handle_pointer_click(float(event.x), float(event.y))

        def _on_configure(self, event: Any) -> None:
            """Keep the UI components laid out against the new window size."""
            if event.widget is not self._root:
                return
            width, height = event.width, event.height
            if width <= 0 or height <= 0:
                return
            if width == self.width and height == self.height:
                return
            self.on_resize(width, height)
            self.renderer.set_window(self)
            self._photo = None
            self._ui_dirty = True

        def _on_key(self, event: Any) -> None:
            """Handle keyboard input for advancing, choices, rollback, and toggles."""
            raw_key = event.keysym.lower()
            is_shift = bool(getattr(event, "state", 0) & 0x0001) or getattr(event, "keysym", "").isupper()
            char = getattr(event, "char", "")
            self.handle_key_press(raw_key, is_shift=is_shift, char=char)

else:

    class PILPlayer:  # type: ignore[no-redef]
        """Stub for PILPlayer when Pillow is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            msg = (
                "Pillow is not installed. Install with 'pip install eager-graphics[software]' "
                "or 'pip install Pillow' (SIMD build: 'eager-graphics[software-simd]')."
            )
            raise ImportError(msg)


__all__ = ["PILPlayer"]
