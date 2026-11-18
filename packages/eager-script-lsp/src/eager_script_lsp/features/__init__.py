"""LSP feature providers for Eager-Script."""

from __future__ import annotations

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

__all__ = [
    "LEGEND",
    "compute_completions",
    "compute_definition",
    "compute_diagnostics",
    "compute_document_links",
    "compute_document_symbols",
    "compute_folding_ranges",
    "compute_hover",
    "compute_references",
    "compute_semantic_tokens",
    "compute_workspace_symbols",
]
