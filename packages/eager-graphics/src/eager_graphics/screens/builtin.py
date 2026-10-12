"""Built-in screens: TitleScreen, SaveLoadScreen, PreferencesScreen, HistoryScreen."""

from __future__ import annotations

from typing import Any

from eager_graphics.protocol import UIDrawBackend
from eager_graphics.screens.screen import Screen
from eager_graphics.screens.widgets import Button, Grid, Label, Slider
from eager_graphics.types import Rect
from eager_graphics.ui_components import TextAnchor


class TitleScreen(Screen):
    """Main menu screen (Start Game, Load Game, Preferences, Quit)."""

    def __init__(self, title: str = "Eager Visual Novel") -> None:
        super().__init__("title")
        self.title = title

    def on_enter(self, session: Any) -> None:
        super().on_enter(session)
        btn_w, btn_h = 240.0, 50.0
        start_x = 100.0
        start_y = 300.0

        def start_game() -> None:
            if hasattr(session, "screens"):
                session.screens.hide(session)
            session.advance()

        self.buttons = [
            Button(
                Rect(start_x, start_y, btn_w, btn_h),
                "Start Game",
                action=start_game,
            ),
            Button(
                Rect(start_x, start_y + 60, btn_w, btn_h),
                "Load Game",
                action=lambda: getattr(session, "screens", None) and session.screens.show("load", session),
            ),
            Button(
                Rect(start_x, start_y + 120, btn_w, btn_h),
                "Preferences",
                action=lambda: getattr(session, "screens", None) and session.screens.show("preferences", session),
            ),
        ]

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        # Background
        backend.draw_rect(0, 0, width, height, self.theme.bg_color)

        # Title
        backend.draw_text(
            self.title,
            100.0,
            150.0,
            color=self.theme.accent_color,
            font_size=self.theme.title_font_size,
            anchor_x=TextAnchor.LEFT,
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
                font_size=self.theme.font_size,
            )


class SaveLoadScreen(Screen):
    """Save / Load slot picker screen."""

    def __init__(self, mode: str = "save") -> None:
        super().__init__(mode)
        self.mode = mode  # "save" or "load"

    def on_enter(self, session: Any) -> None:
        super().on_enter(session)
        self.buttons.clear()

        grid = Grid(Rect(100.0, 110.0, 720.0, 360.0), rows=3, cols=2, spacing_x=24.0, spacing_y=20.0, padding=0.0)
        save_mgr = getattr(session, "save_manager", None)
        existing_slots = set(save_mgr.list_slots()) if save_mgr else set()

        for i in range(6):
            slot_name = f"slot_{i+1}"
            cell = grid.cell_rect_by_index(i)
            status_text = "Saved" if slot_name in existing_slots else "Empty"
            label = f"Slot {i+1} [{status_text}]"

            def make_action(sname: str):
                if self.mode == "save":
                    def save_action() -> None:
                        session.save_game(sname)
                        # Refresh current screen button texts
                        self.on_enter(session)
                    return save_action
                else:
                    def load_action() -> None:
                        if session.load_game(sname) and hasattr(session, "screens"):
                            session.screens.hide(session)
                    return load_action

            self.buttons.append(
                Button(
                    cell,
                    label,
                    action=make_action(slot_name),
                )
            )

        # Back button
        self.buttons.append(
            Button(
                Rect(100.0, 520.0, 140.0, 40.0),
                "Back",
                action=lambda: getattr(session, "screens", None) and session.screens.hide(session),
            )
        )

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        backend.draw_rect(0, 0, width, height, self.theme.bg_color)
        backend.draw_text(
            "Save Game" if self.mode == "save" else "Load Game",
            100.0,
            40.0,
            color=self.theme.text_color,
            font_size=28,
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
                font_size=self.theme.font_size,
            )


class PreferencesScreen(Screen):
    """User preferences configuration screen (Audio Volumes, Text Speed, Auto-Forward)."""

    def __init__(self) -> None:
        super().__init__("preferences")
        self.session: Any = None

    def on_enter(self, session: Any) -> None:
        super().on_enter(session)
        self.session = session
        self.buttons.clear()
        self.sliders.clear()
        self.labels.clear()

        prefs = getattr(session, "preferences", None)

        def make_vol_cb(field_name: str):
            def cb(val: float) -> None:
                if prefs is not None:
                    setattr(prefs, field_name, val)
                    if hasattr(session, "apply_preferences"):
                        session.apply_preferences()
            return cb

        # Audio sliders (y: 120, 170, 220, 270)
        vol_settings = [
            ("Master Volume", "master_volume", getattr(prefs, "master_volume", 1.0) if prefs else 1.0),
            ("Music Volume", "music_volume", getattr(prefs, "music_volume", 0.8) if prefs else 0.8),
            ("SFX Volume", "sfx_volume", getattr(prefs, "sfx_volume", 1.0) if prefs else 1.0),
            ("Voice Volume", "voice_volume", getattr(prefs, "voice_volume", 1.0) if prefs else 1.0),
        ]

        slider_x = 280.0
        slider_w = 300.0
        slider_h = 24.0

        for idx, (label_text, field, current_val) in enumerate(vol_settings):
            sy = 120.0 + idx * 50.0
            self.labels.append(
                Label(label_text, 100.0, sy + 4.0, color=self.theme.text_color, font_size=16)
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

        speed_y = 120.0 + 4 * 50.0
        self.labels.append(
            Label("Text Speed", 100.0, speed_y + 4.0, color=self.theme.text_color, font_size=16)
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

        auto_y = 120.0 + 5 * 50.0
        self.labels.append(
            Label("Auto Forward", 100.0, auto_y + 4.0, color=self.theme.text_color, font_size=16)
        )
        self.sliders.append(
            Slider(
                Rect(slider_x, auto_y, slider_w, slider_h),
                value=auto_norm,
                on_change=auto_cb,
            )
        )

        # Back button
        self.buttons.append(
            Button(
                Rect(100.0, 520.0, 140.0, 40.0),
                "Back",
                action=lambda: getattr(session, "screens", None) and session.screens.hide(session),
            )
        )

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        backend.draw_rect(0, 0, width, height, self.theme.bg_color)
        backend.draw_text(
            "Preferences",
            100.0,
            40.0,
            color=self.theme.text_color,
            font_size=28,
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
                font_size=self.theme.font_size,
            )


class HistoryScreen(Screen):
    """Backlog / History screen displaying past dialogue and narration."""

    def __init__(self) -> None:
        super().__init__("history")
        self.session: Any = None
        self.scroll_offset: int = 0

    def on_enter(self, session: Any) -> None:
        super().on_enter(session)
        self.session = session
        self.scroll_offset = 0
        self.buttons.clear()

        # Up, Down, Back buttons
        self.buttons.append(
            Button(
                Rect(1100.0, 110.0, 100.0, 40.0),
                "▲ Up",
                action=self.scroll_up,
            )
        )
        self.buttons.append(
            Button(
                Rect(1100.0, 170.0, 100.0, 40.0),
                "▼ Down",
                action=self.scroll_down,
            )
        )
        self.buttons.append(
            Button(
                Rect(100.0, 620.0, 140.0, 40.0),
                "Back",
                action=lambda: getattr(session, "screens", None) and session.screens.hide(session),
            )
        )

    def scroll_up(self) -> None:
        backlog = getattr(self.session, "backlog", None)
        max_entries = len(backlog.entries) if backlog else 0
        if self.scroll_offset + 5 < max_entries:
            self.scroll_offset += 1

    def scroll_down(self) -> None:
        if self.scroll_offset > 0:
            self.scroll_offset -= 1

    def draw(self, backend: UIDrawBackend, width: int, height: int) -> None:
        backend.draw_rect(0, 0, width, height, self.theme.bg_color)
        backend.draw_text(
            "Dialogue History",
            100.0,
            40.0,
            color=self.theme.text_color,
            font_size=28,
            anchor_x=TextAnchor.LEFT,
            anchor_y=TextAnchor.TOP,
        )

        backlog = getattr(self.session, "backlog", None)
        entries = backlog.entries if backlog else []

        if not entries:
            backend.draw_text(
                "No dialogue recorded yet.",
                100.0,
                120.0,
                color=self.theme.muted_text_color,
                font_size=16,
            )
        else:
            # Display up to 7 most recent entries with scroll offset
            visible_count = 7
            end_idx = len(entries) - self.scroll_offset
            start_idx = max(0, end_idx - visible_count)
            displayed_slice = entries[start_idx:end_idx]

            curr_y = 110.0
            for entry in displayed_slice:
                if entry.speaker:
                    backend.draw_text(
                        entry.speaker,
                        100.0,
                        curr_y,
                        color=self.theme.accent_color,
                        font_size=14,
                    )
                    backend.draw_text(
                        f": {entry.text}",
                        100.0 + len(entry.speaker) * 9.0,
                        curr_y,
                        color=self.theme.text_color,
                        font_size=14,
                    )
                else:
                    backend.draw_text(
                        entry.text,
                        100.0,
                        curr_y,
                        color=self.theme.muted_text_color,
                        font_size=14,
                    )
                curr_y += 65.0

        for b in self.buttons:
            b.draw(
                backend,
                fill_color=self.theme.button_fill,
                hover_color=self.theme.button_hover,
                border_color=self.theme.button_border,
                text_color=self.theme.button_text,
                font_size=self.theme.font_size,
            )
