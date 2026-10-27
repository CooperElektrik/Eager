"""Unit tests for StorySnapshot, variable management, and persistent state isolation."""

from pathlib import Path

import eager_script
import pytest
from eager_core.events import (
    ChoicePromptEvent,
    DialogueEvent,
    InputPromptEvent,
    SceneEnterEvent,
    SceneExitEvent,
)

from eager_runtime import (
    CallFrame,
    PersistentData,
    StoryRuntimeError,
    StorySnapshot,
    StoryVM,
)

SAMPLE_SCRIPT = """
## Scene 1 --- scene_1
Narrator: Beat 1
Alice: Beat 2
Bob: Beat 3
> scene_2

## Scene 2 --- scene_2
Narrator: Beat 4
"""


def test_variable_get_and_set() -> None:
    graph = eager_script.parse_graph(SAMPLE_SCRIPT)
    vm = StoryVM(graph)
    vm.set_variable("player_name", "Hero")
    vm.set_variable("gold", 150)
    vm.set_variable("has_sword", True)

    assert vm.get_variable("player_name") == "Hero"
    assert vm.get_variable("gold") == 150
    assert vm.get_variable("has_sword") is True
    assert vm.get_variable("unknown_var") is None
    assert vm.get_variable("unknown_var", default=42) == 42


def test_snapshot_serialization() -> None:
    snapshot = StorySnapshot(
        current_scene="scene_1",
        beat_index=2,
        call_stack=(CallFrame(scene_id="main", beat_index=1),),
        variables={"hp": 100, "inventory": ["potion"]},
        visited_scenes=("main", "scene_1"),
    )

    d = snapshot.to_dict()
    assert d["current_scene"] == "scene_1"
    assert d["beat_index"] == 2
    assert len(d["call_stack"]) == 1
    assert d["call_stack"][0]["scene_id"] == "main"
    assert d["variables"]["hp"] == 100

    # JSON round-trip
    json_str = snapshot.to_json(indent=2)
    parsed = StorySnapshot.from_json(json_str)
    assert snapshot == parsed


def test_save_and_load_restoration() -> None:
    graph = eager_script.parse_graph(SAMPLE_SCRIPT)
    vm = StoryVM(graph)
    vm.set_variable("karma", 10)

    # Step 1: enter scene_1
    vm.step()
    # Step 2: Beat 1
    vm.step()
    # Step 3: Beat 2 (Alice)
    evt = vm.step()
    assert isinstance(evt, DialogueEvent)
    assert evt.speaker == "Alice"

    # Save mid-scene
    saved_snapshot = vm.save()
    assert saved_snapshot.current_scene == "scene_1"
    assert saved_snapshot.variables["karma"] == 10

    # Continue playing further
    vm.set_variable("karma", -5)
    vm.step()  # Bob
    vm.step()  # Jump to scene_2
    vm.step()  # Enter scene_2

    assert vm.current_scene_id == "scene_2"
    assert vm.get_variable("karma") == -5

    # Now restore saved state
    vm.load(saved_snapshot)
    assert vm.current_scene_id == "scene_1"
    assert vm.get_variable("karma") == 10

    # Next beat should resume right at Bob's beat!
    next_evt = vm.step()
    assert isinstance(next_evt, DialogueEvent)
    assert next_evt.speaker == "Bob"


def test_load_invalid_scene_raises_error() -> None:
    graph = eager_script.parse_graph(SAMPLE_SCRIPT)
    vm = StoryVM(graph)
    bad_snapshot = StorySnapshot(
        current_scene="non_existent_scene",
        beat_index=0,
        call_stack=(),
        variables={},
        visited_scenes=(),
    )

    with pytest.raises(StoryRuntimeError):
        vm.load(bad_snapshot)


def test_save_at_choice_load_preserves_choice() -> None:
    script = """
## Scene 1 --- scene_1
Narrator: Before choice
? Option A (opt_a)
? Option B (opt_b)

## Option A --- opt_a
Narrator: Picked A
"""
    graph = eager_script.parse_graph(script)
    vm = StoryVM(graph)
    vm.step()  # SceneEnter
    vm.step()  # Narrator: Before choice
    choice_evt = vm.step()  # ChoicePromptEvent
    assert isinstance(choice_evt, ChoicePromptEvent)
    assert vm.pending_choice is not None

    # Save while choice is pending
    snap = vm.save()
    assert snap.pending_choice_beat is not None

    # Create new VM or load snapshot
    vm2 = StoryVM(graph)
    vm2.load(snap)
    assert vm2.pending_choice is not None
    step_evt = vm2.step()
    assert isinstance(step_evt, ChoicePromptEvent)
    assert len(step_evt.options) == 2

    # Can choose after load!
    vm2.choose(0)
    assert vm2.current_scene_id == "opt_a"


def test_save_after_jump_exit_load_preserves_transition() -> None:
    graph = eager_script.parse_graph(SAMPLE_SCRIPT)
    vm = StoryVM(graph)
    vm.step()  # Enter scene_1
    vm.step()  # Narrator
    vm.step()  # Alice
    vm.step()  # Bob
    exit_evt = vm.step()  # Jump to scene_2 (SceneExitEvent)
    assert isinstance(exit_evt, SceneExitEvent)

    # Save right after jump beat was executed
    snap = vm.save()
    assert snap.next_transition_target == "scene_2"

    vm2 = StoryVM(graph)
    vm2.load(snap)
    enter_evt = vm2.step()
    assert isinstance(enter_evt, SceneEnterEvent)
    assert enter_evt.scene_id == "scene_2"


def test_prng_state_restoration_mersenne_twister() -> None:
    graph = eager_script.parse_graph(SAMPLE_SCRIPT)
    vm1 = StoryVM(graph)
    # Consume some random numbers to advance the MT state
    _ = [vm1._rng.random() for _ in range(10)]

    # Save snapshot and round-trip through JSON (which converts inner tuples to lists)
    snap = vm1.save()
    assert snap.rng_state is not None
    json_str = snap.to_json()
    restored_snap = StorySnapshot.from_json(json_str)

    # Confirm that JSON deserialized the MT state vector as a list
    assert restored_snap.rng_state is not None
    assert isinstance(restored_snap.rng_state[1], list)

    # Generate expected future random stream from original VM
    expected_next = [vm1._rng.random() for _ in range(10)]

    # Load snapshot into new VM - should recursively restore nested tuples for setstate
    vm2 = StoryVM(graph)
    vm2.load(restored_snap)

    # Verify new VM generates exactly identical numbers in sequence
    actual_next = [vm2._rng.random() for _ in range(10)]
    assert expected_next == actual_next


def test_load_pending_choice_and_input_beat_id() -> None:
    src = """
## Start --- start
Alice: Before choices
? Option A (a)
? Option B (b)

## Scene A --- a
Alice: Picked A
~ input hero_name What is your name?
Alice: Hero is [hero_name]
"""
    graph = eager_script.parse_graph(src)
    vm = StoryVM(graph)
    vm.step()  # SceneEnter
    vm.step()  # Alice: Before choices
    choice_evt = vm.step()  # ChoicePromptEvent
    assert isinstance(choice_evt, ChoicePromptEvent)
    orig_choice_beat_id = choice_evt.beat_id

    # Save while choice is pending and restore into new VM
    snap = vm.save()
    vm2 = StoryVM(graph)
    vm2.load(snap)
    assert vm2.pending_choice is not None
    assert vm2.pending_choice.beat_id == orig_choice_beat_id

    # Proceed with choice
    vm.choose(0)
    vm.step()  # SceneEnter Scene A
    vm.step()  # Alice: Picked A
    input_evt = vm.step()  # InputPromptEvent
    assert isinstance(input_evt, InputPromptEvent)
    orig_input_beat_id = input_evt.beat_id
    assert orig_input_beat_id is not None

    # Save while input is pending and restore into new VM
    snap_input = vm.save()
    vm3 = StoryVM(graph)
    vm3.load(snap_input)
    assert vm3.pending_input is not None
    assert vm3.pending_input.beat_id == orig_input_beat_id
    assert vm3.pending_input.prompt == input_evt.prompt
    assert vm3.pending_input.var_name == input_evt.var_name


def test_persistent_variable_mutation_and_rollback_isolation(tmp_path: Path) -> None:
    script = """
## Start --- start
$ persistent.coins = 10
$ persistent.coins += 5
$ normal_coins = 100
Narrator: Coins: [persistent.coins] and normal: [normal_coins]
@if persistent.coins > 10
    Narrator: Rich!
@else
    Narrator: Poor!
@end
"""
    p_file = tmp_path / "persistent.json"
    p_data = PersistentData(p_file)

    graph = eager_script.parse_graph(script)
    vm = StoryVM(graph, persistent=p_data)

    # Step past scene enter and sets to dialogue
    enter_ev = vm.step()
    assert isinstance(enter_ev, SceneEnterEvent)
    assert enter_ev.type == "scene_enter"
    ev = vm.step()
    assert isinstance(ev, DialogueEvent)
    assert ev.text == "Coins: 15 and normal: 100"

    # Verify persistent object directly mutated
    assert p_data["coins"] == 15
    assert p_data.coins == 15
    assert "persistent.coins" not in vm.variables
    assert vm.get_variable("persistent.coins") == 15

    # Checkpoint save
    snap = vm.save()
    assert "persistent" not in snap.variables
    assert "persistent.coins" not in snap.variables
    assert snap.variables.get("normal_coins") == 100

    # Step to next beat inside if branch
    ev2 = vm.step()
    assert isinstance(ev2, DialogueEvent)
    assert ev2.text == "Rich!"

    # Now mutate persistent and mutate normal_coins
    vm.set_variable("persistent.coins", 999)
    vm.set_variable("normal_coins", 0)
    assert p_data.coins == 999
    assert vm.get_variable("normal_coins") == 0

    # Restore snapshot (rollback)
    vm.load(snap)
    # normal_coins should be restored, but persistent.coins must NOT be rolled back
    assert vm.get_variable("normal_coins") == 100
    assert vm.get_variable("persistent.coins") == 999
    assert p_data.coins == 999
