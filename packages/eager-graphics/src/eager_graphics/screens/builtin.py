"""Built-in screens: TitleScreen, SaveScreen, PreferencesScreen, HistoryScreen."""

from __future__ import annotations

from typing import Any

from eager_graphics.protocol import UIDrawBackend
from eager_graphics.screens.screen import Screen
from eager_graphics.screens.widgets import Button
from eager_graphics.types import Rect
from eager_graphics.ui_components import TextAnchor


class TitleScreen(Screen):
    """Main menu screen (Start Game, Continue, Load, Preferences, Quit)."""

    def __init__(self, title: str = "Eager Visual Novel") -> None:
        super().__init__("title")
        self.title = title

    def on_enter(self, session: Any) -> None:
        super().on_enter(session)
        # Position buttons
        btn_w, btn_h = 240.0, 50.0
        start_x = 100.0
        start_y = 300.0

        self.buttons = [
            Button(
                Rect(start_x, start_y, btn_w, btn_h),
                "Start Game",
                action=lambda: session.advance(),
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

        # Generate slot buttons
        slot_w, slot_h = 280.0, 100.0
        for i in range(6):
            col = i % 2
            row = i // 2
            x = 100.0 + col * 320.0
            y = 120.0 + row * 120.0
            slot_name = f"slot_{i+1}"

            def make_action(sname: str):
                if self.mode == "save":
                    return lambda: session.save_game(sname)
                return lambda: session.load_game(sname)

            self.buttons.append(
                Button(
                    Rect(x, y, slot_w, slot_h),
                    f"Slot {i+1}",
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
            50.0,
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
