"""End-to-end integration test with Eager StoryVM, EventDispatcher, and Eager-S screenplays."""

from eager_runtime import EventDispatcher, StoryVM
from eager_script import parse_graph

from eager_graphics import StageCompositor, StageDirector

SAMPLE_SCREENPLAY = """
## Courtyard --- courtyard
~ bg castle_courtyard with cut
~ show alice cheerful at left with cut
Alice (excited): Look over there!
~ show guard stern at right with cut
Guard: Halt! Who goes there?
Alice (serious): We are travelers.
~ move alice to center duration=0.0
~ hide guard with cut
? Step forward into the hall (hall)
? Flee into the woods (woods)

## Great Hall --- hall
~ bg hall_interior with cut
Narrator: You entered the hall.

## Dark Woods --- woods
~ bg dark_woods with cut
Narrator: You fled into the woods.
"""


def test_e2e_screenplay_execution_and_stage_state() -> None:
    # 1. Parse screenplay into SceneGraph
    graph = parse_graph(SAMPLE_SCREENPLAY)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()

    # 2. Setup StageCompositor and StageDirector
    compositor = StageCompositor(1920, 1080)
    director = StageDirector(compositor)
    director.bind(dispatcher)

    # 3. Step through the story until the first player choice pause
    choice_event = dispatcher.run_until_pause(vm)
    assert choice_event is not None
    assert choice_event.type == "choice_prompt"

    # 4. Verify visual render list at the choice prompt
    items = compositor.render_list()
    # Should have background (castle_courtyard) and Alice (serious, at center). Guard was hidden!
    assert len(items) == 2

    bg_item = next(it for it in items if it.layer == "background")
    assert bg_item.asset_id == "bg/castle_courtyard"

    alice_item = next(it for it in items if it.layer == "characters")
    assert alice_item.asset_id == "alice/serious"
    assert alice_item.x == 960.0  # Center position

    # Guard should NOT be on stage
    guard_items = [it for it in items if "guard" in it.asset_id]
    assert len(guard_items) == 0

    # 5. Test State Snapshot & Restore (Save/Load)
    story_save = vm.save()
    visual_save = compositor.save_state()

    # Make choice: 0 -> "hall"
    vm.choose(0)
    _ = dispatcher.run_until_pause(vm)
    assert vm.is_ended

    # In Great Hall: background should now be hall_interior
    hall_items = compositor.render_list()
    hall_bg = next(it for it in hall_items if it.layer == "background")
    assert hall_bg.asset_id == "bg/hall_interior"

    # Now reload previous save state
    vm.load(story_save)
    compositor.load_state(visual_save)

    # Re-verify that visual state restored exactly
    restored_items = compositor.render_list()
    assert len(restored_items) == 2
    restored_bg = next(it for it in restored_items if it.layer == "background")
    assert restored_bg.asset_id == "bg/castle_courtyard"
    restored_alice = next(it for it in restored_items if it.layer == "characters")
    assert restored_alice.asset_id == "alice/serious"
    assert restored_alice.x == 960.0


def test_e2e_beat_by_beat_stepping() -> None:
    graph = parse_graph("""
    ## Start --- start
    ~ bg tavern with cut
    ~ show bob smiling at left with cut
    Bob (worried): Are you sure?
    """)
    vm = StoryVM(graph)
    dispatcher = EventDispatcher()
    compositor = StageCompositor(1920, 1080)
    director = StageDirector(compositor)
    director.bind(dispatcher)

    # Beat 1: SceneEnterEvent
    ev1 = vm.step()
    dispatcher.dispatch(ev1)
    assert len(compositor.render_list()) == 0

    # Beat 2: HookEvent (~ bg tavern with cut)
    ev2 = vm.step()
    dispatcher.dispatch(ev2)
    assert len(compositor.render_list()) == 1
    assert compositor.render_list()[0].asset_id == "bg/tavern"

    # Beat 3: HookEvent (~ show bob smiling at left with cut)
    ev3 = vm.step()
    dispatcher.dispatch(ev3)
    assert len(compositor.render_list()) == 2
    bob_elem = next(it for it in compositor.render_list() if it.layer == "characters")
    assert bob_elem.asset_id == "bob/smiling"

    # Beat 4: DialogueEvent (Bob (worried): Are you sure?)
    ev4 = vm.step()
    dispatcher.dispatch(ev4)
    # Expression should auto-update to 'worried' without explicit ~ expr hook!
    bob_elem_updated = next(it for it in compositor.render_list() if it.layer == "characters")
    assert bob_elem_updated.asset_id == "bob/worried"
