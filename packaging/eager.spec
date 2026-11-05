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
    os.path.join(REPO_ROOT, "packages", "eager-core", "src"),
    os.path.join(REPO_ROOT, "packages", "eager-script", "src"),
    os.path.join(REPO_ROOT, "packages", "eager-runtime", "src"),
    os.path.join(REPO_ROOT, "packages", "eager-graphics", "src"),
    os.path.join(REPO_ROOT, "packages", "eager-script-lsp", "src"),
]

EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples")
ASSETS_DIR = os.path.join(EXAMPLES_DIR, "assets")
LOCALES_DIR = os.path.join(EXAMPLES_DIR, "locales")
DEMO_STORY = os.path.join(EXAMPLES_DIR, "demo_story.es")

TEMPLATE_DIR = os.path.join(
    REPO_ROOT, "packages", "eager-runtime", "src", "eager_runtime", "template"
)

# ---------------------------------------------------------------------------
# Hidden imports
#
# Several backends are resolved lazily via ``__getattr__`` in
# ``eager_graphics.renderers`` and via entry points in
# ``eager_core.protocols``.  PyInstaller's dependency scanner cannot see
# those, so we declare them explicitly.
# ---------------------------------------------------------------------------

hiddenimports: list[str] = [
    # Core
    "eager_core.audio",
    "eager_core.backlog",
    "eager_core.characters",
    "eager_core.dispatcher",
    "eager_core.easing",
    "eager_core.events",
    "eager_core.exceptions",
    "eager_core.headless",
    "eager_core.i18n",
    "eager_core.input",
    "eager_core.layout",
    "eager_core.lighting",
    "eager_core.persistent",
    "eager_core.preferences",
    "eager_core.protocols",
    "eager_core.saves",
    "eager_core.state",
    "eager_core.storage",
    "eager_core.text",
    "eager_core.theme",
    "eager_core.timeline",
    "eager_core.timing",
    "eager_core.types",
    "eager_core.ui_state",
    "eager_core.watcher",
    # Script
    "eager_script.ast",
    "eager_script.cli",
    "eager_script.expr",
    "eager_script.graph",
    "eager_script.hooks",
    "eager_script.parser",
    "eager_script.validator",
    # Runtime
    "eager_runtime.assets",
    "eager_runtime.cli",
    "eager_runtime.i18n",
    "eager_runtime.project",
    "eager_runtime.player",
    "eager_runtime.runtime",
    "eager_runtime.session",
    # Graphics core
    "eager_graphics.audio",
    "eager_graphics.compositor",
    "eager_graphics.director",
    "eager_graphics.fonts",
    "eager_graphics.particles",
    "eager_graphics.player",
    "eager_graphics.screens",
    "eager_graphics.stage",
    "eager_graphics.ui_components",
    # Renderer backends (lazy-loaded via __getattr__ / entry points)
    "eager_graphics.renderers.pil",
    "eager_graphics.renderers.pyglet",
    # Audio backends
    "eager_graphics.audio.miniaudio",
    "eager_graphics.audio.pyglet",
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
    datas.append((TEMPLATE_DIR, "eager_runtime/template"))

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    [os.path.join(REPO_ROOT, "packages", "eager-runtime", "src", "eager_runtime", "__main__.py")],
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
