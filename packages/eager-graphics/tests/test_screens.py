"""Tests for Phase 6 screens, menus, theme, and project config."""

import tempfile
from pathlib import Path
from typing import Any

from eager_core.types import WHITE, Color, Rect
from eager_runtime.project import ProjectConfig, merge_graphs
from eager_script import parse_graph

from eager_graphics.screens import Button, ScreenManager, TitleScreen


class MockUIDrawBackend:
    """Mock UIDrawBackend recording draw calls for testing."""

    def __init__(self) -> None:
        self.rects: list[Any] = []
        self.texts: list[Any] = []
        self.images: list[Any] = []

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
        self.rects.append((x, y, width, height, color, border_color, border_width))

    def draw_rect_outline(
        self, x: float, y: float, width: float, height: float, color: Color, line_width: float = 1.0
    ) -> None:
        self.rects.append(("outline", x, y, width, height, color))

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

    def draw_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        font_size: int = 14,
        color: Color = WHITE,
        bold: bool = False,
        italic: bool = False,
        anchor_x: str = "left",
        anchor_y: str = "top",
        cache: bool = True,
        **kwargs: Any,
    ) -> None:
        kw = {
            "font_size": font_size,
            "color": color,
            "bold": bold,
            "italic": italic,
            "anchor_x": anchor_x,
            "anchor_y": anchor_y,
            "cache": cache,
        }
        kw.update(kwargs)
        self.texts.append((text, x, y, kw))

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
        self.images.append((asset_id, x, y, width, height, tint, anchor_x, anchor_y))

    def measure_text(
        self,
        text: str,
        *,
        font_size: int = 14,
        bold: bool = False,
        italic: bool = False,
        cache: bool = True,
    ) -> tuple[float, float]:
        longest = max((len(line) for line in text.splitlines()), default=0)
        return (longest * font_size * 0.5, float(font_size) * 1.2)


class TestScreensAndProject:
    def test_button_and_screen_interaction(self):
        btn_clicked = False

        def on_click():
            nonlocal btn_clicked
            btn_clicked = True

        btn = Button(Rect(10, 10, 100, 40), "Click Me", action=on_click)
        assert btn.hit_test(50, 20)
        assert not (btn.hit_test(200, 200))

        screen = TitleScreen("My Novel")
        mgr = ScreenManager()
        mgr.register(screen)

        class DummySession:
            def advance(self):
                pass

        mgr.show("title", DummySession())
        assert mgr.active_screen is not None
        assert mgr.active_screen.name == "title"

        # Click first button (Start Game)
        mgr.active_screen.handle_mouse_move(150, 320)
        assert mgr.active_screen.handle_mouse_click(150, 320)

    def test_screen_draw(self):
        screen = TitleScreen("Awesome Game")
        backend = MockUIDrawBackend()

        class DummySession:
            def advance(self):
                pass

        screen.on_enter(DummySession())
        screen.draw(backend, 1280, 720)

        assert len(backend.rects) > 0
        assert any("Awesome Game" in t[0] for t in backend.texts)

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
            assert cfg.title == "Merged Novel"
            assert cfg.virtual_width == 1280

        # Merge graphs
        g1 = parse_graph("## Part 1 --- p1\nNarrator: Chapter 1")
        g2 = parse_graph("## Part 2 --- p2\nNarrator: Chapter 2")
        merged = merge_graphs([g1, g2])
        assert len(merged.nodes) == 2
        assert "p1" in merged.nodes
        assert "p2" in merged.nodes

    def test_widgets_bar_and_grid(self):
        from eager_core.types import Color, Rect

        from eager_graphics.screens import Bar, Grid

        bar = Bar(Rect(10, 10, 100, 20), value=0.5, max_value=1.0)
        backend = MockUIDrawBackend()
        bar.draw(
            backend,
            Color(0.1, 0.1, 0.1, 1.0),
            Color(0.8, 0.2, 0.2, 1.0),
            border_color=Color(1, 1, 1, 1),
        )
        assert len(backend.rects) >= 2

        grid = Grid(Rect(0, 0, 300, 200), rows=2, cols=3, padding=0.0, spacing_x=0.0, spacing_y=0.0)
        c0 = grid.cell_rect(0, 0)
        assert (c0.x, c0.y, c0.width, c0.height) == (0, 0, 100, 100)
        c4 = grid.cell_rect_by_index(4)
        assert (c4.x, c4.y, c4.width, c4.height) == (100, 100, 100, 100)

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
        assert session.applied

        # Back button
        back_btn = pref_screen.buttons[0]
        assert pref_screen.handle_mouse_click(back_btn.rect.x + 5, back_btn.rect.y + 5)
        assert not session.screens.is_active

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
        assert len(pref_screen.buttons) == 4
        assert "DEFAULT" in pref_screen.buttons[1].text
        assert "ES" in pref_screen.buttons[2].text
        assert "JA" in pref_screen.buttons[3].text

        # Click Spanish (buttons[2])
        es_btn = pref_screen.buttons[2]
        assert pref_screen.handle_mouse_click(es_btn.rect.x + 5, es_btn.rect.y + 5)
        assert session.chosen_locale == "es"
        assert session.preferences.language == "es"

        # After clicking, screen re-initializes on_enter, so active marker updates
        assert "[ ES ]" in pref_screen.buttons[2].text

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
        assert history_screen.scroll_offset > 0
        history_screen.scroll_down()
        assert history_screen.scroll_offset == 0

        backend = MockUIDrawBackend()
        history_screen.draw(backend, 1280, 720)
        assert any("Dialogue History" in t[0] for t in backend.texts)

    def test_history_screen_draw_before_on_enter(self):
        from eager_graphics.screens import HistoryScreen

        history_screen = HistoryScreen()
        backend = MockUIDrawBackend()
        # Draw without session / before on_enter
        history_screen.draw(backend, 1280, 720)
        assert any("Dialogue History" in t[0] for t in backend.texts)
        assert any("No dialogue recorded yet." in t[0] for t in backend.texts)
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
        assert mgr.is_active
        assert mgr.active_screen is not None
        assert mgr.active_screen.name == "s1"

        mgr.show("s2", None)
        assert mgr.active_screen is not None
        assert mgr.active_screen.name == "s2"

        # Esc dismisses to previous
        assert mgr.handle_key("escape", None)
        assert mgr.active_screen is not None
        assert mgr.active_screen.name == "s1"

        # Esc dismisses final
        assert mgr.handle_key("escape", None)
        assert not mgr.is_active

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
        assert "Slot 1: The Throne Room" in slot1_btn.text
        assert "2026-10-13 15:30" in slot1_btn.text
        assert "Welcome traveler to the kingdom." in slot1_btn.text

        # Slot 2 should show empty
        slot2_btn = screen.buttons[1]
        assert "[Empty Slot]" in slot2_btn.text

        # Draw screen
        backend = MockUIDrawBackend()
        screen.draw(backend, 1280, 720)
        assert any("Slot 1: The Throne Room" in t[0] for t in backend.texts)

    def test_button_multiline_card_draw(self):
        btn = Button(Rect(10, 10, 200, 100), "Title Line\nSubtitle Line\nSnippet Line")
        backend = MockUIDrawBackend()
        btn.draw(
            backend, Color(0, 0, 0, 1), Color(1, 1, 1, 1), Color(1, 1, 1, 1), Color(1, 1, 1, 1)
        )

        drawn_texts = [t[0] for t in backend.texts]
        assert "Title Line" in drawn_texts
        assert "Subtitle Line" in drawn_texts
        assert "Snippet Line" in drawn_texts

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
                self.play_voice_calls: list[str] = []
                self.play_voice: Any = None

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
        assert len(speaker_buttons) == 3
        assert speaker_buttons[0].voice == "bob_01.ogg"
        assert speaker_buttons[1].voice == "alice_02.ogg"
        assert speaker_buttons[2].voice == "narrator_01.ogg"

        # Test hover state
        history_screen.handle_mouse_move(
            speaker_buttons[0].rect.x + 2, speaker_buttons[0].rect.y + 2
        )
        assert speaker_buttons[0].hovered

        # Click the first speaker button to replay voice
        clicked = history_screen.handle_mouse_click(
            speaker_buttons[0].rect.x + 2, speaker_buttons[0].rect.y + 2
        )
        assert clicked
        assert session.audio.played == [("voice", "bob_01.ogg", False)]

        # Click the second speaker button
        clicked2 = history_screen.handle_mouse_click(
            speaker_buttons[1].rect.x + 2, speaker_buttons[1].rect.y + 2
        )
        assert clicked2
        assert session.audio.played[-1] == ("voice", "alice_02.ogg", False)

        # Test draw with mock backend
        backend = MockUIDrawBackend()
        history_screen.draw(backend, 1280, 720)
        speaker_draws = [t for t in backend.texts if t[0] == "🔊"]
        assert len(speaker_draws) == 3

        # Test session.play_voice delegation if play_voice is provided on session
        session.play_voice_calls = []
        session.play_voice = lambda v: session.play_voice_calls.append(v)
        history_screen.replay_voice("custom_voice.ogg")
        assert session.play_voice_calls == ["custom_voice.ogg"]

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
        assert btn_voices == ["voice_8.ogg", "voice_10.ogg", "voice_12.ogg", "voice_14.ogg"]

        history_screen2.scroll_up()
        # After scroll_up (offset 1): displays slice 7..14 (indices 7, 8, 9, 10, 11, 12, 13)
        # Even indices: 8, 10, 12 -> 3 speaker buttons
        btn_voices2 = [b.voice for b in history_screen2.buttons if b.voice]
        assert btn_voices2 == ["voice_8.ogg", "voice_10.ogg", "voice_12.ogg"]

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
        assert up_btn.rect.x + up_btn.rect.width < 800.0
        assert down_btn.rect.x + down_btn.rect.width < 800.0
        assert back_btn.rect.y + back_btn.rect.height < 600.0
        assert up_btn.rect.x > 0.0
        assert back_btn.rect.y > 0.0

        # 2. SaveLoadScreen at 800x600: Grid and Back button must be within bounds
        save_screen = SaveLoadScreen("save", viewport_width=800, viewport_height=600)
        save_back = save_screen.buttons[-1]
        assert save_back.rect.y + save_back.rect.height < 600.0
        for b in save_screen.buttons:
            assert b.rect.x + b.rect.width < 800.0
            assert b.rect.y + b.rect.height < 600.0

        # 3. PreferencesScreen at 800x600: Sliders, labels, and buttons within bounds
        pref_screen = PreferencesScreen(viewport_width=800, viewport_height=600)
        pref_back = pref_screen.buttons[0]
        assert pref_back.rect.y + pref_back.rect.height < 600.0
        for s in pref_screen.sliders:
            assert s.rect.x + s.rect.width < 800.0
            assert s.rect.y + s.rect.height < 600.0

        # 4. TitleScreen at 800x600: Buttons within bounds
        title_screen = TitleScreen("Test Game", viewport_width=800, viewport_height=600)
        for b in title_screen.buttons:
            assert b.rect.x + b.rect.width < 800.0
            assert b.rect.y + b.rect.height < 600.0

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
        assert up_btn.rect.x > 1280.0
        assert back_btn.rect.y > 720.0

        # SaveLoadScreen: Grid slot buttons and back button should scale into 1080p space
        save_screen = SaveLoadScreen("save", viewport_width=1920, viewport_height=1080)
        save_back = save_screen.buttons[-1]
        assert save_back.rect.y > 720.0

        # PreferencesScreen: language buttons should extend past 1280 or sliders scale
        pref_screen = PreferencesScreen(viewport_width=1920, viewport_height=1080)
        assert pref_screen.sliders[0].rect.width > 300.0

        # TitleScreen: Buttons are wider and positioned lower than in 720p
        title_screen = TitleScreen("Test Game", viewport_width=1920, viewport_height=1080)
        assert title_screen.buttons[0].rect.y > 300.0
        assert title_screen.buttons[0].rect.width > 240.0

    def test_dynamic_viewport_resize(self):
        """ScreenManager and Screens should recompute layouts dynamically on resize."""
        screen = TitleScreen("Dynamic Game", viewport_width=1280, viewport_height=720)
        orig_btn_rect = screen.buttons[0].rect

        # Resize to 800x600 via set_viewport
        screen.set_viewport(800, 600)
        resized_rect = screen.buttons[0].rect
        assert orig_btn_rect != resized_rect
        assert resized_rect.width < orig_btn_rect.width
        assert resized_rect.y < orig_btn_rect.y

        # Resize to 1920x1080 via draw
        backend = MockUIDrawBackend()
        screen.draw(backend, 1920, 1080)
        fhd_rect = screen.buttons[0].rect
        assert fhd_rect.width > orig_btn_rect.width
        assert fhd_rect.y > orig_btn_rect.y

    def test_font_size_scaling_with_viewport_height(self):
        """Screen font_size values must scale proportionally with viewport height relative to 720p."""
        from eager_graphics.screens import (
            HistoryScreen,
            PreferencesScreen,
            SaveLoadScreen,
            TitleScreen,
        )

        backend_720 = MockUIDrawBackend()
        backend_1080 = MockUIDrawBackend()

        # 1. TitleScreen: title (32) and button (16)
        title_720 = TitleScreen("Title Test", viewport_width=1280, viewport_height=720)
        title_720.draw(backend_720, 1280, 720)
        texts_720 = {t[0]: t[3].get("font_size") for t in backend_720.texts}
        assert texts_720["Title Test"] == 32
        assert texts_720["Start Game"] == 16

        title_1080 = TitleScreen("Title Test", viewport_width=1920, viewport_height=1080)
        title_1080.draw(backend_1080, 1920, 1080)
        texts_1080 = {t[0]: t[3].get("font_size") for t in backend_1080.texts}
        assert texts_1080["Title Test"] == 48  # 32 * 1.5
        assert texts_1080["Start Game"] == 24  # 16 * 1.5

        # 2. SaveLoadScreen: header (28) and back button (16)
        backend_720.texts.clear()
        backend_1080.texts.clear()
        save_720 = SaveLoadScreen("save", viewport_width=1280, viewport_height=720)
        save_720.draw(backend_720, 1280, 720)
        texts_720 = {t[0]: t[3].get("font_size") for t in backend_720.texts}
        assert texts_720["Save Game"] == 28
        assert texts_720["Back"] == 16

        save_1080 = SaveLoadScreen("save", viewport_width=1920, viewport_height=1080)
        save_1080.draw(backend_1080, 1920, 1080)
        texts_1080 = {t[0]: t[3].get("font_size") for t in backend_1080.texts}
        assert texts_1080["Save Game"] == 42  # 28 * 1.5
        assert texts_1080["Back"] == 24  # 16 * 1.5

        # 3. PreferencesScreen: header (28), labels (16, 18), back button (16)
        backend_720.texts.clear()
        backend_1080.texts.clear()
        pref_720 = PreferencesScreen(viewport_width=1280, viewport_height=720)
        pref_720.draw(backend_720, 1280, 720)
        texts_720 = {t[0]: t[3].get("font_size") for t in backend_720.texts}
        assert texts_720["Preferences"] == 28
        assert texts_720["Master Volume"] == 16
        assert texts_720["Language"] == 18
        assert texts_720["Back"] == 16

        pref_1080 = PreferencesScreen(viewport_width=1920, viewport_height=1080)
        pref_1080.draw(backend_1080, 1920, 1080)
        texts_1080 = {t[0]: t[3].get("font_size") for t in backend_1080.texts}
        assert texts_1080["Preferences"] == 42  # 28 * 1.5
        assert texts_1080["Master Volume"] == 24  # 16 * 1.5
        assert texts_1080["Language"] == 27  # 18 * 1.5
        assert texts_1080["Back"] == 24  # 16 * 1.5

        # 4. HistoryScreen: header (28), empty (16), entry (14)
        backend_720.texts.clear()
        backend_1080.texts.clear()
        hist_720 = HistoryScreen(viewport_width=1280, viewport_height=720)
        hist_720.draw(backend_720, 1280, 720)
        texts_720 = {t[0]: t[3].get("font_size") for t in backend_720.texts}
        assert texts_720["Dialogue History"] == 28
        assert texts_720["No dialogue recorded yet."] == 16

        hist_1080 = HistoryScreen(viewport_width=1920, viewport_height=1080)
        hist_1080.draw(backend_1080, 1920, 1080)
        texts_1080 = {t[0]: t[3].get("font_size") for t in backend_1080.texts}
        assert texts_1080["Dialogue History"] == 42  # 28 * 1.5
        assert texts_1080["No dialogue recorded yet."] == 24  # 16 * 1.5

    def test_screen_manager_and_screen_theme_propagation(self):
        """ScreenManager theme updates must propagate to registered screens."""
        from eager_graphics.screens import ScreenManager, TitleScreen
        from eager_graphics.theme import Theme

        custom_theme = Theme(name="custom_dark", font_size=20, title_font_size=40)
        mgr = ScreenManager(theme=custom_theme)
        title = TitleScreen("Themed Title")
        mgr.register(title)
        assert title.theme.name == "custom_dark"

        new_theme = Theme(name="new_theme", font_size=18, title_font_size=36)
        mgr.set_theme(new_theme)
        assert title.theme.name == "new_theme"
