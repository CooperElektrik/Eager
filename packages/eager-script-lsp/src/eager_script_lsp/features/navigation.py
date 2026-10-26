"""Navigation providers: Definition, References, Symbols, and Call Hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lsprotocol.types import (
    CallHierarchyIncomingCall,
    CallHierarchyItem,
    CallHierarchyOutgoingCall,
    DocumentSymbol,
    Location,
    Position,
    Range,
    SymbolInformation,
    SymbolKind,
)

if TYPE_CHECKING:
    from eager_script_lsp.document import ScriptDocument
    from eager_script_lsp.workspace import WorkspaceIndex

__all__ = [
    "compute_definition",
    "compute_document_symbols",
    "compute_incoming_calls",
    "compute_outgoing_calls",
    "compute_references",
    "compute_workspace_symbols",
    "prepare_call_hierarchy",
]


def compute_definition(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    position: Position,
) -> Location | list[Location] | None:
    """Find the definition location for the symbol under the cursor."""
    token = doc.get_token_at(position.line, position.character)
    if token is None:
        return None

    # 1. Scene label target -> Scene definition
    if token.kind in ("jump_target", "call_target", "choice_target", "label_ref"):
        scene_id = token.value
        sym = workspace.get_scene(scene_id)
        if sym is not None:
            return Location(uri=sym.uri, range=sym.range)

    # 2. Speaker or character -> @character definition
    if token.kind in ("speaker", "character_id", "character_name") or (
        token.kind == "hook_arg" and token.metadata.get("character")
    ):
        char_id = (token.metadata.get("character") or token.value).lower()
        char_sym = workspace.get_character(char_id)
        if char_sym is not None and char_sym.uri and char_sym.range:
            return Location(uri=char_sym.uri, range=char_sym.range)

    # 3. Variable -> @default declaration
    if token.kind == "variable":
        var_name = token.value
        var_sym = workspace.get_variable(var_name)
        if var_sym is not None:
            if var_sym.default_uri and var_sym.default_range:
                return Location(uri=var_sym.default_uri, range=var_sym.default_range)
            if var_sym.mutations:
                return Location(uri=var_sym.mutations[0][0], range=var_sym.mutations[0][1])

    # 4. Asset reference -> media file on disk
    if token.kind in ("hook_arg", "emotion", "voice_path"):
        asset_kind = token.metadata.get("asset_kind")
        disk_path = None
        if asset_kind == "background":
            disk_path = workspace.asset_index.file_paths.get(f"bg:{token.value}")
        elif asset_kind == "voice":
            disk_path = workspace.asset_index.file_paths.get(f"voice:{token.value}")
        elif asset_kind == "character" or token.kind == "emotion":
            char_id = token.metadata.get("character", "")
            expr = token.value.lower()
            disk_path = workspace.asset_index.file_paths.get(f"char:{char_id}/{expr}")
        elif asset_kind == "audio":
            disk_path = workspace.asset_index.file_paths.get(f"audio:{token.value}")

        if disk_path is not None and disk_path.is_file():
            zero_range = Range(start=Position(line=0, character=0), end=Position(line=0, character=0))
            return Location(uri=disk_path.as_uri(), range=zero_range)

    return None


def compute_references(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    position: Position,
    include_declaration: bool = True,
) -> list[Location]:
    """Find all references across the workspace for the symbol at the cursor."""
    token = doc.get_token_at(position.line, position.character)
    if token is None:
        return []

    locations: list[Location] = []

    # 1. Scene label references
    if token.kind in ("label_id", "label_title", "jump_target", "call_target", "choice_target", "label_ref"):
        scene_id = token.metadata.get("scene_id", token.value) if token.metadata else token.value
        if include_declaration:
            sym = workspace.get_scene(scene_id)
            if sym is not None:
                locations.append(Location(uri=sym.uri, range=sym.range))

        ref_list = workspace.references.get(scene_id, [])
        for uri, r in ref_list:
            locations.append(Location(uri=uri, range=r))
        return locations

    # 2. Character references
    if token.kind in ("character_id", "character_name", "speaker"):
        char_id = token.value.lower()
        for doc_uri, d in workspace.documents.items():
            for occ in d.occurrences:
                if occ.kind in ("character_def", "character_ref") and occ.name == char_id:
                    if not include_declaration and occ.kind == "character_def":
                        continue
                    locations.append(Location(uri=doc_uri, range=occ.span.range))
        return locations

    # 3. Variable references
    if token.kind == "variable":
        var_name = token.value
        var_sym = workspace.get_variable(var_name)
        if var_sym is not None:
            if include_declaration and var_sym.default_uri and var_sym.default_range:
                locations.append(Location(uri=var_sym.default_uri, range=var_sym.default_range))
            for uri, r in var_sym.mutations:
                locations.append(Location(uri=uri, range=r))
            for uri, r in var_sym.reads:
                locations.append(Location(uri=uri, range=r))
        return locations

    return locations


def compute_document_symbols(doc: ScriptDocument) -> list[DocumentSymbol]:
    """Build a hierarchical outline of symbols for the document outline sidebar."""
    symbols: list[DocumentSymbol] = []

    # Preamble items
    preamble_children: list[DocumentSymbol] = []
    current_scene_sym: DocumentSymbol | None = None
    current_scene_children: list[DocumentSymbol] = []

    for span in doc.spans:
        if span.kind == "character_id":
            preamble_children.append(
                DocumentSymbol(
                    name=span.value,
                    kind=SymbolKind.Class,
                    range=span.range,
                    selection_range=span.range,
                    detail="Character definition",
                )
            )
        elif span.kind == "variable" and span.start_line < (
            next((s.start_line for s in doc.spans if s.kind == "label_header"), 999999)
        ):
            preamble_children.append(
                DocumentSymbol(
                    name=f"${span.value}",
                    kind=SymbolKind.Constant,
                    range=span.range,
                    selection_range=span.range,
                    detail="Default variable",
                )
            )
        elif span.kind == "label_title":
            # Flush previous scene
            if current_scene_sym is not None:
                current_scene_sym.children = current_scene_children
                symbols.append(current_scene_sym)

            label_span = doc.scene_spans.get(_slug_for_title(span.value, doc, span.start_line)) or span
            whole_scene_range = Range(
                start=Position(line=span.start_line, character=0),
                end=Position(line=len(doc.lines) - 1, character=len(doc.lines[-1]) if doc.lines else 0),
            )
            current_scene_sym = DocumentSymbol(
                name=span.value,
                kind=SymbolKind.Function,
                range=whole_scene_range,
                selection_range=label_span.range,
                detail=f"Scene ID: {label_span.value}",
            )
            current_scene_children = []

        elif current_scene_sym is not None:
            if span.kind == "choice_text":
                current_scene_children.append(
                    DocumentSymbol(
                        name=f"? {span.value}",
                        kind=SymbolKind.EnumMember,
                        range=span.range,
                        selection_range=span.range,
                    )
                )
            elif span.kind == "call_target":
                current_scene_children.append(
                    DocumentSymbol(
                        name=f">> {span.value}",
                        kind=SymbolKind.Event,
                        range=span.range,
                        selection_range=span.range,
                        detail="Subroutine call",
                    )
                )
            elif span.kind == "variable" and span.start_line > current_scene_sym.selection_range.start.line:
                # Mutation
                parent_line = doc.lines[span.start_line]
                if parent_line.strip().startswith("$"):
                    current_scene_children.append(
                        DocumentSymbol(
                            name=f"${span.value}",
                            kind=SymbolKind.Variable,
                            range=span.range,
                            selection_range=span.range,
                            detail="Variable mutation",
                        )
                    )

    if current_scene_sym is not None:
        current_scene_sym.children = current_scene_children
        symbols.append(current_scene_sym)

    if preamble_children:
        symbols.insert(
            0,
            DocumentSymbol(
                name="Preamble",
                kind=SymbolKind.Namespace,
                range=Range(
                    start=Position(line=0, character=0),
                    end=Position(
                        line=preamble_children[-1].range.end.line,
                        character=preamble_children[-1].range.end.character,
                    ),
                ),
                selection_range=Range(start=Position(line=0, character=0), end=Position(line=0, character=0)),
                children=preamble_children,
            ),
        )

    return symbols


def _slug_for_title(title: str, doc: ScriptDocument, line_0: int) -> str:
    """Helper to find the matching scene ID for a title span."""
    for s in doc.spans:
        if s.kind == "label_id" and s.start_line == line_0:
            return s.value
    return title.lower().replace(" ", "_")


def compute_workspace_symbols(workspace: WorkspaceIndex, query: str) -> list[SymbolInformation]:
    """Search for symbols across the entire workspace matching query."""
    results: list[SymbolInformation] = []
    q = query.lower()

    for scene_id, sym in workspace.labels.items():
        if q in scene_id.lower() or q in sym.display_name.lower():
            results.append(
                SymbolInformation(
                    name=sym.display_name,
                    kind=SymbolKind.Function,
                    location=Location(uri=sym.uri, range=sym.range),
                    container_name="Scene",
                )
            )

    for char_id, sym in workspace.characters.items():
        if (q in char_id.lower() or q in sym.name.lower()) and sym.uri and sym.range:
            results.append(
                SymbolInformation(
                    name=sym.name,
                    kind=SymbolKind.Class,
                    location=Location(uri=sym.uri, range=sym.range),
                    container_name="Character",
                )
            )

    for var_name, sym in workspace.variables.items():
        if q in var_name.lower():
            loc_uri = sym.default_uri or (sym.mutations[0][0] if sym.mutations else None)
            loc_range = sym.default_range or (sym.mutations[0][1] if sym.mutations else None)
            if loc_uri and loc_range:
                results.append(
                    SymbolInformation(
                        name=f"${var_name}",
                        kind=SymbolKind.Variable,
                        location=Location(uri=loc_uri, range=loc_range),
                        container_name="Variable",
                    )
                )

    return results


def prepare_call_hierarchy(
    doc: ScriptDocument,
    workspace: WorkspaceIndex,
    position: Position,
) -> list[CallHierarchyItem] | None:
    """Prepare call hierarchy for the scene at the cursor."""
    scene_id = doc.get_scene_at_line(position.line)
    if not scene_id:
        return None
    sym = workspace.get_scene(scene_id)
    if not sym:
        return None

    item = CallHierarchyItem(
        name=sym.display_name,
        kind=SymbolKind.Function,
        detail=f"Scene ID: {sym.id}",
        uri=sym.uri,
        range=sym.range,
        selection_range=sym.range,
    )
    return [item]


def compute_incoming_calls(
    workspace: WorkspaceIndex,
    item: CallHierarchyItem,
) -> list[CallHierarchyIncomingCall]:
    """Return all incoming transition predecessors for the scene."""
    scene_id = item.detail.replace("Scene ID: ", "") if item.detail else item.name
    sym = workspace.get_scene(scene_id)
    if not sym:
        return []

    incoming: list[CallHierarchyIncomingCall] = []
    for pred_id in sorted(sym.predecessors):
        pred_sym = workspace.get_scene(pred_id)
        if pred_sym:
            caller_item = CallHierarchyItem(
                name=pred_sym.display_name,
                kind=SymbolKind.Function,
                detail=f"Scene ID: {pred_sym.id}",
                uri=pred_sym.uri,
                range=pred_sym.range,
                selection_range=pred_sym.range,
            )
            # Find exact reference ranges from pred_sym to sym
            ranges: list[Range] = []
            for src_uri, r in workspace.references.get(scene_id, []):
                if src_uri == pred_sym.uri:
                    ranges.append(r)
            if not ranges:
                ranges = [pred_sym.range]

            incoming.append(
                CallHierarchyIncomingCall(
                    from_=caller_item,
                    from_ranges=ranges,
                )
            )
    return incoming


def compute_outgoing_calls(
    workspace: WorkspaceIndex,
    item: CallHierarchyItem,
) -> list[CallHierarchyOutgoingCall]:
    """Return all outgoing transition successors for the scene."""
    scene_id = item.detail.replace("Scene ID: ", "") if item.detail else item.name
    sym = workspace.get_scene(scene_id)
    if not sym:
        return []

    outgoing: list[CallHierarchyOutgoingCall] = []
    for succ_id in sorted(sym.successors):
        succ_sym = workspace.get_scene(succ_id)
        if succ_sym:
            target_item = CallHierarchyItem(
                name=succ_sym.display_name,
                kind=SymbolKind.Function,
                detail=f"Scene ID: {succ_sym.id}",
                uri=succ_sym.uri,
                range=succ_sym.range,
                selection_range=succ_sym.range,
            )
            # Find transition ranges from sym to succ_id
            ranges: list[Range] = []
            for src_uri, r in workspace.references.get(succ_id, []):
                if src_uri == sym.uri:
                    ranges.append(r)
            if not ranges:
                ranges = [sym.range]

            outgoing.append(
                CallHierarchyOutgoingCall(
                    to=target_item,
                    from_ranges=ranges,
                )
            )
    return outgoing
