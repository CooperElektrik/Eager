"""Tests for Phase 7 features: scene, image, side images, NVL mode, input hook, gallery & achievements."""

from pathlib import Path

from eager_core.events import InputPromptEvent
from eager_runtime.persistent import PersistentData
from eager_runtime.session import GameSession

from eager_graphics.compositor import StageCompositor
from eager_graphics.director import StageDirector
from eager_graphics.renderers.null import NullRenderer
from eager_graphics.ui_components import UIOverlay


def test_scene_and_image_hooks():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    # Put a character sprite on the stage
    compositor.show_character("alice", "happy", position="center", transition="cut")
    assert "alice" in compositor.stage.get_layer("characters").elements


    # ~ scene clears characters and sets background
    director.handle_scene("forest with cut")
    char_layer = compositor.stage.get_layer("characters")
    assert len(char_layer.elements) == 0
    bg_layer = compositor.stage.get_layer("background")
    assert "bg_main" in bg_layer.elements
    assert bg_layer.elements["bg_main"].asset_id == "bg/forest"


    # ~ image displays arbitrary foreground element
    director.handle_image("item_sword props/sword at center z=50")
    fg_layer = compositor.stage.get_layer("foreground")
    assert "item_sword" in fg_layer.elements
    assert fg_layer.elements["item_sword"].asset_id == "props/sword"


def test_side_image_resolution():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    director.register_character("alice", asset_prefix="char/alice", side_image="side/alice")
    director.register_character("bob", asset_prefix="char/bob")

    # Alice has explicit side_image
    side_alice = director._resolve_side_image("alice", "happy")
    assert side_alice == "side/alice"

    # Bob falls back to asset_prefix + emotion
    side_bob = director._resolve_side_image("bob", "smile")
    assert side_bob == "char/bob_smile"

    # Unknown speaker has no side image
    assert director._resolve_side_image("unknown", None) is None


def test_nvl_mode_and_overlay():
    compositor = StageCompositor()
    director = StageDirector(compositor)

    # Toggle NVL mode on
    director.handle_nvl("on")
    assert director.ui_state.nvl_mode is True

    # Simulate dialogue events
    class DummyEvent:
        def __init__(self, speaker, text, emotion=None):
            self.speaker = speaker
            self.text = text
            self.emotion = emotion

    director.handle_dialogue_event(DummyEvent("Alice", "First NVL line."))
    director.handle_dialogue_event(DummyEvent("Bob", "Second NVL line."))
    director.handle_narration_event(DummyEvent(None, "And narrator spoke."))

    assert len(director.ui_state.nvl_entries) == 3
    assert director.ui_state.nvl_entries[0].speaker == "Alice"
    assert director.ui_state.nvl_entries[1].text == "Second NVL line."

    # Append
    director.handle_append_event(DummyEvent(None, "More narrator text."))
    assert "More narrator text." in director.ui_state.nvl_entries[2].text

    # Draw through NullRenderer to verify UIOverlay renders NVL without error
    renderer = NullRenderer()
    overlay = UIOverlay(1280, 720)
    overlay.draw(renderer, director.ui_state)

    # Verify rect was drawn for NVL window
    rects = [c for c in renderer.ui_calls if c["kind"] == "rect"]
    assert len(rects) > 0

    # Clear NVL
    director.handle_nvl_clear("")
    assert len(director.ui_state.nvl_entries) == 0

    # Toggle NVL off
    director.handle_nvl("off")
    assert director.ui_state.nvl_mode is False


def test_input_prompt_event_and_submission(tmp_path: Path):
    script = """
## Start
~ input player_name "What is your name?"
Alice: Hello, [player_name]!
"""
    script_file = tmp_path / "story.es"
    script_file.write_text(script, encoding="utf-8")

    session = GameSession(script_file)
    ev = session.advance()

    # Should pause on input_prompt
    assert isinstance(ev, InputPromptEvent)
    assert ev.var_name == "player_name"
    assert ev.prompt == "What is your name?"

    # Advance is blocked until input is submitted
    assert session.advance() == ev

    # Submit input
    diag = session.submit_input("Hero")
    assert diag is not None
    assert diag.type == "dialogue"
    assert "Hello, Hero!" in diag.text
    assert session.vm.get_variable("player_name") == "Hero"


def test_gallery_and_achievements(tmp_path: Path):
    pfile = tmp_path / "persistent.json"
    p = PersistentData(pfile)

    assert not p.is_gallery_unlocked("cg_ending_1")
    p.unlock_gallery("cg_ending_1")
    assert p.is_gallery_unlocked("cg_ending_1")

    assert not p.has_achievement("ach_first_win")
    p.unlock_achievement("ach_first_win")
    assert p.has_achievement("ach_first_win")

    # Reload from disk
    p2 = PersistentData(pfile)
    assert p2.is_gallery_unlocked("cg_ending_1")
    assert p2.has_achievement("ach_first_win")
