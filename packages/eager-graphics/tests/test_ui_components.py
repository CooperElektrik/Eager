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
    # Default cinematic mode spans full width and docks flush to the bottom edge
    box = DialogueBox(1280, 720)
    box.set_content(None, "Hello")
    cx, cy, cw, ch = box.layout().box

    assert cy + ch == pytest.approx(720)
    assert cx == pytest.approx(0)
    assert cw == pytest.approx(1280)


def test_dialogue_box_nameplate_straddles_top_edge() -> None:
    boxed_style = TextboxStyle(
        layout_mode="classic",
        show_nameplate_box=True,
        min_margin=20.0,
        margin_ratio=0.05,
        bottom_gap=25.0,
        nameplate_overlap=15.0,
    )
    box = DialogueBox(1280, 720, style=boxed_style)
    box.set_content("Meris", "You have returned.")

    layout = box.layout()
    assert layout.nameplate is not None

    _, box_y, _, _ = layout.box
    name_y = layout.nameplate[1]
    name_h = layout.nameplate[3]

    # The nameplate is centred on the box's top edge, overhanging equally.
    assert name_y + (name_h / 2) == pytest.approx(box_y)
    assert name_y < box_y


def test_dialogue_box_cinematic_inline_speaker() -> None:
    box = DialogueBox(1280, 720)
    box.set_content("Meris", "You have returned.")

    layout = box.layout()
    assert layout.nameplate is None


def test_dialogue_box_no_nameplate_for_narration() -> None:
    boxed_style = TextboxStyle(layout_mode="classic", show_nameplate_box=True)
    box = DialogueBox(1280, 720, style=boxed_style)
    box.set_content(None, "The wind howls.")

    assert box.layout().nameplate is None


def test_dialogue_box_nameplate_width_scales_with_name() -> None:
    boxed_style = TextboxStyle(layout_mode="classic", show_nameplate_box=True)
    short = DialogueBox(1280, 720, style=boxed_style)
    short.set_content("Al", "x")
    long = DialogueBox(1280, 720, style=boxed_style)
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
    boxed_style = TextboxStyle(
        layout_mode="classic",
        show_nameplate_box=True,
        gradient_top=None,
        gradient_bottom=None,
    )
    box = DialogueBox(1280, 720, style=boxed_style)
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


def test_dialogue_box_cinematic_draw_emits_gradient_and_inline_text() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    box.set_content("Meris", "You have returned.")

    box.draw(backend)

    grads = [c for c in backend.ui_calls if c["kind"] == "gradient_rect"]
    texts = [c for c in backend.ui_calls if c["kind"] == "text"]

    # Two-stage background gradient scrim (top fade + lower plate)
    assert len(grads) == 2
    # Speaker name, dialogue text, and clean advance indicator
    assert len(texts) == 3
    assert texts[0]["text"] == "Meris"
    assert texts[1]["text"] == "You have returned."
    assert texts[2]["text"] == "▾"


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
    assert wrapped == [("Short text", 0, 10)]

    wrapped_broken = wrap_text("Line 1\nLine 2", 200, backend.measure_text, font_size=14)
    assert wrapped_broken == [("Line 1", 0, 6), ("Line 2", 7, 13)]


def test_formatted_text_wrapping_with_consecutive_spaces_and_long_words() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    # Consecutive spaces + inline style tags + overlong word
    box.set_content("Alice", "Hello    {b}brave{/b} supercalifragilisticexpialidocious {color=#ff0000}world{/color}!")
    box.draw(backend)

    # All text pieces should be drawn without find() returning -1 misalignment
    drawn_texts = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "brave" in drawn_texts
    assert "world" in drawn_texts


def test_wrap_cache_distinguishes_backends_and_fonts() -> None:
    from eager_graphics.ui_components import _WRAP_CACHE, _get_wrapped_lines

    _WRAP_CACHE.clear()

    class RendererA:
        def measure_text(self, text: str, font_size: int = 14) -> tuple[float, float]:
            return (len(text) * 10.0, 14.0)

    class RendererB:
        def measure_text(self, text: str, font_size: int = 14) -> tuple[float, float]:
            return (len(text) * 20.0, 14.0)

    r_a = RendererA()
    r_b = RendererB()

    text = "hello world from eager engine"
    res_a = _get_wrapped_lines(text, 120.0, r_a.measure_text, font_size=14)
    res_b = _get_wrapped_lines(text, 120.0, r_b.measure_text, font_size=14)

    assert len(_WRAP_CACHE) == 2
    assert res_a != res_b



def test_dialogue_box_respects_viewport_changes() -> None:
    box = DialogueBox(1280, 720)
    box.set_content(None, "Hello")
    wide_y = box.layout().box[1]

    box.set_viewport(1280, 1080)
    tall_y = box.layout().box[1]

    # A taller viewport pushes the bottom-docked box further down.
    assert tall_y > wide_y


def test_textbox_style_scaling_helpers() -> None:
    style = TextboxStyle(
        min_margin=20.0,
        margin_ratio=0.05,
        min_height=110.0,
        height_ratio=0.22,
    )

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
    assert ys[1] - ys[0] == pytest.approx(44 + 12)


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
    style = ChoiceMenuStyle(button_width=600, button_width_ratio=0.6)
    # Capped at the absolute maximum on wide viewports.
    assert style.button_width_for(4000) == pytest.approx(600)
    # Proportional on narrow ones.
    assert style.button_width_for(800) == pytest.approx(480)


def test_choice_menu_draw_labels_are_numbered_from_one() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720, style=ChoiceMenuStyle(show_numbering=True))
    menu.set_options(_options(2))

    menu.draw(backend)

    texts = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert texts == ["[1]  Option 0", "[2]  Option 1"]


def test_choice_menu_cinematic_draw_is_clean_without_number_brackets() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(2))

    menu.draw(backend)

    texts = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert texts == ["Option 0", "Option 1"]


def test_choice_menu_option_text_is_vertically_centred() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720)
    menu.set_options(_options(1))

    menu.draw(backend)
    label = next(c for c in backend.ui_calls if c["kind"] == "text")

    _, by, _, bh = menu.layout()[0]
    assert label["anchor_y"] == TextAnchor.MIDDLE
    assert label["y"] == pytest.approx(by + bh / 2)


def test_choice_menu_disabled_options_rendering_and_hit_test() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720)
    opts = (
        ChoiceOption(0, "Normal Option", "scene_a", enabled=True),
        ChoiceOption(1, "Locked Option", "scene_b", enabled=False),
    )
    menu.set_options(opts)

    # 1. Hit test on enabled option succeeds
    r0 = menu.layout()[0]
    assert menu.hit_test(r0[0] + r0[2] / 2, r0[1] + r0[3] / 2) == 0

    # 2. Hit test on disabled option returns None (click ignored)
    r1 = menu.layout()[1]
    assert menu.hit_test(r1[0] + r1[2] / 2, r1[1] + r1[3] / 2) is None

    # 3. Draw produces muted text color with lock prefix on disabled option
    menu.draw(backend)
    texts = [c for c in backend.ui_calls if c["kind"] == "text"]
    assert len(texts) == 2
    assert texts[0]["text"] == "Normal Option"
    assert texts[0]["color"] == menu.style.text_color.to_hex()

    assert texts[1]["text"].startswith(menu.style.lock_symbol)
    assert "Locked Option" in texts[1]["text"]
    assert texts[1]["color"] == menu.style.disabled_text_color.to_hex()


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
    overlay = UIOverlay(
        1280,
        720,
        dialogue_style=TextboxStyle(
            layout_mode="classic",
            show_nameplate_box=True,
            gradient_top=None,
            gradient_bottom=None,
        ),
        choice_style=ChoiceMenuStyle(),
    )

    ui = UIState(speaker="Meris", text="Choose.")
    overlay.draw(backend, ui, _FakePrompt(_options(2)))

    rects = [c for c in backend.ui_calls if c["kind"] == "rect"]
    # Textbox + nameplate + two choice buttons.
    assert len(rects) == 4


def test_overlay_cinematic_mode_draws_layers() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)

    ui = UIState(speaker="Meris", text="Choose.")
    overlay.draw(backend, ui, _FakePrompt(_options(2)))

    grads = [c for c in backend.ui_calls if c["kind"] == "gradient_rect"]
    rects = [c for c in backend.ui_calls if c["kind"] == "rect"]
    # 2 gradient scrim stages + 2 choice button rects
    assert len(grads) == 2
    assert len(rects) == 2


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
    assert overlay.dialogue_box.style.arrow_symbol not in labels


def test_overlay_shows_advance_arrow_without_choices() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)

    ui = UIState(speaker="Meris", text="Choose.")
    overlay.draw(backend, ui, None)

    labels = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert overlay.dialogue_box.style.arrow_symbol in labels


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
    ["draw_rect", "draw_gradient_rect", "draw_text", "draw_image", "measure_text"],
)
def test_null_renderer_implements_uidraw_backend(method: str) -> None:
    backend = NullRenderer()
    assert callable(getattr(backend, method))


def test_null_renderer_records_rect_primitives() -> None:
    from eager_core.types import RED, WHITE

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
    for method in ("draw_rect", "draw_gradient_rect", "draw_text", "draw_image", "measure_text"):
        assert callable(getattr(renderer, method))


@pytest.mark.skipif(importlib.util.find_spec("PIL") is None, reason="Pillow not installed")
def test_pil_draw_rect_repaints_frame_buffer() -> None:
    from eager_core.types import WHITE

    from eager_graphics.renderers.pil import PILRenderer

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
    for method in ("draw_rect", "draw_gradient_rect", "draw_text", "draw_image", "measure_text"):
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
    assert not any(t["text"] == box.style.arrow_symbol for t in texts)

    # When reveal completes, arrow appears
    backend.ui_calls.clear()
    box.set_content("Alice", "Hello brave new world!", visible_chars=None)
    box.draw(backend)
    texts_after = [c for c in backend.ui_calls if c["kind"] == "text"]
    assert any(t["text"] == box.style.arrow_symbol for t in texts_after)


def test_choice_menu_selection_highlight_and_prefix() -> None:
    backend = NullRenderer()
    menu = ChoiceMenu(1280, 720, style=ChoiceMenuStyle(layout_mode="classic", show_numbering=True))
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


def test_dialogue_box_text_tags_render_styles() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    box.set_content(
        None,
        "Hello {b}brave{/b} {i}new{/i} {color=#ff0000}world{/color} {size=1.5}huge{/size}!",
    )
    box.draw(backend)

    text_calls = [c for c in backend.ui_calls if c["kind"] == "text" and c["text"] not in ("▼", "▾")]
    # Raw markup tags should never be emitted as text
    for call in text_calls:
        assert "{" not in call["text"]
        assert "}" not in call["text"]

    # Check bold segment
    brave_call = next(c for c in text_calls if c["text"] == "brave")
    assert brave_call["bold"] is True
    assert brave_call["italic"] is False

    # Check italic segment
    new_call = next(c for c in text_calls if c["text"] == "new")
    assert new_call["italic"] is True
    assert new_call["bold"] is False

    # Check color segment
    world_call = next(c for c in text_calls if c["text"] == "world")
    assert world_call["color"].lower() in ("#ff0000", "#ff0000ff")

    # Check size segment
    huge_call = next(c for c in text_calls if c["text"] == "huge")
    assert huge_call["font_size"] == round(box.style.text_font_size * 1.5)


def test_dialogue_box_typewriter_reveal_aligns_with_tags() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    # Plain text is "Hello world!" (12 chars). Slicing 8 chars yields "Hello " + "wo"
    box.set_content("Alice", "Hello {b}world{/b}!", visible_chars=8)
    box.draw(backend)

    dialogue_calls = [
        c for c in backend.ui_calls if c["kind"] == "text" and c["text"] not in ("Alice", "▼", "▾")
    ]
    # Verify no raw tag markup
    for c in dialogue_calls:
        assert "{" not in c["text"]
        assert "}" not in c["text"]

    combined_text = "".join(c["text"] for c in dialogue_calls)
    assert combined_text == "Hello wo"

    # Verify bold styling was maintained on the sliced segment
    bold_parts = [c for c in dialogue_calls if c["bold"]]
    assert len(bold_parts) == 1
    assert bold_parts[0]["text"] == "wo"

    # Advance arrow must NOT be visible because 8 < 12
    arrow_calls = [c for c in backend.ui_calls if c["kind"] == "text" and c["text"] in ("▼", "▾")]
    assert len(arrow_calls) == 0


def test_dialogue_box_advance_arrow_shows_when_plain_text_fully_revealed() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    # Raw string is 19 chars, plain text is 12 chars.
    # At visible_chars=12, plain text is fully revealed even though 12 < len(raw)
    box.set_content(None, "Hello {b}world{/b}!", visible_chars=12)
    box.draw(backend)

    arrow_calls = [c for c in backend.ui_calls if c["kind"] == "text" and c["text"] in ("▼", "▾")]
    assert len(arrow_calls) == 1


def test_dialogue_box_typewriter_reveal_float_visible_chars() -> None:
    backend = NullRenderer()
    box = DialogueBox(1280, 720)
    # Pacing clock can produce float visible_chars (e.g. 5.5, 7.8)
    box.set_content("Alice", "Hello {b}brave new{/b} world!", visible_chars=8.7)
    box.draw(backend)

    dialogue_calls = [
        c for c in backend.ui_calls if c["kind"] == "text" and c["text"] not in ("Alice", "▼", "▾")
    ]
    combined_text = "".join(c["text"] for c in dialogue_calls)
    assert combined_text == "Hello br"


def test_ui_overlay_error_overlay() -> None:
    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)
    state = UIState(speaker="Narrator", text="Normal text")

    overlay.error_overlay = "Scene not found: 'missing_scene'"
    overlay.draw(backend, state)

    texts = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "Scene Not Found" in texts
    assert "Scene not found: 'missing_scene'" in texts

    # Clear error overlay
    backend.ui_calls.clear()
    overlay.error_overlay = None
    overlay.draw(backend, state)
    texts_cleared = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "Scene Not Found" not in texts_cleared


def test_input_box_modal_rendering() -> None:
    from eager_core.events import InputPromptEvent

    backend = NullRenderer()
    overlay = UIOverlay(1280, 720)
    state = UIState(speaker="Narrator", text="What is your name?")
    prompt = InputPromptEvent(var_name="player_name", prompt="What is your name?", default="Hero")

    overlay.draw(backend, state, active_input_prompt=prompt, input_text="Valiant")

    texts = [c["text"] for c in backend.ui_calls if c["kind"] == "text"]
    assert "What is your name?" in texts
    assert "Valiant" in texts
    assert "Press Enter to confirm" in texts

    # Overlay cursor update
    overlay.input_box.update(0.6)
    assert overlay.input_box.cursor_visible is False
    overlay.input_box.update(0.6)
    assert overlay.input_box.cursor_visible is True


def test_theme_and_styles_unification() -> None:
    """Theme must bridge cleanly to TextboxStyle and ChoiceMenuStyle."""
    from eager_core.types import Color

    from eager_graphics.theme import Theme
    from eager_graphics.ui_components import (
        ChoiceMenu,
        ChoiceMenuStyle,
        DialogueBox,
        QuickMenu,
        TextboxStyle,
        UIOverlay,
    )

    custom_theme = Theme(
        name="crimson_gold",
        bg_color=Color(0.1, 0.0, 0.0, 1.0),
        primary_color=Color(0.8, 0.1, 0.1, 1.0),
        accent_color=Color(1.0, 0.8, 0.2, 1.0),
        text_color=Color(0.98, 0.98, 0.98, 1.0),
        muted_text_color=Color(0.7, 0.6, 0.6, 1.0),
        dialogue_box_fill=Color(0.15, 0.02, 0.02, 0.95),
        dialogue_box_border=Color(1.0, 0.8, 0.2, 0.3),
        nameplate_fill=Color(0.3, 0.05, 0.05, 0.9),
        nameplate_text=Color(1.0, 0.85, 0.3, 1.0),
        button_fill=Color(0.25, 0.04, 0.04, 0.85),
        button_hover=Color(0.45, 0.08, 0.08, 0.95),
        button_border=Color(1.0, 0.8, 0.2, 0.5),
        button_text=Color(1.0, 1.0, 1.0, 1.0),
        font_size=20,
    )

    # 1. to_textbox_style and TextboxStyle.from_theme
    tb_style = custom_theme.to_textbox_style()
    assert tb_style.box_fill == custom_theme.dialogue_box_fill
    assert tb_style.nameplate_text == custom_theme.nameplate_text
    assert tb_style.show_nameplate_box is True
    assert tb_style.text_font_size == 19  # 20 - 1

    from_tb = TextboxStyle.from_theme(custom_theme)
    assert from_tb == tb_style

    # 2. to_choice_menu_style and ChoiceMenuStyle.from_theme
    choice_style = custom_theme.to_choice_menu_style()
    assert choice_style.button_fill == custom_theme.button_fill
    assert choice_style.button_hover_fill == custom_theme.button_hover
    assert choice_style.accent_bar_color == custom_theme.accent_color
    assert choice_style.text_font_size == 18  # 20 - 2

    from_choice = ChoiceMenuStyle.from_theme(custom_theme)
    assert from_choice == choice_style

    # 3. UIOverlay configured with Theme
    overlay = UIOverlay(1280, 720, theme=custom_theme)
    assert overlay.dialogue_box.style.box_fill == custom_theme.dialogue_box_fill
    assert overlay.choice_menu.style.button_fill == custom_theme.button_fill
    assert overlay.quick_menu.theme == custom_theme

    # 4. set_theme dynamic update
    alt_theme = Theme(name="ice_blue", dialogue_box_fill=Color(0.0, 0.1, 0.3, 0.9))
    overlay.set_theme(alt_theme)
    assert overlay.dialogue_box.style.box_fill == alt_theme.dialogue_box_fill

    # 5. Direct DialogueBox, ChoiceMenu, QuickMenu theme support
    diag_box = DialogueBox(theme=custom_theme)
    assert diag_box.style.box_fill == custom_theme.dialogue_box_fill
    diag_box.set_theme(alt_theme)
    assert diag_box.style.box_fill == alt_theme.dialogue_box_fill

    cmenu = ChoiceMenu(theme=custom_theme)
    assert cmenu.style.button_fill == custom_theme.button_fill
    cmenu.set_theme(alt_theme)
    assert cmenu.style.button_fill == alt_theme.button_fill

    qmenu = QuickMenu(theme=custom_theme)
    assert qmenu.theme == custom_theme
    qmenu.set_theme(alt_theme)
    assert qmenu.theme == alt_theme
