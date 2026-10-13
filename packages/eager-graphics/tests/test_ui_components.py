"""Tests for the renderer-agnostic UI components in eager_graphics.ui_components."""

from __future__ import annotations

import importlib.util

import pytest

from eager_graphics.renderers.null import NullRenderer
from eager_graphics.ui_components import (
    ChoiceMenu,
    ChoiceMenuStyle,
    DialogueBox,
    DialogueBoxLayout,
    EndNotice,
    TextAnchor,
    TextboxStyle,
    UIOverlay,
)
from eager_graphics.ui_state import ChoiceOption, UIState

# ── DialogueBox ────────────────────────────────────────────────────────────


def test_dialogue_box_is_docked_at_the_bottom() -> None:
    box = DialogueBox(1280, 720)
    box.set_content(None, "Hello")

    layout = box.layout()
    bx, by, bw, bh = layout.box

    assert by + bh == pytest.approx(720 - 25)
    assert bx == pytest.approx(64)
    assert bw == pytest.approx(1152)


def test_dialogue_box_nameplate_straddles_top_edge() -> None:
    box = DialogueBox(1280, 720)
    box.set_content("Meris", "You have returned.")

    layout = box.layout()
    assert layout.nameplate is not None

    _, box_y, _, _ = layout.box
    name_y = layout.nameplate[1]
    name_h = layout.nameplate[3]

    # The nameplate is centred on the box's top edge, overhanging equally.
    assert name_y + (name_h / 2) == pytest.approx(box_y)
    assert name_y < box_y


def test_dialogue_box_no_nameplate_for_narration() -> None:
    box = DialogueBox(1280, 720)
    box.set_content(None, "The wind howls.")

    assert box.layout().nameplate is None


def test_dialogue_box_nameplate_width_scales_with_name() -> None:
    short = DialogueBox(1280, 720)
    short.set_content("Al", "x")
    long = DialogueBox(1280, 720)
    long.set_content("Bartholomew", "x")

    assert long.nameplate_width() > short.nameplate_width()
    assert long.nameplate_width() <= 250


def test_dialogue_box_hides_arrow_when_choices_are_active() -> None:
    box = DialogueBox(1280, 720)
    box.set_content("Meris", "Choose wisely.")
    box.show_advance_arrow = False

    assert box.layout().show_arrow is False


def test_dialogue_box_cache_key_tracks_visible_state() -> None:
    box = DialogueBox(1280, 720)
    box.set_content("Meris", "One")

    key_before = box.cache_key()
    box.set_content("Meris", "Two")
    assert box.cache_key() != key_before

    box.set_content("Meris", "One")
    assert box.cache_key() == key_before


def test_dialogue_box_draw_emits_expected_primitives() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    box.set_content("Meris", "You have returned.")

    box.draw(backend)

    rects = [c for c in backend.ui_calls if c["kind"] == "rect"]
    texts = [c for c in backend.ui_calls if c["kind"] == "text"]

    # Box background plus the speaker nameplate.
    assert len(rects) == 2
    # Nameplate label, dialogue text, and the advance arrow.
    assert len(texts) == 3
    assert texts[0]["text"] == "Meris"
    assert texts[1]["text"] == "You have returned."


def test_dialogue_box_draw_is_a_noop_without_text() -> None:
    backend = NullRenderer()
    DialogueBox(1280, 720).draw(backend)
    assert backend.ui_calls == []


def test_dialogue_box_draws_multiline_wrapped_text() -> None:
    from eager_graphics.ui_components import wrap_text

    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    # text_max_w is ~1072 px. With NullRenderer measure_text (len * 14 * 0.5 = len * 7 px),
    # a line needs > 154 characters to wrap.
    long_text = (
        "This is an exceptionally long dialogue line written specifically to ensure that "
        "the automatic word-wrapping logic in DialogueBox will break it across multiple distinct lines "
        "even when measured by the NullRenderer monospace-estimate implementation."
    )
    box.set_content("Alice", long_text)
    box.draw(backend)

    # Filter text calls for lines that are not the nameplate or arrow
    text_calls = [c for c in backend.ui_calls if c["kind"] == "text"]
    dialogue_lines = [c for c in text_calls if c["text"] not in ("Alice", "▼")]

    assert len(dialogue_lines) >= 2
    # Verify line height vertical spacing
    line_spacing = dialogue_lines[1]["y"] - dialogue_lines[0]["y"]
    assert line_spacing == pytest.approx(box.style.text_font_size * 1.35)

    # Directly verify wrap_text function
    wrapped = wrap_text("Short text", 200, backend.measure_text, font_size=14)
    assert wrapped == ["Short text"]

    wrapped_broken = wrap_text("Line 1\nLine 2", 200, backend.measure_text, font_size=14)
    assert wrapped_broken == ["Line 1", "Line 2"]



def test_dialogue_box_respects_viewport_changes() -> None:
    box = DialogueBox(1280, 720)
    box.set_content(None, "Hello")
    wide_y = box.layout().box[1]

    box.set_viewport(1280, 1080)
    tall_y = box.layout().box[1]

    # A taller viewport pushes the bottom-docked box further down.
    assert tall_y > wide_y


def test_textbox_style_scaling_helpers() -> None:
    style = TextboxStyle()

    assert style.box_margin(1280) == pytest.approx(64)
    assert style.box_margin(320) == pytest.approx(20)
    assert style.box_height(720) == pytest.approx(158)
    assert style.box_height(200) == pytest.approx(110)


# ── ChoiceMenu ─────────────────────────────────────────────────────────────


def _options(n: int) -> tuple[ChoiceOption, ...]:
    return tuple(ChoiceOption(i, f"Option {i}", f"target_{i}") for i in range(n))


def test_choice_menu_layout_is_centered_and_stacked() -> None:
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(3))

    rects = menu.layout()
    assert len(rects) == 3

    xs = {r[0] for r in rects}
    assert len(xs) == 1, "all buttons share one column"

    # Strictly increasing y: option 0 on top, last option at the bottom.
    ys = [r[1] for r in rects]
    assert ys == sorted(ys)
    assert ys[1] - ys[0] == pytest.approx(42 + 12)


def test_choice_menu_hit_test_matches_drawn_geometry() -> None:
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(3))

    for index, (bx, by, bw, bh) in enumerate(menu.layout()):
        # Centre of each button resolves to its own index.
        assert menu.hit_test(bx + bw / 2, by + bh / 2) == index


def test_choice_menu_hit_test_misses_outside_buttons() -> None:
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(2))

    # Far left of the screen, outside the centred column.
    assert menu.hit_test(0, 0) is None
    # Bottom-right corner, below the stacked buttons.
    assert menu.hit_test(1279, 719) is None


def test_choice_menu_hit_test_is_none_when_empty() -> None:
    menu = ChoiceMenu(1280, 720)
    assert menu.hit_test(640, 360) is None


def test_choice_menu_clear_removes_options() -> None:
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(2))
    assert menu.layout()

    menu.clear()
    assert menu.layout() == ()
    assert menu.cache_key()[2] == ()


def test_choice_menu_set_options_handles_none() -> None:
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(2))
    menu.set_options(None)
    assert menu.layout() == ()


def test_choice_menu_scales_with_resolution() -> None:
    menu = ChoiceMenu(1920, 1080)
    menu.set_options(_options(2))

    wide_w = menu.layout()[0][2]
    menu.set_viewport(640, 360)
    narrow_w = menu.layout()[0][2]

    assert narrow_w < wide_w


def test_choice_menu_style_button_width_cap() -> None:
    style = ChoiceMenuStyle()
    # Capped at the absolute maximum on wide viewports.
    assert style.button_width_for(4000) == pytest.approx(600)
    # Proportional on narrow ones.
    assert style.button_width_for(800) == pytest.approx(480)


def test_choice_menu_draw_labels_are_numbered_from_one() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(2))

    menu.draw(backend)

    texts = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert texts == ["[1]  Option 0", "[2]  Option 1"]


def test_choice_menu_option_text_is_vertically_centred() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(1))

    menu.draw(backend)
    label = next(c for c in backend.ui_calls if c["kind"] == "text")

    _, by, _, bh = menu.layout()[0]
    assert label["anchor_y"] == TextAnchor.MIDDLE
    assert label["y"] == pytest.approx(by + bh / 2)


# ── EndNotice ──────────────────────────────────────────────────────────────


def test_end_notice_banner_is_docked_above_the_bottom_gap() -> None:
    notice = EndNotice(1280, 720)
    bx, by, bw, bh = notice.layout()

    assert bx == 0
    assert bw == 1280
    assert by + bh == pytest.approx(720 - 30)


def test_end_notice_draw_centres_its_message() -> None:
    backend = NullRenderer()
    EndNotice(1280, 720).draw(backend)

    rect = next(c for c in backend.ui_calls if c["kind"] == "rect")
    label = next(c for c in backend.ui_calls if c["kind"] == "text")

    assert rect["width"] == pytest.approx(1280)
    assert label["anchor_x"] == TextAnchor.CENTER
    assert label["anchor_y"] == TextAnchor.MIDDLE
    assert label["x"] == pytest.approx(640)
    assert label["text"] == EndNotice.DEFAULT_MESSAGE


# ── UIOverlay ──────────────────────────────────────────────────────────────


class _FakePrompt:
    def __init__(self, options: tuple[ChoiceOption, ...]) -> None:
        self.options = options


def test_overlay_draws_all_three_layers_when_appropriate() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)

    ui = UIState(speaker="Meris", text="Choose.")
    overlay.draw(backend, ui, _FakePrompt(_options(2)))

    rects = [c for c in backend.ui_calls if c["kind"] == "rect"]
    # Textbox + nameplate + two choice buttons.
    assert len(rects) == 4


def test_overlay_hides_textbox_when_finished() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)

    ui = UIState(speaker="Meris", text="Goodbye.", is_finished=True)
    overlay.draw(backend, ui, None)

    labels = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "Goodbye." not in labels
    assert EndNotice.DEFAULT_MESSAGE in labels


def test_overlay_hides_advance_arrow_during_choices() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)

    ui = UIState(speaker="Meris", text="Choose.")
    overlay.draw(backend, ui, _FakePrompt(_options(1)))

    labels = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "▼" not in labels


def test_overlay_shows_advance_arrow_without_choices() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)

    ui = UIState(speaker="Meris", text="Choose.")
    overlay.draw(backend, ui, None)

    labels = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "▼" in labels


def test_overlay_is_finished_override_takes_precedence() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)

    ui = UIState(speaker="Meris", text="Still going.")
    overlay.draw(backend, ui, None, is_finished=True)

    labels = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "Still going." not in labels


def test_overlay_hit_test_choice_delegates_to_menu() -> None:
    overlay = UIOverlay(1280, 720)
    overlay.sync(UIState(speaker="Meris", text="Choose."), _FakePrompt(_options(2)))

    bx, by, bw, bh = overlay.choice_menu.layout()[1]
    assert overlay.hit_test_choice(bx + bw / 2, by + bh / 2) == 1


def test_overlay_sync_clears_menu_when_prompt_is_none() -> None:
    overlay = UIOverlay(1280, 720)
    overlay.sync(UIState(text="Choose."), _FakePrompt(_options(2)))
    assert overlay.choice_menu.options

    overlay.sync(UIState(text="No longer a choice."), None)
    assert overlay.choice_menu.options == ()


def test_overlay_set_viewport_propagates_to_children() -> None:
    overlay = UIOverlay(1280, 720)
    overlay.set_viewport(640, 480)

    assert overlay.dialogue_box.viewport_width == 640
    assert overlay.choice_menu.viewport_height == 480
    assert overlay.end_notice.viewport_width == 640


def test_overlay_draw_is_idempotent_across_frames() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)
    ui = UIState(speaker="Meris", text="Steady.")

    overlay.draw(backend, ui, None)
    first = list(backend.ui_calls)

    backend.clear_ui_calls()
    overlay.draw(backend, ui, None)

    assert backend.ui_calls == first


# ── Backend protocol conformance ───────────────────────────────────────────


@pytest.mark.parametrize(
    "method",
    ["draw_rect", "draw_text", "draw_image", "measure_text"],
)
def test_null_renderer_implements_uidraw_backend(method: str) -> None:
    backend = NullRenderer()
    assert callable(getattr(backend, method))


def test_null_renderer_records_rect_primitives() -> None:
    from eager_graphics.types import RED, WHITE

    backend = NullRenderer()
    backend.draw_rect(10, 20, 30, 40, RED, border_color=WHITE, border_width=2)

    call = backend.ui_calls[0]
    assert call["kind"] == "rect"
    assert call["x"] == 10
    assert call["height"] == 40
    assert call["border_width"] == 2


def test_null_renderer_measure_text_grows_with_length() -> None:
    backend = NullRenderer()
    short = backend.measure_text("hi", font_size=14)
    long = backend.measure_text("hi there friend", font_size=14)

    assert long[0] > short[0]
    assert short[1] > 0


# ── Layout type contract ───────────────────────────────────────────────────


def test_dialogue_box_layout_contains() -> None:
    layout = DialogueBoxLayout(
        box=(10.0, 20.0, 100.0, 50.0),
        nameplate=None,
        show_arrow=True,
    )
    assert layout.contains(50, 40)
    assert not layout.contains(0, 0)
    assert not layout.contains(200, 40)


# ── Backend primitives ─────────────────────────────────────────────────────


@pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="Pillow not installed")
def test_pil_renderer_implements_uidraw_backend() -> None:
    from eager_graphics.renderers.pil import PILRenderer

    renderer = PILRenderer(width=320, height=240)
    for method in ("draw_rect", "draw_text", "draw_image", "measure_text"):
        assert callable(getattr(renderer, method))


@pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="Pillow not installed")
def test_pil_draw_rect_repaints_frame_buffer() -> None:
    from eager_graphics.renderers.pil import PILRenderer
    from eager_graphics.types import WHITE

    renderer = PILRenderer(width=64, height=64)
    renderer.clear()
    before = renderer.image.convert("RGB").getpixel((32, 32))

    renderer.draw_rect(0, 0, 64, 64, WHITE)
    after = renderer.image.convert("RGB").getpixel((32, 32))

    assert after != before
    assert after[0] > 200


@pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="Pillow not installed")
def test_pil_measure_text_scales_with_font_size() -> None:
    from eager_graphics.renderers.pil import PILRenderer

    renderer = PILRenderer(width=320, height=240)
    small = renderer.measure_text("Meris", font_size=12)
    large = renderer.measure_text("Meris", font_size=30)

    assert large[0] >= small[0]
    assert all(v > 0 for v in small)


@pytest.mark.skipif(importlib.util.find_spec("pyglet") is None, reason="Pyglet not installed")
def test_pyglet_flip_y_converts_top_left_to_bottom_left() -> None:
    from eager_graphics.renderers.pyglet import PygletRenderer

    renderer = PygletRenderer()
    renderer.width, renderer.height = 1280, 720

    # A point on the bottom edge in our space sits at y=0 in Pyglet space.
    assert renderer._flip_y(720) == pytest.approx(0)
    # A point on the top edge sits at y=720.
    assert renderer._flip_y(0) == pytest.approx(720)
    # An extent is subtracted so the far edge maps correctly.
    assert renderer._flip_y(600, 120) == pytest.approx(0)


@pytest.mark.skipif(importlib.util.find_spec("pyglet") is None, reason="Pyglet not installed")
def test_pyglet_measure_text_returns_finite_values() -> None:
    from eager_graphics.renderers.pyglet import PygletRenderer

    renderer = PygletRenderer()
    width, height = renderer.measure_text("Meris", font_size=14)

    assert width > 0
    assert height > 0


@pytest.mark.skipif(importlib.util.find_spec("pyglet") is None, reason="Pyglet not installed")
def test_pyglet_renderer_implements_uidraw_backend() -> None:
    from eager_graphics.renderers.pyglet import PygletRenderer

    renderer = PygletRenderer()
    for method in ("draw_rect", "draw_text", "draw_image", "measure_text"):
        assert callable(getattr(renderer, method))


def test_dialogue_box_typewriter_reveal_draws_partial_text_and_hides_arrow() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    box.set_content("Alice", "Hello brave new world!", visible_chars=5)

    box.draw(backend)

    texts = [c for c in backend.ui_calls if c["kind"] == "text"]
    # Nameplate + dialogue line
    assert any(t["text"] == "Alice" for t in texts)
    assert any(t["text"] == "Hello" for t in texts)
    # Advance arrow should be hidden while typing
    assert not any(t["text"] == "▼" for t in texts)

    # When reveal completes, arrow appears
    backend.ui_calls.clear()
    box.set_content("Alice", "Hello brave new world!", visible_chars=None)
    box.draw(backend)
    texts_after = [c for c in backend.ui_calls if c["kind"] == "text"]
    assert any(t["text"] == "▼" for t in texts_after)


def test_choice_menu_selection_highlight_and_prefix() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720)
    opts = [ChoiceOption(0, "Fight"), ChoiceOption(1, "Flee")]
    menu.set_options(opts)

    # By default, not selected
    menu.draw(backend)
    texts_unselected = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert texts_unselected == ["[1]  Fight", "[2]  Flee"]

    # Select first option
    backend.ui_calls.clear()
    menu.selected_index = 0
    menu.draw(backend)
    texts_selected = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert texts_selected == ["> [1]  Fight", "[2]  Flee"]


def test_ui_overlay_status_badge_rendering() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)
    state = UIState(speaker="Narrator", text="Testing status badge.")

    overlay.draw(backend, state, status_badge="SKIP >>")
    texts = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "SKIP >>" in texts

