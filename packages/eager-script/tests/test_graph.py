"""Unit tests for SceneGraph model and transformation."""

import json

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


def test_basic_graph_construction() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)

    assert graph.entry == "courtyard"
    assert len(graph.nodes) == 4
    assert "courtyard" in graph.nodes
    assert "peaceful_entry" in graph.nodes
    assert "combat_start" in graph.nodes
    assert "finish" in graph.nodes

    # Check node attributes
    cy = graph.nodes["courtyard"]
    assert cy.id == "courtyard"
    assert cy.display_name == "Courtyard"
    assert cy.line_number == 2
    assert cy.speakers == ("Narrator", "Guard")
    assert cy.hooks == ()
    assert len(cy.body) > 0

    pe = graph.nodes["peaceful_entry"]
    assert pe.speakers == ("Guard",)
    assert pe.hooks == ("play_chime",)

    # Check edges
    assert len(graph.edges) == 5

    choice_edges = [e for e in graph.edges if e.kind == "choice"]
    assert len(choice_edges) == 2
    assert choice_edges[0].source == "courtyard"
    assert choice_edges[0].target == "peaceful_entry"
    assert choice_edges[0].label == "Announce yourself peacefully"

    assert choice_edges[1].source == "courtyard"
    assert choice_edges[1].target == "combat_start"
    assert choice_edges[1].label == "Draw your sword"

    call_edges = [e for e in graph.edges if e.kind == "call"]
    assert len(call_edges) == 1
    assert call_edges[0].source == "combat_start"
    assert call_edges[0].target == "trigger_combat"

    jump_edges = [e for e in graph.edges if e.kind == "jump"]
    assert len(jump_edges) == 2


def test_preamble() -> None:
    script_with_preamble = """
# Script setup
Once upon a time, before the story began...
~ init_system

## Chapter 1 --- ch1
Alice: Hello!
"""
    graph = parse_graph(script_with_preamble)
    assert graph.entry == "ch1"
    assert len(graph.preamble) == 2
    assert isinstance(graph.preamble[0], ParsedNarration)
    assert isinstance(graph.preamble[1], ParsedHook)


def test_successors_and_predecessors() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)

    assert graph.successors("courtyard") == ["peaceful_entry", "combat_start"]
    assert graph.successors("peaceful_entry") == ["finish"]
    assert graph.successors("finish") == []

    assert graph.predecessors("finish") == ["peaceful_entry", "combat_start"]
    assert graph.predecessors("courtyard") == []


def test_reachability() -> None:
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
    assert graph.entry == "start"

    assert graph.is_reachable("start")
    assert graph.is_reachable("branch_a")
    assert graph.is_reachable("finish")
    assert not graph.is_reachable("orphan")

    assert graph.reachable_from("start") == {"start", "branch_a", "finish"}
    assert graph.reachable_from("orphan") == {"orphan", "finish"}
    assert graph.reachable_from("non_existent") == set()


def test_dead_ends_and_terminals() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)
    assert graph.dead_ends() == ["finish"]
    assert graph.terminal_scenes() == ["finish"]

    # In a script with subroutines
    sub_graph = parse_graph(SUBROUTINE_SCRIPT)
    # inspect_item has no outgoing jump/choice, but ends with << (return)
    assert sub_graph.dead_ends() == ["inspect_item", "the_end"]
    # inspect_item is a subroutine returning, so terminal_scenes should only be the_end
    assert sub_graph.terminal_scenes() == ["the_end"]


def test_hubs_and_branching_points() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)
    # finish has in-degree 2
    assert graph.hubs(threshold=2) == ["finish"]
    assert graph.hubs(threshold=3) == []

    # courtyard has 2 successors; combat_start has 2 successors (trigger_combat, finish)
    assert graph.branching_points() == ["courtyard", "combat_start"]


def test_to_dict_and_to_json() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)

    # With body included
    d_full = graph.to_dict(include_body=True)
    assert d_full["entry"] == "courtyard"
    assert "nodes" in d_full
    assert "edges" in d_full
    assert "preamble" in d_full
    assert "body" in d_full["nodes"]["courtyard"]
    assert len(d_full["nodes"]["courtyard"]["body"]) > 0

    json_str = graph.to_json(include_body=True, indent=2)
    parsed_json = json.loads(json_str)
    assert parsed_json["entry"] == "courtyard"

    # Without body included
    d_slim = graph.to_dict(include_body=False)
    assert "body" not in d_slim["nodes"]["courtyard"]
    assert d_slim["preamble"] == []


def test_to_dot() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)
    dot = graph.to_dot()
    assert "digraph SceneGraph {" in dot
    assert '"courtyard"' in dot
    assert '"peaceful_entry"' in dot
    assert 'label="Announce yourself peacefully"' in dot
    assert 'style="dashed"' in dot  # call edge
    assert dot.endswith("}")


def test_to_mermaid() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)
    mermaid = graph.to_mermaid()
    assert "flowchart TD" in mermaid
    assert 'courtyard["Courtyard"]' in mermaid
    assert "courtyard -->|Announce yourself peacefully| peaceful_entry" in mermaid
    assert "combat_start -.->|call| trigger_combat" in mermaid
    assert "peaceful_entry --> finish" in mermaid


def test_empty_and_preamble_only_graph() -> None:
    empty_graph = to_graph([])
    assert empty_graph.entry is None
    assert empty_graph.nodes == {}
    assert empty_graph.edges == ()
    assert empty_graph.preamble == ()

    preamble_graph = parse_graph("Narrator: Just some narration without scenes.")
    assert preamble_graph.entry is None
    assert preamble_graph.nodes == {}
    assert preamble_graph.edges == ()
    assert len(preamble_graph.preamble) == 1


def test_to_graph_from_iterator() -> None:
    graph_from_list = parse_graph(SAMPLE_SCRIPT)
    graph_from_iter = to_graph(parse_iter(SAMPLE_SCRIPT))
    assert graph_from_list == graph_from_iter


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


def test_lowered_nodes_and_edges() -> None:
    graph = parse_graph(INLINE_CHOICE_GRAPH_SCRIPT)
    assert graph.anonymous_scenes() == ["tavern__anon_3", "tavern__anon_6"]

    anon = graph.nodes["tavern__anon_3"]
    assert anon.is_anonymous
    assert anon.display_name == "Order an ale"
    assert anon.speakers == ("Bartender",)
    assert isinstance(anon.body[-1], ParsedReturn)

    # Option targets are rewritten to the anonymous scene ids.
    choice_set = next(item for item in graph.nodes["tavern"].body if isinstance(item, ParsedChoiceSet))
    assert choice_set.options[0].target == "tavern__anon_3"
    assert choice_set.options[1].target == "tavern__anon_6"

    choice_edges = [e for e in graph.edges if e.kind == "choice"]
    assert len(choice_edges) == 2
    assert choice_edges[0].target == "tavern__anon_3"
    assert choice_edges[0].label == "Order an ale"


def test_successors_and_terminals() -> None:
    graph = parse_graph(INLINE_CHOICE_GRAPH_SCRIPT)
    assert "tavern__anon_3" in graph.successors("tavern")
    # Anonymous scenes return to the menu, so they are not terminal scenes or dead ends.
    assert "tavern__anon_3" not in graph.terminal_scenes()
    assert "tavern__anon_3" not in graph.dead_ends()
    assert "nightfall" in graph.terminal_scenes()


def test_anonymous_jump_inside_block_leaves_scene() -> None:
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
    assert len(jump_edges) == 1
    assert jump_edges[0].target == "b"


def test_nested_inline_blocks_lower_recursively() -> None:
    script = """\
## Outer --- outer
? Reaction
    Alice: first
    ? Nested
        Bob: deep
    Alice: back
"""
    graph = parse_graph(script)
    assert sorted(graph.anonymous_scenes()) == ["outer__anon_2", "outer__anon_2__anon_4"]
    assert graph.nodes["outer__anon_2__anon_4"].is_anonymous


def test_empty_graph_unaffected() -> None:
    graph = to_graph([])
    assert graph.anonymous_scenes() == []


def test_find_path_linear_and_branching() -> None:
    graph = parse_graph(SAMPLE_SCRIPT)
    # Entry to finish via peaceful_entry
    path = graph.find_path("courtyard", "finish")
    assert path is not None
    assert path[0] == "courtyard"
    assert path[-1] == "finish"
    assert path == ["courtyard", "peaceful_entry", "finish"] or path == ["courtyard", "combat_start", "finish"]

    # Direct path between adjacent
    assert graph.find_path("peaceful_entry", "finish") == ["peaceful_entry", "finish"]
    # Same node
    assert graph.find_path("courtyard", "courtyard") == ["courtyard"]
    # Non-existent target or backwards path
    assert graph.find_path("finish", "courtyard") is None
    assert graph.find_path("courtyard", "nonexistent") is None


def test_find_root_ancestor() -> None:
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
    assert graph.find_root_ancestor("sub_b") == "sub_a"
    # intro has no predecessors
    assert graph.find_root_ancestor("intro") is None


def test_graph_elif_else_cumulative_condition_accumulation() -> None:
    script = """
## Main --- main
@if a
    > scene_a
@elif b
    > scene_b
@elif c
    > scene_c
@else
    > scene_d
@end
"""
    graph = parse_graph(script)
    edges = {e.target: e.condition for e in graph.edges if e.kind == "jump"}

    assert edges["scene_a"] == "a"
    assert edges["scene_b"] == "(not (a)) and (b)"
    assert edges["scene_c"] == "(not (a)) and (not (b)) and (c)"
    assert edges["scene_d"] == "(not (a)) and (not (b)) and (not (c))"
