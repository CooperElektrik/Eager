"""Language server protocol implementation for Eager-Script screenplays."""

from __future__ import annotations

import logging
from pathlib import Path

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.completion import compute_completions
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.features.hover import compute_hover
from eager_script_lsp.features.lenses import compute_code_lenses, compute_inlay_hints
from eager_script_lsp.features.navigation import (
    compute_definition,
    compute_document_symbols,
    compute_incoming_calls,
    compute_outgoing_calls,
    compute_references,
    compute_workspace_symbols,
    prepare_call_hierarchy,
)
from eager_script_lsp.features.refactor import (
    compute_code_actions,
    compute_rename,
    prepare_rename,
)
from eager_script_lsp.features.tokens import (
    LEGEND,
    compute_color_presentation,
    compute_document_colors,
    compute_document_links,
    compute_folding_ranges,
    compute_semantic_tokens,
)
from eager_script_lsp.workspace import WorkspaceIndex, uri_to_path

logger = logging.getLogger(__name__)


class EagerLanguageServer(LanguageServer):
    """Eager-Script Language Server."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__("eager-script-lsp", "0.4.0", *args, **kwargs)
        self.workspace_index: WorkspaceIndex = WorkspaceIndex(Path.cwd())


def create_server() -> EagerLanguageServer:
    """Create and configure an EagerLanguageServer instance with all LSP features."""
    server = EagerLanguageServer()

    @server.feature(types.INITIALIZE)
    def on_initialize(params: types.InitializeParams) -> None:
        root_path = Path.cwd()
        if params.root_uri:
            root_path = uri_to_path(params.root_uri)
        elif params.workspace_folders and len(params.workspace_folders) > 0:
            root_path = uri_to_path(params.workspace_folders[0].uri)

        server.workspace_index = WorkspaceIndex(root_path)
        server.workspace_index.initialize()

    def _get_or_sync_doc(uri: str) -> ScriptDocument | None:
        doc = server.workspace_index.get_document(uri)
        if doc is None:
            try:
                pygls_doc = server.workspace.get_text_document(uri)
                doc = server.workspace_index.update_document(uri, pygls_doc.source)
            except (KeyError, ValueError, OSError) as e:
                logger.debug("Could not sync doc from workspace for %s: %s", uri, e)
        return doc

    def _validate_and_publish(uri: str) -> None:
        doc = _get_or_sync_doc(uri)
        if doc is not None:
            diags = compute_diagnostics(doc, server.workspace_index)
            server.text_document_publish_diagnostics(
                types.PublishDiagnosticsParams(uri=uri, diagnostics=diags)
            )

    def _validate_and_publish_all() -> None:
        for doc_uri in list(server.workspace_index.documents.keys()):
            if server.workspace_index._is_excluded_uri(doc_uri):
                continue
            _validate_and_publish(doc_uri)

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def on_did_open(params: types.DidOpenTextDocumentParams) -> None:
        uri = params.text_document.uri
        try:
            pygls_doc = server.workspace.get_text_document(uri)
            text = pygls_doc.source
        except (KeyError, ValueError, OSError):
            text = params.text_document.text
        server.workspace_index.update_document(uri, text)
        _validate_and_publish_all()

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def on_did_change(params: types.DidChangeTextDocumentParams) -> None:
        uri = params.text_document.uri
        try:
            pygls_doc = server.workspace.get_text_document(uri)
            text = pygls_doc.source
        except (KeyError, ValueError, OSError):
            if params.content_changes:
                text = params.content_changes[-1].text
            else:
                return
        server.workspace_index.update_document(uri, text)
        _validate_and_publish_all()

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE)
    def on_did_save(params: types.DidSaveTextDocumentParams) -> None:
        uri = params.text_document.uri
        try:
            pygls_doc = server.workspace.get_text_document(uri)
            server.workspace_index.update_document(uri, pygls_doc.source)
        except (KeyError, ValueError, OSError) as e:
            logger.debug("Could not sync doc on save for %s: %s", uri, e)
        _validate_and_publish_all()

    @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
    def on_did_close(params: types.DidCloseTextDocumentParams) -> None:
        uri = params.text_document.uri
        path = uri_to_path(uri)
        if path.exists():
            try:
                server.workspace_index.update_document(uri, path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as e:
                logger.debug("Failed to reload closed doc from disk for %s: %s", uri, e)
        else:
            server.workspace_index.remove_document(uri)
        _validate_and_publish_all()

    @server.feature(
        types.TEXT_DOCUMENT_COMPLETION,
        types.CompletionOptions(
            trigger_characters=[">", "?", "~", "@", "$", "[", "{", "(", ":", " ", "=", "/"],
            resolve_provider=False,
        ),
    )
    def on_completion(params: types.CompletionParams) -> types.CompletionList:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return types.CompletionList(is_incomplete=False, items=[])
        return compute_completions(doc, server.workspace_index, params.position)

    @server.feature(types.TEXT_DOCUMENT_HOVER)
    def on_hover(params: types.HoverParams) -> types.Hover | None:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return None
        return compute_hover(doc, server.workspace_index, params.position)

    @server.feature(types.TEXT_DOCUMENT_DEFINITION)
    def on_definition(params: types.DefinitionParams):
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return None
        return compute_definition(doc, server.workspace_index, params.position)

    @server.feature(types.TEXT_DOCUMENT_REFERENCES)
    def on_references(params: types.ReferenceParams) -> list[types.Location]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_references(
            doc,
            server.workspace_index,
            params.position,
            include_declaration=params.context.include_declaration,
        )

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def on_document_symbol(params: types.DocumentSymbolParams) -> list[types.DocumentSymbol]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_document_symbols(doc)

    @server.feature(types.WORKSPACE_SYMBOL)
    def on_workspace_symbol(params: types.WorkspaceSymbolParams) -> list[types.SymbolInformation]:
        return compute_workspace_symbols(server.workspace_index, params.query)

    @server.feature(types.TEXT_DOCUMENT_PREPARE_RENAME)
    def on_prepare_rename(params: types.PrepareRenameParams) -> types.Range | None:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return None
        return prepare_rename(doc, server.workspace_index, params.position)

    @server.feature(types.TEXT_DOCUMENT_RENAME, types.RenameOptions(prepare_provider=True))
    def on_rename(params: types.RenameParams) -> types.WorkspaceEdit | None:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return None
        return compute_rename(doc, server.workspace_index, params.position, params.new_name)

    @server.feature(types.TEXT_DOCUMENT_CODE_ACTION)
    def on_code_action(params: types.CodeActionParams) -> list[types.CodeAction]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_code_actions(doc, server.workspace_index, params.range, params.context)

    @server.feature(types.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, LEGEND)
    def on_semantic_tokens(params: types.SemanticTokensParams) -> types.SemanticTokens:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return types.SemanticTokens(data=[])
        return compute_semantic_tokens(doc)

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_COLOR)
    def on_document_color(params: types.DocumentColorParams) -> list[types.ColorInformation]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_document_colors(doc)

    @server.feature(types.TEXT_DOCUMENT_COLOR_PRESENTATION)
    def on_color_presentation(params: types.ColorPresentationParams) -> list[types.ColorPresentation]:
        return compute_color_presentation(params.color, params.range)

    @server.feature(types.TEXT_DOCUMENT_FOLDING_RANGE)
    def on_folding_range(params: types.FoldingRangeParams) -> list[types.FoldingRange]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_folding_ranges(doc)

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_LINK, types.DocumentLinkOptions(resolve_provider=False))
    def on_document_link(params: types.DocumentLinkParams) -> list[types.DocumentLink]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_document_links(doc, server.workspace_index)

    @server.feature(types.TEXT_DOCUMENT_CODE_LENS, types.CodeLensOptions(resolve_provider=False))
    def on_code_lens(params: types.CodeLensParams) -> list[types.CodeLens]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_code_lenses(doc, server.workspace_index)

    @server.feature(types.TEXT_DOCUMENT_INLAY_HINT, types.InlayHintOptions(resolve_provider=False))
    def on_inlay_hint(params: types.InlayHintParams) -> list[types.InlayHint]:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return []
        return compute_inlay_hints(doc, server.workspace_index, params.range)

    @server.feature(types.TEXT_DOCUMENT_PREPARE_CALL_HIERARCHY)
    def on_prepare_call_hierarchy(params: types.CallHierarchyPrepareParams) -> list[types.CallHierarchyItem] | None:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return None
        return prepare_call_hierarchy(doc, server.workspace_index, params.position)

    @server.feature(types.CALL_HIERARCHY_INCOMING_CALLS)
    def on_incoming_calls(params: types.CallHierarchyIncomingCallsParams) -> list[types.CallHierarchyIncomingCall]:
        return compute_incoming_calls(server.workspace_index, params.item)

    @server.feature(types.CALL_HIERARCHY_OUTGOING_CALLS)
    def on_outgoing_calls(params: types.CallHierarchyOutgoingCallsParams) -> list[types.CallHierarchyOutgoingCall]:
        return compute_outgoing_calls(server.workspace_index, params.item)

    return server
