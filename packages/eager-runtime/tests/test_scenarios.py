"""E2E Test Suite for cross-feature combinations and real-world application scenarios."""

from __future__ import annotations

from pathlib import Path

import eager_script
from eager_core.events import (
    ChoicePromptEvent,
    DialogueEvent,
    InputPromptEvent,
    NarrationEvent,
    StoryEndEvent,
)
from eager_core.i18n import TranslationCatalog, TranslationManager

from eager_runtime import (
    GameSession,
    StoryVM,
)
from eager_runtime.i18n import extract_catalog


class TestCrossFeatureScenarios:
    """Complex multi-feature integration, state resilience, and interplay."""

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


class TestApplicationScenarios:
    """End-to-end realistic story applications and comprehensive pipelines."""

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
