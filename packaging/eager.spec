# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building standalone Eager exports.

Builds a one-file executable.  Run from the repo root::

    pyinstaller packaging/eager.spec --noconfirm

Output lands in ``dist/eager`` (a single executable) on each platform.
Data files (assets, locales, demo story) are NOT embedded — they are
copied alongside the executable by ``packaging/build_export.py``.
"""

from __future__ import annotations

import os
import sys

from PyInstaller.building.build_main import Analysis  # type: ignore[import]
from PyInstaller.building.api import PYZ, EXE  # type: ignore[import]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.getcwd())

SRC_DIRS = [
    os.path.join(REPO_ROOT, "packages", "eager", "src"),
    os.path.join(REPO_ROOT, "packages", "eager-script-lsp", "src"),
]

EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples")
ASSETS_DIR = os.path.join(EXAMPLES_DIR, "assets")
LOCALES_DIR = os.path.join(EXAMPLES_DIR, "locales")
DEMO_STORY = os.path.join(EXAMPLES_DIR, "demo_story.es")

TEMPLATE_DIR = os.path.join(
    REPO_ROOT, "packages", "eager", "src", "eager", "template"
)

# ---------------------------------------------------------------------------
# Hidden imports
#
# Several backends and players are resolved lazily via ``__getattr__`` in
# ``eager.ui``, ``eager.backends.renderers``, and ``eager.backends.audio``.
# PyInstaller's dependency scanner cannot see those, so we declare them explicitly.
# ---------------------------------------------------------------------------

hiddenimports: list[str] = [
    # Core
    "eager.core.assets",
    "eager.core.audio",
    "eager.core.backlog",
    "eager.core.characters",
    "eager.core.dispatcher",
    "eager.core.easing",
    "eager.core.events",
    "eager.core.exceptions",
    "eager.core.i18n",
    "eager.core.input",
    "eager.core.layout",
    "eager.core.lighting",
    "eager.core.persistent",
    "eager.core.preferences",
    "eager.core.saves",
    "eager.core.state",
    "eager.core.storage",
    "eager.core.text",
    "eager.core.theme",
    "eager.core.timeline",
    "eager.core.timing",
    "eager.core.types",
    "eager.core.ui_state",
    "eager.core.watcher",
    # Script
    "eager.script.ast",
    "eager.script.expr",
    "eager.script.graph",
    "eager.script.hooks",
    "eager.script.includes",
    "eager.script.parser",
    "eager.script.project",
    "eager.script.tokens",
    "eager.script.validator",
    # VM
    "eager.vm.i18n",
    "eager.vm.runtime",
    # Stage
    "eager.stage.compositor",
    "eager.stage.director",
    "eager.stage.fonts",
    "eager.stage.particles",
    "eager.stage.stage",
    # UI & Players (pil_player / pyglet_player are lazy-loaded via __getattr__)
    "eager.ui.components",
    "eager.ui.pil_player",
    "eager.ui.player",
    "eager.ui.pyglet_player",
    "eager.ui.screens",
    "eager.ui.terminal_player",
    # Session & CLI
    "eager.session.session",
    "eager.cli",
    # Backends (lazy-loaded via __getattr__)
    "eager.backends.exceptions",
    "eager.backends.fonts",
    "eager.backends.types",
    "eager.backends.renderers.null",
    "eager.backends.renderers.pil",
    "eager.backends.renderers.pyglet",
    "eager.backends.audio.null",
    "eager.backends.audio.miniaudio",
    "eager.backends.audio.pyglet",
    # Optional third-party backends
    "miniaudio",
    "PIL",
    "pyglet",
]

# ---------------------------------------------------------------------------
# Data files (embedded in the one-file executable; also copied to disk
# by build_export.py so the runtime can access them as real files)
# ---------------------------------------------------------------------------

datas: list[tuple[str, str]] = []

if os.path.isdir(ASSETS_DIR):
    datas.append((ASSETS_DIR, "examples/assets"))

if os.path.isdir(LOCALES_DIR):
    datas.append((LOCALES_DIR, "examples/locales"))

if os.path.isfile(DEMO_STORY):
    datas.append((DEMO_STORY, "examples"))

if os.path.isdir(TEMPLATE_DIR):
    datas.append((TEMPLATE_DIR, "eager/template"))

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    [os.path.join(REPO_ROOT, "packages", "eager", "src", "eager", "cli", "__main__.py")],
    pathex=SRC_DIRS,
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="eager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # One-file mode (default): everything is bundled into a single executable.
    # exclude_binaries=False (default) appends the PKG archive to the EXE.
    # append_pkg=True (default) keeps the default one-file behaviour.
)
