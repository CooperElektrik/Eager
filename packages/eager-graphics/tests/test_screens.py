"""Tests for Phase 6 screens, menus, theme, and project config."""

import tempfile
import unittest
from pathlib import Path

from eager_runtime.project import ProjectConfig, merge_graphs
from eager_script import parse_graph

from eager_graphics.screens import Button, ScreenManager, TitleScreen
from eager_graphics.types import Color, Rect


class MockUIDrawBackend:
    """Mock UIDrawBackend recording draw calls for testing."""

    def __init__(self) -> None:
        self.rects = []
        self.texts = []

    def draw_rect(self, x: float, y: float, w: float, h: float, color: Color) -> None:
        self.rects.append((x, y, w, h, color))

    def draw_rect_outline(self, x: float, y: float, w: float, h: float, color: Color, line_width: float = 1.0) -> None:
        self.rects.append(("outline", x, y, w, h, color))

    def draw_gradient_rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        top_color: Color,
        bottom_color: Color,
    ) -> None:
        self.rects.append(("gradient", x, y, width, height, top_color, bottom_color))

    def draw_text(self, x: float, y: float, text: str, **kwargs) -> None:
        self.texts.append((text, x, y, kwargs))


class TestScreensAndProject(unittest.TestCase):
    def test_button_and_screen_interaction(self):
        btn_clicked = False

        def on_click():
            nonlocal btn_clicked
            btn_clicked = True

        btn = Button(Rect(10, 10, 100, 40), "Click Me", action=on_click)
        self.assertTrue(btn.hit_test(50, 20))
        self.assertFalse(btn.hit_test(200, 200))

        screen = TitleScreen("My Novel")
        mgr = ScreenManager()
        mgr.register(screen)

        class DummySession:
            def advance(self): pass

        mgr.show("title", DummySession())
        self.assertEqual(mgr.active_screen.name, "title")

        # Click first button (Start Game)
        mgr.active_screen.handle_mouse_move(150, 320)
        self.assertTrue(mgr.active_screen.handle_mouse_click(150, 320))

    def test_screen_draw(self):
        screen = TitleScreen("Awesome Game")
        backend = MockUIDrawBackend()

        class DummySession:
            def advance(self): pass

        screen.on_enter(DummySession())
        screen.draw(backend, 1280, 720)

        self.assertTrue(len(backend.rects) > 0)
        self.assertTrue(any("Awesome Game" in t[0] for t in backend.texts))

    def test_project_config_and_graph_merge(self):
        with tempfile.TemporaryDirectory() as td:
            toml_path = Path(td) / "game.toml"
            toml_path.write_text("""
[game]
title = "Merged Novel"
version = "2.0.0"

[window]
width = 1280
height = 720
""")
            cfg = ProjectConfig.load(toml_path)
            self.assertEqual(cfg.title, "Merged Novel")
            self.assertEqual(cfg.virtual_width, 1280)

        # Merge graphs
        g1 = parse_graph("## Part 1 --- p1\nNarrator: Chapter 1")
        g2 = parse_graph("## Part 2 --- p2\nNarrator: Chapter 2")
        merged = merge_graphs([g1, g2])
        self.assertEqual(len(merged.nodes), 2)
        self.assertIn("p1", merged.nodes)
        self.assertIn("p2", merged.nodes)

    def test_widgets_bar_and_grid(self):
        from eager_graphics.screens import Bar, Grid
        from eager_graphics.types import Color, Rect

        bar = Bar(Rect(10, 10, 100, 20), value=0.5, max_value=1.0)
        backend = MockUIDrawBackend()
        bar.draw(backend, Color(0.1, 0.1, 0.1, 1.0), Color(0.8, 0.2, 0.2, 1.0), border_color=Color(1, 1, 1, 1))
        self.assertTrue(len(backend.rects) >= 2)

        grid = Grid(Rect(0, 0, 300, 200), rows=2, cols=3, padding=0.0, spacing_x=0.0, spacing_y=0.0)
        c0 = grid.cell_rect(0, 0)
        self.assertEqual((c0.x, c0.y, c0.width, c0.height), (0, 0, 100, 100))
        c4 = grid.cell_rect_by_index(4)
        self.assertEqual((c4.x, c4.y, c4.width, c4.height), (100, 100, 100, 100))

    def test_preferences_screen(self):
        from eager_graphics.screens import PreferencesScreen

        class DummyPreferences:
            master_volume = 1.0
            music_volume = 0.8
            sfx_volume = 1.0
            voice_volume = 1.0
            text_speed = 50.0
            auto_forward_time = 3.0

        class DummySession:
            def __init__(self):
                self.preferences = DummyPreferences()
                self.applied = False
                self.screens = ScreenManager()

            def apply_preferences(self):
                self.applied = True

        session = DummySession()
        pref_screen = PreferencesScreen()
        session.screens.register(pref_screen)
        session.screens.show("preferences", session)

        # Hit test slider
        slider = pref_screen.sliders[0]
        pref_screen.handle_mouse_click(slider.rect.x + slider.rect.width * 0.5, slider.rect.y + 5)
        self.assertTrue(session.applied)

        # Back button
        back_btn = pref_screen.buttons[0]
        self.assertTrue(pref_screen.handle_mouse_click(back_btn.rect.x + 5, back_btn.rect.y + 5))
        self.assertFalse(session.screens.is_active)

    def test_preferences_screen_language_selection(self):
        from eager_graphics.screens import PreferencesScreen

        class DummyPreferences:
            master_volume = 1.0
            music_volume = 1.0
            sfx_volume = 1.0
            voice_volume = 1.0
            text_speed = 50.0
            auto_forward_time = 3.0
            language = "default"

        class DummyTranslationManager:
            def available_locales(self):
                return ["default", "es", "ja"]

        class DummySession:
            def __init__(self):
                self.preferences = DummyPreferences()
                self.translation_manager = DummyTranslationManager()
                self.screens = ScreenManager()
                self.chosen_locale = "default"

            def apply_preferences(self):
                pass

            def set_language(self, locale: str):
                self.chosen_locale = locale
                self.preferences.language = locale

        session = DummySession()
        pref_screen = PreferencesScreen()
        session.screens.register(pref_screen)
        session.screens.show("preferences", session)

        # Button 0 is Back, Buttons 1..3 are languages: default, es, ja
        self.assertEqual(len(pref_screen.buttons), 4)
        self.assertIn("DEFAULT", pref_screen.buttons[1].text)
        self.assertIn("ES", pref_screen.buttons[2].text)
        self.assertIn("JA", pref_screen.buttons[3].text)

        # Click Spanish (buttons[2])
        es_btn = pref_screen.buttons[2]
        self.assertTrue(pref_screen.handle_mouse_click(es_btn.rect.x + 5, es_btn.rect.y + 5))
        self.assertEqual(session.chosen_locale, "es")
        self.assertEqual(session.preferences.language, "es")

        # After clicking, screen re-initializes on_enter, so active marker updates
        self.assertIn("[ ES ]", pref_screen.buttons[2].text)

    def test_history_screen(self):
        from eager_graphics.screens import HistoryScreen

        class DummyEntry:
            speaker = "Alice"
            text = "Hello world"

        class DummyBacklog:
            def __init__(self):
                self.entries = [DummyEntry() for _ in range(10)]

        class DummySession:
            def __init__(self):
                self.backlog = DummyBacklog()
                self.screens = ScreenManager()

        session = DummySession()
        history_screen = HistoryScreen()
        session.screens.register(history_screen)
        session.screens.show("history", session)

        history_screen.scroll_up()
        self.assertGreater(history_screen.scroll_offset, 0)
        history_screen.scroll_down()
        self.assertEqual(history_screen.scroll_offset, 0)

        backend = MockUIDrawBackend()
        history_screen.draw(backend, 1280, 720)
        self.assertTrue(any("Dialogue History" in t[0] for t in backend.texts))

    def test_screen_manager_navigation_and_input(self):
        from eager_graphics.screens import Screen

        s1 = Screen("s1")
        s2 = Screen("s2")
        mgr = ScreenManager()
        mgr.register(s1)
        mgr.register(s2)

        mgr.show("s1", None)
        self.assertTrue(mgr.is_active)
        self.assertEqual(mgr.active_screen.name, "s1")

        mgr.show("s2", None)
        self.assertEqual(mgr.active_screen.name, "s2")

        # Esc dismisses to previous
        self.assertTrue(mgr.handle_key("escape", None))
        self.assertEqual(mgr.active_screen.name, "s1")

        # Esc dismisses final
        self.assertTrue(mgr.handle_key("escape", None))
        self.assertFalse(mgr.is_active)

    def test_saveload_screen_renders_slot_metadata(self):
        from eager_graphics.screens import SaveLoadScreen

        class DummyMeta:
            slot_name = "slot_1"
            timestamp = "2026-10-13T15:30:00Z"
            scene_id = "throne_room"
            scene_name = "The Throne Room"
            dialogue_snippet = "Welcome traveler to the kingdom."

        class DummySaveManager:
            def get_slot_metadata(self, slot_name: str):
                if slot_name == "slot_1":
                    return DummyMeta()
                return None

        class DummySession:
            def __init__(self):
                self.save_manager = DummySaveManager()
                self.screens = ScreenManager()

        session = DummySession()
        screen = SaveLoadScreen("save")
        screen.on_enter(session)

        # Slot 1 button should contain title, timestamp, and snippet
        slot1_btn = screen.buttons[0]
        self.assertIn("Slot 1: The Throne Room", slot1_btn.text)
        self.assertIn("2026-10-13 15:30", slot1_btn.text)
        self.assertIn("Welcome traveler to the kingdom.", slot1_btn.text)

        # Slot 2 should show empty
        slot2_btn = screen.buttons[1]
        self.assertIn("[Empty Slot]", slot2_btn.text)

        # Draw screen
        backend = MockUIDrawBackend()
        screen.draw(backend, 1280, 720)
        self.assertTrue(any("Slot 1: The Throne Room" in t[0] for t in backend.texts))

    def test_button_multiline_card_draw(self):
        btn = Button(Rect(10, 10, 200, 100), "Title Line\nSubtitle Line\nSnippet Line")
        backend = MockUIDrawBackend()
        btn.draw(backend, Color(0, 0, 0, 1), Color(1, 1, 1, 1), Color(1, 1, 1, 1), Color(1, 1, 1, 1))

        drawn_texts = [t[0] for t in backend.texts]
        self.assertIn("Title Line", drawn_texts)
        self.assertIn("Subtitle Line", drawn_texts)
        self.assertIn("Snippet Line", drawn_texts)


if __name__ == "__main__":
    unittest.main()
