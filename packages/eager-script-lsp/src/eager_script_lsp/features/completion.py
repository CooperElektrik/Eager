"""Context-aware auto-completion engine for Eager-Script screenplays."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    CompletionList,
    InsertTextFormat,
    Position,
    Range,
    TextEdit,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex

BUILTIN_HOOKS = [
    ("bg", "Change background image with optional transition"),
    ("bg_clear", "Clear background image"),
    ("scene", "Clear stage and display new background"),
    ("show", "Show character sprite with emotion, position, and transition"),
    ("hide", "Hide character sprite with transition"),
    ("move", "Move character sprite to new position"),
    ("expr", "Change character emotion sprite"),
    ("image", "Display overlay image"),
    ("fade_in", "Fade in stage from color"),
    ("fade_out", "Fade out stage to color"),
    ("flash", "Screen flash effect"),
    ("shake", "Screen shake effect"),
    ("play", "Play audio track on specified channel"),
    ("stop", "Stop audio playback on channel"),
    ("volume", "Adjust channel volume"),
    ("nvl", "Switch to NVL full-screen text mode"),
    ("nvl_clear", "Clear NVL text overlay"),
    ("input", "Prompt user for text input into variable"),
]

HOOK_POSITIONS = [
    "left", "center_left", "center", "center_right", "right",
    "far_left", "far_right", "offscreen_left", "offscreen_right",
]

HOOK_TRANSITIONS = [
    "cut", "fade", "crossfade", "dissolve",
    "slide_left", "slide_right", "slide_up", "slide_down",
]

HOOK_KWARGS = [
    ("duration=", "duration=${1:1.0}"),
    ("easing=", "easing=${1:linear}"),
    ("color=", "color=${1:#ffffff}"),
    ("flip_h=", "flip_h=${1:true}"),
    ("z=", "z=${1:0}"),
    ("fade=", "fade=${1:1.0}"),
    ("volume=", "volume=${1:1.0}"),
    ("loop=", "loop=${1:true}"),
]

BUILTIN_EXPR_FUNCS = [
    ("visited(label)", "visited('${1:scene_id}')", "Check if scene has been visited"),
    ("seen(label)", "seen('${1:scene_id}')", "Check if scene has ever been visited across playthroughs"),
    ("random(a, b)", "random(${1:1}, ${2:10})", "Return random integer between a and b"),
    ("chance(p)", "chance(${1:0.5})", "Return True with probability p (0.0 to 1.0)"),
    ("min(a, b)", "min(${1:a}, ${2:b})", "Return smaller value"),
    ("max(a, b)", "max(${1:a}, ${2:b})", "Return larger value"),
    ("abs(x)", "abs(${1:x})", "Absolute value"),
    ("len(x)", "len(${1:x})", "Length of string"),
    ("int(x)", "int(${1:x})", "Convert to integer"),
    ("str(x)", "str(${1:x})", "Convert to string"),
    ("round(x)", "round(${1:x})", "Round number"),
]

DIRECTIVES = [
    ("@character", '@character ${1:id} "${2:Name}" color=${3:#ffffff}', "Declare character with styling attributes"),
    ("@default", "@default ${1:var_name} = ${2:0}", "Declare global variable with initial default value"),
    ("@if", "@if ${1:condition}", "Conditional branch start"),
    ("@elif", "@elif ${1:condition}", "Alternative conditional branch"),
    ("@else", "@else", "Fallback branch"),
    ("@end", "@end", "Close conditional block"),
]

INLINE_TAGS = [
    ("{b}...{/b}", "{b}${1:bold text}{/b}", "Bold text styling"),
    ("{i}...{/i}", "{i}${1:italic text}{/i}", "Italic text styling"),
    ("{color=#...}", "{color=${1:#ffffff}}${2:colored text}{/color}", "Color text formatting"),
    ("{size=...}", "{size=${1:1.2}}${2:sized text}{/size}", "Font scaling factor"),
    ("{w=...}", "{w=${1:0.5}}", "Inline text pause (seconds)"),
    ("{p=...}", "{p=${1:1.0}}", "Wait for click pause point"),
    ("{voice:...}", "{voice:${1:path}}", "Trigger voice audio clip"),
    ("{id=...}", "{id=${1:stable_id}}", "Pin explicit content ID for localization"),
]


def compute_completions(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    position: Position,
) -> CompletionList:
    """Return context-sensitive completions at the cursor position."""
    line_0 = position.line
    char_0 = position.character
    if line_0 >= len(doc.lines):
        return CompletionList(is_incomplete=False, items=[])

    line_text = doc.lines[line_0]
    line_prefix = line_text[:char_0]
    items: list[CompletionItem] = []

    # 1. Target scene completions: '> ...', '>> ...', '? Text (<cursor>)', or inside visited('...')
    jump_match = re.search(r"(>>|>)\s*$", line_prefix)
    if (
        jump_match
        or re.search(r"\?\s*.+\(\s*$", line_prefix)
        or re.search(r"\b(visited|seen)\s*\(\s*['\"]?$", line_prefix)
    ):
        for scene_id, sym in workspace.labels.items():
            item = CompletionItem(
                label=scene_id,
                kind=CompletionItemKind.Function,
                detail=f"Scene: {sym.display_name}",
                documentation=sym.docstring or f"Scene defined in {sym.uri}",
            )
            if jump_match:
                op = jump_match.group(1)
                op_start = jump_match.start(1)
                has_space = " " in line_prefix[op_start:]
                if has_space:
                    item.text_edit = TextEdit(
                        range=Range(
                            start=Position(line=line_0, character=char_0),
                            end=Position(line=line_0, character=char_0),
                        ),
                        new_text=scene_id,
                    )
                else:
                    item.text_edit = TextEdit(
                        range=Range(
                            start=Position(line=line_0, character=op_start),
                            end=Position(line=line_0, character=char_0),
                        ),
                        new_text=f"{op} {scene_id}",
                    )
                    item.filter_text = f"{op}{scene_id}"
            items.append(item)
        return CompletionList(is_incomplete=False, items=items)

    # 2. Emotion sprite completions inside Speaker (<cursor>)
    speaker_paren_match = re.search(r"^([A-Za-z_][A-Za-z0-9_\s\.\-\'\"]*?)\s*\(([^)]*)$", line_prefix)
    if speaker_paren_match:
        speaker_name = speaker_paren_match.group(1).strip().lower()
        expressions = workspace.asset_index.characters.get(speaker_name, set())
        for expr in sorted(expressions):
            items.append(
                CompletionItem(
                    label=expr,
                    kind=CompletionItemKind.EnumMember,
                    detail=f"Sprite expression for '{speaker_name}'",
                )
            )
        return CompletionList(is_incomplete=False, items=items)

    # 3. Directives at line start: '@...'
    if line_prefix.strip().startswith("@"):
        at_col = line_text.find("@")
        for label, snippet, doc_str in DIRECTIVES:
            items.append(
                CompletionItem(
                    label=label,
                    kind=CompletionItemKind.Keyword,
                    insert_text=snippet,
                    insert_text_format=InsertTextFormat.Snippet,
                    documentation=doc_str,
                    filter_text=label,
                    text_edit=TextEdit(
                        range=Range(
                            start=Position(line=line_0, character=at_col),
                            end=Position(line=line_0, character=char_0),
                        ),
                        new_text=snippet,
                    ),
                )
            )
        return CompletionList(is_incomplete=False, items=items)

    # 4. Engine hook completions: '~ ...'
    if line_prefix.lstrip().startswith("~"):
        tilde_col = line_prefix.rfind("~")
        hook_tail = line_prefix[tilde_col + 1:].strip()
        tokens = hook_tail.split()

        # Command position: '~ <cursor>'
        if len(tokens) == 0 or (len(tokens) == 1 and not line_prefix.endswith(" ")):
            has_space_after_tilde = " " in line_prefix[tilde_col:]
            if has_space_after_tilde:
                word_start = char_0 - len(tokens[0]) if tokens else char_0
                for name, doc_str in BUILTIN_HOOKS:
                    items.append(
                        CompletionItem(
                            label=name,
                            kind=CompletionItemKind.Function,
                            documentation=doc_str,
                            text_edit=TextEdit(
                                range=Range(
                                    start=Position(line=line_0, character=word_start),
                                    end=Position(line=line_0, character=char_0),
                                ),
                                new_text=f"{name} ",
                            ),
                        )
                    )
            else:
                for name, doc_str in BUILTIN_HOOKS:
                    items.append(
                        CompletionItem(
                            label=name,
                            kind=CompletionItemKind.Function,
                            documentation=doc_str,
                            filter_text=f"~{name}",
                            text_edit=TextEdit(
                                range=Range(
                                    start=Position(line=line_0, character=tilde_col),
                                    end=Position(line=line_0, character=char_0),
                                ),
                                new_text=f"~ {name} ",
                            ),
                        )
                    )
            return CompletionList(is_incomplete=False, items=items)

        hook_cmd = tokens[0]

        # '~ bg <cursor>' or '~ scene <cursor>'
        if hook_cmd in ("bg", "scene"):
            for bg in sorted(workspace.asset_index.backgrounds):
                items.append(
                    CompletionItem(
                        label=bg,
                        kind=CompletionItemKind.File,
                        detail="Background Asset",
                    )
                )
            for kw in ("with", "duration="):
                items.append(CompletionItem(label=kw, kind=CompletionItemKind.Keyword))
            return CompletionList(is_incomplete=False, items=items)

        # '~ show <cursor>' / '~ expr <cursor>' / '~ move <cursor>'
        if hook_cmd in ("show", "hide", "move", "expr"):
            # Character position (first arg)
            if len(tokens) == 1 or (len(tokens) == 2 and not line_prefix.endswith(" ")):
                for char_id, sym in workspace.characters.items():
                    items.append(
                        CompletionItem(
                            label=char_id,
                            kind=CompletionItemKind.Class,
                            detail=f"Character: {sym.name}",
                        )
                    )
                return CompletionList(is_incomplete=False, items=items)

            # Expression position (second arg)
            target_char = tokens[1].lower()
            if (len(tokens) == 2 and line_prefix.endswith(" ")) or (len(tokens) == 3 and not line_prefix.endswith(" ")):
                expressions = workspace.asset_index.characters.get(target_char, set())
                for expr in sorted(expressions):
                    items.append(
                        CompletionItem(
                            label=expr,
                            kind=CompletionItemKind.EnumMember,
                            detail=f"Expression for '{target_char}'",
                        )
                    )

            # Contextual keywords, positions, and transitions
            for kw in ("at", "with", "to"):
                items.append(CompletionItem(label=kw, kind=CompletionItemKind.Keyword))
            for pos in HOOK_POSITIONS:
                items.append(CompletionItem(label=pos, kind=CompletionItemKind.Value, detail="Stage Position"))
            for trans in HOOK_TRANSITIONS:
                items.append(CompletionItem(label=trans, kind=CompletionItemKind.Event, detail="Transition"))
            for kwarg_label, kwarg_snip in HOOK_KWARGS:
                items.append(
                    CompletionItem(
                        label=kwarg_label,
                        kind=CompletionItemKind.Property,
                        insert_text=kwarg_snip,
                        insert_text_format=InsertTextFormat.Snippet,
                    )
                )
            return CompletionList(is_incomplete=False, items=items)

        # '~ play <cursor>'
        if hook_cmd in ("play", "stop", "volume") or hook_cmd.startswith("play_"):
            for chan in ("music", "sound", "voice", "ambient"):
                items.append(CompletionItem(label=chan, kind=CompletionItemKind.Enum, detail="Audio Channel"))
            for track in sorted(workspace.asset_index.audio):
                items.append(CompletionItem(label=track, kind=CompletionItemKind.File, detail="Audio Track"))
            for kw in ("fade=", "volume=", "loop="):
                items.append(CompletionItem(label=kw, kind=CompletionItemKind.Property))
            return CompletionList(is_incomplete=False, items=items)

    # 5. Inline text tags inside dialogue: '{<cursor>'
    if line_prefix.endswith("{") or re.search(r"\{[a-zA-Z0-9_]*$", line_prefix):
        for label, snippet, doc_str in INLINE_TAGS:
            items.append(
                CompletionItem(
                    label=label,
                    kind=CompletionItemKind.Snippet,
                    insert_text=snippet.lstrip("{") if line_prefix.endswith("{") else snippet,
                    insert_text_format=InsertTextFormat.Snippet,
                    documentation=doc_str,
                )
            )
        # Voice clips
        for v in sorted(workspace.asset_index.voice):
            items.append(
                CompletionItem(
                    label=f"voice:{v}",
                    kind=CompletionItemKind.File,
                    insert_text=f"voice:{v}}}" if line_prefix.endswith("{") else f"{{voice:{v}}}",
                    detail="Voice Clip Asset",
                )
            )
        return CompletionList(is_incomplete=False, items=items)

    # 6. Variable interpolation: '[<cursor>'
    if line_prefix.endswith("[") or re.search(r"\[[A-Za-z0-9_]*$", line_prefix):
        for var_name, sym in workspace.variables.items():
            items.append(
                CompletionItem(
                    label=var_name,
                    kind=CompletionItemKind.Variable,
                    detail=f"Default: {sym.default_val or 'none'}",
                    insert_text=f"{var_name}]" if line_prefix.endswith("[") else f"[{var_name}]",
                )
            )
        return CompletionList(is_incomplete=False, items=items)

    # 7. Expressions in '$ ...', '@if ...', '@elif ...', or '? ... if ...'
    if (
        line_prefix.strip().startswith("$")
        or line_prefix.strip().startswith(("@if", "@elif"))
        or " if " in line_prefix
    ):
        for var_name, sym in workspace.variables.items():
            items.append(
                CompletionItem(
                    label=var_name,
                    kind=CompletionItemKind.Variable,
                    detail=f"Variable (default={sym.default_val})",
                )
            )
        for label, snippet, doc_str in BUILTIN_EXPR_FUNCS:
            items.append(
                CompletionItem(
                    label=label,
                    kind=CompletionItemKind.Function,
                    insert_text=snippet,
                    insert_text_format=InsertTextFormat.Snippet,
                    documentation=doc_str,
                )
            )
        return CompletionList(is_incomplete=False, items=items)

    # 8. Speaker names at start of line
    if not line_prefix.strip() or re.match(r"^[A-Za-z0-9_]+$", line_prefix.strip()):
        for char_id, sym in workspace.characters.items():
            items.append(
                CompletionItem(
                    label=sym.name,
                    kind=CompletionItemKind.Class,
                    detail=f"Speaker: {sym.id}",
                    insert_text=f"{sym.name}: ",
                )
            )
        items.append(
            CompletionItem(
                label="Narrator",
                kind=CompletionItemKind.Class,
                detail="Default speakerless narrator",
                insert_text="Narrator: ",
            )
        )

    return CompletionList(is_incomplete=False, items=items)
