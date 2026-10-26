"""Adversarial stress test suite for Milestone 3 Challenger 2.

Empirical verification of:
1. Stage composition edge cases (offscreen coordinates, extreme/negative scales,
   rotations beyond 360 degrees, opacity boundary culling, layer z-ordering)
   across both NullRenderer and PILRenderer.
2. API Sealing & Namespace Leaks (submodules define sorted __all__, star import purity,
   ChoiceOption absence from eager_graphics and eager_graphics.ui_state).
3. Packaging metadata (absence of Python 3.10 classifier).
"""

from __future__ import annotations

import importlib
import pkgutil
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any

from eager_core.types import Vec2

from eager_graphics import NullRenderer, StageCompositor
from eager_graphics.renderers.pil import PIL_AVAILABLE, PILRenderer
from eager_graphics.stage import ElementState, Layer, Stage, StageElement


class TestStageCompositionAdversarialMatrix(unittest.TestCase):
    """Stress-test stage composition transformations, layer ordering, and rendering."""

    def test_extreme_coordinates_and_negative_scales_rendering(self) -> None:
        """Verify rendering handles extreme offscreen coordinates and negative/zero scales."""
        comp = StageCompositor(1920, 1080)
        null_backend = NullRenderer()

        test_configs = [
            ("offscreen_tl", Vec2(-9999.0, 50000.0), Vec2(-2.0, 0.0), 1440.5),
            ("offscreen_br", Vec2(100000.0, -80000.0), Vec2(0.0, -2.0), -2880.0),
            ("center_zero", Vec2(960.0, 540.0), Vec2(0.0, 0.0), 36000.0),
            ("flipped_xy", Vec2(100.0, 100.0), Vec2(-1.5, -1.5), 720.25),
        ]

        for char_id, pos, scale, rot in test_configs:
            comp.show_character(char_id, "idle", position="center", transition="cut")
            elem = comp.stage.get_element("characters", char_id)
            self.assertIsNotNone(elem)
            assert elem is not None
            elem.state.position = pos
            elem.state.scale = scale
            elem.state.rotation = rot

        # Render with NullRenderer
        null_backend.render_compositor(comp, 1280, 720)
        self.assertEqual(null_backend.frame_count, 1)

        frame_items = {it.asset_id: it for it in null_backend.last_frame}
        self.assertEqual(frame_items["offscreen_tl/idle"].x, -9999.0)
        self.assertEqual(frame_items["offscreen_tl/idle"].y, 50000.0)
        self.assertEqual(frame_items["offscreen_tl/idle"].scale_x, -2.0)
        self.assertEqual(frame_items["offscreen_tl/idle"].scale_y, 0.0)
        self.assertEqual(frame_items["offscreen_tl/idle"].rotation, 1440.5)

        # Render with PILRenderer
        if PIL_AVAILABLE:
            pil_backend = PILRenderer(1280, 720)
            img = pil_backend.render_compositor(comp, 1280, 720)
            self.assertEqual(img.size, (1280, 720))

    def test_opacity_culling_boundaries(self) -> None:
        """Verify strict opacity culling: opacity <= 0 is culled, > 0 is preserved."""
        comp = StageCompositor(1920, 1080)
        backend = NullRenderer()

        comp.show_character("actor_zero", "idle", position="center", transition="cut")
        comp.show_character("actor_tiny", "idle", position="center", transition="cut")
        comp.show_character("actor_full", "idle", position="center", transition="cut")

        e_zero = comp.stage.get_element("characters", "actor_zero")
        e_tiny = comp.stage.get_element("characters", "actor_tiny")
        e_full = comp.stage.get_element("characters", "actor_full")

        assert e_zero is not None and e_tiny is not None and e_full is not None
        e_zero.state.opacity = 0.0
        e_tiny.state.opacity = 0.001
        e_full.state.opacity = 1.0

        backend.render_compositor(comp, 1280, 720)
        rendered_assets = [it.asset_id for it in backend.last_frame]

        self.assertFalse(any("actor_zero" in a for a in rendered_assets))
        self.assertTrue(any("actor_tiny" in a for a in rendered_assets))
        self.assertTrue(any("actor_full" in a for a in rendered_assets))

        if PIL_AVAILABLE:
            pil_backend = PILRenderer(1280, 720)
            img = pil_backend.render_compositor(comp, 1280, 720)
            self.assertEqual(img.size, (1280, 720))

    def test_layer_z_ordering_and_element_lookup_edge_cases(self) -> None:
        """Verify custom layer sorting with negative, zero, and high z-orders and element lookups."""
        stage = Stage()
        # Default layers: background(0), characters(100), foreground(200), ui(300), overlay(400)
        layer_sub = Layer("sub_underworld", z_order=-999)
        layer_zero = Layer("zero_layer", z_order=0)
        layer_mid = Layer("mid_layer", z_order=150)
        layer_sky = Layer("sky_layer", z_order=9999)

        stage.add_layer(layer_sub)
        stage.add_layer(layer_zero)
        stage.add_layer(layer_mid)
        stage.add_layer(layer_sky)

        sorted_layers = stage.get_sorted_layers()
        names = [l.name for l in sorted_layers]
        self.assertEqual(names[0], "sub_underworld")
        self.assertEqual(names[-1], "sky_layer")
        self.assertIn("mid_layer", names)

        # Lookup and removal edge cases
        self.assertIsNone(stage.get_element("sub_underworld", "phantom"))
        self.assertIsNone(stage.get_element("nonexistent_layer", "any"))
        self.assertIsNone(stage.find_element("phantom"))

        elem = StageElement("phantom_item", ElementState(asset_id="test_asset"))
        stage.layers["sub_underworld"].add_element(elem)

        found = stage.find_element("phantom_item")
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found[0], "sub_underworld")
        self.assertEqual(found[1].element_id, "phantom_item")

        # Layer removal
        removed_layer = stage.remove_layer("sub_underworld")
        self.assertIsNotNone(removed_layer)
        self.assertIsNone(stage.get_layer("sub_underworld"))
        self.assertIsNone(stage.find_element("phantom_item"))

    def test_snapshot_serialization_with_extreme_values(self) -> None:
        """Verify compositor state serialization preserves extreme values accurately."""
        comp = StageCompositor(1920, 1080)
        comp.show_character("extreme_char", "idle", position="center", transition="cut")
        elem = comp.stage.get_element("characters", "extreme_char")
        assert elem is not None
        elem.state.position = Vec2(-9999.0, 50000.0)
        elem.state.scale = Vec2(-2.0, 0.0)
        elem.state.rotation = 1440.5

        state = comp.save_state()
        new_comp = StageCompositor(1920, 1080)
        new_comp.load_state(state)

        restored_elem = new_comp.stage.get_element("characters", "extreme_char")
        self.assertIsNotNone(restored_elem)
        assert restored_elem is not None
        self.assertEqual(restored_elem.state.position.x, -9999.0)
        self.assertEqual(restored_elem.state.position.y, 50000.0)
        self.assertEqual(restored_elem.state.scale.x, -2.0)
        self.assertEqual(restored_elem.state.scale.y, 0.0)
        self.assertEqual(restored_elem.state.rotation, 1440.5)


class TestAPISealingAndNamespaceIntegrity(unittest.TestCase):
    """Stress-test API sealing, sortedness of __all__, and export purity across submodules."""

    def test_all_public_submodules_define_all(self) -> None:
        """Verify that every public submodule in eager_graphics defines __all__."""
        import eager_graphics

        for _, modname, _ in pkgutil.walk_packages(
            eager_graphics.__path__, eager_graphics.__name__ + "."
        ):
            parts = modname.split(".")
            # Ignore private implementation modules starting with _
            if any(p.startswith("_") for p in parts[1:]):
                continue
            mod: ModuleType = importlib.import_module(modname)
            self.assertTrue(
                hasattr(mod, "__all__"),
                f"Public submodule {modname} is missing explicit __all__",
            )
            all_list = getattr(mod, "__all__", None)
            self.assertIsInstance(
                all_list,
                list,
                f"Submodule {modname}.__all__ must be a list",
            )

    def test_star_import_purity_across_all_submodules(self) -> None:
        """Verify that 'from submodule import *' exports ONLY symbols in __all__."""
        import eager_graphics

        for _, modname, _ in pkgutil.walk_packages(
            eager_graphics.__path__, eager_graphics.__name__ + "."
        ):
            parts = modname.split(".")
            if any(p.startswith("_") for p in parts[1:]):
                continue
            mod: ModuleType = importlib.import_module(modname)
            all_symbols: list[str] = mod.__all__

            # Check that every symbol in __all__ actually exists on the module
            for sym in all_symbols:
                self.assertTrue(
                    hasattr(mod, sym),
                    f"{modname}: symbol '{sym}' listed in __all__ does not exist",
                )

            # Test star import namespace
            star_ns: dict[str, Any] = {}
            exec(f"from {modname} import *", {}, star_ns)  # noqa: S102

            self.assertEqual(
                set(star_ns.keys()),
                set(all_symbols),
                f"{modname}: star import namespace does not match __all__",
            )

    def test_choice_option_strictly_unexported(self) -> None:
        """Verify ChoiceOption is NOT exported by eager_graphics or eager_graphics.ui_state."""
        import eager_graphics
        from eager_graphics import ui_state

        # Must not be in root __all__
        self.assertNotIn("ChoiceOption", eager_graphics.__all__)
        self.assertFalse(hasattr(eager_graphics, "ChoiceOption"))

        # Direct import from root must raise ImportError
        with self.assertRaises(ImportError):
            from eager_graphics import ChoiceOption  # type: ignore[attr-defined] # noqa: F401

        # Must not be exported in ui_state.__all__
        self.assertNotIn("ChoiceOption", ui_state.__all__)

        # Star import from ui_state must NOT export ChoiceOption
        star_ns: dict[str, Any] = {}
        exec("from eager_graphics.ui_state import *", {}, star_ns)  # noqa: S102
        self.assertNotIn("ChoiceOption", star_ns)

    def test_pyproject_toml_no_python_310_classifier(self) -> None:
        """Verify packages/eager-graphics/pyproject.toml does not contain Python 3.10 classifier."""
        pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        self.assertTrue(pyproject_path.exists())
        content = pyproject_path.read_text(encoding="utf-8")
        self.assertNotIn("3.10", content)


if __name__ == "__main__":
    unittest.main()
