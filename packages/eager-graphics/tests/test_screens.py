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

    def draw_text(self, text: str, x: float, y: float, **kwargs) -> None:
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


if __name__ == "__main__":
    unittest.main()
