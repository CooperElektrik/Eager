"""Tests for story VM translation, catalog extraction, and localization pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

import eager_script
from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    InputPromptEvent,
    NarrationEvent,
)
from eager_core.i18n import TranslationCatalog, TranslationManager

from eager_runtime.cli import _cmd_i18n_check, _cmd_i18n_extract
from eager_runtime.i18n import extract_catalog, merge_catalog, validate_catalog
from eager_runtime.runtime import StoryVM


def test_story_vm_event_translation_and_interpolation() -> None:
    text = """
@default player_name = "Robin"
@default coins = 42
## Market --- market
Merchant: Welcome to the bazaar, [player_name]!
- You have [coins] gold coins.
? Buy a sword (armory)
? Leave the market (town)
"""
    graph = eager_script.parse_graph(text)
    cat_tpl = extract_catalog(graph, locale="template")
    keys = list(cat_tpl.strings.keys())
    # keys: market dialogue, market append, market choice 0, market choice 1
    d_key = keys[0]
    a_key = keys[1]
    c0_key = keys[2]
    c1_key = keys[3]

    tm = TranslationManager()
    cat_es = TranslationCatalog(
        locale="es",
        strings={
            d_key: "Bienvenido al bazar, [player_name]!",
            a_key: "Tienes [coins] monedas de oro.",
            c0_key: "Comprar una espada",
            c1_key: "Salir del mercado",
        },
        speakers={"Merchant": "Comerciante"},
    )
    tm.register_catalog(cat_es)
    tm.set_locale("es")

    vm = StoryVM(graph, translation_manager=tm)

    # 0. SceneEnterEvent
    enter_ev = vm.step()
    assert enter_ev is not None
    assert enter_ev.type == "scene_enter"

    # 1. Dialogue beat
    ev1 = vm.step()
    assert isinstance(ev1, DialogueEvent)
    assert ev1.speaker == "Comerciante"
    assert ev1.text == "Bienvenido al bazar, Robin!"
    assert ev1.beat_id == d_key

    # 2. Append beat
    ev2 = vm.step()
    assert isinstance(ev2, AppendEvent)
    assert ev2.text == "Tienes 42 monedas de oro."
    assert ev2.beat_id == a_key

    # 3. Choice beat
    ev3 = vm.step()
    assert isinstance(ev3, ChoicePromptEvent)
    choice_cid = c0_key.rsplit(".choice_", 1)[0]
    assert ev3.beat_id == choice_cid
    assert len(ev3.options) == 2
    assert ev3.options[0].text == "Comprar una espada"
    assert ev3.options[0].beat_id == c0_key
    assert ev3.options[1].text == "Salir del mercado"
    assert ev3.options[1].beat_id == c1_key


def test_story_vm_fallback_to_source_text() -> None:
    text = """
## Intro --- intro
Alice: Hello!
Just a walk.
"""
    graph = eager_script.parse_graph(text)
    cat_tpl = extract_catalog(graph, locale="template")
    intro_d_key = next(k for k, v in cat_tpl.strings.items() if v == "Hello!")

    tm = TranslationManager()
    # Missing narration translation
    cat_es = TranslationCatalog(
        locale="es",
        strings={intro_d_key: "Hola!"},
    )
    tm.register_catalog(cat_es)
    tm.set_locale("es")

    vm = StoryVM(graph, translation_manager=tm)
    vm.step()  # SceneEnterEvent

    ev1 = vm.step()
    assert isinstance(ev1, DialogueEvent)
    assert ev1.text == "Hola!"

    ev2 = vm.step()
    assert isinstance(ev2, NarrationEvent)
    # Falls back to original source text
    assert ev2.text == "Just a walk."


def test_extract_catalog_from_graph() -> None:
    text = """
## Scene 1 --- s1
Narrator: A gentle breeze.
Hero: Ready for adventure!
? Go north (north)
? Go south (south)
"""
    graph = eager_script.parse_graph(text)
    cat = extract_catalog(graph, locale="template")

    assert cat.locale == "template"
    vals = list(cat.strings.values())
    assert "A gentle breeze." in vals
    assert "Ready for adventure!" in vals
    assert "Go north" in vals
    assert "Go south" in vals
    assert "Hero" in cat.speakers
    assert all(k.startswith("s1.") for k in cat.strings)
    assert not any(k.endswith((".0", ".1", ".2")) for k in cat.strings)


def test_merge_catalog_preserves_existing() -> None:
    template = TranslationCatalog(
        locale="template",
        strings={
            "s1.k1": "First line",
            "s1.k2": "Second line (new)",
        },
        speakers={"Hero": "Hero"},
    )
    existing = TranslationCatalog(
        locale="es",
        strings={
            "s1.k1": "Primera linea",
            "s_old.k_old": "Old obsolete line",
        },
        speakers={"Hero": "Héroe"},
    )

    merged, stats = merge_catalog(template, existing)

    assert merged.locale == "es"
    assert merged.strings["s1.k1"] == "Primera linea"
    assert merged.strings["s1.k2"] == ""  # New empty slot
    assert stats["translated"] == 1
    assert stats["new"] == 1
    assert stats["obsolete"] == 1
    assert merged.speakers["Hero"] == "Héroe"


def test_validate_catalog_coverage() -> None:
    text = """
## S1 --- s1
Alice: Line 1
Alice: Line 2
Alice: Line 3
"""
    graph = eager_script.parse_graph(text)
    cat_tpl = extract_catalog(graph, locale="template")
    keys = list(cat_tpl.strings.keys())

    cat_partial = TranslationCatalog(
        locale="es",
        strings={
            keys[0]: "Línea 1",
            keys[1]: "Línea 2",
            "s_obsolete.old": "Old",
        },
    )

    result = validate_catalog(cat_partial, graph)
    assert result["total"] == 3
    assert result["translated"] == 2
    assert result["untranslated"] == 1
    assert result["obsolete"] == 1
    assert result["coverage_percent"] == 66.7
    assert not result["is_complete"]
    assert keys[2] in result["missing_keys"]


def test_cli_i18n_extract_and_check(tmp_path: Path) -> None:
    script_file = tmp_path / "game.es"
    script_file.write_text(
        """
## Start --- start
Guide: Welcome!
- Enjoy your stay.
""",
        encoding="utf-8",
    )

    out_json = tmp_path / "locales" / "template.json"
    args_ext = argparse.Namespace(
        script=str(script_file),
        output=str(out_json),
        locale="template",
        merge=False,
    )
    code_ext = _cmd_i18n_extract(args_ext)
    assert code_ext == 0
    assert out_json.is_file()

    cat = TranslationCatalog.load_json(out_json)
    assert len(cat.strings) == 2
    assert all(k.startswith("start.") for k in cat.strings)

    args_chk = argparse.Namespace(
        catalog=str(out_json),
        script=str(script_file),
        strict=True,
    )
    code_chk = _cmd_i18n_check(args_chk)
    assert code_chk == 0


def test_cli_test_run_with_lang(tmp_path: Path) -> None:
    script_file = tmp_path / "game.es"
    script_file.write_text(
        """
## Start --- start
Guide: Welcome!
""",
        encoding="utf-8",
    )
    graph = eager_script.parse_graph(script_file.read_text(encoding="utf-8"))
    cat_tpl = extract_catalog(graph, locale="template")
    start_key = next(iter(cat_tpl.strings))

    loc_dir = tmp_path / "locales"
    loc_dir.mkdir()
    vi_cat = TranslationCatalog(
        locale="vi",
        strings={start_key: "Chao mung!"},
        speakers={"Guide": "Huong dan vien"},
    )
    vi_cat.save_json(loc_dir / "vi.json")

    from eager_runtime.cli import run_test_run

    args = argparse.Namespace(
        script=str(script_file),
        lang="vi",
        all_paths=False,
        max_steps=10,
    )
    code = run_test_run(args)
    assert code == 0


def test_content_addressed_translations_stable_under_insertion() -> None:
    """Verify that inserting a new line of dialogue does not shift or break existing translations."""
    # Original screenplay
    script_v1 = """
## Scene --- scene1
Alice: Welcome traveler!
Alice: The road ahead is perilous.
"""
    graph_v1 = eager_script.parse_graph(script_v1)
    cat_v1 = extract_catalog(graph_v1, locale="de")

    # Translate the second line using its content-addressed key
    # Find the content-addressed key for "The road ahead is perilous."
    content_key = None
    for k, v in cat_v1.strings.items():
        if v == "The road ahead is perilous." and not k.endswith(".1"):
            content_key = k
            break
    assert content_key is not None

    cat_de = TranslationCatalog(
        locale="de",
        strings={
            content_key: "Der Weg vor uns ist gefährlich.",
        },
    )
    tm = TranslationManager()
    tm.register_catalog(cat_de)
    tm.set_locale("de")

    # Screenplay with an inserted dialogue beat between line 1 and line 2
    script_v2 = """
## Scene --- scene1
Alice: Welcome traveler!
Bob: Don't forget your supplies!
Alice: The road ahead is perilous.
"""
    graph_v2 = eager_script.parse_graph(script_v2)
    vm = StoryVM(graph_v2, translation_manager=tm)
    vm.step()  # SceneEnterEvent

    ev1 = vm.step()
    assert isinstance(ev1, DialogueEvent)
    assert ev1.speaker == "Alice"
    assert ev1.text == "Welcome traveler!"

    ev_inserted = vm.step()
    assert isinstance(ev_inserted, DialogueEvent)
    assert ev_inserted.speaker == "Bob"
    assert ev_inserted.text == "Don't forget your supplies!"

    ev2 = vm.step()
    assert isinstance(ev2, DialogueEvent)
    assert ev2.speaker == "Alice"
    # Even though its positional index shifted from 1 to 2, it still gets translated correctly!
    assert ev2.text == "Der Weg vor uns ist gefährlich."


def test_explicit_beat_id_translation() -> None:
    """Verify that explicit beat IDs {id=...} are respected for translations and event beat_id."""
    script = """
## Intro --- intro
Alice: Welcome to the tavern! {id=tavern_welcome}
"""
    graph = eager_script.parse_graph(script)
    cat = extract_catalog(graph, locale="es")
    assert "intro.tavern_welcome" in cat.strings
    # Translatable source text should not contain the metadata tag
    assert cat.strings["intro.tavern_welcome"] == "Welcome to the tavern!"

    # In untranslated gameplay, the tag must not leak to the player
    vm_untranslated = StoryVM(graph)
    vm_untranslated.step()
    ev_raw = vm_untranslated.step()
    assert isinstance(ev_raw, DialogueEvent)
    assert ev_raw.text == "Welcome to the tavern!"
    assert ev_raw.beat_id == "intro.tavern_welcome"

    tm = TranslationManager()
    tm.register_catalog(
        TranslationCatalog(
            locale="es",
            strings={"intro.tavern_welcome": "¡Bienvenido a la taberna!"},
        )
    )
    tm.set_locale("es")

    vm = StoryVM(graph, translation_manager=tm)
    vm.step()  # SceneEnterEvent

    ev = vm.step()
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "¡Bienvenido a la taberna!"
    assert ev.beat_id == "intro.tavern_welcome"


def test_input_hook_catalog_extraction_variants() -> None:
    """Verify that ~ input hooks across all syntax variants extract clean prompt strings."""
    script = """
## Intro --- intro
~ input hero_name "Enter your name:" "Traveler"
~ input player_title default="Valiant" "What is your title?"
~ input persona prompt="Who are you?" default="Explorer"
~ input unquoted_name What is your full name?
~ input fallback_name
~ input explicit_id "{id=hero_prompt} Type your name:"
~ input_mode off
~ scene bg_room
"""
    graph = eager_script.parse_graph(script)
    cat = extract_catalog(graph, locale="template")

    # Check extracted prompt strings
    prompt_values = list(cat.strings.values())
    assert "Enter your name:" in prompt_values
    assert "What is your title?" in prompt_values
    assert "Who are you?" in prompt_values
    assert "What is your full name?" in prompt_values
    assert "Enter input:" in prompt_values
    assert "Type your name:" in prompt_values

    # Check explicit beat id was honored
    assert "intro.hero_prompt.input" in cat.strings
    assert cat.strings["intro.hero_prompt.input"] == "Type your name:"

    # Confirm non-input hooks (~ input_mode, ~ scene) did not register as input beats
    assert not any(k.endswith(".input_mode") for k in cat.strings)
    assert len([k for k in cat.strings if k.endswith(".input")]) == 6


def test_validate_catalog_input_hooks() -> None:
    """Verify validate_catalog properly tracks .input keys and ignores non-input hooks."""
    script = """
## Intro --- intro
~ input hero_name "Enter your name:" "Traveler"
~ input_mode off
"""
    graph = eager_script.parse_graph(script)
    cat = extract_catalog(graph, locale="es")
    inp_key = next(k for k in cat.strings if k.endswith(".input"))

    # When untranslated:
    cat.strings[inp_key] = ""
    audit = validate_catalog(cat, graph)
    assert audit["total"] == 1
    assert audit["untranslated"] == 1
    assert inp_key in audit["missing_keys"]

    # When translated:
    cat.strings[inp_key] = "Ingrese su nombre:"
    audit2 = validate_catalog(cat, graph)
    assert audit2["total"] == 1
    assert audit2["translated"] == 1
    assert audit2["untranslated"] == 0


def test_story_vm_input_hook_translation_and_save_load() -> None:
    """Verify that StoryVM translates input prompt and preserves translation across save/load."""
    script = """
## Intro --- intro
~ input hero_name "Enter your name:" "Traveler"
Hero: My name is [hero_name].
"""
    graph = eager_script.parse_graph(script)
    cat = extract_catalog(graph, locale="template")
    inp_key = next(k for k in cat.strings if k.endswith(".input"))

    tm = TranslationManager()
    tm.register_catalog(
        TranslationCatalog(
            locale="es",
            strings={inp_key: "Ingrese su nombre:"},
        )
    )
    tm.set_locale("es")

    vm = StoryVM(graph, translation_manager=tm)
    vm.step()  # SceneEnterEvent

    # Step onto input hook
    ev = vm.step()
    assert isinstance(ev, InputPromptEvent)
    assert ev.prompt == "Ingrese su nombre:"
    assert ev.default == "Traveler"
    assert ev.var_name == "hero_name"
    assert ev.beat_id == inp_key

    # Save state while waiting on input prompt
    snapshot = vm.save()
    assert snapshot.pending_input_beat is not None

    # Restore in new VM with translation manager
    vm2 = StoryVM(graph, translation_manager=tm)
    vm2.load(snapshot)
    assert vm2.pending_input is not None
    assert vm2.pending_input.prompt == "Ingrese su nombre:"
    assert vm2.pending_input.default == "Traveler"
    assert vm2.pending_input.var_name == "hero_name"
    assert vm2.pending_input.beat_id == inp_key

    # Submitting input resumes story
    vm2.submit_input("Carlos")
    diag_ev = vm2.step()
    assert isinstance(diag_ev, DialogueEvent)
    assert diag_ev.text == "My name is Carlos."


def test_character_display_name_resolves_before_speaker_translation() -> None:
    from eager_script import parse_graph

    script = """
@character h "Hoshiko"

## Start --- start
h: Konnichiwa!
"""
    graph = parse_graph(script)
    tm = TranslationManager()
    cat_ja = TranslationCatalog(
        locale="ja",
        speakers={"Hoshiko": "星子"},
    )
    tm.register_catalog(cat_ja)
    tm.set_locale("ja")

    vm = StoryVM(graph, translation_manager=tm)
    vm.step()  # SceneEnterEvent
    ev = vm.step()
    assert isinstance(ev, DialogueEvent)
    assert ev.speaker == "星子"


def test_character_speaker_translation_fallback_by_id() -> None:
    from eager_script import parse_graph

    script = """
@character h "Hoshiko"

## Start --- start
h: Konnichiwa!
"""
    graph = parse_graph(script)
    tm = TranslationManager()
    # Catalog translates using raw speaker ID 'h' (e.g. from extract_catalog)
    cat_ja = TranslationCatalog(
        locale="ja",
        speakers={"h": "星子"},
    )
    tm.register_catalog(cat_ja)
    tm.set_locale("ja")

    vm = StoryVM(graph, translation_manager=tm)
    vm.step()  # SceneEnterEvent
    ev = vm.step()
    assert isinstance(ev, DialogueEvent)
    assert ev.speaker == "星子"




