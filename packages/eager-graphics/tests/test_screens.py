"""Tests for Phase 6 screens, menus, theme, and project config."""

import tempfile
import unittest
from pathlib import Path

from eager_core.types import Color, Rect
from eager_runtime.project import ProjectConfig, merge_graphs
from eager_script import parse_graph

from eager_graphics.screens import Button, ScreenManager, TitleScreen


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
        from eager_core.types import Color, Rect

        from eager_graphics.screens import Bar, Grid

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

    def test_history_screen_draw_before_on_enter(self):
        from eager_graphics.screens import HistoryScreen

        history_screen = HistoryScreen()
        backend = MockUIDrawBackend()
        # Draw without session / before on_enter
        history_screen.draw(backend, 1280, 720)
        self.assertTrue(any("Dialogue History" in t[0] for t in backend.texts))
        self.assertTrue(any("No dialogue recorded yet." in t[0] for t in backend.texts))
        # Back button action should be safe to call even without session
        for btn in history_screen.buttons:
            if btn.text == "Back" and btn.action:
                btn.action()

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

    def test_history_screen_voice_replay_speaker_buttons(self):
        from eager_graphics.screens import HistoryScreen

        class DummyEntry:
            def __init__(self, speaker, text, voice=None):
                self.speaker = speaker
                self.text = text
                self.voice = voice

        class DummyBacklog:
            def __init__(self, entries):
                self.entries = entries

        class MockAudio:
            def __init__(self):
                self.played = []

            def play(self, channel, asset_path, *, loop=False, **kwargs):
                self.played.append((channel, str(asset_path), loop))

        class DummySession:
            def __init__(self, entries):
                self.backlog = DummyBacklog(entries)
                self.screens = ScreenManager()
                self.audio = MockAudio()

        entries = [
            DummyEntry("Alice", "Hello without voice", voice=None),
            DummyEntry("Bob", "Voice clip 1", voice="bob_01.ogg"),
            DummyEntry("Alice", "Voice clip 2", voice="alice_02.ogg"),
            DummyEntry(None, "Narration voice", voice="narrator_01.ogg"),
        ]
        session = DummySession(entries)
        history_screen = HistoryScreen()
        session.screens.register(history_screen)
        session.screens.show("history", session)

        # Check buttons: Up, Down, Back + 3 speaker buttons for the 3 entries with voice
        speaker_buttons = [b for b in history_screen.buttons if b.text == "🔊"]
        self.assertEqual(len(speaker_buttons), 3)
        self.assertEqual(speaker_buttons[0].voice, "bob_01.ogg")
        self.assertEqual(speaker_buttons[1].voice, "alice_02.ogg")
        self.assertEqual(speaker_buttons[2].voice, "narrator_01.ogg")

        # Test hover state
        history_screen.handle_mouse_move(speaker_buttons[0].rect.x + 2, speaker_buttons[0].rect.y + 2)
        self.assertTrue(speaker_buttons[0].hovered)

        # Click the first speaker button to replay voice
        clicked = history_screen.handle_mouse_click(speaker_buttons[0].rect.x + 2, speaker_buttons[0].rect.y + 2)
        self.assertTrue(clicked)
        self.assertEqual(session.audio.played, [("voice", "bob_01.ogg", False)])

        # Click the second speaker button
        clicked2 = history_screen.handle_mouse_click(speaker_buttons[1].rect.x + 2, speaker_buttons[1].rect.y + 2)
        self.assertTrue(clicked2)
        self.assertEqual(session.audio.played[-1], ("voice", "alice_02.ogg", False))

        # Test draw with mock backend
        backend = MockUIDrawBackend()
        history_screen.draw(backend, 1280, 720)
        speaker_draws = [t for t in backend.texts if t[0] == "🔊"]
        self.assertEqual(len(speaker_draws), 3)

        # Test session.play_voice delegation if play_voice is provided on session
        session.play_voice_calls = []
        session.play_voice = lambda v: session.play_voice_calls.append(v)
        history_screen.replay_voice("custom_voice.ogg")
        self.assertEqual(session.play_voice_calls, ["custom_voice.ogg"])

        # Scrolling test with voice buttons
        many_entries = [
            DummyEntry("Char", f"Line {i}", voice=f"voice_{i}.ogg" if i % 2 == 0 else None)
            for i in range(15)
        ]
        scroll_session = DummySession(many_entries)
        history_screen2 = HistoryScreen()
        scroll_session.screens.register(history_screen2)
        scroll_session.screens.show("history", scroll_session)

        # Offset 0: displays slice 8..15 (7 entries: indices 8, 9, 10, 11, 12, 13, 14)
        # Even indices in 8..14 are 8, 10, 12, 14 -> 4 speaker buttons
        btn_voices = [b.voice for b in history_screen2.buttons if b.voice]
        self.assertEqual(btn_voices, ["voice_8.ogg", "voice_10.ogg", "voice_12.ogg", "voice_14.ogg"])

        history_screen2.scroll_up()
        # After scroll_up (offset 1): displays slice 7..14 (indices 7, 8, 9, 10, 11, 12, 13)
        # Even indices: 8, 10, 12 -> 3 speaker buttons
        btn_voices2 = [b.voice for b in history_screen2.buttons if b.voice]
        self.assertEqual(btn_voices2, ["voice_8.ogg", "voice_10.ogg", "voice_12.ogg"])

    def test_proportional_layout_800x600_no_clipping(self):
        """Screens rendered at 800x600 must keep all widgets within bounds without clipping."""
        from eager_graphics.screens import (
            HistoryScreen,
            PreferencesScreen,
            SaveLoadScreen,
            TitleScreen,
        )

        # 1. HistoryScreen at 800x600: Up/Down buttons must not be at x=1100, Back button not at y=620
        history = HistoryScreen(viewport_width=800, viewport_height=600)
        up_btn = history.buttons[0]
        down_btn = history.buttons[1]
        back_btn = history.buttons[2]

        # In 800x600, all buttons must fit completely inside [0, 800] x [0, 600]
        self.assertLess(up_btn.rect.x + up_btn.rect.width, 800.0)
        self.assertLess(down_btn.rect.x + down_btn.rect.width, 800.0)
        self.assertLess(back_btn.rect.y + back_btn.rect.height, 600.0)
        self.assertGreater(up_btn.rect.x, 0.0)
        self.assertGreater(back_btn.rect.y, 0.0)

        # 2. SaveLoadScreen at 800x600: Grid and Back button must be within bounds
        save_screen = SaveLoadScreen("save", viewport_width=800, viewport_height=600)
        save_back = save_screen.buttons[-1]
        self.assertLess(save_back.rect.y + save_back.rect.height, 600.0)
        for b in save_screen.buttons:
            self.assertLess(b.rect.x + b.rect.width, 800.0)
            self.assertLess(b.rect.y + b.rect.height, 600.0)

        # 3. PreferencesScreen at 800x600: Sliders, labels, and buttons within bounds
        pref_screen = PreferencesScreen(viewport_width=800, viewport_height=600)
        pref_back = pref_screen.buttons[0]
        self.assertLess(pref_back.rect.y + pref_back.rect.height, 600.0)
        for s in pref_screen.sliders:
            self.assertLess(s.rect.x + s.rect.width, 800.0)
            self.assertLess(s.rect.y + s.rect.height, 600.0)

        # 4. TitleScreen at 800x600: Buttons within bounds
        title_screen = TitleScreen("Test Game", viewport_width=800, viewport_height=600)
        for b in title_screen.buttons:
            self.assertLess(b.rect.x + b.rect.width, 800.0)
            self.assertLess(b.rect.y + b.rect.height, 600.0)

    def test_proportional_layout_1920x1080_scales_beyond_1280x720(self):
        """Screens rendered at 1920x1080 must expand beyond the 1280x720 bounding area."""
        from eager_graphics.screens import (
            HistoryScreen,
            PreferencesScreen,
            SaveLoadScreen,
            TitleScreen,
        )

        # HistoryScreen: Up/Down buttons should be placed proportionally near right margin (x > 1280)
        history = HistoryScreen(viewport_width=1920, viewport_height=1080)
        up_btn = history.buttons[0]
        back_btn = history.buttons[2]
        self.assertGreater(up_btn.rect.x, 1280.0)
        self.assertGreater(back_btn.rect.y, 720.0)

        # SaveLoadScreen: Grid slot buttons and back button should scale into 1080p space
        save_screen = SaveLoadScreen("save", viewport_width=1920, viewport_height=1080)
        save_back = save_screen.buttons[-1]
        self.assertGreater(save_back.rect.y, 720.0)

        # PreferencesScreen: language buttons should extend past 1280 or sliders scale
        pref_screen = PreferencesScreen(viewport_width=1920, viewport_height=1080)
        self.assertGreater(pref_screen.sliders[0].rect.width, 300.0)

        # TitleScreen: Buttons are wider and positioned lower than in 720p
        title_screen = TitleScreen("Test Game", viewport_width=1920, viewport_height=1080)
        self.assertGreater(title_screen.buttons[0].rect.y, 300.0)
        self.assertGreater(title_screen.buttons[0].rect.width, 240.0)

    def test_dynamic_viewport_resize(self):
        """ScreenManager and Screens should recompute layouts dynamically on resize."""
        screen = TitleScreen("Dynamic Game", viewport_width=1280, viewport_height=720)
        orig_btn_rect = screen.buttons[0].rect

        # Resize to 800x600 via set_viewport
        screen.set_viewport(800, 600)
        resized_rect = screen.buttons[0].rect
        self.assertNotEqual(orig_btn_rect, resized_rect)
        self.assertLess(resized_rect.width, orig_btn_rect.width)
        self.assertLess(resized_rect.y, orig_btn_rect.y)

        # Resize to 1920x1080 via draw
        backend = MockUIDrawBackend()
        screen.draw(backend, 1920, 1080)
        fhd_rect = screen.buttons[0].rect
        self.assertGreater(fhd_rect.width, orig_btn_rect.width)
        self.assertGreater(fhd_rect.y, orig_btn_rect.y)


if __name__ == "__main__":
    unittest.main()
