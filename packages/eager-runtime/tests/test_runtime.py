"""Unit tests for story runtime execution: VM flow, choices, subroutines, expressions, and warping."""

from __future__ import annotations

import eager_script
import pytest
from eager_core.events import (
    AppendEvent,
    ChoicePromptEvent,
    DialogueEvent,
    FreshBoxEvent,
    NarrationEvent,
    SceneEnterEvent,
    SceneExitEvent,
    StoryEndEvent,
)
from eager_script import parse, parse_graph, validate

from eager_runtime import (
    GameSession,
    PersistentData,
    StoryRuntimeError,
    StoryVM,
)

LINEAR_SCRIPT = """
## Intro --- intro
The sun rises over the quiet hills.
- The morning mist slowly clears.
/ A rooster crows in the distance.
Hero: Time to begin our adventure.
> forest

## Forest --- forest
Dense trees shade the path ahead.
Hero (determined): Let's keep moving.
"""

CHOICE_SCRIPT = """
## Crossroads --- crossroads
Narrator: Two paths diverge before you.
? Take the mountain pass (mountain)
? Walk through the dark valley (valley)

## Mountain Pass --- mountain
Narrator: The air is crisp and cold.
> finish

## Dark Valley --- valley
Narrator: Shadows stretch long across the canyon.
> finish

## Finished --- finish
Narrator: Journey complete.
"""

INLINE_CHOICE_SCRIPT = """
@default gold = 10

## Tavern --- tavern
Bartender: What will it be?
? Order an ale
    $ gold -= 3
    Bartender: Coming right up.
? Ask for water
    Bartender: Suit yourself.
Bartender: Anything else?
> nightfall

## Nightfall --- nightfall
Narrator: The night deepens.
"""

JUMP_INLINE_SCRIPT = """
## Crossroads --- crossroads
? Take the shortcut
    Narrator: You duck through the alley.
    > arrive
Narrator: Reached only when the block falls through.

## Arrive --- arrive
Narrator: You arrive early.
"""

SUBROUTINE_SCRIPT = """
## Main --- main
Hero: Preparing to investigate.
>> sub_inspect
Hero: Investigation concluded.
> final

## Sub Inspect --- sub_inspect
Narrator: Inspecting ancient relic.
>> sub_nested
Narrator: Relic inspection finished.
<<

## Sub Nested --- sub_nested
Narrator: Found hidden engravings!
<<

## Final --- final
Narrator: The story ends.
"""

WARP_STORY = """
## Intro --- intro
~ bg classroom with cut
~ show guide smile at center with cut
$ gold = 100
~ play music bgm.mp3
~ play sound sfx.wav
Guide: Welcome to class!
> act1

## Act 1 --- act1
~ expr guide happy
Guide: Time for our first lesson.
? Study history (history)
? Study science (science)

## History --- history
$ subject = "history"
~ bg library with cut
Guide: History is fascinating.
> exam

## Science --- science
$ subject = "science"
~ bg lab with cut
Guide: Science is wonderful.
> exam

## Exam --- exam
Guide: Time for the exam!
"""

DISCONNECTED_STORY = """
## Main --- main
Narrator: Hello.

## Secret Start --- secret_start
~ bg dungeon with cut
~ show monster angry at center with cut
$ secret_found = True
> secret_end

## Secret End --- secret_end
Narrator: The dungeon ends here.
"""


# ---------------------------------------------------------------------------
# Linear Flow and Visited Scenes
# ---------------------------------------------------------------------------

def test_linear_execution_flow() -> None:
    graph = eager_script.parse_graph(LINEAR_SCRIPT)
    vm = StoryVM(graph)
    events = []
    while not vm.is_ended:
        event = vm.step()
        if event is not None:
            events.append(event)

    # 1. SceneEnterEvent for intro
    assert isinstance(events[0], SceneEnterEvent)
    assert events[0].scene_id == "intro"

    # 2. NarrationEvent
    assert isinstance(events[1], NarrationEvent)
    assert "The sun rises" in events[1].text

    # 3. AppendEvent
    assert isinstance(events[2], AppendEvent)
    assert "The morning mist" in events[2].text

    # 4. FreshBoxEvent
    assert isinstance(events[3], FreshBoxEvent)
    assert "A rooster crows" in events[3].text

    # 5. DialogueEvent
    assert isinstance(events[4], DialogueEvent)
    assert events[4].speaker == "Hero"
    assert events[4].text == "Time to begin our adventure."
    assert events[4].emotion is None

    # 6. SceneExitEvent (jump)
    assert isinstance(events[5], SceneExitEvent)
    assert events[5].transition_kind == "jump"
    assert events[5].target == "forest"

    # 7. SceneEnterEvent for forest
    assert isinstance(events[6], SceneEnterEvent)
    assert events[6].scene_id == "forest"

    # 8. Narration in forest
    assert isinstance(events[7], NarrationEvent)

    # 9. Dialogue with emotion
    assert isinstance(events[8], DialogueEvent)
    assert events[8].emotion == "determined"

    # 10. StoryEndEvent
    assert isinstance(events[9], StoryEndEvent)
    assert events[9].reason == "terminal"
    assert vm.is_ended


def test_visited_scenes_tracking() -> None:
    graph = eager_script.parse_graph(LINEAR_SCRIPT)
    vm = StoryVM(graph)
    while not vm.is_ended:
        vm.step()

    assert vm.visited_scenes == {"intro", "forest"}


def test_empty_graph_handling() -> None:
    empty_graph = eager_script.to_graph([])
    vm = StoryVM(empty_graph)
    assert vm.current_scene_id is None
    event = vm.step()
    assert isinstance(event, StoryEndEvent)
    assert event.reason == "no_entry"
    assert vm.is_ended


# ---------------------------------------------------------------------------
# Branching and Choice Handling
# ---------------------------------------------------------------------------

def test_branching_selection_numeric() -> None:
    graph = eager_script.parse_graph(CHOICE_SCRIPT)
    vm = StoryVM(graph)

    # Step until choice prompt
    prompt = None
    while not vm.is_ended:
        event = vm.step()
        if isinstance(event, ChoicePromptEvent):
            prompt = event
            break

    assert isinstance(prompt, ChoicePromptEvent)
    assert len(prompt.options) == 2
    assert prompt.options[0].text == "Take the mountain pass"
    assert prompt.options[0].target == "mountain"
    assert prompt.options[1].text == "Walk through the dark valley"
    assert prompt.options[1].target == "valley"

    # Calling step() again while choice is pending returns the prompt without advancing
    repeat_event = vm.step()
    assert repeat_event == prompt

    # Select choice 1 (valley)
    vm.choose(1)
    assert vm.pending_choice is None

    # Next event should enter valley scene
    next_event = vm.step()
    assert isinstance(next_event, SceneEnterEvent)
    assert next_event.scene_id == "valley"


def test_branching_selection_by_target_id() -> None:
    graph = eager_script.parse_graph(CHOICE_SCRIPT)
    vm = StoryVM(graph)

    while not vm.is_ended:
        event = vm.step()
        if isinstance(event, ChoicePromptEvent):
            break

    vm.choose("mountain")
    next_event = vm.step()
    assert isinstance(next_event, SceneEnterEvent)
    assert next_event.scene_id == "mountain"


def test_invalid_choice_raises_error() -> None:
    graph = eager_script.parse_graph(CHOICE_SCRIPT)
    vm = StoryVM(graph)
    while not vm.is_ended:
        event = vm.step()
        if isinstance(event, ChoicePromptEvent):
            break

    with pytest.raises(StoryRuntimeError):
        vm.choose(99)  # Index out of bounds

    with pytest.raises(StoryRuntimeError):
        vm.choose("non_existent_target")


def test_choose_without_pending_choice_raises_error() -> None:
    graph = eager_script.parse_graph(CHOICE_SCRIPT)
    vm = StoryVM(graph)
    # At start, no choice prompt active
    with pytest.raises(StoryRuntimeError):
        vm.choose(0)


# ---------------------------------------------------------------------------
# Inline Choice Blocks
# ---------------------------------------------------------------------------

def _run_inline(script: str, choice: int = 0) -> tuple[StoryVM, list]:
    graph = eager_script.parse_graph(script)
    vm = StoryVM(graph)
    events: list = []
    while not vm.is_ended:
        event = vm.step()
        if event is None:
            break
        events.append(event)
        if isinstance(event, ChoicePromptEvent):
            vm.choose(choice)
    return vm, events


def test_inline_block_executes_then_resumes_scene() -> None:
    vm, events = _run_inline(INLINE_CHOICE_SCRIPT, choice=0)

    texts = [e.text for e in events if isinstance(e, DialogueEvent)]
    assert texts == ["What will it be?", "Coming right up.", "Anything else?", "The night deepens."]
    assert vm.get_variable("gold") == 7

    entered = [e.scene_id for e in events if isinstance(e, SceneEnterEvent)]
    assert "tavern__anon_6" in entered

    returns = [e for e in events if isinstance(e, SceneExitEvent) and e.transition_kind == "return"]
    assert any(r.target == "tavern" for r in returns)

    assert isinstance(events[-1], StoryEndEvent)
    assert events[-1].scene_id == "nightfall"


def test_alternative_inline_branch_does_not_mutate_state() -> None:
    vm, _events = _run_inline(INLINE_CHOICE_SCRIPT, choice=1)
    assert vm.get_variable("gold") == 10


def test_jump_inside_inline_block_skips_continuation() -> None:
    _vm, events = _run_inline(JUMP_INLINE_SCRIPT, choice=0)
    texts = [e.text for e in events if isinstance(e, DialogueEvent)]
    assert texts == ["You duck through the alley.", "You arrive early."]
    assert "Reached only when the block falls through." not in texts


def test_nested_inline_blocks() -> None:
    script = """
## Hub --- hub
? Outer reaction
    Narrator: outer start
    ? Inner reaction
        Narrator: inner beat
    Narrator: outer end
Narrator: hub end
"""
    graph = eager_script.parse_graph(script)
    vm = StoryVM(graph)
    texts: list[str] = []
    while not vm.is_ended:
        event = vm.step()
        if event is None:
            break
        if isinstance(event, DialogueEvent):
            texts.append(event.text)
        if isinstance(event, ChoicePromptEvent):
            vm.choose(0)
    assert texts == ["outer start", "inner beat", "outer end", "hub end"]


def test_inline_option_with_condition() -> None:
    script = """
@default has_key = False
## Door --- door
? Pick the lock if has_key
    $ picked = True
    Narrator: The lock clicks open.
? Knock
    $ knocked = True
    Narrator: You knock politely.
"""
    graph = eager_script.parse_graph(script)
    vm = StoryVM(graph)
    vm.step()  # SceneEnter
    prompt = vm.step()  # ChoicePrompt
    assert isinstance(prompt, ChoicePromptEvent)
    assert not prompt.options[0].enabled
    assert prompt.options[1].enabled

    with pytest.raises(StoryRuntimeError):
        vm.choose(0)

    vm.choose(1)
    while not vm.is_ended:
        if vm.step() is None:
            break
    assert vm.get_variable("knocked") is True
    assert vm.get_variable("picked") is None


def test_nested_inline_jump_abandons_all_inline_frames() -> None:
    script = """
## Main --- main
Narrator: main start
? Option A
    Narrator: in A
    ? Option B
        Narrator: in B
        > final_scene
    Narrator: after B in A
Narrator: main end

## FinalScene --- final_scene
Narrator: in final scene
"""
    _vm, events = _run_inline(script, choice=0)
    texts = [e.text for e in events if isinstance(e, DialogueEvent)]
    assert texts == ["main start", "in A", "in B", "in final scene"]
    assert "main end" not in texts
    assert "after B in A" not in texts


def test_choice_inside_inline_targeting_named_scene_abandons_inline_frames() -> None:
    script = """
## Main --- main
Narrator: main start
? Option A
    Narrator: in A
    ? Go away (final_scene)
Narrator: main end

## FinalScene --- final_scene
Narrator: in final scene
"""
    _vm, events = _run_inline(script, choice=0)
    texts = [e.text for e in events if isinstance(e, DialogueEvent)]
    assert texts == ["main start", "in A", "in final scene"]
    assert "main end" not in texts


# ---------------------------------------------------------------------------
# Logic, Variables, Conditionals, and Expressions
# ---------------------------------------------------------------------------

def test_variable_default_and_mutation() -> None:
    script = """
@default affinity = 0
@default player_name = "Alex"

## Start --- start
Narrator: Hello, [player_name]!
$ affinity += 10
$ player_name = "Alexander"
Narrator: Now named [player_name] with affinity [affinity].
"""
    graph = parse_graph(script)
    vm = StoryVM(graph)

    ev = vm.step()  # SceneEnter
    assert isinstance(ev, SceneEnterEvent)
    assert ev.type == "scene_enter"

    ev = vm.step()  # Narration
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Hello, Alex!"

    ev = vm.step()  # Narration after $ mutations
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Now named Alexander with affinity 10."
    assert vm.get_variable("affinity") == 10
    assert vm.get_variable("player_name") == "Alexander"


def test_conditional_if_elif_else_branching() -> None:
    script = """
@default score = 15

## Scene --- scene
@if score > 20
Narrator: High score!
@elif score > 10
Narrator: Medium score!
@else
Narrator: Low score!
@end
Narrator: End of evaluation.
"""
    graph = parse_graph(script)
    vm = StoryVM(graph)
    vm.step()  # SceneEnter

    ev = vm.step()  # Medium score!
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Medium score!"

    ev = vm.step()  # End of evaluation.
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "End of evaluation."


def test_conditional_choices() -> None:
    script = """
@default has_key = False

## Door --- door
Guard: State your action.
? Unlock door (enter) if has_key
? Walk away (leave)

## Enter --- enter
Guard: Welcome.

## Leave --- leave
Guard: Farewell.
"""
    graph = parse_graph(script)
    vm = StoryVM(graph)
    vm.step()  # SceneEnter
    vm.step()  # Guard dialogue

    prompt = vm.step()  # ChoicePromptEvent
    assert isinstance(prompt, ChoicePromptEvent)
    assert prompt.type == "choice_prompt"
    assert len(prompt.options) == 2
    # Option 0 should be disabled
    assert not prompt.options[0].enabled
    assert prompt.options[1].enabled

    # Attempting to choose disabled option raises error
    with pytest.raises(StoryRuntimeError):
        vm.choose(0)

    # Choosing enabled option succeeds
    vm.choose(1)
    assert vm.current_scene_id == "leave"


def test_character_definition_and_interpolation() -> None:
    script = """
@character a "Alice" color=#ff0000

## Scene --- scene
a: Hello there!
"""
    graph = parse_graph(script)
    assert "a" in graph.characters
    assert graph.characters["a"]["name"] == "Alice"

    vm = StoryVM(graph)
    vm.step()  # SceneEnter
    ev = vm.step()
    assert isinstance(ev, DialogueEvent)
    assert ev.speaker == "Alice"
    assert ev.text == "Hello there!"


def test_escaped_brackets_and_nested_expressions() -> None:
    script = """
@default x = 5

## Scene --- scene
Narrator: Escaped [[bracket]] and value [x].
"""
    graph = parse_graph(script)
    vm = StoryVM(graph)
    vm.step()
    ev = vm.step()
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Escaped [bracket] and value 5."


def test_validator_detects_unclosed_if_and_syntax_error() -> None:
    script = """
## Scene --- scene
@if 1 > 0
Alice: Hello
"""
    res = validate(parse(script))
    assert not res.is_valid
    assert any("Unclosed @if block" in e.message for e in res.errors)

    script_err = """
## Scene --- scene
@if (invalid syntax ==
Alice: Hello
@end
"""
    res_err = validate(parse(script_err))
    assert not res_err.is_valid
    assert any("Invalid expression" in e.message for e in res_err.errors)


def test_private_attribute_blocking_in_interpolation() -> None:
    script = """
## Scene --- scene
Narrator: Secret is [persistent.__class__], [persistent._data], and [_private].
"""
    graph = parse_graph(script)
    vm = StoryVM(graph)
    vm.set_variable("persistent", PersistentData())
    vm.set_variable("_private", "secret_leak")
    vm.step()  # SceneEnter
    ev = vm.step()  # Narration
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Secret is [persistent.__class__], [persistent._data], and [_private]."


# ---------------------------------------------------------------------------
# Subroutine Execution
# ---------------------------------------------------------------------------

def test_nested_subroutine_call_stack() -> None:
    graph = eager_script.parse_graph(SUBROUTINE_SCRIPT)
    vm = StoryVM(graph)
    events = []

    while not vm.is_ended:
        event = vm.step()
        if event is not None:
            events.append(event)

    # Trace scene transitions
    enter_scenes = [e.scene_id for e in events if isinstance(e, SceneEnterEvent)]
    assert enter_scenes == ["main", "sub_inspect", "sub_nested", "final"]

    # Check call events
    calls = [e for e in events if isinstance(e, SceneExitEvent) and e.transition_kind == "call"]
    assert len(calls) == 2
    assert calls[0].scene_id == "main"
    assert calls[0].target == "sub_inspect"
    assert calls[1].scene_id == "sub_inspect"
    assert calls[1].target == "sub_nested"

    # Check return events
    returns = [e for e in events if isinstance(e, SceneExitEvent) and e.transition_kind == "return"]
    assert len(returns) == 2
    assert returns[0].scene_id == "sub_nested"
    assert returns[0].target == "sub_inspect"
    assert returns[1].scene_id == "sub_inspect"
    assert returns[1].target == "main"

    # Check dialogue beats order
    hero_dialogues = [e.text for e in events if isinstance(e, DialogueEvent) and e.speaker == "Hero"]
    assert hero_dialogues == [
        "Preparing to investigate.",
        "Investigation concluded.",
    ]

    # End event
    last_event = events[-1]
    assert isinstance(last_event, StoryEndEvent)
    assert last_event.reason == "terminal"


# ---------------------------------------------------------------------------
# Scene Warping
# ---------------------------------------------------------------------------

def test_warp_simulates_stage_state_and_variables() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)

    # Warp directly to Act 1
    success = session.warp("act1")
    assert success is True
    assert session.vm.current_scene_id == "act1"

    # Stage background should be classroom from intro
    items = session.compositor.render_list()
    bg_items = [it for it in items if it.layer == "background"]
    assert len(bg_items) == 1
    assert "classroom" in bg_items[0].asset_id

    # Character guide should be present with expression from intro
    char_items = [it for it in items if it.layer == "characters"]
    assert len(char_items) == 1
    assert "guide" in char_items[0].asset_id

    # Variable from intro should be set
    assert session.vm.get_variable("gold") == 100

    # Backlog should contain Intro dialogue
    assert len(session.backlog.entries) >= 1
    assert any("Welcome to class!" in entry.text for entry in session.backlog.entries)

    # Continuous audio (music) was requested; one-shot sound was suppressed
    music_chan = session.audio.channels.get("music")
    assert music_chan is not None
    assert music_chan.is_playing is True

    sound_chan = session.audio.channels.get("sound")
    assert sound_chan is None or sound_chan.is_playing is False

    # UI text should be clean for Act 1
    assert session.director.ui_state.text is None

    # Advancing now executes Act 1 beats (modifying expression to happy)
    evt = session.advance()
    assert isinstance(evt, DialogueEvent)
    assert evt.speaker == "Guide"
    assert evt.text == "Time for our first lesson."

    char_items = [it for it in session.compositor.render_list() if it.layer == "characters"]
    assert len(char_items) == 1
    assert "happy" in char_items[0].asset_id


def test_warp_branching_choices() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)

    assert session.warp("history") is True
    assert session.vm.current_scene_id == "history"
    bg_items = [it for it in session.compositor.render_list() if it.layer == "background"]
    assert "classroom" in bg_items[0].asset_id

    evt = session.advance()
    assert isinstance(evt, DialogueEvent)
    assert evt.text == "History is fascinating."
    assert session.vm.get_variable("subject") == "history"
    bg_items = [it for it in session.compositor.render_list() if it.layer == "background"]
    assert "library" in bg_items[0].asset_id

    # New session: Warp to Exam
    session2 = GameSession(graph)
    assert session2.warp("exam") is True
    assert session2.vm.current_scene_id == "exam"
    assert session2.vm.get_variable("subject") in ("history", "science")
    bg_items2 = [it for it in session2.compositor.render_list() if it.layer == "background"]
    assert len(bg_items2) == 1
    assert any(bg in bg_items2[0].asset_id for bg in ("library", "lab"))


def test_warp_disconnected_root_ancestor() -> None:
    graph = eager_script.parse_graph(DISCONNECTED_STORY)
    session = GameSession(graph)

    assert session.warp("secret_end") is True
    assert session.vm.current_scene_id == "secret_end"

    items = session.compositor.render_list()
    bg_items = [it for it in items if it.layer == "background"]
    assert "dungeon" in bg_items[0].asset_id
    char_items = [it for it in items if it.layer == "characters"]
    assert len(char_items) == 1
    assert "monster" in char_items[0].asset_id
    assert session.vm.get_variable("secret_found") is True


def test_warp_direct_without_simulation() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)

    assert session.warp("act1", simulate=False) is True
    assert session.vm.current_scene_id == "act1"

    assert session.vm.get_variable("gold") is None
    bg_items = [it for it in session.compositor.render_list() if it.layer == "background"]
    assert len(bg_items) == 0


def test_warp_invalid_target() -> None:
    graph = eager_script.parse_graph(WARP_STORY)
    session = GameSession(graph)
    assert session.warp("nonexistent_scene") is False


# ---------------------------------------------------------------------------
# StoryVM History Architecture Invariant
# ---------------------------------------------------------------------------

def test_vm_has_no_legacy_history_stack() -> None:
    """StoryVM must remain lightweight and stateless without internal history stacks."""
    graph = eager_script.parse_graph(LINEAR_SCRIPT)
    vm = StoryVM(graph)
    assert not hasattr(vm, "_history")
    assert not hasattr(vm, "history")
    assert not hasattr(vm, "rollback")
