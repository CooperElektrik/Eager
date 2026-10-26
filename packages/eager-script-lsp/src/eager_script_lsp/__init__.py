"""Full-featured Language Server Protocol (LSP) package for Eager-Script screenplays."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version("eager-script-lsp")
except (importlib.metadata.PackageNotFoundError, ImportError):
    __version__ = "0.6.0"
