"""Unit tests for SceneGraph model, transformation, and CLI graph command."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from eager_script import (
    ParsedChoiceSet,
    ParsedHook,
    ParsedNarration,
    ParsedReturn,
    parse_graph,
    parse_iter,
    to_graph,
)

SAMPLE_SCRIPT = """
## Courtyard --- courtyard

Narrator: Rain pours down against the stone pavement.
- You pull your cloak tighter around your shoulders.

Guard: Who goes there? State your business.

? Announce yourself peacefully (peaceful_entry)
? Draw your sword (combat_start)

## Peaceful Entry --- peaceful_entry
~ play_chime
Guard: Welcome, traveler. Enter freely.
> finish

## Combat Start --- combat_start
Guard (angry): You will regret this!
>> trigger_combat
> finish

## Finished --- finish
Narrator: The gates close behind you.
"""

SUBROUTINE_SCRIPT = """
## Main --- main
Hero: We need to inspect this artifact.
>> inspect_item
> the_end

## Inspect Item --- inspect_item
Narrator: A shimmering ancient relic.
~ glow_effect
<<

## The End --- the_end
Narrator: Done.
"""


class TestSceneGraphModel(unittest.TestCase):
    def test_basic_graph_construction(self):
        graph = parse_graph(SAMPLE_SCRIPT)

        self.assertEqual(graph.entry, "courtyard")
        self.assertEqual(len(graph.nodes), 4)
        self.assertIn("courtyard", graph.nodes)
        self.assertIn("peaceful_entry", graph.nodes)
        self.assertIn("combat_start", graph.nodes)
        self.assertIn("finish", graph.nodes)

        # Check node attributes
        cy = graph.nodes["courtyard"]
        self.assertEqual(cy.id, "courtyard")
        self.assertEqual(cy.display_name, "Courtyard")
        self.assertEqual(cy.line_number, 2)
        self.assertEqual(cy.speakers, ("Narrator", "Guard"))
        self.assertEqual(cy.hooks, ())
        self.assertTrue(len(cy.body) > 0)

        pe = graph.nodes["peaceful_entry"]
        self.assertEqual(pe.speakers, ("Guard",))
        self.assertEqual(pe.hooks, ("play_chime",))

        # Check edges
        self.assertEqual(len(graph.edges), 5)

        choice_edges = [e for e in graph.edges if e.kind == "choice"]
        self.assertEqual(len(choice_edges), 2)
        self.assertEqual(choice_edges[0].source, "courtyard")
        self.assertEqual(choice_edges[0].target, "peaceful_entry")
        self.assertEqual(choice_edges[0].label, "Announce yourself peacefully")

        self.assertEqual(choice_edges[1].source, "courtyard")
        self.assertEqual(choice_edges[1].target, "combat_start")
        self.assertEqual(choice_edges[1].label, "Draw your sword")

        call_edges = [e for e in graph.edges if e.kind == "call"]
        self.assertEqual(len(call_edges), 1)
        self.assertEqual(call_edges[0].source, "combat_start")
        self.assertEqual(call_edges[0].target, "trigger_combat")

        jump_edges = [e for e in graph.edges if e.kind == "jump"]
        self.assertEqual(len(jump_edges), 2)

    def test_preamble(self):
        script_with_preamble = """
# Script setup
Once upon a time, before the story began...
~ init_system

## Chapter 1 --- ch1
Alice: Hello!
"""
        graph = parse_graph(script_with_preamble)
        self.assertEqual(graph.entry, "ch1")
        self.assertEqual(len(graph.preamble), 2)
        self.assertIsInstance(graph.preamble[0], ParsedNarration)
        self.assertIsInstance(graph.preamble[1], ParsedHook)

    def test_successors_and_predecessors(self):
        graph = parse_graph(SAMPLE_SCRIPT)

        self.assertEqual(graph.successors("courtyard"), ["peaceful_entry", "combat_start"])
        self.assertEqual(graph.successors("peaceful_entry"), ["finish"])
        self.assertEqual(graph.successors("finish"), [])

        self.assertEqual(graph.predecessors("finish"), ["peaceful_entry", "combat_start"])
        self.assertEqual(graph.predecessors("courtyard"), [])

    def test_reachability(self):
        script = """
## Start --- start
> branch_a

## Branch A --- branch_a
> finish

## Orphan Scene --- orphan
> finish

## Finish --- finish
Narrator: Done.
"""
        graph = parse_graph(script)
        self.assertEqual(graph.entry, "start")

        self.assertTrue(graph.is_reachable("start"))
        self.assertTrue(graph.is_reachable("branch_a"))
        self.assertTrue(graph.is_reachable("finish"))
        self.assertFalse(graph.is_reachable("orphan"))

        self.assertEqual(graph.reachable_from("start"), {"start", "branch_a", "finish"})
        self.assertEqual(graph.reachable_from("orphan"), {"orphan", "finish"})
        self.assertEqual(graph.reachable_from("non_existent"), set())

    def test_dead_ends_and_terminals(self):
        graph = parse_graph(SAMPLE_SCRIPT)
        self.assertEqual(graph.dead_ends(), ["finish"])
        self.assertEqual(graph.terminal_scenes(), ["finish"])

        # In a script with subroutines
        sub_graph = parse_graph(SUBROUTINE_SCRIPT)
        # inspect_item has no outgoing jump/choice, but ends with << (return)
        self.assertEqual(sub_graph.dead_ends(), ["inspect_item", "the_end"])
        # inspect_item is a subroutine returning, so terminal_scenes should only be the_end
        self.assertEqual(sub_graph.terminal_scenes(), ["the_end"])

    def test_hubs_and_branching_points(self):
        graph = parse_graph(SAMPLE_SCRIPT)
        # finish has in-degree 2
        self.assertEqual(graph.hubs(threshold=2), ["finish"])
        self.assertEqual(graph.hubs(threshold=3), [])

        # courtyard has 2 successors; combat_start has 2 successors (trigger_combat, finish)
        self.assertEqual(graph.branching_points(), ["courtyard", "combat_start"])

    def test_to_dict_and_to_json(self):
        graph = parse_graph(SAMPLE_SCRIPT)

        # With body included
        d_full = graph.to_dict(include_body=True)
        self.assertEqual(d_full["entry"], "courtyard")
        self.assertIn("nodes", d_full)
        self.assertIn("edges", d_full)
        self.assertIn("preamble", d_full)
        self.assertIn("body", d_full["nodes"]["courtyard"])
        self.assertTrue(len(d_full["nodes"]["courtyard"]["body"]) > 0)

        json_str = graph.to_json(include_body=True, indent=2)
        parsed_json = json.loads(json_str)
        self.assertEqual(parsed_json["entry"], "courtyard")

        # Without body included
        d_slim = graph.to_dict(include_body=False)
        self.assertNotIn("body", d_slim["nodes"]["courtyard"])
        self.assertEqual(d_slim["preamble"], [])

    def test_to_dot(self):
        graph = parse_graph(SAMPLE_SCRIPT)
        dot = graph.to_dot()
        self.assertIn("digraph SceneGraph {", dot)
        self.assertIn('"courtyard"', dot)
        self.assertIn('"peaceful_entry"', dot)
        self.assertIn('label="Announce yourself peacefully"', dot)
        self.assertIn('style="dashed"', dot)  # call edge
        self.assertTrue(dot.endswith("}"))

    def test_to_mermaid(self):
        graph = parse_graph(SAMPLE_SCRIPT)
        mermaid = graph.to_mermaid()
        self.assertIn("flowchart TD", mermaid)
        self.assertIn('courtyard["Courtyard"]', mermaid)
        self.assertIn("courtyard -->|Announce yourself peacefully| peaceful_entry", mermaid)
        self.assertIn("combat_start -.->|call| trigger_combat", mermaid)
        self.assertIn("peaceful_entry --> finish", mermaid)

    def test_empty_and_preamble_only_graph(self):
        empty_graph = to_graph([])
        self.assertIsNone(empty_graph.entry)
        self.assertEqual(empty_graph.nodes, {})
        self.assertEqual(empty_graph.edges, ())
        self.assertEqual(empty_graph.preamble, ())

        preamble_graph = parse_graph("Narrator: Just some narration without scenes.")
        self.assertIsNone(preamble_graph.entry)
        self.assertEqual(preamble_graph.nodes, {})
        self.assertEqual(preamble_graph.edges, ())
        self.assertEqual(len(preamble_graph.preamble), 1)

    def test_to_graph_from_iterator(self):
        graph_from_list = parse_graph(SAMPLE_SCRIPT)
        graph_from_iter = to_graph(parse_iter(SAMPLE_SCRIPT))
        self.assertEqual(graph_from_list, graph_from_iter)


class TestGraphCLI(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, "-m", "eager_script", *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_graph_json_stdout(self):
        with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
            f.write(SAMPLE_SCRIPT)
            f_path = f.name

        try:
            res = self.run_cli("graph", f_path)
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertEqual(data["entry"], "courtyard")
            self.assertIn("nodes", data)
            self.assertIn("edges", data)
            self.assertIn("body", data["nodes"]["courtyard"])
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_cli_graph_no_body(self):
        with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
            f.write(SAMPLE_SCRIPT)
            f_path = f.name

        try:
            res = self.run_cli("graph", f_path, "--no-body")
            self.assertEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertNotIn("body", data["nodes"]["courtyard"])
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_cli_graph_dot_and_mermaid(self):
        with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
            f.write(SAMPLE_SCRIPT)
            f_path = f.name

        try:
            # DOT format
            res_dot = self.run_cli("graph", f_path, "--format", "dot")
            self.assertEqual(res_dot.returncode, 0)
            self.assertIn("digraph SceneGraph {", res_dot.stdout)

            # Mermaid format
            res_mmd = self.run_cli("graph", f_path, "--format", "mermaid")
            self.assertEqual(res_mmd.returncode, 0)
            self.assertIn("flowchart TD", res_mmd.stdout)
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_cli_graph_output_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".es", delete=False) as f:
            f.write(SAMPLE_SCRIPT)
            src_path = f.name

        out_path = Path(src_path + ".out.json")
        try:
            res = self.run_cli("graph", src_path, "-o", str(out_path))
            self.assertEqual(res.returncode, 0)
            self.assertTrue(out_path.exists())
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(data["entry"], "courtyard")
        finally:
            Path(src_path).unlink(missing_ok=True)
            out_path.unlink(missing_ok=True)

    def test_cli_graph_file_not_found(self):
        res = self.run_cli("graph", "non_existent_file_12345.es")
        self.assertEqual(res.returncode, 1)
        self.assertIn("File not found", res.stderr)


INLINE_CHOICE_GRAPH_SCRIPT = """\
## Tavern --- tavern
Bartender: What will it be?
? Order an ale
    $ gold -= 3
    Bartender: Coming right up.
? Ask for water
    Bartender: Suit yourself.
Narrator: You settle by the fire.
> nightfall

## Nightfall --- nightfall
Narrator: The night deepens.
"""


class TestAnonymousScenes(unittest.TestCase):
    """Test suite for anonymous scene lowering of inline choice blocks."""

    def setUp(self) -> None:
        self.graph = parse_graph(INLINE_CHOICE_GRAPH_SCRIPT)

    def test_lowered_nodes_and_edges(self) -> None:
        self.assertEqual(self.graph.anonymous_scenes(), ["tavern__anon_3", "tavern__anon_6"])

        anon = self.graph.nodes["tavern__anon_3"]
        self.assertTrue(anon.is_anonymous)
        self.assertEqual(anon.display_name, "Order an ale")
        self.assertEqual(anon.speakers, ("Bartender",))
        self.assertIsInstance(anon.body[-1], ParsedReturn)

        # Option targets are rewritten to the anonymous scene ids.
        choice_set = next(item for item in self.graph.nodes["tavern"].body if isinstance(item, ParsedChoiceSet))
        self.assertEqual(choice_set.options[0].target, "tavern__anon_3")
        self.assertEqual(choice_set.options[1].target, "tavern__anon_6")

        choice_edges = [e for e in self.graph.edges if e.kind == "choice"]
        self.assertEqual(len(choice_edges), 2)
        self.assertEqual(choice_edges[0].target, "tavern__anon_3")
        self.assertEqual(choice_edges[0].label, "Order an ale")

    def test_successors_and_terminals(self) -> None:
        self.assertIn("tavern__anon_3", self.graph.successors("tavern"))
        # Anonymous scenes return to the menu, so they are not terminal scenes or dead ends.
        self.assertNotIn("tavern__anon_3", self.graph.terminal_scenes())
        self.assertNotIn("tavern__anon_3", self.graph.dead_ends())
        self.assertIn("nightfall", self.graph.terminal_scenes())

    def test_anonymous_jump_inside_block_leaves_scene(self) -> None:
        script = """\
## A --- a
? Go
    > b

## B --- b
Narrator: done
"""
        graph = parse_graph(script)
        anon_id = graph.anonymous_scenes()[0]
        jump_edges = [e for e in graph.edges if e.source == anon_id and e.kind == "jump"]
        self.assertEqual(len(jump_edges), 1)
        self.assertEqual(jump_edges[0].target, "b")

    def test_nested_inline_blocks_lower_recursively(self) -> None:
        script = """\
## Outer --- outer
? Reaction
    Alice: first
    ? Nested
        Bob: deep
    Alice: back
"""
        graph = parse_graph(script)
        self.assertEqual(
            sorted(graph.anonymous_scenes()), ["outer__anon_2", "outer__anon_2__anon_4"]
        )
        self.assertTrue(graph.nodes["outer__anon_2__anon_4"].is_anonymous)

    def test_empty_graph_unaffected(self) -> None:
        graph = to_graph([])
        self.assertEqual(graph.anonymous_scenes(), [])

    def test_find_path_linear_and_branching(self) -> None:
        graph = parse_graph(SAMPLE_SCRIPT)
        # Entry to finish via peaceful_entry
        path = graph.find_path("courtyard", "finish")
        self.assertIsNotNone(path)
        assert path is not None
        self.assertEqual(path[0], "courtyard")
        self.assertEqual(path[-1], "finish")
        self.assertTrue(path == ["courtyard", "peaceful_entry", "finish"] or path == ["courtyard", "combat_start", "finish"])

        # Direct path between adjacent
        self.assertEqual(graph.find_path("peaceful_entry", "finish"), ["peaceful_entry", "finish"])
        # Same node
        self.assertEqual(graph.find_path("courtyard", "courtyard"), ["courtyard"])
        # Non-existent target or backwards path
        self.assertIsNone(graph.find_path("finish", "courtyard"))
        self.assertIsNone(graph.find_path("courtyard", "nonexistent"))

    def test_find_root_ancestor(self) -> None:
        script = """
## Intro --- intro
Narrator: Hello.

## Sub A --- sub_a
Narrator: Branch A.
> sub_b

## Sub B --- sub_b
Narrator: Branch B.
"""
        graph = parse_graph(script)
        # sub_b's root ancestor should be sub_a
        self.assertEqual(graph.find_root_ancestor("sub_b"), "sub_a")
        # intro has no predecessors
        self.assertIsNone(graph.find_root_ancestor("intro"))



if __name__ == "__main__":
    unittest.main()
