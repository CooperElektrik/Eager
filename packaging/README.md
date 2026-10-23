# Eager Export / Build Tooling

This directory contains the build configuration for producing standalone Eager
exports for **Windows** and **Debian/Ubuntu**.

## Layout

```
packaging/
├── README.md              # this file
├── eager.spec             # PyInstaller spec (one-file executable)
├── build_export.py        # build orchestrator
├── windows/
│   └── eager.iss          # Inno Setup installer script
└── debian/
    └── DEBIAN/
        └── control        # .deb package control metadata
```

## Prerequisites

PyInstaller is intentionally **not** a project dependency (see `AGENTS.md`).
Install it in the active environment before building:

```bash
uv pip install pyinstaller
# or
pip install pyinstaller
```

For Debian `.deb` packaging, `dpkg-deb` must be on `PATH` (installed by the
`dpkg-dev` package on Debian/Ubuntu).

For Windows Inno Setup packaging, `iscc` (Inno Setup compiler) must be on
`PATH`.

## Usage

Build for the current platform:

```bash
python packaging/build_export.py
```

Build for a specific platform:

```bash
python packaging/build_export.py --platform windows --output dist/windows
python packaging/build_export.py --platform debian --output dist/debian
```

### Output

- **`dist/<platform>/`** — standalone application directory containing the
  `eager` executable plus `examples/` and `eager_runtime/` data folders.
- **`dist/windows-installer/`** — Inno Setup `.exe` installer (Windows only).
- **`dist/debian.deb`** — Debian package (Debian/Ubuntu only).

## How it works

1. `build_export.py` invokes PyInstaller against `packaging/eager.spec`.
2. PyInstaller produces a **one-file executable** (`eager` / `eager.exe`)
   that bundles the Python interpreter, all Eager packages, and the optional
   renderer backends (Pyglet, PIL, miniaudio).
3. Data files (example assets, locales, demo story, template project) are
   copied alongside the executable so the runtime can access them as real
   files.
4. On Windows, Inno Setup wraps the directory into a `.exe` installer.
5. On Debian, `dpkg-deb` wraps the directory into a `.deb` package installed
   under `/opt/eager/` with a `/usr/bin/eager` wrapper script.

## Platform notes

| Platform | Output | Notes |
|----------|--------|-------|
| Linux (Debian/Ubuntu) | `eager` executable + `.deb` | 64-bit only; depends on `libgl1`, `libjpeg62`, `zlib1g`, `libfreetype6`, `libwebp7` |
| Windows | `eager.exe` + Inno Setup `.exe` | Requires Visual C++ Redistributable (bundled by installer) |

## Related

- `packaging/eager.spec` — PyInstaller spec; edit here to add hidden imports or data files.
- `packaging/windows/eager.iss` — Inno Setup script; edit to customize the Windows installer.
- `packaging/debian/DEBIAN/control` — Debian control file; edit to change package metadata or dependencies.
