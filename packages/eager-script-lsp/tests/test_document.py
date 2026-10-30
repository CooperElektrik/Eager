"""Unit tests for resilient document scanner and column span tracking."""

from __future__ import annotations

from eager_script_lsp.document import ScriptDocument


def test_scan_valid_document():
    text = """## Prologue --- prologue
Narrator: Hello world!
~ bg classroom_day with crossfade duration=1.0
~ show hoshiko smile at center
Hoshiko (smile): Are you ready, [player_name]?
? Yes, let's go! (journey_start) if visited('prologue')
> journey_start
"""
    doc = ScriptDocument("file:///test.es", text)
    assert len(doc.syntax_errors) == 0
    assert len(doc.ast_items) > 0
    assert doc.scene_graph is not None
    assert "prologue" in doc.scene_graph.nodes

    # Check label spans
    tok = doc.get_token_at(0, 5)
    assert tok is not None
    assert tok.kind == "label_title"
    assert tok.value == "Prologue"

    label_id_tok = doc.get_token_at(0, 18)
    assert label_id_tok is not None
    assert label_id_tok.kind == "label_id"
    assert label_id_tok.value == "prologue"

    # Check hook spans
    hook_name_tok = doc.get_token_at(2, 3)
    assert hook_name_tok is not None
    assert hook_name_tok.kind == "hook_name"
    assert hook_name_tok.value == "bg"

    # Check speaker and emotion spans
    speaker_tok = doc.get_token_at(4, 2)
    assert speaker_tok is not None
    assert speaker_tok.kind == "speaker"
    assert speaker_tok.value == "Hoshiko"

    emotion_tok = doc.get_token_at(4, 10)
    assert emotion_tok is not None
    assert emotion_tok.kind == "emotion"
    assert emotion_tok.value == "smile"

    # Check variable interpolation
    var_tok = doc.get_token_at(4, 35)
    assert var_tok is not None
    assert var_tok.kind == "variable"
    assert var_tok.value == "player_name"

    # Check choice target
    target_tok = doc.get_token_at(5, 20)
    assert target_tok is not None
    assert target_tok.kind == "choice_target"
    assert target_tok.value == "journey_start"


def test_scan_resilient_to_incomplete_lines():
    text = """## Prologue --- prologue
Narrator: Hello
> 
Hoshiko: Mid typing choice below
? 
@if 
Narrator: After errors
"""
    doc = ScriptDocument("file:///broken.es", text)
    # Should catch errors on incomplete lines
    error_lines = [err.line for err in doc.syntax_errors]
    assert 2 in error_lines  # '> '
    assert 4 in error_lines  # '? '
    assert 5 in error_lines  # '@if '

    # Despite errors, the file still extracts AST items for other lines
    assert len(doc.ast_items) > 0
    assert any(getattr(item, "text", "") == "Hello" for item in doc.ast_items)
    assert any(getattr(item, "text", "") == "After errors" for item in doc.ast_items)


def test_scan_inline_choice_blocks():
    text = """## Decision --- decision
? Option A
    Narrator: You chose A
    > scene_a
? Option B
    Narrator: You chose B
    > scene_b
"""
    doc = ScriptDocument("file:///inline.es", text)
    assert len(doc.syntax_errors) == 0
    assert len(doc.ast_items) > 0


def test_implicit_label_slug():
    text = """## The Ancient Forest
Narrator: Birds sing in the trees.
"""
    doc = ScriptDocument("file:///implicit.es", text)
    assert len(doc.syntax_errors) == 0
    assert "the_ancient_forest" in doc.scene_spans
    tok = doc.scene_spans["the_ancient_forest"]
    assert tok.value == "the_ancient_forest"
    assert tok.metadata["implicit"] is True
    assert tok.metadata["display_name"] == "The Ancient Forest"


def test_expression_string_literal_not_parsed_as_variable():
    text = """## Start --- start
@if player_class == "warrior" and visited('forest_path')
Narrator: Welcome warrior!
@end
"""
    doc = ScriptDocument("file:///expr_test.es", text)
    var_reads = [occ.name for occ in doc.occurrences if occ.kind == "variable_read"]
    assert "player_class" in var_reads
    assert "warrior" not in var_reads
    assert "forest_path" not in var_reads


def test_inline_comment_inside_quotes():
    text = """## Start --- start
Narrator: "Hello #world" # Blue comment
"""
    doc = ScriptDocument("file:///comment_test.es", text)
    comments = [s.value for s in doc.spans if s.kind == "comment"]
    assert len(comments) == 1
    assert "# Blue comment" in comments[0]
    dialogue_spans = [s.value for s in doc.spans if s.kind == "dialogue_text"]
    assert any("#world" in d for d in dialogue_spans)


def test_exact_regex_offsets_substring_edge_cases():
    text = """@character a "a" color=#112233
$ x = x == 1
"""
    doc = ScriptDocument("file:///substring_test.es", text)
    # Check variable 'x' on line 1
    var_mut = next(occ for occ in doc.occurrences if occ.kind == "variable_mutation")
    assert var_mut.span.start_col == 2
    assert var_mut.span.end_col == 3

    # Check color on line 0
    color_span = next(s for s in doc.spans if s.kind == "color_literal")
    assert color_span.start_col == 23
    assert color_span.end_col == 30


def test_dotted_persistent_variable_in_expression():
    text = """$ persistent.ending_a = true
@if persistent.ending_a
    Alice: Unlocked!
@end
"""
    doc = ScriptDocument("file:///persistent_test.es", text)
    # Mutation on line 0
    mutations = [occ for occ in doc.occurrences if occ.kind == "variable_mutation"]
    assert len(mutations) == 1
    assert mutations[0].name == "persistent.ending_a"

    # Read on line 1 inside @if
    reads = [occ for occ in doc.occurrences if occ.kind == "variable_read"]
    assert any(occ.name == "persistent.ending_a" for occ in reads)


def test_choice_text_scans_inline_tags_and_variables():
    text = """## Start --- start
? Pay [gold] coins {color=#ffd700} (buy) if gold >= 10
"""
    doc = ScriptDocument("file:///choice_tags.es", text)
    reads = [occ for occ in doc.occurrences if occ.kind == "variable_read"]
    assert any(occ.name == "gold" for occ in reads)
    colors = [s for s in doc.spans if s.kind == "color_literal"]
    assert any(s.value == "#ffd700" for s in colors)


def test_document_get_beat_occurrence_multiple_identical_beats():
    text = """## Start --- start
Alice: Hello!
Alice: Other text
Alice: Hello!
"""
    doc = ScriptDocument("file:///dup_beats.es", text)
    # Line 1 is first 'Alice: Hello!' -> occurrence 1
    occ1 = doc.get_beat_occurrence(1)
    assert occ1 == 1

    # Line 3 is second 'Alice: Hello!' -> occurrence 2
    occ2 = doc.get_beat_occurrence(3)
    assert occ2 == 2


def test_include_directive_syntax_and_masking():
    text = '@include "other.es"\n## Start --- start\nNarrator: Hi\n'
    doc = ScriptDocument("file:///main.es", text)
    assert len(doc.syntax_errors) == 0
    inc_spans = [s for s in doc.spans if s.kind == "include_path"]
    assert len(inc_spans) == 1
    assert inc_spans[0].value == "other.es"

    bad_text = "@include\n## Start --- start\n"
    bad_doc = ScriptDocument("file:///bad.es", bad_text)
    assert len(bad_doc.syntax_errors) == 1
    assert "Invalid @include syntax" in bad_doc.syntax_errors[0].message


def test_inline_choice_ast_lookup_and_scene_resolution():
    text = """## Scene 1 --- s1
? Choice A
    Alice: Inside choice!
"""
    doc = ScriptDocument("file:///choice.es", text)
    item = doc.get_item_at_line(2)
    assert item is not None
    assert getattr(item, "speaker", None) == "Alice"
    scene = doc.get_scene_at_line(2)
    assert scene == "s1__anon_2"


def test_scan_append_and_fresh_box_variants():
    text = """## Start --- start
-text
-\ttabbed
/
/fresh
"""
    doc = ScriptDocument("file:///boxes.es", text)
    assert len(doc.syntax_errors) == 0
    appends = [s for s in doc.spans if s.kind == "append_marker"]
    assert len(appends) == 2
    fresh = [s for s in doc.spans if s.kind == "fresh_box_marker"]
    assert len(fresh) == 2


