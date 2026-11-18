"""E2E Test Suite for cross-feature combinations and real-world application scenarios."""

from __future__ import annotations

from pathlib import Path

import eager.script
from eager.core.events import (
    ChoicePromptEvent,
    DialogueEvent,
    NarrationEvent,
)
from eager.session import GameSession
from eager.vm import StoryVM


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
        graph = eager.script.parse_graph(script)
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
        graph = eager.script.parse_graph(script)
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
        graph = eager.script.parse_graph(script)
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
        graph = eager.script.parse_graph(script)
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
        graph = eager.script.parse_graph(script)
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
$ detective_name = "Sherlock"
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
        graph = eager.script.parse_graph(script)
        save_dir = tmp_path / "manor_saves"

        # --- Playthrough 1: Gather sufficient clues in Library -> True Ending ---
        session1 = GameSession(graph, headless=True, save_dir=save_dir)
        session1.advance()  # Prologue narration
        session1.advance()  # detective: My name is Sherlock...
        session1.advance()  # detective: Lord Blackwood's...
        session1.advance()  # CrimeScene dialogue

        # Choose Library
        choice_ev = session1.advance()
        assert isinstance(choice_ev, ChoicePromptEvent)

        # Save game at the branching crossroads
        save_meta = session1.save_game("branch_point")
        assert save_meta.scene_id == "crime_scene"

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
