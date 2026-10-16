#!/usr/bin/env python3
"""Build and install Pillow-SIMD into a Python environment.

Pillow-SIMD is a drop-in fork of Pillow that adds SSE4/AVX2 kernels for resize,
alpha composition, blur, grayscale and channel operations.  It is the optional
software backend for ``eager-graphics``::

    pip install eager-graphics[software-simd]

Two details of Pillow-SIMD cannot be expressed as an ordinary package extra and
are handled here instead:

1. PyPI only publishes a source distribution, so the install always compiles on
   the local machine and needs the usual Pillow build prerequisites (a C
   compiler plus the JPEG and zlib development headers).  Those are checked up
   front so a missing header fails fast without disturbing the environment.
2. ``pillow-simd`` and ``pillow`` both install the top-level ``PIL`` package, so
   the regular Pillow distribution must be uninstalled first.  Installing both
   silently clobbers files, so this helper performs the swap explicitly and
   restores Pillow if the build fails or the result lacks a required extension.
3. A source build can succeed while silently dropping optional extensions such
   as ``_imagingft`` (FreeType text rendering).  The installed build is verified
   for the features eager-graphics needs before the swap is considered done.

For the faster AVX2 codepath the compiler is invoked with ``-mavx2`` (Pillow-SIMD
defaults to SSE4).  Only use AVX2 if every machine that will run the resulting
environment supports it.

Prerequisites (Debian/Ubuntu shown; adapt for your platform)::

    sudo apt-get install build-essential pkg-config libjpeg-dev zlib1g-dev \
        libfreetype-dev libwebp-dev

Usage:
    python scripts/install_pillow_simd.py                 # SSE4 build into .venv
    python scripts/install_pillow_simd.py --avx2          # AVX2 build
    python scripts/install_pillow_simd.py --python python3.12
    python scripts/install_pillow_simd.py --skip-deps-check
    python scripts/install_pillow_simd.py --dry-run       # print commands only
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SIMD_TARGETS = ("sse4", "avx2")
INSTALLERS = ("auto", "pip", "uv")
PILLOW_REQUIREMENT = "Pillow>=10.0.0"
PILLOW_SIMD_REQUIREMENT = "pillow-simd>=10.0.0"

# Mirrors the build requirements eager-graphics relies on: JPEG and zlib are
# hard requirements of Pillow itself, while FreeType provides the ``_imagingft``
# extension that ``ImageFont.truetype`` (dialogue text) needs.  ``jpeglib.h``
# intentionally relies on the includer to provide ``size_t`` and ``FILE``, so
# those headers come first.
_DEP_PROBE_SOURCE = """\
#include <stddef.h>
#include <stdio.h>
#include <jpeglib.h>
#include <zlib.h>
#include <ft2build.h>
#include FT_FREETYPE_H
int main(void) { return 0; }
"""

_DEP_HINT = """\
Pillow-SIMD compiles from source and needs the JPEG, zlib and FreeType
development files (FreeType is required for TrueType text rendering).
Install them for your platform and re-run:
  Debian/Ubuntu : sudo apt-get install build-essential pkg-config \\
                    libjpeg-dev zlib1g-dev libfreetype-dev libwebp-dev
  Fedora/RHEL   : sudo dnf install gcc pkgconf-pkg-config libjpeg-turbo-devel \\
                    zlib-devel freetype-devel libwebp-devel
  Arch          : sudo pacman -S base-devel pkgconf libjpeg-turbo zlib freetype2 libwebp
  macOS (brew)  : brew install pkg-config jpeg zlib freetype webp
Pass --skip-deps-check to attempt the build anyway."""


def _default_python() -> str:
    """Return the workspace ``.venv`` interpreter if present, else this one."""
    repo_root = Path(__file__).resolve().parents[1]
    for candidate in (
        repo_root / ".venv" / "bin" / "python",
        repo_root / ".venv" / "Scripts" / "python.exe",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _is_workspace_venv(python: str) -> bool:
    """Return True if *python* belongs to the repository's ``.venv``."""
    venv = (Path(__file__).resolve().parents[1] / ".venv").resolve()
    try:
        # Compare the containing venv directory rather than the interpreter
        # itself, which is usually a symlink to a system Python.
        candidate = Path(python).absolute().parent.parent.resolve()
    except OSError:
        return False
    return candidate == venv


def _compiler(target: str) -> list[str]:
    """Return the C compiler command (including SIMD flags for *target*)."""
    tokens = (os.environ.get("CC") or "cc").split()
    if target == "avx2" and "-mavx2" not in tokens:
        tokens.append("-mavx2")
    return tokens


def _build_env(target: str) -> dict[str, str]:
    """Return the environment used to compile Pillow-SIMD for *target*."""
    env = dict(os.environ)
    env["CC"] = " ".join(_compiler(target))
    return env


def _freetype_cflags() -> list[str]:
    """Return include flags for FreeType, via pkg-config or known locations."""
    if shutil.which("pkg-config"):
        result = subprocess.run(
            ["pkg-config", "--cflags", "freetype2"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.split()
    for directory in ("/usr/include/freetype2", "/usr/local/include/freetype2"):
        if (Path(directory) / "ft2build.h").is_file():
            return [f"-I{directory}"]
    return []


def _check_native_deps(target: str) -> tuple[bool, str]:
    """Compile a tiny probe to confirm the JPEG/zlib/FreeType build deps exist.

    Returns ``(ok, detail)``.  Platforms where a POSIX ``cc`` probe does not
    apply (Windows, or no compiler on PATH) report ``ok`` and let the real build
    surface any error.
    """
    if platform.system() == "Windows":
        return True, "skipped on Windows"
    compiler = _compiler(target)
    if shutil.which(compiler[0]) is None:
        return True, f"compiler {compiler[0]!r} not found; skipping probe"
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "probe.c"
        binary = Path(tmp) / "probe"
        source.write_text(_DEP_PROBE_SOURCE, encoding="utf-8")
        result = subprocess.run(
            [
                *compiler,
                *_freetype_cflags(),
                str(source),
                "-ljpeg",
                "-lz",
                "-lfreetype",
                "-o",
                str(binary),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    return result.returncode == 0, result.stderr.strip()


def _resolve_installer(requested: str) -> str:
    """Return ``"uv"`` or ``"pip"`` for *requested* (``auto`` prefers uv)."""
    if requested != "auto":
        return requested
    return "uv" if shutil.which("uv") else "pip"


def _uninstall_cmd(installer: str, python: str) -> list[str]:
    if installer == "uv":
        return ["uv", "pip", "uninstall", "--python", python, "pillow"]
    return [python, "-m", "pip", "uninstall", "-y", "pillow"]


def _install_cmd(installer: str, python: str) -> list[str]:
    if installer == "uv":
        return [
            "uv", "pip", "install", "--python", python, "--no-cache", "--reinstall",
            "--no-binary", "pillow-simd", PILLOW_SIMD_REQUIREMENT,
        ]
    return [
        python, "-m", "pip", "install", "--no-cache-dir", "--force-reinstall",
        "--no-binary", "pillow-simd", PILLOW_SIMD_REQUIREMENT,
    ]


def _restore_cmd(installer: str, python: str) -> list[str]:
    if installer == "uv":
        return ["uv", "pip", "install", "--python", python, "--no-cache", PILLOW_REQUIREMENT]
    return [python, "-m", "pip", "install", "--no-cache-dir", PILLOW_REQUIREMENT]


def _run(cmd: list[str], *, env: dict[str, str] | None, dry_run: bool) -> int:
    display = " ".join(cmd)
    if "\n" in display:
        display = display.split("\n", 1)[0] + " ..."
    print("$ " + display, file=sys.stderr)
    if dry_run:
        return 0
    return subprocess.call(cmd, env=env)


def _pip_available(installer: str, python: str) -> bool:
    if installer == "uv":
        return shutil.which("uv") is not None
    return subprocess.run(
        [python, "-m", "pip", "--version"], capture_output=True, check=False
    ).returncode == 0


def _verify(python: str, *, dry_run: bool) -> int:
    """Confirm the build imports with the imaging features eager-graphics needs."""
    check = (
        "import PIL, PIL._imaging\n"
        "try:\n"
        "    import PIL._imagingft\n"
        "except ImportError as exc:\n"
        "    raise SystemExit('error: build lacks FreeType/TrueType support: %s' % exc)\n"
        "from PIL import features\n"
        "print('Pillow build:', PIL.__version__)\n"
        "print('  core      :', PIL._imaging.__file__)\n"
        "print('  freetype2 :', features.check('freetype2'))\n"
        "print('  webp      :', features.check('webp'))\n"
    )
    return _run([python, "-c", check], env=None, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--python",
        default=_default_python(),
        help="Interpreter whose environment is modified (default: .venv or current).",
    )
    parser.add_argument(
        "--simd",
        dest="simd",
        choices=SIMD_TARGETS,
        default=None,
        metavar="{sse4,avx2}",
        help="Compile with SSE4 (default) or AVX2 code paths.",
    )
    parser.add_argument(
        "--avx2",
        action="store_true",
        help="Shorthand for --simd avx2.",
    )
    parser.add_argument(
        "--installer",
        choices=INSTALLERS,
        default="auto",
        help="Package installer to use (default: uv if available, else pip).",
    )
    parser.add_argument(
        "--skip-deps-check",
        action="store_true",
        help="Skip the JPEG/zlib/FreeType header probe and attempt the build regardless.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the installer commands without executing them.",
    )
    args = parser.parse_args(argv)

    target = "avx2" if args.avx2 else (args.simd or "sse4")
    python = args.python
    env = _build_env(target)
    installer = _resolve_installer(args.installer)

    if not _pip_available(installer, python):
        print(
            f"error: no working '{installer}' installer for {python}.\n"
            "Install uv (https://docs.astral.sh/uv/) or pip in that environment.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Installing {PILLOW_SIMD_REQUIREMENT} ({target}) into {python} via {installer}\n"
        "Note: this compiles from source and replaces the regular Pillow distribution.\n",
        file=sys.stderr,
    )
    if _is_workspace_venv(python):
        print(
            "Warning: this is the workspace .venv. A later 'uv sync' reinstalls the regular\n"
            "Pillow dev dependency and overwrites the SIMD build, so re-run this script\n"
            "after each sync.\n",
            file=sys.stderr,
        )

    # 0. Fail fast if the C build dependencies are missing, before Pillow is touched.
    if not args.skip_deps_check and not args.dry_run:
        ok, detail = _check_native_deps(target)
        if not ok:
            print(f"error: build dependency check failed.\n{_DEP_HINT}", file=sys.stderr)
            if detail:
                print(f"\nprobe output:\n{detail}", file=sys.stderr)
            return 1

    # 1. Remove regular Pillow so the two PIL providers cannot clobber each other.
    if _run(_uninstall_cmd(installer, python), env=None, dry_run=args.dry_run):
        print("error: failed to uninstall pillow", file=sys.stderr)
        return 1

    # 2. Build and install the source-only SIMD fork.
    if _run(_install_cmd(installer, python), env=env, dry_run=args.dry_run):
        print("error: failed to build/install pillow-simd", file=sys.stderr)
        if not args.dry_run:
            print("Restoring the regular Pillow distribution...", file=sys.stderr)
            _run(_restore_cmd(installer, python), env=None, dry_run=False)
        return 1

    # 3. Confirm the environment imports the SIMD build with FreeType support.
    if _verify(python, dry_run=args.dry_run) and not args.dry_run:
        print(
            "error: the installed build is missing features eager-graphics needs.",
            file=sys.stderr,
        )
        print("Restoring the regular Pillow distribution...", file=sys.stderr)
        _run(_restore_cmd(installer, python), env=None, dry_run=False)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
