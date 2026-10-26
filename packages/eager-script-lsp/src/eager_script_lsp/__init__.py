"""Full-featured Language Server Protocol (LSP) package for Eager-Script screenplays."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version("eager-script-lsp")
except (importlib.metadata.PackageNotFoundError, ImportError):
    __version__ = "0.7.0"

from eager_script_lsp.document import (
    ScriptDocument,
    SymbolOccurrence,
    SyntaxIssue,
    TokenSpan,
)
from eager_script_lsp.server import (
    EagerLanguageServer,
    create_server,
)
from eager_script_lsp.workspace import (
    AssetIndex,
    CharacterSymbol,
    SceneSymbol,
    VariableSymbol,
    WorkspaceIndex,
    path_to_uri,
    uri_to_path,
)

__all__ = [
    "AssetIndex",
    "CharacterSymbol",
    "EagerLanguageServer",
    "SceneSymbol",
    "ScriptDocument",
    "SymbolOccurrence",
    "SyntaxIssue",
    "TokenSpan",
    "VariableSymbol",
    "WorkspaceIndex",
    "__version__",
    "create_server",
    "path_to_uri",
    "uri_to_path",
]
