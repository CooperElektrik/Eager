"""Built-in screens: TitleScreen, GameMenuScreen, SaveLoadScreen, PreferencesScreen, HistoryScreen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from eager_core.text import _get_wrapped_lines, parse_text_tags
from eager_core.types import Color, Rect

from eager_graphics.protocol import UIDrawBackend
from eager_graphics.screens.screen import Screen
from eager_graphics.screens.widgets import Button, Grid, Label, SaveSlotButton, Slider
from eager_graphics.theme import Theme
from eager_graphics.ui_components import TextAnchor


class TitleScreen(Screen):
    """Main menu screen (Start Game, Load Game, Preferences, Quit)."""

    def __init__(
        self,
        title: str = "Eager Visual Novel",
        theme: Theme | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        super().__init__("title", theme=theme, viewport_width=viewport_width, viewport_height=viewport_height)
        self.title: str = title
        self.session: Any = None
        self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Recompute button dimensions and positions based on current viewport size."""
        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        btn_w = vw * (300.0 / 1280.0)
        btn_h = vh * (48.0 / 720.0)
        btn_x = (vw - btn_w) / 2.0
        start_y = vh * (280.0 / 720.0)
        spacing_y = vh * (60.0 / 720.0)

        def start_game() -> None:
            if hasattr(self.session, "screens"):
                self.session.screens.hide_all(self.session)
            if self.session is not None:
                self.session.mode = "game"
                if hasattr(self.session, "restart_story") and (
                    getattr(self.session, "is_finished", False)
                    or getattr(getattr(self.session, "vm", None), "_beat_index", 0) > 0
                ):
                    self.session.restart_story()
                elif hasattr(self.session, "advance"):
                    self.session.advance()

        def quit_game() -> None:
            if self.session is not None:
                from eager_core.input import InputAction

                if hasattr(self.session, "handle_input"):
                    self.session.handle_input(InputAction.QUIT)
                player = getattr(self.session, "_player", None)
                if player is not None and hasattr(player, "close"):
                    player.close()
                elif hasattr(self.session, "close"):
                    self.session.close()

        self.buttons = [
            Button(
                Rect(btn_x, start_y, btn_w, btn_h),
                "Start Game",
                action=start_game,
            ),
            Button(
                Rect(btn_x, start_y + spacing_y, btn_w, btn_h),
                "Load Game",
                action=lambda: getattr(self.session, "screens", None) and self.session.screens.show("load", self.session),
            ),
            Button(
                Rect(btn_x, start_y + spacing_y * 2, btn_w, btn_h),
                "Preferences",
                action=lambda: getattr(self.session, "screens", None) and self.session.screens.show("preferences", self.session),
            ),
            Button(
                Rect(btn_x, start_y + spacing_y * 3, btn_w, btn_h),
                "Quit",
                action=quit_game,
            ),
        ]

    def on_enter(self, session: Any) -> None:
        """Handle screen presentation entry and initialize viewport.

        Args:
            session: Active GameSession instance.
        """
        super().on_enter(session)
        self.session = session
        if hasattr(session, "overlay") and session.overlay is not None:
            ov = session.overlay
            if getattr(ov, "width", None) and getattr(ov, "height", None):
                self.viewport_width = ov.width
                self.viewport_height = ov.height
        self.rebuild_layout()

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render title screen background, title text, and menu buttons.

        Args:
            backend: UIDrawBackend primitive rendering interface.
            width: Target render surface width in pixels.
            height: Target render surface height in pixels.
        """
        super().draw(backend, width, height)

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        # Background
        backend.draw_rect(0, 0, width, height, self.theme.bg_color)

        # Title
        backend.draw_text(
            vw / 2.0,
            vh * (160.0 / 720.0),
            self.title,
            color=self.theme.accent_color,
            font_size=self.scale_font_size(self.theme.title_font_size),
            anchor_x=TextAnchor.CENTER,
            anchor_y=TextAnchor.TOP,
        )

        # Buttons
        for b in self.buttons:
            b.draw(
                backend,
                fill_color=self.theme.button_fill,
                hover_color=self.theme.button_hover,
                border_color=self.theme.button_border,
                text_color=self.theme.button_text,
                font_size=self.scale_font_size(self.theme.font_size),
            )


class GameMenuScreen(Screen):
    """In-game pause and navigation menu (Resume, Save, Load, History, Preferences, Title, Quit)."""

    def __init__(
        self,
        theme: Theme | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        super().__init__("game_menu", theme=theme, viewport_width=viewport_width, viewport_height=viewport_height)
        self.session: Any = None
        self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Recompute button dimensions and positions based on current viewport size."""
        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        btn_w = vw * (300.0 / 1280.0)
        btn_h = vh * (44.0 / 720.0)
        btn_x = (vw - btn_w) / 2.0
        start_y = vh * (175.0 / 720.0)
        spacing_y = vh * (52.0 / 720.0)

        def resume_game() -> None:
            if hasattr(self.session, "screens"):
                self.session.screens.hide(self.session)

        def show_screen(name: str) -> Callable[[], None]:
            return lambda: getattr(self.session, "screens", None) and self.session.screens.show(name, self.session)

        def return_to_title() -> None:
            if self.session is not None and hasattr(self.session, "return_to_title"):
                self.session.return_to_title()

        def quit_game() -> None:
            if self.session is not None:
                from eager_core.input import InputAction

                if hasattr(self.session, "handle_input"):
                    self.session.handle_input(InputAction.QUIT)
                player = getattr(self.session, "_player", None)
                if player is not None and hasattr(player, "close"):
                    player.close()
                elif hasattr(self.session, "close"):
                    self.session.close()

        self.buttons = [
            Button(Rect(btn_x, start_y + spacing_y * 0, btn_w, btn_h), "Resume", action=resume_game),
            Button(Rect(btn_x, start_y + spacing_y * 1, btn_w, btn_h), "Save Game", action=show_screen("save")),
            Button(Rect(btn_x, start_y + spacing_y * 2, btn_w, btn_h), "Load Game", action=show_screen("load")),
            Button(Rect(btn_x, start_y + spacing_y * 3, btn_w, btn_h), "Dialogue History", action=show_screen("history")),
            Button(Rect(btn_x, start_y + spacing_y * 4, btn_w, btn_h), "Preferences", action=show_screen("preferences")),
            Button(Rect(btn_x, start_y + spacing_y * 5, btn_w, btn_h), "Main Menu", action=return_to_title),
            Button(Rect(btn_x, start_y + spacing_y * 6, btn_w, btn_h), "Quit Game", action=quit_game),
        ]

    def on_enter(self, session: Any) -> None:
        """Handle screen presentation entry and initialize viewport.

        Args:
            session: Active GameSession instance.
        """
        super().on_enter(session)
        self.session = session
        if hasattr(session, "overlay") and session.overlay is not None:
            ov = session.overlay
            if getattr(ov, "width", None) and getattr(ov, "height", None):
                self.viewport_width = ov.width
                self.viewport_height = ov.height
        self.rebuild_layout()

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render darkened modal scrim, menu header, and navigation buttons.

        Args:
            backend: UIDrawBackend primitive rendering interface.
            width: Target render surface width in pixels.
            height: Target render surface height in pixels.
        """
        super().draw(backend, width, height)

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        # Semi-transparent dark overlay scrim over gameplay stage
        backend.draw_rect(0, 0, width, height, Color(0.04, 0.05, 0.08, 0.88))

        backend.draw_text(
            vw / 2.0,
            vh * (100.0 / 720.0),
            "Game Menu",
            color=self.theme.accent_color,
            font_size=self.scale_font_size(self.theme.title_font_size),
            anchor_x=TextAnchor.CENTER,
            anchor_y=TextAnchor.TOP,
        )

        for b in self.buttons:
            b.draw(
                backend,
                fill_color=self.theme.button_fill,
                hover_color=self.theme.button_hover,
                border_color=self.theme.button_border,
                text_color=self.theme.button_text,
                font_size=self.scale_font_size(self.theme.font_size),
            )


class SaveLoadScreen(Screen):
    """Save / Load slot picker screen."""

    def __init__(
        self,
        mode: str = "save",
        theme: Theme | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        super().__init__(mode, theme=theme, viewport_width=viewport_width, viewport_height=viewport_height)
        self.mode: str = mode  # "save" or "load"
        self.session: Any = None
        self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Reconstruct slot grid buttons and metadata previews for current viewport."""
        self.buttons.clear()

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        grid_w = vw * (840.0 / 1280.0)
        grid_x = (vw - grid_w) / 2.0
        grid_y = vh * (110.0 / 720.0)
        grid_h = vh * (380.0 / 720.0)
        spacing_x = vw * (28.0 / 1280.0)
        spacing_y = vh * (22.0 / 720.0)

        grid = Grid(
            Rect(grid_x, grid_y, grid_w, grid_h),
            rows=3,
            cols=2,
            spacing_x=spacing_x,
            spacing_y=spacing_y,
            padding=0.0,
        )
        save_mgr = getattr(self.session, "save_manager", None)

        for i in range(6):
            slot_name = f"slot_{i+1}"
            cell = grid.cell_rect_by_index(i)
            meta = save_mgr.get_slot_metadata(slot_name) if save_mgr else None
            if meta is not None:
                scene_name = meta.scene_name or meta.scene_id or f"Scene {i+1}"
                ts = meta.timestamp
                if "T" in ts:
                    d_part, t_part = ts.split("T", 1)
                    ts_clean = f"{d_part} {t_part[:5]}"
                else:
                    ts_clean = ts[:16] if ts else ""
                snip = meta.dialogue_snippet or ""
                if len(snip) > 36:
                    snip = snip[:33] + "..."
                if snip:
                    label = f"Slot {i+1}: {scene_name}\n{ts_clean}\n\"{snip}\""
                else:
                    label = f"Slot {i+1}: {scene_name}\n{ts_clean}"
            else:
                label = f"Slot {i+1}\n[Empty Slot]"

            def make_action(sname: str):
                if self.mode == "save":
                    def save_action() -> None:
                        if self.session is not None and hasattr(self.session, "save_game"):
                            self.session.save_game(sname)
                        # Refresh current screen button texts
                        self.rebuild_layout()
                    return save_action
                else:
                    def load_action() -> None:
                        if (
                            self.session is not None
                            and hasattr(self.session, "load_game")
                            and self.session.load_game(sname)
                        ):
                            if hasattr(self.session, "screens"):
                                self.session.screens.hide_all(self.session)
                            self.session.mode = "game"
                            self.session._ui_dirty = True
                            player = getattr(self.session, "_player", None)
                            if player is not None and hasattr(player, "_sync_state"):
                                player._sync_state()
                                player._mark_ui_dirty()
                    return load_action

            self.buttons.append(
                SaveSlotButton(
                    cell,
                    label,
                    action=make_action(slot_name),
                )
            )

        # Back button
        back_x = grid_x
        back_y = vh * (520.0 / 720.0)
        back_w = vw * (140.0 / 1280.0)
        back_h = vh * (40.0 / 720.0)
        self.buttons.append(
            Button(
                Rect(back_x, back_y, back_w, back_h),
                "Back",
                action=lambda: getattr(self.session, "screens", None) and self.session.screens.hide(self.session),
            )
        )

    def on_enter(self, session: Any) -> None:
        """Handle screen presentation entry and initialize viewport.

        Args:
            session: Active GameSession instance.
        """
        super().on_enter(session)
        self.session = session
        if hasattr(session, "overlay") and session.overlay is not None:
            ov = session.overlay
            if getattr(ov, "width", None) and getattr(ov, "height", None):
                self.viewport_width = ov.width
                self.viewport_height = ov.height
        self.rebuild_layout()

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render save/load screen slot buttons and navigation chrome.

        Args:
            backend: UIDrawBackend primitive rendering interface.
            width: Target render surface width in pixels.
            height: Target render surface height in pixels.
        """
        super().draw(backend, width, height)

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)
        grid_w = vw * (840.0 / 1280.0)
        grid_x = (vw - grid_w) / 2.0

        backend.draw_rect(0, 0, width, height, self.theme.bg_color)
        backend.draw_text(
            grid_x,
            vh * (40.0 / 720.0),
            "Save Game" if self.mode == "save" else "Load Game",
            color=self.theme.text_color,
            font_size=self.scale_font_size(28),
            anchor_x=TextAnchor.LEFT,
            anchor_y=TextAnchor.TOP,
        )
        for b in self.buttons:
            b.draw(
                backend,
                fill_color=self.theme.button_fill,
                hover_color=self.theme.button_hover,
                border_color=self.theme.button_border,
                text_color=self.theme.button_text,
                font_size=self.scale_font_size(self.theme.font_size),
            )


class PreferencesScreen(Screen):
    """User preferences configuration screen (Audio Volumes, Text Speed, Auto-Forward)."""

    def __init__(
        self,
        theme: Theme | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        super().__init__("preferences", theme=theme, viewport_width=viewport_width, viewport_height=viewport_height)
        self.session: Any = None
        self.rebuild_layout()

    def rebuild_layout(self) -> None:
        """Reconstruct volume sliders, text speed controls, and language buttons."""
        self.buttons.clear()
        self.sliders.clear()
        self.labels.clear()

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        prefs = getattr(self.session, "preferences", None)

        def make_vol_cb(field_name: str):
            def cb(val: float) -> None:
                if prefs is not None:
                    setattr(prefs, field_name, val)
                    if self.session is not None and hasattr(self.session, "apply_preferences"):
                        self.session.apply_preferences()
            return cb

        # Audio sliders (y: 120, 170, 220, 270)
        vol_settings = [
            ("Master Volume", "master_volume", getattr(prefs, "master_volume", 1.0) if prefs else 1.0),
            ("Music Volume", "music_volume", getattr(prefs, "music_volume", 0.8) if prefs else 0.8),
            ("SFX Volume", "sfx_volume", getattr(prefs, "sfx_volume", 1.0) if prefs else 1.0),
            ("Voice Volume", "voice_volume", getattr(prefs, "voice_volume", 1.0) if prefs else 1.0),
        ]

        label_x = vw * (100.0 / 1280.0)
        base_y = vh * (120.0 / 720.0)
        step_y = vh * (50.0 / 720.0)
        slider_x = vw * (280.0 / 1280.0)
        slider_w = vw * (300.0 / 1280.0)
        slider_h = vh * (24.0 / 720.0)
        label_offset_y = vh * (4.0 / 720.0)

        for idx, (label_text, field, current_val) in enumerate(vol_settings):
            sy = base_y + idx * step_y
            self.labels.append(
                Label(
                    label_text,
                    label_x,
                    sy + label_offset_y,
                    color=self.theme.text_color,
                    font_size=self.scale_font_size(16),
                )
            )
            self.sliders.append(
                Slider(
                    Rect(slider_x, sy, slider_w, slider_h),
                    value=max(0.0, min(1.0, current_val)),
                    on_change=make_vol_cb(field),
                )
            )

        # Text Speed (0..100 cps mapped to 0..1)
        raw_speed = getattr(prefs, "text_speed", 50.0) if prefs else 50.0
        speed_norm = max(0.0, min(1.0, raw_speed / 100.0))

        def speed_cb(val: float) -> None:
            if prefs is not None:
                prefs.text_speed = val * 100.0

        speed_y = base_y + 4 * step_y
        self.labels.append(
            Label(
                "Text Speed",
                label_x,
                speed_y + label_offset_y,
                color=self.theme.text_color,
                font_size=self.scale_font_size(16),
            )
        )
        self.sliders.append(
            Slider(
                Rect(slider_x, speed_y, slider_w, slider_h),
                value=speed_norm,
                on_change=speed_cb,
            )
        )

        # Auto-Forward Time (1..10s mapped to 0..1)
        raw_auto = getattr(prefs, "auto_forward_time", 3.0) if prefs else 3.0
        auto_norm = max(0.0, min(1.0, (raw_auto - 1.0) / 9.0))

        def auto_cb(val: float) -> None:
            if prefs is not None:
                prefs.auto_forward_time = 1.0 + val * 9.0

        auto_y = base_y + 5 * step_y
        self.labels.append(
            Label(
                "Auto Forward",
                label_x,
                auto_y + label_offset_y,
                color=self.theme.text_color,
                font_size=self.scale_font_size(16),
            )
        )
        self.sliders.append(
            Slider(
                Rect(slider_x, auto_y, slider_w, slider_h),
                value=auto_norm,
                on_change=auto_cb,
            )
        )

        # Back button
        back_x = vw * (100.0 / 1280.0)
        back_y = vh * (520.0 / 720.0)
        back_w = vw * (140.0 / 1280.0)
        back_h = vh * (40.0 / 720.0)
        self.buttons.append(
            Button(
                Rect(back_x, back_y, back_w, back_h),
                "Back",
                action=lambda: getattr(self.session, "screens", None) and self.session.screens.hide(self.session),
            )
        )

        # Language Selector
        tm = getattr(self.session, "translation_manager", None)
        available_locales = tm.available_locales() if tm is not None else ["default"]
        current_locale = getattr(prefs, "language", "default") if prefs else "default"

        lang_x = vw * (680.0 / 1280.0)
        lang_y = base_y
        self.labels.append(
            Label(
                "Language",
                lang_x,
                lang_y + label_offset_y,
                color=self.theme.text_color,
                font_size=self.scale_font_size(18),
            )
        )

        lang_btn_w = vw * (140.0 / 1280.0)
        lang_btn_h = vh * (36.0 / 720.0)
        lang_offset_y = vh * (36.0 / 720.0)
        lang_step_y = vh * (46.0 / 720.0)

        for l_idx, loc in enumerate(available_locales):
            btn_y = lang_y + lang_offset_y + l_idx * lang_step_y
            btn_label = f"[ {loc.upper()} ]" if loc.lower() == current_locale.lower() else f"  {loc.upper()}  "

            def make_lang_cb(target_loc: str):
                def cb() -> None:
                    if self.session is not None and hasattr(self.session, "set_language"):
                        self.session.set_language(target_loc)
                    elif prefs is not None:
                        prefs.language = target_loc
                    self.rebuild_layout()
                return cb

            self.buttons.append(
                Button(
                    Rect(lang_x, btn_y, lang_btn_w, lang_btn_h),
                    btn_label,
                    action=make_lang_cb(loc),
                )
            )

    def on_enter(self, session: Any) -> None:
        """Handle preferences screen entry and sync controls.

        Args:
            session: Active GameSession instance.
        """
        super().on_enter(session)
        self.session = session
        if hasattr(session, "overlay") and session.overlay is not None:
            ov = session.overlay
            if getattr(ov, "width", None) and getattr(ov, "height", None):
                self.viewport_width = ov.width
                self.viewport_height = ov.height
        self.rebuild_layout()

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render preferences screen controls, labels, and sliders.

        Args:
            backend: UIDrawBackend primitive rendering interface.
            width: Target render surface width in pixels.
            height: Target render surface height in pixels.
        """
        super().draw(backend, width, height)

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        backend.draw_rect(0, 0, width, height, self.theme.bg_color)
        backend.draw_text(
            vw * (100.0 / 1280.0),
            vh * (40.0 / 720.0),
            "Preferences",
            color=self.theme.text_color,
            font_size=self.scale_font_size(28),
            anchor_x=TextAnchor.LEFT,
            anchor_y=TextAnchor.TOP,
        )

        for lbl in self.labels:
            lbl.draw(backend)

        for s in self.sliders:
            s.draw(backend, bar_color=self.theme.button_fill, fill_color=self.theme.primary_color)

        for b in self.buttons:
            b.draw(
                backend,
                fill_color=self.theme.button_fill,
                hover_color=self.theme.button_hover,
                border_color=self.theme.button_border,
                text_color=self.theme.button_text,
                font_size=self.scale_font_size(self.theme.font_size),
            )


class HistoryScreen(Screen):
    """Backlog / History screen displaying past dialogue and narration."""

    def __init__(
        self,
        theme: Theme | None = None,
        viewport_width: int = 1280,
        viewport_height: int = 720,
    ) -> None:
        super().__init__("history", theme=theme, viewport_width=viewport_width, viewport_height=viewport_height)
        self.session: Any = None
        self.scroll_offset: int = 0
        self._last_built_scroll_offset: int | None = None
        self._last_built_entry_count: int | None = None
        self._last_built_viewport: tuple[int, int] | None = None
        self._rebuild_buttons()

    def on_enter(self, session: Any) -> None:
        """Handle history screen entry, resetting scroll offset.

        Args:
            session: Active GameSession instance.
        """
        super().on_enter(session)
        self.session = session
        if hasattr(session, "overlay") and session.overlay is not None:
            ov = session.overlay
            if getattr(ov, "width", None) and getattr(ov, "height", None):
                self.viewport_width = ov.width
                self.viewport_height = ov.height
        self.scroll_offset = 0
        self._rebuild_buttons()

    def rebuild_layout(self) -> None:
        """Rebuild history scroll buttons and voice replay triggers."""
        self._rebuild_buttons()

    def _make_voice_action(self, voice_path: str) -> Callable[[], None]:
        return lambda: self.replay_voice(voice_path)

    def replay_voice(self, voice: str) -> None:
        """Replay recorded voice audio for a backlog entry."""
        if not voice or self.session is None:
            return
        if hasattr(self.session, "play_voice") and callable(self.session.play_voice):
            self.session.play_voice(voice)
            return

        audio = getattr(self.session, "audio", None) or getattr(getattr(self.session, "director", None), "audio", None)
        if audio is not None and hasattr(audio, "play") and callable(audio.play):
            audio.play("voice", str(voice), loop=False)

    def _rebuild_buttons(self) -> None:
        self.buttons.clear()

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        up_x = vw * (1100.0 / 1280.0)
        up_y = vh * (110.0 / 720.0)
        down_y = vh * (170.0 / 720.0)
        btn_w = vw * (100.0 / 1280.0)
        btn_h = vh * (40.0 / 720.0)

        back_x = vw * (100.0 / 1280.0)
        back_y = vh * (620.0 / 720.0)
        back_w = vw * (140.0 / 1280.0)
        back_h = vh * (40.0 / 720.0)

        # Up, Down, Back buttons
        self.buttons.append(
            Button(
                Rect(up_x, up_y, btn_w, btn_h),
                "▲ Up",
                action=self.scroll_up,
            )
        )
        self.buttons.append(
            Button(
                Rect(up_x, down_y, btn_w, btn_h),
                "▼ Down",
                action=self.scroll_down,
            )
        )
        self.buttons.append(
            Button(
                Rect(back_x, back_y, back_w, back_h),
                "Back",
                action=lambda: getattr(self.session, "screens", None) and self.session.screens.hide(self.session) if self.session is not None else None,
            )
        )

        backlog = getattr(self.session, "backlog", None) if self.session is not None else None
        entries = backlog.entries if backlog else []
        self._last_built_scroll_offset = self.scroll_offset
        self._last_built_entry_count = len(entries)
        self._last_built_viewport = (self.viewport_width, self.viewport_height)

        if not entries:
            return

        # Display up to 7 most recent entries with scroll offset
        visible_count = 7
        end_idx = len(entries) - self.scroll_offset
        start_idx = max(0, end_idx - visible_count)
        displayed_slice = entries[start_idx:end_idx]

        curr_y = vh * (110.0 / 720.0)
        step_y = vh * (65.0 / 720.0)
        spk_x = vw * (52.0 / 1280.0)
        spk_w = vw * (36.0 / 1280.0)
        spk_h = vh * (28.0 / 720.0)
        spk_offset_y = vh * (6.0 / 720.0)

        for entry in displayed_slice:
            voice = getattr(entry, "voice", None)
            if voice:
                voice_str = str(voice)
                self.buttons.append(
                    Button(
                        Rect(spk_x, curr_y - spk_offset_y, spk_w, spk_h),
                        "🔊",
                        action=self._make_voice_action(voice_str),
                        voice=voice_str,
                    )
                )
            curr_y += step_y

    def scroll_up(self) -> None:
        """Scroll backward toward older dialogue entries."""
        if self.session is None:
            return
        backlog = getattr(self.session, "backlog", None)
        max_entries = len(backlog.entries) if backlog else 0
        if self.scroll_offset + 5 < max_entries:
            self.scroll_offset += 1
            self._rebuild_buttons()

    def scroll_down(self) -> None:
        """Scroll forward toward newer dialogue entries."""
        if self.session is None:
            return
        if self.scroll_offset > 0:
            self.scroll_offset -= 1
            self._rebuild_buttons()

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        """Render dialogue history lines, speaker labels, and navigation buttons.

        Args:
            backend: UIDrawBackend primitive rendering interface.
            width: Target render surface width in pixels.
            height: Target render surface height in pixels.
        """
        super().draw(backend, width, height)

        vw = float(self.viewport_width)
        vh = float(self.viewport_height)

        if self.session is not None:
            backlog = getattr(self.session, "backlog", None)
            entries = backlog.entries if backlog else []
            if (
                not self.buttons
                or self._last_built_scroll_offset != self.scroll_offset
                or self._last_built_entry_count != len(entries)
                or self._last_built_viewport != (self.viewport_width, self.viewport_height)
            ):
                self._rebuild_buttons()
        else:
            entries = []

        backend.draw_rect(0, 0, width, height, self.theme.bg_color)
        title_x = vw * (100.0 / 1280.0)
        title_y = vh * (40.0 / 720.0)
        title_font_size = self.scale_font_size(28)
        empty_font_size = self.scale_font_size(16)
        entry_font_size = self.scale_font_size(14)
        btn_font_size = self.scale_font_size(self.theme.font_size)

        backend.draw_text(
            title_x,
            title_y,
            "Dialogue History",
            color=self.theme.text_color,
            font_size=title_font_size,
            anchor_x=TextAnchor.LEFT,
            anchor_y=TextAnchor.TOP,
        )

        if not entries:
            backend.draw_text(
                title_x,
                vh * (120.0 / 720.0),
                "No dialogue recorded yet.",
                color=self.theme.muted_text_color,
                font_size=empty_font_size,
            )
        else:
            # Display up to 7 most recent entries with scroll offset
            visible_count = 7
            end_idx = len(entries) - self.scroll_offset
            start_idx = max(0, end_idx - visible_count)
            displayed_slice = entries[start_idx:end_idx]

            curr_y = vh * (110.0 / 720.0)
            step_y = vh * (65.0 / 720.0)
            entry_x = vw * (100.0 / 1280.0)
            max_text_w = vw * (960.0 / 1280.0)
            line_h = float(entry_font_size) * 1.35

            for entry in displayed_slice:
                plain_text = parse_text_tags(entry.text).plain_text
                if entry.speaker:
                    speaker_name_w, _ = backend.measure_text(
                        entry.speaker, font_size=entry_font_size, bold=True
                    )
                    if speaker_name_w <= 0.0:
                        speaker_name_w = len(entry.speaker) * 9.0 * (vw / 1280.0)

                    colon_w, _ = backend.measure_text(": ", font_size=entry_font_size)
                    if colon_w <= 0.0:
                        colon_w = 12.0 * (vw / 1280.0)

                    speaker_total_w = speaker_name_w + colon_w
                    avail_w = max(100.0, max_text_w - speaker_total_w)

                    backend.draw_text(
                        entry_x,
                        curr_y,
                        entry.speaker,
                        color=self.theme.accent_color,
                        font_size=entry_font_size,
                        bold=True,
                    )
                    backend.draw_text(
                        entry_x + speaker_name_w,
                        curr_y,
                        ": ",
                        color=self.theme.accent_color,
                        font_size=entry_font_size,
                    )

                    wrapped = _get_wrapped_lines(
                        plain_text,
                        avail_w,
                        backend.measure_text,
                        font_size=entry_font_size,
                    )
                    lines = [w[0] if isinstance(w, tuple) else w for w in wrapped]
                    if not lines:
                        lines = [plain_text]

                    for line_idx, line_str in enumerate(lines):
                        if line_idx >= 3:
                            break
                        ly = curr_y + (line_idx * line_h)
                        backend.draw_text(
                            entry_x + speaker_total_w,
                            ly,
                            line_str,
                            color=self.theme.text_color,
                            font_size=entry_font_size,
                        )
                else:
                    wrapped = _get_wrapped_lines(
                        plain_text,
                        max_text_w,
                        backend.measure_text,
                        font_size=entry_font_size,
                    )
                    lines = [w[0] if isinstance(w, tuple) else w for w in wrapped]
                    if not lines:
                        lines = [plain_text]

                    for line_idx, line_str in enumerate(lines):
                        if line_idx >= 3:
                            break
                        ly = curr_y + (line_idx * line_h)
                        backend.draw_text(
                            entry_x,
                            ly,
                            line_str,
                            color=self.theme.muted_text_color,
                            font_size=entry_font_size,
                        )
                rendered_lines = min(len(lines), 3)
                entry_height = max(step_y, (rendered_lines * line_h) + vh * (15.0 / 720.0))
                curr_y += entry_height

        for b in self.buttons:
            b.draw(
                backend,
                fill_color=self.theme.button_fill,
                hover_color=self.theme.button_hover,
                border_color=self.theme.button_border,
                text_color=self.theme.button_text,
                font_size=btn_font_size,
            )


__all__ = ["GameMenuScreen", "HistoryScreen", "PreferencesScreen", "SaveLoadScreen", "TitleScreen"]
