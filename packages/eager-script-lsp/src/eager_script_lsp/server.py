"""Language server protocol implementation for Eager-Script screenplays."""

from __future__ import annotations

import importlib.metadata
import logging
from pathlib import Path
from typing import Any

from lsprotocol import types
from pygls.lsp.server import LanguageServer

try:
    _server_version = importlib.metadata.version("eager-script-lsp")
except (importlib.metadata.PackageNotFoundError, ImportError):
    _server_version = "0.9.0"

_SERVER_VERSION: str = _server_version
from eager_script_lsp.document import ScriptDocument
from eager_script_lsp.features.completion import compute_completions
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.features.hover import compute_hover
from eager_script_lsp.features.navigation import (
    compute_definition,
    compute_document_symbols,
    compute_references,
    compute_workspace_symbols,
)
from eager_script_lsp.features.tokens import (
    LEGEND,
    compute_document_links,
    compute_folding_ranges,
    compute_semantic_tokens,
)
from eager_script_lsp.workspace import WorkspaceIndex, uri_to_path

logger = logging.getLogger(__name__)

__all__ = [
    "EagerLanguageServer",
    "create_server",
]


class EagerLanguageServer(LanguageServer):
    """Eager-Script Language Server."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__("eager-script-lsp", _SERVER_VERSION, *args, **kwargs)
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

    def _validate_and_publish(uri: str, *, check_disk_assets: bool = True) -> None:
        doc = _get_or_sync_doc(uri)
        if doc is not None:
            diags = compute_diagnostics(
                doc, server.workspace_index, check_disk_assets=check_disk_assets
            )
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
            if params.content_changes and getattr(params.content_changes[-1], "range", None) is None:
                text = params.content_changes[-1].text
            else:
                return
        server.workspace_index.update_document(uri, text)
        _validate_and_publish(uri, check_disk_assets=False)

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
            server.text_document_publish_diagnostics(
                types.PublishDiagnosticsParams(uri=uri, diagnostics=[])
            )
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

    @server.feature(types.TEXT_DOCUMENT_SEMANTIC_TOKENS_FULL, LEGEND)
    def on_semantic_tokens(params: types.SemanticTokensParams) -> types.SemanticTokens:
        doc = _get_or_sync_doc(params.text_document.uri)
        if doc is None:
            return types.SemanticTokens(data=[])
        return compute_semantic_tokens(doc)

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

    return server
