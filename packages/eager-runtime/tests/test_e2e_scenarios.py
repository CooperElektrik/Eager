"""Comprehensive Opaque-Box E2E Test Suite for eager-mono stabilization.

4-Tier Systematic Testing:
  - Tier 1: Feature Coverage (>=5 tests per feature across 8 features = 40 tests)
      * Screenplay Parsing
      * VM Execution
      * Dialogue & Narration
      * Choices (branching, conditional, inline)
      * Input Prompt
      * Save / Load
      * Checkpoint & Rollback
      * Internationalization (i18n)
  - Tier 2: Boundary & Corner Cases (8 tests)
  - Tier 3: Cross-Feature Combinations (7 tests)
  - Tier 4: Real-World Application Scenarios (3 tests)
"""

from __future__ import annotations

from pathlib import Path

import eager_script
import pytest
from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    InputPromptEvent,
    NarrationEvent,
    SceneEnterEvent,
    StoryEndEvent,
)
from eager_core.i18n import TranslationCatalog, TranslationManager
from eager_script import (
    ParsedAppend,
    ParsedChoiceSet,
    ParsedDialogue,
    ParsedFreshBox,
    ParsedHook,
    ParsedNarration,
    ParsedSet,
)

from eager_runtime import (
    GameSession,
    SaveManager,
    StoryRuntimeError,
    StoryVM,
)
from eager_runtime.i18n import extract_catalog

# ==============================================================================
# TIER 1: Feature Coverage (>=5 tests per feature across 8 features)
# ==============================================================================


class TestTier1Feature1ScreenplayParsing:
    """Tier 1 - Feature 1: Screenplay parsing specifications."""

    def test_parse_linear_dialogue_narration_append_freshbox(self) -> None:
        script = """
## Opening --- opening
The quiet morning arrives.
- Sunlight filters through the oak leaves.
/ A bell tolls in the distance.
Traveler: A new journey begins.
"""
        graph = eager_script.parse_graph(script)
        assert "opening" in graph.nodes
        node = graph.nodes["opening"]
        body = node.body
        assert isinstance(body[0], ParsedNarration)
        assert "The quiet morning arrives." in body[0].text
        assert isinstance(body[1], ParsedAppend)
        assert "Sunlight filters" in body[1].text
        assert isinstance(body[2], ParsedFreshBox)
        assert "A bell tolls" in body[2].text
        assert isinstance(body[3], ParsedDialogue)
        assert body[3].speaker == "Traveler"
        assert body[3].text == "A new journey begins."

    def test_parse_dialogue_with_emotions_and_characters(self) -> None:
        script = """
@character guide "Hermit Guide" role="mentor" color="#336699"

## Camp --- camp
guide (thoughtful): Study the stars before you venture forth.
guide (smiling): They will guide your footsteps.
"""
        graph = eager_script.parse_graph(script)
        assert "guide" in graph.characters
        char_info = graph.characters["guide"]
        assert char_info["name"] == "Hermit Guide"
        assert char_info["attrs"]["role"] == "mentor"
        node = graph.nodes["camp"]
        assert isinstance(node.body[0], ParsedDialogue)
        assert node.body[0].speaker == "guide"
        assert node.body[0].emotion == "thoughtful"
        assert isinstance(node.body[1], ParsedDialogue)
        assert node.body[1].emotion == "smiling"

    def test_parse_branching_and_conditional_choices(self) -> None:
        script = """
## Crossroad --- crossroad
? Take high road (high_road)
? Take secret trail (secret_trail) if has_map
? Turn back (camp)
"""
        graph = eager_script.parse_graph(script)
        node = graph.nodes["crossroad"]
        assert len(node.body) == 1
        choice_set = node.body[0]
        assert isinstance(choice_set, ParsedChoiceSet)
        assert len(choice_set.options) == 3
        assert choice_set.options[0].text == "Take high road"
        assert choice_set.options[0].target == "high_road"
        assert choice_set.options[0].condition is None
        assert choice_set.options[1].text == "Take secret trail"
        assert choice_set.options[1].target == "secret_trail"
        assert choice_set.options[1].condition == "has_map"
        assert choice_set.options[2].target == "camp"

    def test_parse_inline_choices_lowering(self) -> None:
        script = """
## Tavern --- tavern
Barkeeper: What will you drink?
? Order spring water
    Barkeeper: Clean and fresh.
? Order spiced cider
    $ coins -= 2
    Barkeeper: That warms the bones.
Barkeeper: Enjoy your rest.
"""
        graph = eager_script.parse_graph(script)
        assert "tavern" in graph.nodes
        anon_nodes = [nid for nid in graph.nodes if "__anon_" in nid]
        assert len(anon_nodes) == 2
        for nid in anon_nodes:
            assert graph.nodes[nid].is_anonymous is True

    def test_parse_directives_variables_and_defaults(self) -> None:
        script = """
@default starting_coins = 50
@default hero_title = "Wanderer"

## Intro --- intro
$ coins = starting_coins
$ coins += 10
~ bg tavern_day with dissolve
~ input player_alias "Enter your alias:" "Shadow"
Narrator: Setup finished.
"""
        graph = eager_script.parse_graph(script)
        assert len(graph.defaults) >= 2
        node = graph.nodes["intro"]
        assert any(isinstance(item, ParsedSet) and item.target == "coins" for item in node.body)
        assert any(isinstance(item, ParsedHook) and item.hook_name.startswith("bg") for item in node.body)
        assert any(isinstance(item, ParsedHook) and item.hook_name.startswith("input") for item in node.body)


class TestTier1Feature2VMExecution:
    """Tier 1 - Feature 2: VM execution and state machine behavior."""

    def test_vm_linear_execution_flow(self) -> None:
        script = """
## Intro --- intro
Step 1.
/ Step 2.
/ Step 3.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        events = []
        while not vm.is_ended:
            ev = vm.step()
            if ev:
                events.append(ev)
        assert isinstance(events[0], SceneEnterEvent)
        assert events[0].scene_id == "intro"
        assert isinstance(events[1], NarrationEvent)
        assert events[1].text == "Step 1."
        assert isinstance(events[2], FreshBoxEvent)
        assert events[2].text == "Step 2."
        assert isinstance(events[3], FreshBoxEvent)
        assert events[3].text == "Step 3."
        assert isinstance(events[4], StoryEndEvent)
        assert events[4].reason == "terminal"

    def test_vm_conditional_jump_branching(self) -> None:
        script = """
@default power = 75
## Trial --- trial
@if power >= 100
    Godlike power.
@elif power >= 50
    Mighty power.
@else
    Mortal power.
@end
/ Trial evaluated.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        events = []
        while not vm.is_ended:
            ev = vm.step()
            if ev and isinstance(ev, (NarrationEvent, FreshBoxEvent)):
                events.append(ev.text)
        assert events == ["Mighty power.", "Trial evaluated."]

    def test_vm_subroutine_call_and_return(self) -> None:
        script = """
## Main --- main
Before subroutine.
>> helper
Returned to main.

## Helper --- helper
Executing helper routine.
<<
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        events = []
        while not vm.is_ended:
            ev = vm.step()
            if ev and isinstance(ev, (NarrationEvent, FreshBoxEvent)):
                events.append(ev.text)
        assert events == [
            "Before subroutine.",
            "Executing helper routine.",
            "Returned to main.",
        ]

    def test_vm_variable_arithmetic_mutation(self) -> None:
        script = """
## Calc --- calc
$ score = 100
$ score += 50
$ score -= 20
$ score *= 2
$ score /= 4
$ score %= 30
Score is [score].
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, NarrationEvent):
                # (100 + 50 - 20) = 130 * 2 = 260 / 4 = 65 % 30 = 5
                assert "Score is 5" in ev.text
        assert vm.get_variable("score") == 5

    def test_vm_text_interpolation_and_escapes(self) -> None:
        script = """
@default player = "Arthur"
@default title = "King"
## Throne --- throne
All hail [title] [player]!
/ Literal [[bracketed]] tag test.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        narrations = []
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, (NarrationEvent, FreshBoxEvent)):
                narrations.append(ev.text)
        assert narrations[0] == "All hail King Arthur!"
        assert narrations[1] == "Literal [bracketed] tag test."


class TestTier1Feature3Dialogue:
    """Tier 1 - Feature 3: Dialogue presentation and structure."""

    def test_dialogue_speaker_text_extraction(self) -> None:
        script = """
## Chat --- chat
Alice: Greetings, friend.
Bob: Good day to you.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        dialogues = []
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, DialogueEvent):
                dialogues.append((ev.speaker, ev.text, ev.line_number))
        assert dialogues[0] == ("Alice", "Greetings, friend.", 3)
        assert dialogues[1] == ("Bob", "Good day to you.", 4)

    def test_dialogue_emotion_preservation(self) -> None:
        script = """
## EmotionScene --- scene
Alice (worried): Are you certain about this?
Bob (confident): Absolutely certain.
Alice: Then let us proceed.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        dialogues = []
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, DialogueEvent):
                dialogues.append((ev.speaker, ev.emotion, ev.text))
        assert dialogues[0] == ("Alice", "worried", "Are you certain about this?")
        assert dialogues[1] == ("Bob", "confident", "Absolutely certain.")
        assert dialogues[2] == ("Alice", None, "Then let us proceed.")

    def test_dialogue_append_continuation(self) -> None:
        script = """
## Monologue --- monologue
Alice: The ancient gate stands tall.
- Moss clings to every weathered stone.
- A faint light glimmers through the keyhole.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # SceneEnterEvent
        d1 = vm.step()
        assert isinstance(d1, DialogueEvent)
        assert d1.text == "The ancient gate stands tall."
        a1 = vm.step()
        assert isinstance(a1, AppendEvent)
        assert "Moss clings" in a1.text
        a2 = vm.step()
        assert isinstance(a2, AppendEvent)
        assert "A faint light" in a2.text

    def test_dialogue_freshbox_split(self) -> None:
        script = """
## Speech --- speech
Alice: This is the first chapter of our tale.
/ Now begins the second chapter.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        d1 = vm.step()
        assert isinstance(d1, DialogueEvent)
        assert "first chapter" in d1.text
        f1 = vm.step()
        assert isinstance(f1, FreshBoxEvent)
        assert "second chapter" in f1.text

    def test_dialogue_voice_clip_tag_preservation(self) -> None:
        script = """
## VoiceScene --- voice_scene
Alice: {voice: audio/alice_greeting.ogg} Hello traveler!
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        d1 = vm.step()
        assert isinstance(d1, DialogueEvent)
        assert d1.voice == "audio/alice_greeting.ogg"
        assert d1.text == "Hello traveler!"


class TestTier1Feature4Choices:
    """Tier 1 - Feature 4: Choice prompts and branching decisions."""

    def test_choice_prompt_generation_and_selection(self) -> None:
        script = """
## Crossroads --- crossroads
Where to?
? Go to Castle (castle)
? Go to Forest (forest)

## Castle --- castle
At the castle.

## Forest --- forest
In the forest.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        vm.step()  # narration
        prompt = vm.step()
        assert isinstance(prompt, ChoicePromptEvent)
        assert len(prompt.options) == 2
        assert prompt.options[0].text == "Go to Castle"
        assert prompt.options[1].text == "Go to Forest"
        vm.choose(1)
        assert vm.current_scene_id == "forest"

    def test_choice_condition_evaluation_enabled_disabled(self) -> None:
        script = """
@default gold = 10
## Shop --- shop
? Buy potion (potion) if gold >= 50
? Buy bread (bread) if gold >= 5

## Potion --- potion
Potion bought.

## Bread --- bread
Bread bought.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        prompt = vm.step()
        assert isinstance(prompt, ChoicePromptEvent)
        assert prompt.options[0].enabled is False
        assert prompt.options[1].enabled is True

    def test_choice_select_by_text_or_target(self) -> None:
        script = """
## Decision --- decision
? Option Alpha (alpha_scene)
? Option Beta (beta_scene)

## Alpha Scene --- alpha_scene
Alpha.

## Beta Scene --- beta_scene
Beta.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()
        prompt = vm.step()
        assert isinstance(prompt, ChoicePromptEvent)
        # Select by target scene name
        vm.choose("beta_scene")
        assert vm.current_scene_id == "beta_scene"

    def test_choice_select_disabled_raises_error(self) -> None:
        script = """
@default locked = True
## Gate --- gate
? Open gate (inside) if not locked
? Knock on door (knock)

## Inside --- inside
Inside.

## Knock --- knock
Knocked.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()
        prompt = vm.step()
        assert isinstance(prompt, ChoicePromptEvent)
        assert prompt.options[0].enabled is False
        with pytest.raises(StoryRuntimeError, match="Cannot select disabled choice"):
            vm.choose(0)
        # Still can choose valid option
        vm.choose(1)
        assert vm.current_scene_id == "knock"

    def test_choice_inline_block_execution_and_resumption(self) -> None:
        script = """
## Tavern --- tavern
Alice: What would you like?
? Drink coffee
    $ energy = 10
    Alice: Hot and robust!
? Drink tea
    $ energy = 5
    Alice: Soothing and herbal!
Alice: Now, back to our business.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        vm.step()  # dialogue 'What would you like?'
        prompt = vm.step()  # choice
        assert isinstance(prompt, ChoicePromptEvent)
        vm.choose(0)  # choose coffee
        dialogues = []
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, DialogueEvent):
                dialogues.append(ev.text)
        assert dialogues == ["Hot and robust!", "Now, back to our business."]
        assert vm.get_variable("energy") == 10


class TestTier1Feature5InputPrompt:
    """Tier 1 - Feature 5: Text input prompt interaction."""

    def test_input_prompt_event_emission(self) -> None:
        script = """
## Welcome --- welcome
~ input hero_name "What is your title, hero?" "Vanguard"
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        prompt = vm.step()
        assert isinstance(prompt, InputPromptEvent)
        assert prompt.var_name == "hero_name"
        assert prompt.prompt == "What is your title, hero?"
        assert prompt.default == "Vanguard"

    def test_input_prompt_vm_pauses_execution(self) -> None:
        script = """
## Query --- query
~ input code "Enter secret passcode:" ""
Access granted.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        p1 = vm.step()
        assert isinstance(p1, InputPromptEvent)
        p2 = vm.step()
        assert isinstance(p2, InputPromptEvent)
        assert vm.pending_input is not None

    def test_input_prompt_submission_updates_variable(self) -> None:
        script = """
## Naming --- naming
~ input adventurer "Enter your name:" "Hero"
Greetings, [adventurer].
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()
        ev = vm.step()
        assert isinstance(ev, InputPromptEvent)
        vm.submit_input("Perseus")
        assert vm.get_variable("adventurer") == "Perseus"
        assert vm.pending_input is None
        n1 = vm.step()
        assert isinstance(n1, NarrationEvent)
        assert n1.text == "Greetings, Perseus."

    def test_input_prompt_default_fallback(self) -> None:
        script = """
## Guild --- guild
~ input rank "Rank:" "Novice"
Assigned rank is [rank].
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()
        ev = vm.step()
        assert isinstance(ev, InputPromptEvent)
        # Fall back to default
        vm.submit_input(ev.default)
        assert vm.get_variable("rank") == "Novice"
        n1 = vm.step()
        assert isinstance(n1, NarrationEvent)
        assert n1.text == "Assigned rank is Novice."

    def test_input_prompt_interpolation_in_prompt_string(self) -> None:
        script = """
@default realm = "Arcadia"
## Welcome --- welcome
~ input knight_name "Who defends [realm]?" "Defender"
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()
        ev = vm.step()
        assert isinstance(ev, InputPromptEvent)
        assert ev.prompt == "Who defends Arcadia?"


class TestTier1Feature6SaveLoad:
    """Tier 1 - Feature 6: Checkpoints, saving, and slot loading."""

    def test_saveload_at_dialogue_beat(self, tmp_path: Path) -> None:
        script = """
## Journey --- journey
$ stamina = 100
Alice: Beat one.
$ stamina = 85
Alice: Beat two.
Alice: Beat three.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        session.advance()  # Beat one
        session.advance()  # Beat two
        assert session.vm.get_variable("stamina") == 85
        meta = session.save_game("slot_beat2")
        assert meta.slot_name == "slot_beat2"

        session.advance()  # Beat three
        assert session.director.ui_state.text == "Beat three."

        ok = session.load_game("slot_beat2")
        assert ok is True
        assert session.director.ui_state.text == "Beat two."
        assert session.vm.get_variable("stamina") == 85

    def test_saveload_at_choice_prompt(self, tmp_path: Path) -> None:
        script = """
## Decision --- decision
Alice: Decide your route.
? Mountain (mountain)
? Sea (sea)

## Mountain --- mountain
Alice: High peaks.

## Sea --- sea
Alice: Deep waters.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        session.advance()  # Dialogue
        ev_choice = session.advance()  # Choice prompt
        assert isinstance(ev_choice, ChoicePromptEvent)
        assert session.active_choice_prompt is not None

        session.save_game("slot_choice")
        session.choose(0)  # advance to mountain
        assert session.vm.current_scene_id == "mountain"

        ok = session.load_game("slot_choice")
        assert ok is True
        assert session.active_choice_prompt is not None
        assert len(session.active_choice_prompt.options) == 2
        # Choose the other branch after loading
        session.choose(1)
        assert session.vm.current_scene_id == "sea"

    def test_saveload_at_input_prompt(self, tmp_path: Path) -> None:
        script = """
## Setup --- setup
Alice: Identify yourself.
~ input codename "Codename:" "Agent"
Alice: Welcome aboard, [codename].
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        session.advance()  # Dialogue
        inp = session.advance()  # Input prompt
        assert isinstance(inp, InputPromptEvent)

        session.save_game("slot_input")
        session.submit_input("Falcon")
        assert session.director.ui_state.text == "Welcome aboard, Falcon."

        ok = session.load_game("slot_input")
        assert ok is True
        assert session.active_input_prompt is not None
        assert session.active_input_prompt.var_name == "codename"
        session.submit_input("Eagle")
        assert session.director.ui_state.text == "Welcome aboard, Eagle."

    def test_saveload_quicksave_and_quickload(self, tmp_path: Path) -> None:
        script = """
## Story --- story
Alice: Point A.
Alice: Point B.
Alice: Point C.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        session.advance()
        qs = session.quicksave()
        assert qs.slot_name.startswith("quick_")

        session.advance()
        session.advance()
        assert session.director.ui_state.text == "Point C."

        ok = session.quickload()
        assert ok is True
        assert session.director.ui_state.text == "Point A."

    def test_saveload_slot_listing_and_metadata(self, tmp_path: Path) -> None:
        script = """
## ChapterOne --- chap1
Alice: Exploring the ruins.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        session.advance()
        session.save_game("manual_1")
        session.save_game("manual_2")

        sm = SaveManager(tmp_path)
        slots = sm.list_slots()
        slot_names = [s.slot_name for s in slots]
        assert "manual_1" in slot_names
        assert "manual_2" in slot_names
        meta = sm.get_slot_metadata("manual_1")
        assert meta is not None
        assert meta.scene_id == "chap1"
        assert meta.dialogue_snippet is not None
        assert "Exploring the ruins." in meta.dialogue_snippet


class TestTier1Feature7Rollback:
    """Tier 1 - Feature 7: Narrative interaction rollback and roll-forward."""

    def test_rollback_linear_dialogue_sequence(self) -> None:
        script = """
## Tale --- tale
Alice: Beat One.
Alice: Beat Two.
Alice: Beat Three.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True)
        session.advance()  # Beat 1
        assert session.director.ui_state.text == "Beat One."
        session.advance()  # Beat 2
        assert session.director.ui_state.text == "Beat Two."
        session.advance()  # Beat 3
        assert session.director.ui_state.text == "Beat Three."

        assert session.can_rollback is True
        assert session.rollback() is True
        assert session.director.ui_state.text == "Beat Two."

        assert session.rollback() is True
        assert session.director.ui_state.text == "Beat One."

    def test_rollback_roll_forward_redo(self) -> None:
        script = """
## ForwardTest --- fwd
Alice: Step 1.
Alice: Step 2.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True)
        session.advance()
        session.advance()
        assert session.director.ui_state.text == "Step 2."

        session.rollback()
        assert session.director.ui_state.text == "Step 1."
        assert session.can_roll_forward is True

        assert session.roll_forward() is True
        assert session.director.ui_state.text == "Step 2."

    def test_rollback_backlog_synchronization(self) -> None:
        script = """
## LogTest --- log
Alice: First sentence.
Alice: Second sentence.
Alice: Third sentence.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True)
        session.advance()
        session.advance()
        session.advance()
        assert len(session.backlog.entries) == 3

        session.rollback()
        assert len(session.backlog.entries) == 2
        assert session.backlog.entries[-1].text == "Second sentence."

    def test_rollback_history_depth_limit(self) -> None:
        script = """
## LimitTest --- lim
Alice: Beat 1.
Alice: Beat 2.
Alice: Beat 3.
Alice: Beat 4.
Alice: Beat 5.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, rollback_limit=2)
        session.advance()
        session.advance()
        session.advance()
        session.advance()
        session.advance()

        # Depth capped at max_history (2)
        assert session.checkpoints.depth <= 2

    def test_rollback_at_start_returns_false(self) -> None:
        script = """
## Empty --- empty
Alice: Hello.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True)
        # At inception before any advance
        assert session.can_rollback is False
        assert session.rollback() is False


class TestTier1Feature8I18n:
    """Tier 1 - Feature 8: Internationalization and catalog localization."""

    def test_i18n_catalog_extraction_from_graph(self) -> None:
        script = """
## Harbor --- harbor
Sailor: All aboard for the southern isles! {id=welcome}
? Buy ticket (ticket)
? Stay on shore (shore)
~ input passenger_name "Your name, voyager?" "Traveler" {id=inp_name}
"""
        graph = eager_script.parse_graph(script)
        catalog = extract_catalog(graph, locale="template")
        keys = set(catalog.strings.keys())
        assert "harbor.welcome" in keys
        assert any("choice_0" in k for k in keys)
        assert any("choice_1" in k for k in keys)
        assert "harbor.inp_name.input" in keys

    def test_i18n_dialogue_and_speaker_translation(self) -> None:
        script = """
## Intro --- intro
Knight: Stand and declare yourself! {id=challenge}
"""
        graph = eager_script.parse_graph(script)
        cat_fr = TranslationCatalog(
            locale="fr",
            strings={"intro.challenge": "Halte et déclarez-vous !"},
            speakers={"Knight": "Chevalier"},
        )
        tm = TranslationManager()
        tm.register_catalog(cat_fr)
        tm.set_locale("fr")

        vm = StoryVM(graph, translation_manager=tm)
        vm.step()  # enter
        ev = vm.step()
        assert isinstance(ev, DialogueEvent)
        assert ev.speaker == "Chevalier"
        assert ev.text == "Halte et déclarez-vous !"

    def test_i18n_choice_option_translation(self) -> None:
        script = """
## Tavern --- tavern
? Order ale (ale)
? Drink water (water)
"""
        graph = eager_script.parse_graph(script)
        cat_tpl = extract_catalog(graph, locale="template")
        c_keys = [k for k in cat_tpl.strings if "choice_" in k]
        assert len(c_keys) == 2
        cat_de = TranslationCatalog(
            locale="de",
            strings={
                c_keys[0]: "Ein Bier bestellen",
                c_keys[1]: "Wasser trinken",
            },
        )
        tm = TranslationManager()
        tm.register_catalog(cat_de)
        tm.set_locale("de")

        vm = StoryVM(graph, translation_manager=tm)
        vm.step()  # enter
        prompt = vm.step()
        assert isinstance(prompt, ChoicePromptEvent)
        assert prompt.options[0].text == "Ein Bier bestellen"
        assert prompt.options[1].text == "Wasser trinken"

    def test_i18n_input_prompt_translation(self) -> None:
        script = """
## Gate --- gate
~ input secret "Say the password:" "Open" {id=pass_input}
"""
        graph = eager_script.parse_graph(script)
        cat_es = TranslationCatalog(
            locale="es",
            strings={"gate.pass_input.input": "Diga la contraseña:"},
        )
        tm = TranslationManager()
        tm.register_catalog(cat_es)
        tm.set_locale("es")

        vm = StoryVM(graph, translation_manager=tm)
        vm.step()
        prompt = vm.step()
        assert isinstance(prompt, InputPromptEvent)
        assert prompt.prompt == "Diga la contraseña:"

    def test_i18n_dynamic_locale_switching(self, tmp_path: Path) -> None:
        script = """
## Town --- town
Merchant: Good morning! {id=m_greet}
Merchant: Safe travels! {id=m_farewell}
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        cat_it = TranslationCatalog(
            locale="it",
            strings={
                "town.m_greet": "Buongiorno!",
                "town.m_farewell": "Buon viaggio!",
            },
            speakers={"Merchant": "Mercante"},
        )
        session.translation_manager.register_catalog(cat_it)

        # Advance first dialogue in English
        ev1 = session.advance()
        assert isinstance(ev1, DialogueEvent)
        assert ev1.speaker == "Merchant"
        assert ev1.text == "Good morning!"

        # Switch dynamically to Italian
        session.set_language("it")
        ev2 = session.advance()
        assert isinstance(ev2, DialogueEvent)
        assert ev2.speaker == "Mercante"
        assert ev2.text == "Buon viaggio!"


# ==============================================================================
# TIER 2: Boundary & Corner Cases
# ==============================================================================


class TestTier2BoundaryAndCornerCases:
    """Tier 2: Boundary conditions, empty payloads, and failure edge cases."""

    def test_empty_script_handling(self) -> None:
        script = """
# Only comments and whitespace

"""
        graph = eager_script.parse_graph(script)
        assert len(graph.nodes) == 0
        vm = StoryVM(graph)
        ev = vm.step()
        assert isinstance(ev, StoryEndEvent)
        assert ev.reason == "no_entry"

    def test_single_line_scene(self) -> None:
        script = """
## Solitary --- solitary
Just one thought before the end.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        ev1 = vm.step()
        assert isinstance(ev1, SceneEnterEvent)
        ev2 = vm.step()
        assert isinstance(ev2, NarrationEvent)
        assert ev2.text == "Just one thought before the end."
        ev3 = vm.step()
        assert isinstance(ev3, StoryEndEvent)
        assert ev3.reason == "terminal"

    def test_deep_branch_hierarchy(self) -> None:
        script = """
## L0 --- l0
>> l1
Finished L0.

## L1 --- l1
>> l2
<<

## L2 --- l2
>> l3
<<

## L3 --- l3
>> l4
<<

## L4 --- l4
Reached deep depth 4.
<<
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        events = []
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, (NarrationEvent, FreshBoxEvent)):
                events.append(ev.text)
        assert events == ["Reached deep depth 4.", "Finished L0."]

    def test_rapid_choice_picking(self) -> None:
        script = """
## Step1 --- step1
? Next (step2)

## Step2 --- step2
? Next (step3)

## Step3 --- step3
? Next (step4)

## Step4 --- step4
Destination reached.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        for expected_next in ["step2", "step3", "step4"]:
            vm.step()  # enter
            prompt = vm.step()  # choice
            assert isinstance(prompt, ChoicePromptEvent)
            vm.choose(0)
            assert vm.current_scene_id == expected_next
        vm.step()  # enter
        final_ev = vm.step()
        assert isinstance(final_ev, NarrationEvent)
        assert final_ev.text == "Destination reached."

    def test_corrupt_save_slot_resilience(self, tmp_path: Path) -> None:
        save_dir = tmp_path / "saves"
        save_dir.mkdir(parents=True, exist_ok=True)
        corrupt_file = save_dir / "broken_slot.json"
        corrupt_file.write_text("{malformed_json: true, unterminated", encoding="utf-8")

        sm = SaveManager(save_dir)
        loaded_cp = sm.load_slot("broken_slot")
        assert loaded_cp is None

        script = "## Start --- start\nAlice: Playing.\n"
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=save_dir)
        session.advance()
        load_ok = session.load_game("broken_slot")
        assert load_ok is False
        assert session.director.ui_state.text == "Playing."

    def test_jump_to_nonexistent_scene_raises_runtime_error(self) -> None:
        script = """
## Start --- start
Alice: We are here.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        with pytest.raises(StoryRuntimeError, match="Cannot jump to unknown scene 'ghost_scene'"):
            vm.jump("ghost_scene")

    def test_unconditional_jump_out_of_inline_choice_cleans_callstack(self) -> None:
        script = """
## Start --- start
Alice: Prepare for transit.
? Jump through rift
    Alice: Leaping now!
    > destination
Alice: This line must never be reached!

## Destination --- destination
Alice: Safely in new realm.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        vm.step()  # dialogue 'Prepare'
        prompt = vm.step()  # choice
        assert isinstance(prompt, ChoicePromptEvent)
        vm.choose(0)  # branch into inline choice that jumps

        dialogues = []
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, DialogueEvent):
                dialogues.append(ev.text)
        assert dialogues == ["Leaping now!", "Safely in new realm."]
        assert "This line must never be reached!" not in dialogues

    def test_missing_interpolation_variable_fallback(self) -> None:
        script = """
## Test --- test
Hello [nonexistent_variable] world.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()
        ev = vm.step()
        assert isinstance(ev, NarrationEvent)
        assert ev.text == "Hello [nonexistent_variable] world."


# ==============================================================================
# TIER 3: Cross-Feature Combinations
# ==============================================================================


class TestTier3CrossFeatureCombinations:
    """Tier 3: Complex multi-feature integration, state resilience, and interplay."""

    def test_choices_nested_inside_conditionals(self) -> None:
        script = """
@default player_class = "mage"
## GuildHall --- guild
@if player_class == "warrior"
    ? Train swordsmanship (sword)
    ? Train shield defense (shield)
@else
    ? Study ancient spells (spells)
    ? Brew potions (potions)
@end

## Spells --- spells
Casting arcane arts.

## Potions --- potions
Brewing elixirs.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        prompt = vm.step()
        assert isinstance(prompt, ChoicePromptEvent)
        assert len(prompt.options) == 2
        assert prompt.options[0].text == "Study ancient spells"
        assert prompt.options[1].text == "Brew potions"
        vm.choose(0)
        assert vm.current_scene_id == "spells"

    def test_rollback_across_branching_choices(self) -> None:
        script = """
## Split --- split
Make your choice.
? Red Route (red)
? Blue Route (blue)

## Red Route --- red
Alice: You took the red route.

## Blue Route --- blue
Bob: You took the blue route.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True)
        session.advance()  # Narration
        session.advance()  # Choice prompt
        assert session.active_choice_prompt is not None

        # Choose Red
        session.choose(0)
        assert session.director.ui_state.speaker == "Alice"
        assert session.director.ui_state.text == "You took the red route."

        # Rollback back to choice prompt
        ok = session.rollback()
        assert ok is True
        assert session.active_choice_prompt is not None
        assert len(session.active_choice_prompt.options) == 2

        # Choose Blue
        session.choose(1)
        assert session.director.ui_state.speaker == "Bob"
        assert session.director.ui_state.text == "You took the blue route."

    def test_variable_mutation_persisting_across_save_load(self, tmp_path: Path) -> None:
        script = """
## Bank --- bank
$ balance = 100
Alice: Initial balance [balance].
$ balance += 250
Alice: Updated balance [balance].
$ balance -= 300
Alice: Final balance [balance].
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        session.advance()  # Initial: 100
        assert session.vm.get_variable("balance") == 100

        session.advance()  # Updated: 350
        assert session.vm.get_variable("balance") == 350
        session.save_game("mid_transaction")

        session.advance()  # Final: 50
        assert session.vm.get_variable("balance") == 50

        ok = session.load_game("mid_transaction")
        assert ok is True
        assert session.vm.get_variable("balance") == 350
        assert session.director.ui_state.text == "Updated balance 350."

    def test_persistent_data_survives_rollback_and_loads(self, tmp_path: Path) -> None:
        script = """
## Achievement --- ach
$ persistent.secret_unlocked = True
Alice: Unlocked secret.
$ coins = 50
Alice: Gained coins.
"""
        graph = eager_script.parse_graph(script)
        session = GameSession(graph, headless=True, save_dir=tmp_path)
        session.advance()
        assert session.persistent.get("secret_unlocked") is True

        session.advance()
        assert session.vm.get_variable("coins") == 50

        # Rollback story state
        session.rollback()
        # Story variable rolled back
        assert session.vm.get_variable("coins") is None
        # Persistent data NOT rolled back!
        assert session.persistent.get("secret_unlocked") is True

    def test_localized_dialogue_with_variable_interpolation(self) -> None:
        script = """
@default player_name = "Roland"
@default crowns = 42
## Market --- market
Merchant: Welcome [player_name], you possess [crowns] crowns! {id=welcome_msg}
"""
        graph = eager_script.parse_graph(script)
        cat_es = TranslationCatalog(
            locale="es",
            strings={"market.welcome_msg": "¡Bienvenido [player_name], posees [crowns] coronas!"},
            speakers={"Merchant": "Comerciante"},
        )
        tm = TranslationManager()
        tm.register_catalog(cat_es)
        tm.set_locale("es")

        vm = StoryVM(graph, translation_manager=tm)
        vm.step()  # enter
        ev = vm.step()
        assert isinstance(ev, DialogueEvent)
        assert ev.speaker == "Comerciante"
        assert ev.text == "¡Bienvenido Roland, posees 42 coronas!"

    def test_input_prompt_feeding_conditional_choice(self) -> None:
        script = """
## GateKeeper --- gatekeeper
~ input age "State your age:" "16"
? Enter the arena (arena) if int(age) >= 18
? Visit the training yard (training)

## Arena --- arena
Arena entered.

## Training --- training
Training yard entered.
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        inp = vm.step()
        assert isinstance(inp, InputPromptEvent)
        # Supply adult age
        vm.submit_input("21")
        prompt = vm.step()
        assert isinstance(prompt, ChoicePromptEvent)
        assert prompt.options[0].enabled is True
        vm.choose(0)
        assert vm.current_scene_id == "arena"

    def test_subroutine_called_from_inline_choice(self) -> None:
        script = """
## Crossroads --- crossroads
? Seek blessing
    >> priest_blessing
    Alice: We are now blessed!
? Proceed without blessing
    Alice: Moving on.

Alice: Journey continues.

## Blessing --- priest_blessing
Priest: May the light guide you.
<<
"""
        graph = eager_script.parse_graph(script)
        vm = StoryVM(graph)
        vm.step()  # enter
        vm.step()  # choice
        vm.choose(0)  # pick inline choice that calls subroutine

        dialogues = []
        while not vm.is_ended:
            ev = vm.step()
            if isinstance(ev, DialogueEvent):
                dialogues.append(f"{ev.speaker}: {ev.text}")
        assert dialogues == [
            "Priest: May the light guide you.",
            "Alice: We are now blessed!",
            "Alice: Journey continues.",
        ]


# ==============================================================================
# TIER 4: Real-World Application Scenarios
# ==============================================================================


class TestTier4RealWorldApplicationScenarios:
    """Tier 4: End-to-end realistic story applications and comprehensive pipelines."""

    def test_complete_visual_novel_investigation_mystery(self, tmp_path: Path) -> None:
        """A complete multi-scene branching visual novel story:

        1. Setup investigator name via text input
        2. Exploration of manor, gathering clues
        3. Saving checkpoint to named slot
        4. Branching routes: investigate library vs interrogate butler
        5. Climax scene with conditional ending
        6. Persistent ending unlock verification
        7. Reloading save slot and playing alternate branch for second ending
        """
        script = """
@character detective "Lead Detective" color="#4a90e2"
@character butler "Jeeves the Butler" color="#7b8a8b"
@default clues_found = 0

## Prologue --- prologue
The rain hammers against the stained glass windows of Blackwood Manor.
~ input detective_name "Enter investigator name:" "Sam Vance"
detective: My name is [detective_name], private investigator.
detective: Lord Blackwood's signet ring is missing. Let us begin.
> crime_scene

## CrimeScene --- crime_scene
detective: Two places warrant immediate inspection.
? Search the library archives (library)
? Question the butler in the parlor (parlor)

## Library --- library
detective: Dusty volumes line the oak shelves.
$ clues_found += 1
? Examine the hidden safe behind the painting
    $ clues_found += 1
    detective: The safe was opened without forced entry!
? Inspect the muddy footprint by the window
    detective: A size 10 boot print.
> confrontation

## Parlor --- parlor
butler: Good evening, Detective [detective_name].
butler: I was polishing the silverware all evening.
? Press him about the scratches on his hands
    $ clues_found += 1
    butler (nervous): An unfortunate gardening mishap!
? Accept his alibi for now
    detective: Very well, Jeeves.
> confrontation

## Confrontation --- confrontation
detective: All evidence points to a conclusion.
@if clues_found >= 2
    detective: The evidence is indisputable. The culprit is unmasked!
    $ persistent.true_detective_ending = True
    Case closed - True Mastermind Exposed.
@else
    detective: We lack decisive proof. The trail goes cold.
    $ persistent.cold_case_ending = True
    Case unresolved - Cold Case.
@end
"""
        graph = eager_script.parse_graph(script)
        save_dir = tmp_path / "manor_saves"

        # --- Playthrough 1: Gather sufficient clues in Library -> True Ending ---
        session1 = GameSession(graph, headless=True, save_dir=save_dir)
        session1.advance()  # Prologue narration
        session1.advance()  # Input prompt for detective name
        session1.submit_input("Sherlock")
        session1.advance()  # detective: My name is Sherlock...
        session1.advance()  # detective: Lord Blackwood's...
        session1.advance()  # CrimeScene dialogue

        # Save game at the branching crossroads
        save_meta = session1.save_game("branch_point")
        assert save_meta.scene_id == "crime_scene"

        # Choose Library
        choice_ev = session1.advance()
        assert isinstance(choice_ev, ChoicePromptEvent)
        session1.choose(0)  # library

        session1.advance()  # Library narration/dialogue
        sub_choice = session1.advance()  # Examine safe
        assert isinstance(sub_choice, ChoicePromptEvent)
        session1.choose(0)  # safe -> clues_found becomes 2!

        session1.advance()  # safe dialogue
        session1.advance()  # Confrontation dialogue
        end_narration = session1.advance()  # Case Closed
        assert isinstance(end_narration, NarrationEvent)
        assert "True Mastermind Exposed" in end_narration.text
        assert session1.persistent.get("true_detective_ending") is True
        assert session1.persistent.get("cold_case_ending") is None

        # --- Playthrough 2: Reload branch_point, choose Parlor without pressing -> Cold Case ---
        session2 = GameSession(graph, headless=True, save_dir=save_dir)
        load_ok = session2.load_game("branch_point")
        assert load_ok is True
        assert session2.vm.current_scene_id == "crime_scene"
        assert session2.vm.get_variable("detective_name") == "Sherlock"

        # Choose Parlor
        session2.choose(1)  # parlor
        session2.advance()  # butler: Good evening...
        session2.advance()  # butler: I was polishing...
        parlor_choice = session2.advance()
        assert isinstance(parlor_choice, ChoicePromptEvent)
        session2.choose(1)  # Accept alibi -> clues_found remains 0

        session2.advance()  # detective: Very well
        session2.advance()  # detective: All evidence
        cold_narration = session2.advance()
        assert isinstance(cold_narration, NarrationEvent)
        assert "Cold Case" in cold_narration.text

        # Verify persistent store now contains BOTH unlocked endings!
        assert session2.persistent.get("true_detective_ending") is True
        assert session2.persistent.get("cold_case_ending") is True

    def test_multi_language_full_session_flow(self, tmp_path: Path) -> None:
        """Run a bilingual visual novel story with prologue, dialogue, choices, and input prompt.

        Switch language on the fly (EN -> DE), verify localization across all event types,
        save in alternate language, reload, and verify state consistency.
        """
        script = """
## Prologue --- prologue
The portal hums with ancient power. {id=prologue_narration}
~ input traveler_role "Declare your calling:" "Wanderer" {id=inp_role}
Elder: Welcome, brave [traveler_role]. {id=elder_greet}
? Enter portal (portal)
? Retreat to safety (safety)

## Portal --- portal
You step into the unknown. {id=portal_narration}

## Safety --- safety
You return to the valley. {id=safety_narration}
"""
        graph = eager_script.parse_graph(script)
        cat_tpl = extract_catalog(graph, locale="template")
        c_keys = [k for k in cat_tpl.strings if "choice_" in k]
        assert len(c_keys) == 2
        cat_de = TranslationCatalog(
            locale="de",
            strings={
                "prologue.prologue_narration": "Das Portal summt mit uralter Kraft.",
                "prologue.inp_role.input": "Erkläre deine Berufung:",
                "prologue.elder_greet": "Willkommen, tapferer [traveler_role].",
                c_keys[0]: "Das Portal betreten",
                c_keys[1]: "In Sicherheit zurückziehen",
                "portal.portal_narration": "Du trittst ins Unbekannte ein.",
            },
            speakers={"Elder": "Ältester"},
        )
        save_dir = tmp_path / "i18n_saves"
        session = GameSession(graph, headless=True, save_dir=save_dir)
        session.translation_manager.register_catalog(cat_de)

        # 1. Step in English
        ev1 = session.advance()
        assert isinstance(ev1, NarrationEvent)
        assert ev1.text == "The portal hums with ancient power."

        # 2. Switch to German
        session.set_language("de")

        # 3. Input prompt in German
        ev2 = session.advance()
        assert isinstance(ev2, InputPromptEvent)
        assert ev2.prompt == "Erkläre deine Berufung:"

        # 4. Dialogue in German with speaker and variable interpolation returned by submit_input
        ev3 = session.submit_input("Magier")
        assert isinstance(ev3, DialogueEvent)
        assert ev3.speaker == "Ältester"
        assert ev3.text == "Willkommen, tapferer Magier."

        # 5. Choice prompt in German
        ev4 = session.advance()
        assert isinstance(ev4, ChoicePromptEvent)
        assert ev4.options[0].text == "Das Portal betreten"
        assert ev4.options[1].text == "In Sicherheit zurückziehen"

        # 6. Save in German session
        session.save_game("german_checkpoint")

        # 7. Reload in new session and verify preferences & text
        session_loaded = GameSession(graph, headless=True, save_dir=save_dir)
        session_loaded.translation_manager.register_catalog(cat_de)
        load_ok = session_loaded.load_game("german_checkpoint")
        assert load_ok is True
        assert session_loaded.active_choice_prompt is not None
        assert session_loaded.active_choice_prompt.options[0].text == "Das Portal betreten"

        # Pick choice and complete
        ev_final = session_loaded.choose(0)
        assert isinstance(ev_final, NarrationEvent)
        assert ev_final.text == "Du trittst ins Unbekannte ein."
        ev_end = session_loaded.advance()
        assert isinstance(ev_end, StoryEndEvent)
        assert ev_end.reason == "terminal"

    def test_session_resilience_and_corrupt_quicksave_recovery(self, tmp_path: Path) -> None:
        """Verify session handles corrupted quicksave file gracefully without crashing

        and successfully recovers to normal gameplay.
        """
        script = """
## Story --- story
Alice: Beginning journey.
Alice: Checkpoint reached.
Alice: Final chapter.
"""
        graph = eager_script.parse_graph(script)
        save_dir = tmp_path / "resilience_saves"
        session = GameSession(graph, headless=True, save_dir=save_dir)

        session.advance()
        session.quicksave()
        session.advance()

        # Artificially corrupt the quicksave file
        quick_file = save_dir / "quick_1.json"
        assert quick_file.exists()
        quick_file.write_text("CORRUPTED_BINARY_DATA_\x00\x01\x02", encoding="utf-8")

        # Attempt quickload: should fail gracefully, returning False
        assert session.quickload() is False

        # Gameplay can continue uninterrupted
        ev3 = session.advance()
        assert isinstance(ev3, DialogueEvent)
        assert ev3.text == "Final chapter."

        # Normal manual save succeeds cleanly
        meta = session.save_game("healthy_slot")
        assert meta.slot_name == "healthy_slot"

        # Healthy load succeeds cleanly
        assert session.load_game("healthy_slot") is True
        assert session.director.ui_state.text == "Final chapter."
