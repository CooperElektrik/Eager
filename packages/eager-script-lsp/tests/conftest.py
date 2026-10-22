"""Shared test fixtures for eager-script-lsp."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from eager_script_lsp.server import create_server
from eager_script_lsp.workspace import WorkspaceIndex


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "assets" / "bg").mkdir(parents=True)
        (root / "assets" / "characters").mkdir(parents=True)
        (root / "locales").mkdir(parents=True)
        index = WorkspaceIndex(root)
        index.initialize()
        yield root, index


@pytest.fixture
def lsp_server():
    return create_server()
