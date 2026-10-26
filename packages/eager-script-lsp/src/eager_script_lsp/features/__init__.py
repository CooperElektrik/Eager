"""LSP feature providers for Eager-Script."""

from __future__ import annotations

from eager_script_lsp.features.completion import compute_completions
from eager_script_lsp.features.diagnostics import compute_diagnostics
from eager_script_lsp.features.hover import compute_hover
from eager_script_lsp.features.lenses import (
    compute_code_lenses,
    compute_inlay_hints,
)
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

__all__ = [
    "LEGEND",
    "compute_code_actions",
    "compute_code_lenses",
    "compute_color_presentation",
    "compute_completions",
    "compute_definition",
    "compute_diagnostics",
    "compute_document_colors",
    "compute_document_links",
    "compute_document_symbols",
    "compute_folding_ranges",
    "compute_hover",
    "compute_incoming_calls",
    "compute_inlay_hints",
    "compute_outgoing_calls",
    "compute_references",
    "compute_rename",
    "compute_semantic_tokens",
    "compute_workspace_symbols",
    "prepare_call_hierarchy",
    "prepare_rename",
]
