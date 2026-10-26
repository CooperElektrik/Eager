"""Adversarial stress harness for eager-script-lsp features, edge cases, and resilience (M4 Challenger 1).

Covers:
1. Completion engine:
   - Edge and boundary positions: empty string, out-of-bounds columns, negative/large coords.
   - Whitespace lines: spaces, tabs, mixed whitespace fallback to narrator/character.
   - Partially typed jumps, calls, multi-word scene slugs, and non-matching filters.
   - Choices: inline targets, partial scene targets, unknown targets, conditional choices.
   - Directives: snippet triggers, prefix filtering, and prevention of keyword shadowing in expressions.
   - Expressions and variables: variables with underscores, digits, dots, built-in DSL functions.
   - Engine hooks: hook triggers, command arguments, asset listings, and unknown character resilience.
2. Hover and navigation:
   - Out-of-bounds coordinates (line=999999, character=999999, max uinteger).
   - Missing symbols: non-existent scenes, characters, variables (uninitialized read, mutation-only), assets.
   - Unicode, Cyrillic, Japanese, and emoji in scene titles, character definitions, and dialogue.
   - Multi-byte character column offsets and text span alignment.
3. Document synchronization and recovery:
   - Heavily broken scripts with >30 syntax errors (recovery cap resilience).
   - Deeply nested unclosed @if blocks and stray @else/@elif/@end directives.
   - Rapid document lifecycle: 50+ open, edit, and close cycles on untracked documents.
   - Unusual byte and control sequences (CRLF/CR mixing, escape codes, nulls).
"""

from __future__ import annotations

from pathlib import Path

from lsprotocol import types
from lsprotocol.types import (
    DiagnosticSeverity,
    Location,
    MarkupContent,
    Position,
    TextEdit,
)

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.completion import compute_completions
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.features.hover import compute_hover
from eager_script_lsp.features.navigation import (
    compute_definition,
    compute_document_symbols,
    compute_references,
)
from eager_script_lsp.server import create_server
from eager_script_lsp.workspace import WorkspaceIndex


class TestCompletionAdversarial:
    """Empirical adversarial stress testing of the completion provider."""

    def test_completions_at_edge_positions_and_empty_document(self) -> None:
        """Verify completion returns cleanly at extreme positions without crashing."""
        index = WorkspaceIndex(Path("."))
        empty_doc = ScriptDocument("file:///empty.es", "")
        index.documents["file:///empty.es"] = empty_doc
        index._rebuild_index()

        # Empty document at origin and extreme positions
        assert len(compute_completions(empty_doc, index, Position(line=0, character=0)).items) == 0
        assert len(compute_completions(empty_doc, index, Position(line=0, character=999999)).items) == 0
        assert len(compute_completions(empty_doc, index, Position(line=999999, character=999999)).items) == 0

        # One-line document with character past line length
        one_line = ScriptDocument("file:///one.es", "## Start --- start\n")
        index.documents["file:///one.es"] = one_line
        index._rebuild_index()
        past_end = compute_completions(one_line, index, Position(line=0, character=999999))
        assert isinstance(past_end.items, list)

    def test_completions_on_whitespace_and_empty_lines(self) -> None:
        """Verify empty lines and various whitespace trigger narrator and declared character completions."""
        script = """@character alice "Alice" color=#ff0000
## Scene 1 --- s1

   
\t\t
"""
        doc = ScriptDocument("file:///whitespace.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///whitespace.es"] = doc
        index._rebuild_index()

        for line_idx in [2, 3, 4]:
            comp = compute_completions(doc, index, Position(line=line_idx, character=0))
            labels = [item.label for item in comp.items]
            assert "Narrator" in labels
            assert "Alice" in labels

    def test_completions_partially_typed_jumps_and_multiword_scenes(self) -> None:
        """Verify jump completions with partial typing, multi-word scene slugs, and non-matching filters."""
        script = """## Start Scene --- start_scene
## Grand Hall --- grand-hall
## Ending Epilogue --- ending_epilogue

> 
> st
> grand
> non_matching_label
>> 
>> end
"""
        doc = ScriptDocument("file:///jumps.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///jumps.es"] = doc
        index._rebuild_index()

        # Line 4: '> ' (cursor after space) -> all scenes
        c_all = compute_completions(doc, index, Position(line=4, character=2))
        all_labels = {item.label for item in c_all.items}
        assert {"start_scene", "grand-hall", "ending_epilogue"}.issubset(all_labels)

        # Line 5: '> st' -> only start_scene
        c_st = compute_completions(doc, index, Position(line=5, character=4))
        st_labels = [item.label for item in c_st.items]
        assert st_labels == ["start_scene"]
        assert isinstance(c_st.items[0].text_edit, TextEdit)
        assert c_st.items[0].text_edit.range.start.character == 2
        assert c_st.items[0].text_edit.range.end.character == 4

        # Line 6: '> grand' -> grand-hall (hyphenated slug)
        c_grand = compute_completions(doc, index, Position(line=6, character=7))
        assert [item.label for item in c_grand.items] == ["grand-hall"]

        # Line 7: '> non_matching_label' -> empty list
        c_none = compute_completions(doc, index, Position(line=7, character=20))
        assert len(c_none.items) == 0

        # Line 8: '>> ' -> all scenes for subroutine call
        c_call = compute_completions(doc, index, Position(line=8, character=3))
        assert len(c_call.items) >= 3

        # Line 9: '>> end' -> ending_epilogue
        c_end = compute_completions(doc, index, Position(line=9, character=6))
        assert [item.label for item in c_end.items] == ["ending_epilogue"]

    def test_completions_choice_inline_targets_and_conditionals(self) -> None:
        """Verify choice targets with open paren, partial scene typing, and condition fallthrough."""
        script = """## Room A --- room_a
## Room B --- room_b

? Open door (
? Enter portal (room_
? Secret passage (unknown
? Check key if 
"""
        doc = ScriptDocument("file:///choices.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///choices.es"] = doc
        index._rebuild_index()

        # Open paren: suggests all scenes
        c_open = compute_completions(doc, index, Position(line=3, character=13))
        assert {i.label for i in c_open.items} == {"room_a", "room_b"}

        # Partial typing: room_
        c_partial = compute_completions(doc, index, Position(line=4, character=20))
        assert {i.label for i in c_partial.items} == {"room_a", "room_b"}

        # Unknown filter: no match
        c_unknown = compute_completions(doc, index, Position(line=5, character=24))
        assert len(c_unknown.items) == 0

        # Choice condition: 'if ' falls through to expression completions
        c_if = compute_completions(doc, index, Position(line=6, character=15))
        func_labels = [i.label for i in c_if.items]
        assert "visited(label)" in func_labels
        assert "random(a, b)" in func_labels

    def test_completions_directives_and_expression_shadowing_guard(self) -> None:
        """Verify @ directives trigger at line start but do not shadow expressions inside @if and @elif."""
        script = """@
@c
@if 
@elif 
@default 
"""
        doc = ScriptDocument("file:///directives.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///directives.es"] = doc
        index._rebuild_index()

        # '@' suggests directives
        c_at = compute_completions(doc, index, Position(line=0, character=1))
        directive_labels = [i.label for i in c_at.items]
        assert "@character" in directive_labels
        assert "@default" in directive_labels
        assert "@if" in directive_labels

        # '@c' suggests directives
        c_c = compute_completions(doc, index, Position(line=1, character=2))
        assert "@character" in [i.label for i in c_c.items]

        # '@if ' (cursor after space) MUST NOT suggest @character snippets
        c_if = compute_completions(doc, index, Position(line=2, character=4))
        if_labels = [i.label for i in c_if.items]
        assert "@character" not in if_labels
        assert "visited(label)" in if_labels
        assert "chance(p)" in if_labels

        # '@elif ' (cursor after space) MUST NOT suggest @character snippets
        c_elif = compute_completions(doc, index, Position(line=3, character=6))
        elif_labels = [i.label for i in c_elif.items]
        assert "@character" not in elif_labels
        assert "seen(label)" in elif_labels

    def test_completions_expressions_and_variables_with_special_patterns(self) -> None:
        """Verify variable completion for identifiers with underscores, digits, and DSL functions."""
        script = """@default player_hp = 100
@default _flag_secret = 1
@default score2026 = 50

$ 
$ visited(
Narrator: Current HP is [
Narrator: Secret is [_
"""
        doc = ScriptDocument("file:///vars.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///vars.es"] = doc
        index._rebuild_index()

        # After '$ '
        c_expr = compute_completions(doc, index, Position(line=4, character=2))
        expr_labels = [i.label for i in c_expr.items]
        assert "player_hp" in expr_labels
        assert "_flag_secret" in expr_labels
        assert "score2026" in expr_labels
        assert "round(x)" in expr_labels

        # Inside '$ visited(' -> suggests scene labels
        c_vis = compute_completions(doc, index, Position(line=5, character=10))
        assert isinstance(c_vis.items, list)

        # Inside '[' dialogue interpolation
        c_bracket = compute_completions(doc, index, Position(line=6, character=25))
        var_labels = [i.label for i in c_bracket.items]
        assert "player_hp" in var_labels
        assert "_flag_secret" in var_labels
        assert "score2026" in var_labels

        # Inside '[_' prefix filter
        c_under = compute_completions(doc, index, Position(line=7, character=22))
        under_labels = [i.label for i in c_under.items]
        assert "_flag_secret" in under_labels

    def test_completions_engine_hooks_resilience(self) -> None:
        """Verify ~ engine hooks, kwargs, and unknown character tolerance."""
        script = """@character bob "Bob" color=#0000ff
~
~ 
~ show 
~ show bob 
~ show unknown_entity 
~ bg 
~ play 
"""
        doc = ScriptDocument("file:///hooks.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///hooks.es"] = doc
        index._rebuild_index()

        # '~' and '~ '
        c_tilde = compute_completions(doc, index, Position(line=1, character=1))
        assert "show" in [i.label for i in c_tilde.items]
        c_space = compute_completions(doc, index, Position(line=2, character=2))
        assert "bg" in [i.label for i in c_space.items]

        # '~ show ' -> suggests declared characters
        c_show = compute_completions(doc, index, Position(line=3, character=7))
        assert "bob" in [i.label for i in c_show.items]

        # '~ show bob ' -> suggests positions and transitions
        c_bob = compute_completions(doc, index, Position(line=4, character=11))
        bob_labels = [i.label for i in c_bob.items]
        assert "center" in bob_labels
        assert "fade" in bob_labels
        assert "duration=" in bob_labels

        # '~ show unknown_entity ' -> does not crash, still suggests positions/transitions
        c_unk = compute_completions(doc, index, Position(line=5, character=22))
        unk_labels = [i.label for i in c_unk.items]
        assert "right" in unk_labels
        assert "dissolve" in unk_labels

        # '~ bg '
        c_bg = compute_completions(doc, index, Position(line=6, character=5))
        assert "with" in [i.label for i in c_bg.items]

        # '~ play '
        c_play = compute_completions(doc, index, Position(line=7, character=7))
        play_labels = [i.label for i in c_play.items]
        assert "music" in play_labels
        assert "sound" in play_labels


class TestHoverAndNavigationAdversarial:
    """Empirical adversarial stress testing of hover, definition, and references."""

    def test_out_of_bounds_queries(self) -> None:
        """Verify coordinates outside document bounds safely return None or empty lists."""
        index = WorkspaceIndex(Path("."))
        doc = ScriptDocument("file:///bounds.es", "## Start --- start\nNarrator: Hello\n> start\n")
        index.documents["file:///bounds.es"] = doc
        index._rebuild_index()

        extremes = [
            Position(line=0, character=999999),
            Position(line=999999, character=0),
            Position(line=999999, character=999999),
            Position(line=2147483647, character=2147483647),
        ]

        for pos in extremes:
            assert compute_hover(doc, index, pos) is None
            assert compute_definition(doc, index, pos) is None
            assert compute_references(doc, index, pos) == []

        # Document symbols on empty doc
        empty_doc = ScriptDocument("file:///empty2.es", "")
        assert compute_document_symbols(empty_doc) == []

    def test_missing_symbols_resilience(self) -> None:
        """Verify queries on missing scenes, characters, variables, and assets do not crash."""
        script = """## Start --- start
> missing_scene_target
unknown_speaker: Hello there!
~ show ghost_character
Narrator: Reading [uninitialized_var]
$ mutation_only_var = 42
~ bg non_existent_bg
Narrator: {voice:missing_audio.ogg} Speak
"""
        doc = ScriptDocument("file:///missing.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///missing.es"] = doc
        index._rebuild_index()

        # 1. Missing scene target (line 1, col 5)
        pos_scene = Position(line=1, character=5)
        assert compute_hover(doc, index, pos_scene) is None
        assert compute_definition(doc, index, pos_scene) is None

        # 2. Unknown speaker (line 2, col 5)
        pos_spk = Position(line=2, character=5)
        h_spk = compute_hover(doc, index, pos_spk)
        assert h_spk is not None
        assert isinstance(h_spk.contents, MarkupContent)
        assert "unknown_speaker" in h_spk.contents.value
        assert compute_definition(doc, index, pos_spk) is None

        # 3. Uninitialized variable read (line 4, col 23)
        pos_var = Position(line=4, character=23)
        h_var = compute_hover(doc, index, pos_var)
        assert h_var is not None
        assert isinstance(h_var.contents, MarkupContent)
        assert "uninitialized_var" in h_var.contents.value
        assert "undefined" in h_var.contents.value
        assert compute_definition(doc, index, pos_var) is None

        # 4. Mutation-only variable definition fallback (line 5, col 4)
        pos_mut = Position(line=5, character=4)
        def_mut = compute_definition(doc, index, pos_mut)
        assert isinstance(def_mut, Location)
        assert def_mut.uri == "file:///missing.es"
        assert def_mut.range.start.line == 5

        # 5. Missing background asset (line 6, col 6)
        pos_bg = Position(line=6, character=6)
        assert compute_hover(doc, index, pos_bg) is None
        assert compute_definition(doc, index, pos_bg) is None

        # 6. Missing voice asset (line 7, col 18)
        pos_voice = Position(line=7, character=18)
        assert compute_hover(doc, index, pos_voice) is None
        assert compute_definition(doc, index, pos_voice) is None

    def test_unicode_and_multibyte_internationalization(self) -> None:
        """Verify Japanese, Cyrillic, emoji, and multi-byte text in scenes, characters, and dialogue."""
        script = """# 🌸 Sakura & Snow Monogatari
@character yuki "白雪姫 👸" color=#ffffff
@character ivan "Иван Царевич" color=#ff2222

## 🌸 第一章：桜と雪 --- ch1_sakura
yuki: こんにちは世界！ 🌸 Здравствуйте!
ivan: Привет, мир! 🚀
Narrator: Mixed emoji 🌍 ✨ and symbols [yuki_score]
> ch2_ru

## Глава 2: Великая тайна 🌟 --- ch2_ru
Narrator: Конец истории ✨
"""
        doc = ScriptDocument("file:///i18n.es", script)
        index = WorkspaceIndex(Path("."))
        index.documents["file:///i18n.es"] = doc
        index._rebuild_index()

        # No syntax errors on valid unicode script
        assert len(doc.syntax_errors) == 0

        # Hover on Japanese scene title (line 4, col 5)
        h_jp_scene = compute_hover(doc, index, Position(line=4, character=5))
        assert h_jp_scene is not None
        assert isinstance(h_jp_scene.contents, MarkupContent)
        assert "第一章：桜と雪" in h_jp_scene.contents.value

        # Hover on Cyrillic scene title (line 10, col 5)
        h_ru_scene = compute_hover(doc, index, Position(line=10, character=5))
        assert h_ru_scene is not None
        assert isinstance(h_ru_scene.contents, MarkupContent)
        assert "Глава 2: Великая тайна 🌟" in h_ru_scene.contents.value

        # Hover on speaker 'yuki' (line 5, col 1) -> shows display name '白雪姫 👸'
        h_yuki = compute_hover(doc, index, Position(line=5, character=1))
        assert h_yuki is not None
        assert isinstance(h_yuki.contents, MarkupContent)
        assert "白雪姫 👸" in h_yuki.contents.value

        # Definition on speaker 'yuki' -> jumps to @character definition on line 1
        def_yuki = compute_definition(doc, index, Position(line=5, character=1))
        assert isinstance(def_yuki, Location)
        assert def_yuki.range.start.line == 1

        # References on speaker 'yuki' -> finds definition and dialogue line
        refs_yuki = compute_references(doc, index, Position(line=5, character=1))
        assert len(refs_yuki) >= 2

        # Hover on speaker 'ivan' (line 6, col 1) -> shows Cyrillic display name
        h_ivan = compute_hover(doc, index, Position(line=6, character=1))
        assert h_ivan is not None
        assert isinstance(h_ivan.contents, MarkupContent)
        assert "Иван Царевич" in h_ivan.contents.value

        # Multi-byte dialogue line column offset verification
        # Line 7: 'Narrator: Mixed emoji 🌍 ✨ and symbols [yuki_score]'
        var_token = doc.get_token_at(7, 43)
        assert var_token is not None
        assert var_token.kind == "variable"
        assert var_token.value == "yuki_score"


class TestDocumentSyncAndRecoveryAdversarial:
    """Empirical adversarial stress testing of AST recovery, nested blocks, and server lifecycle."""

    def test_heavily_broken_scripts_recovery_limit(self) -> None:
        """Verify documents with excessive syntax errors cap recovery attempts without hanging or crashing."""
        index = WorkspaceIndex(Path("."))

        # 45 broken choices lacking indented blocks + lexical errors
        broken_lines = [
            "## Valid Start --- valid_start",
            "> ",  # lexical error
            "@if ",  # lexical error
        ] + [f"? Broken choice {i}" for i in range(45)] + [
            "## Valid End --- valid_end",
            "Narrator: Survived",
            "> valid_start",
        ]

        script = "\n".join(broken_lines)
        doc = ScriptDocument("file:///heavily_broken.es", script)
        index.documents["file:///heavily_broken.es"] = doc
        index._rebuild_index()

        # Recovery halts at bounded max attempts (30 for parser + 2 lexical)
        assert len(doc.syntax_errors) == 32
        diags = compute_diagnostics(doc, index)
        assert len(diags) == 32

        # Hover on valid start scene remains functional
        h_start = compute_hover(doc, index, Position(line=0, character=5))
        assert h_start is not None
        assert isinstance(h_start.contents, MarkupContent)
        assert "Valid Start" in h_start.contents.value

    def test_deeply_nested_and_stray_conditionals(self) -> None:
        """Verify diagnostics cleanly flag deeply nested unclosed @if blocks and stray directives."""
        index = WorkspaceIndex(Path("."))
        script = """## Start --- s
@if cond1
    Narrator: 1
    @if cond2
        Narrator: 2
        @if cond3
            Narrator: 3
            @else
            Narrator: 3 else
            @elif cond4
            Narrator: 3 elif
        @end
@else
@elif stray_elif
@end
@end
@else
"""
        doc = ScriptDocument("file:///deep_nested.es", script)
        diags = compute_diagnostics(doc, index)
        error_msgs = [d.message for d in diags if d.severity == DiagnosticSeverity.Error]

        # Catches misplaced @elif after @else and stray @else
        assert any("@elif cannot follow @else" in m for m in error_msgs)
        assert any("@else without matching @if" in m for m in error_msgs)

    def test_rapid_server_document_lifecycle(self) -> None:
        """Verify rapid DidOpen, DidChange, and DidClose of 50 untracked documents without state corruption."""
        server = create_server()
        gen = server.protocol.lsp_initialize(
            types.InitializeParams(capabilities=types.ClientCapabilities(), root_uri="file:///tmp")
        )
        try:
            func, args, kwargs = next(gen)
            gen.send(func(*args, **(kwargs or {})))
        except StopIteration:
            pass
        server.protocol.lsp_initialized(types.InitializedParams())

        published_diagnostics: list[types.PublishDiagnosticsParams] = []
        server.text_document_publish_diagnostics = lambda p: published_diagnostics.append(p)  # type: ignore[assignment]

        for i in range(50):
            uri = f"file:///tmp/rapid_untracked_{i}.es"

            # 1. DidOpen
            open_gen = server.protocol.lsp_text_document__did_open(
                types.DidOpenTextDocumentParams(
                    text_document=types.TextDocumentItem(
                        uri=uri,
                        language_id="eager-script",
                        version=1,
                        text=f"## Scene_{i} --- s_{i}\nNarrator: Line {i}\n> s_{i}\n",
                    )
                )
            )
            try:
                for x in open_gen:
                    f, a, kw = x
                    f(*a, **(kw or {}))
            except TypeError:
                pass
            assert uri in server.workspace_index.documents

            # 2. DidChange (incremental partial edit)
            change_gen = server.protocol.lsp_text_document__did_change(
                types.DidChangeTextDocumentParams(
                    text_document=types.VersionedTextDocumentIdentifier(uri=uri, version=2),
                    content_changes=[
                        types.TextDocumentContentChangePartial(
                            range=types.Range(
                                start=types.Position(line=2, character=0),
                                end=types.Position(line=2, character=0),
                            ),
                            range_length=0,
                            text="Narrator: Additional dialogue\n",
                        )
                    ],
                )
            )
            try:
                for x in change_gen:
                    f, a, kw = x
                    f(*a, **(kw or {}))
            except TypeError:
                pass

            # 3. DidClose
            close_gen = server.protocol.lsp_text_document__did_close(
                types.DidCloseTextDocumentParams(
                    text_document=types.TextDocumentIdentifier(uri=uri)
                )
            )
            try:
                for x in close_gen:
                    f, a, kw = x
                    f(*a, **(kw or {}))
            except TypeError:
                pass

            # Buffer must be evicted from workspace
            assert uri not in server.workspace_index.documents

        # Check empty diagnostics were published for closed buffers
        empty_published = [p for p in published_diagnostics if len(p.diagnostics) == 0]
        assert len(empty_published) >= 50

    def test_unusual_characters_and_newlines_resilience(self) -> None:
        """Verify parser and token scanner handle CRLF, solitary CR, nulls, and control sequences."""
        crlf_script = "## Start --- start\r\nNarrator: Hello CRLF\r\n> start\r\n"
        cr_script = "## Start --- start\rNarrator: Hello CR\r> start\r"
        null_script = "## Start --- start\nNarrator: Hello \x00 null\n> start\n"
        ansi_script = "## Start --- start\nNarrator: \x1b[31mRed text\x1b[0m\n> start\n"

        index = WorkspaceIndex(Path("."))
        for label, raw_text in [
            ("crlf", crlf_script),
            ("cr", cr_script),
            ("null", null_script),
            ("ansi", ansi_script),
        ]:
            doc = ScriptDocument(f"file:///{label}.es", raw_text)
            assert isinstance(doc.lines, list)
            assert len(doc.lines) > 0
            index.documents[f"file:///{label}.es"] = doc
            index._rebuild_index()
            # Hover on scene header doesn't crash
            h = compute_hover(doc, index, Position(line=0, character=4))
            assert h is not None
            assert isinstance(h.contents, MarkupContent)
            assert "Start" in h.contents.value
