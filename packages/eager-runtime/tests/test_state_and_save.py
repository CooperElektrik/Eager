"""Unit tests for state management, variable storage, and snapshot serialization in StoryVM."""

import unittest

import eager_script

from eager_runtime import (
    CallFrame,
    DialogueEvent,
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


class TestStateAndSave(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = eager_script.parse_graph(SAMPLE_SCRIPT)

    def test_variable_get_and_set(self) -> None:
        vm = StoryVM(self.graph)
        vm.set_variable("player_name", "Hero")
        vm.set_variable("gold", 150)
        vm.set_variable("has_sword", True)

        self.assertEqual(vm.get_variable("player_name"), "Hero")
        self.assertEqual(vm.get_variable("gold"), 150)
        self.assertTrue(vm.get_variable("has_sword"))
        self.assertIsNone(vm.get_variable("unknown_var"))
        self.assertEqual(vm.get_variable("unknown_var", default=42), 42)

    def test_snapshot_serialization(self) -> None:
        snapshot = StorySnapshot(
            current_scene="scene_1",
            beat_index=2,
            call_stack=(CallFrame(scene_id="main", beat_index=1),),
            variables={"hp": 100, "inventory": ["potion"]},
            visited_scenes=("main", "scene_1"),
        )

        d = snapshot.to_dict()
        self.assertEqual(d["current_scene"], "scene_1")
        self.assertEqual(d["beat_index"], 2)
        self.assertEqual(len(d["call_stack"]), 1)
        self.assertEqual(d["call_stack"][0]["scene_id"], "main")
        self.assertEqual(d["variables"]["hp"], 100)

        # JSON round-trip
        json_str = snapshot.to_json(indent=2)
        parsed = StorySnapshot.from_json(json_str)
        self.assertEqual(snapshot, parsed)

    def test_save_and_load_restoration(self) -> None:
        vm = StoryVM(self.graph)
        vm.set_variable("karma", 10)

        # Step 1: enter scene_1
        vm.step()
        # Step 2: Beat 1
        vm.step()
        # Step 3: Beat 2 (Alice)
        evt = vm.step()
        assert isinstance(evt, DialogueEvent)
        self.assertEqual(evt.speaker, "Alice")

        # Save mid-scene
        saved_snapshot = vm.save()
        self.assertEqual(saved_snapshot.current_scene, "scene_1")
        self.assertEqual(saved_snapshot.variables["karma"], 10)

        # Continue playing further
        vm.set_variable("karma", -5)
        vm.step()  # Bob
        vm.step()  # Jump to scene_2
        vm.step()  # Enter scene_2

        self.assertEqual(vm.current_scene_id, "scene_2")
        self.assertEqual(vm.get_variable("karma"), -5)

        # Now restore saved state
        vm.load(saved_snapshot)
        self.assertEqual(vm.current_scene_id, "scene_1")
        self.assertEqual(vm.get_variable("karma"), 10)

        # Next beat should resume right at Bob's beat!
        next_evt = vm.step()
        assert isinstance(next_evt, DialogueEvent)
        self.assertEqual(next_evt.speaker, "Bob")

    def test_load_invalid_scene_raises_error(self) -> None:
        vm = StoryVM(self.graph)
        bad_snapshot = StorySnapshot(
            current_scene="non_existent_scene",
            beat_index=0,
            call_stack=(),
            variables={},
            visited_scenes=(),
        )

        with self.assertRaises(StoryRuntimeError):
            vm.load(bad_snapshot)

    def test_save_at_choice_load_preserves_choice(self) -> None:
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
        from eager_runtime import ChoicePromptEvent
        self.assertIsInstance(choice_evt, ChoicePromptEvent)
        self.assertIsNotNone(vm.pending_choice)

        # Save while choice is pending
        snap = vm.save()
        self.assertIsNotNone(snap.pending_choice_beat)

        # Create new VM or load snapshot
        vm2 = StoryVM(graph)
        vm2.load(snap)
        self.assertIsNotNone(vm2.pending_choice)
        step_evt = vm2.step()
        self.assertIsInstance(step_evt, ChoicePromptEvent)
        self.assertEqual(len(step_evt.options), 2)

        # Can choose after load!
        vm2.choose(0)
        self.assertEqual(vm2.current_scene_id, "opt_a")

    def test_save_after_jump_exit_load_preserves_transition(self) -> None:
        vm = StoryVM(self.graph)
        vm.step()  # Enter scene_1
        vm.step()  # Narrator
        vm.step()  # Alice
        vm.step()  # Bob
        exit_evt = vm.step()  # Jump to scene_2 (SceneExitEvent)
        from eager_runtime import SceneExitEvent
        self.assertIsInstance(exit_evt, SceneExitEvent)

        # Save right after jump beat was executed
        snap = vm.save()
        self.assertEqual(snap.next_transition_target, "scene_2")

        vm2 = StoryVM(self.graph)
        vm2.load(snap)
        enter_evt = vm2.step()
        from eager_runtime import SceneEnterEvent
        self.assertIsInstance(enter_evt, SceneEnterEvent)
        self.assertEqual(enter_evt.scene_id, "scene_2")

    def test_prng_state_restoration_mersenne_twister(self) -> None:
        vm1 = StoryVM(self.graph)
        # Consume some random numbers to advance the MT state
        _ = [vm1._rng.random() for _ in range(10)]

        # Save snapshot and round-trip through JSON (which converts inner tuples to lists)
        snap = vm1.save()
        self.assertIsNotNone(snap.rng_state)
        json_str = snap.to_json()
        restored_snap = StorySnapshot.from_json(json_str)

        # Confirm that JSON deserialized the MT state vector as a list
        self.assertIsInstance(restored_snap.rng_state[1], list)

        # Generate expected future random stream from original VM
        expected_next = [vm1._rng.random() for _ in range(10)]

        # Load snapshot into new VM - should recursively restore nested tuples for setstate
        vm2 = StoryVM(self.graph)
        vm2.load(restored_snap)

        # Verify new VM generates exactly identical numbers in sequence
        actual_next = [vm2._rng.random() for _ in range(10)]
        self.assertEqual(expected_next, actual_next)

    def test_load_pending_choice_and_input_beat_id(self) -> None:
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
        from eager_runtime import ChoicePromptEvent, InputPromptEvent
        self.assertIsInstance(choice_evt, ChoicePromptEvent)
        orig_choice_beat_id = choice_evt.beat_id

        # Save while choice is pending and restore into new VM
        snap = vm.save()
        vm2 = StoryVM(graph)
        vm2.load(snap)
        self.assertIsNotNone(vm2.pending_choice)
        self.assertEqual(vm2.pending_choice.beat_id, orig_choice_beat_id)

        # Proceed with choice
        vm.choose(0)
        vm.step()  # SceneEnter Scene A
        vm.step()  # Alice: Picked A
        input_evt = vm.step()  # InputPromptEvent
        self.assertIsInstance(input_evt, InputPromptEvent)
        orig_input_beat_id = input_evt.beat_id
        self.assertIsNotNone(orig_input_beat_id)

        # Save while input is pending and restore into new VM
        snap_input = vm.save()
        vm3 = StoryVM(graph)
        vm3.load(snap_input)
        self.assertIsNotNone(vm3.pending_input)
        self.assertEqual(vm3.pending_input.beat_id, orig_input_beat_id)
        self.assertEqual(vm3.pending_input.prompt, input_evt.prompt)
        self.assertEqual(vm3.pending_input.var_name, input_evt.var_name)


