from eager_script import ParsedCharacter, parse_graph, parse_iter


def test_character_quoted_attributes_with_spaces():
    script = '@character hero "Hero" title="The Great Magician" color="#ff0000" role="Protagonist and Leader"'
    items = list(parse_iter(script))
    assert len(items) == 1
    char = items[0]
    assert isinstance(char, ParsedCharacter)
    assert char.id == "hero"
    assert char.name == "Hero"
    attr_dict = dict(char.attrs)
    assert attr_dict.get("title") == "The Great Magician"
    assert attr_dict.get("color") == "#ff0000"
    assert attr_dict.get("role") == "Protagonist and Leader"


def test_graph_elif_else_cumulative_condition_accumulation():
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
