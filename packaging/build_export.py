#!/usr/bin/env python3
"""Build standalone Eager exports for Windows and Debian.

Usage::

    python packaging/build_export.py                    # build for current platform
    python packaging/build_export.py --platform windows --output dist/windows
    python packaging/build_export.py --platform debian  --output dist/debian

This script:

1. Runs PyInstaller against ``packaging/eager.spec`` (one-file mode).
2. Post-processes the output into a platform-specific layout:
   - Copies the standalone executable into the output folder.
   - Copies data files (assets, locales, demo story) alongside it.
3. (Optional) Packages an Inno Setup installer on Windows.
4. (Optional) Packages a .deb on Debian/Ubuntu.

PyInstaller must be installed in the active environment (it is intentionally
not a project dependency — see AGENTS.md).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = REPO_ROOT / "packaging" / "eager.spec"


def _run(cmd: list[str], *, cwd: Path | None = None, check: bool = True) -> int:
    print("$ " + " ".join(cmd))
    return subprocess.call(cmd, cwd=str(cwd) if cwd else None)


def _ensure_pyinstaller() -> None:
    """Verify PyInstaller is available; give a helpful error if not."""
    try:
        import PyInstaller  # noqa: F401
    except ImportError as exc:
        print(
            "error: PyInstaller is not installed in this environment.\n"
            "Install it first:\n"
            "  uv pip install pyinstaller\n"
            "or:\n"
            "  pip install pyinstaller",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


def build_pyinstaller(platform: str, output: Path) -> Path:
    """Run PyInstaller and return the path to the built app directory."""
    _ensure_pyinstaller()

    dist_dir = REPO_ROOT / "dist"
    build_dir = REPO_ROOT / "build"

    # Clean previous outputs for a deterministic build.
    for d in (dist_dir, build_dir):
        if d.exists():
            shutil.rmtree(d)

    cmd = [
        "pyinstaller",
        str(SPEC_FILE),
        "--noconfirm",
        "--clean",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
    ]

    rc = _run(cmd)
    if rc != 0:
        raise SystemExit(f"PyInstaller failed with exit code {rc}")

    # PyInstaller one-file output is a single executable in dist/eager
    exe_path = dist_dir / "eager"
    if sys.platform.startswith("win"):
        exe_path = dist_dir / "eager.exe"

    if not exe_path.exists():
        raise SystemExit(f"expected PyInstaller output at {exe_path}, not found")

    # Create the platform-specific output folder.
    if output.exists():
        shutil.rmtree(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    # Copy the executable.
    shutil.copy2(exe_path, output / exe_path.name)
    if not sys.platform.startswith("win"):
        (output / exe_path.name).chmod(0o755)

    # Copy data files alongside the executable so the runtime can access them.
    examples_dir = REPO_ROOT / "examples"
    assets_src = examples_dir / "assets"
    locales_src = examples_dir / "locales"
    demo_story_src = examples_dir / "demo_story.es"
    template_src = (
        REPO_ROOT / "packages" / "eager-runtime" / "src" / "eager_runtime" / "template"
    )

    if assets_src.exists():
        shutil.copytree(assets_src, output / "examples" / "assets")
    if locales_src.exists():
        shutil.copytree(locales_src, output / "examples" / "locales")
    if demo_story_src.exists():
        shutil.copy2(demo_story_src, output / "examples" / "demo_story.es")
    if template_src.exists():
        shutil.copytree(template_src, output / "eager_runtime" / "template")

    print(f"\nBuilt {platform} export at: {output}")
    return output


def package_windows(app_dir: Path, output: Path) -> None:
    """Wrap the Windows app dir into an Inno Setup installer (.exe)."""
    iss = REPO_ROOT / "packaging" / "windows" / "eager.iss"
    if not iss.exists():
        print(f"warning: Inno Setup script not found at {iss}; skipping installer", file=sys.stderr)
        return

    iscc = shutil.which("iscc")
    if iscc is None:
        print(
            "warning: 'iscc' (Inno Setup compiler) not found on PATH; skipping installer",
            file=sys.stderr,
        )
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        iscc,
        f"/DAppSourceDir={app_dir}",
        f"/DOutputDir={output}",
        str(iss),
    ]
    rc = _run(cmd)
    if rc != 0:
        raise SystemExit(f"Inno Setup failed with exit code {rc}")
    print(f"\nWindows installer at: {output}")


def package_debian(app_dir: Path, output: Path) -> None:
    """Wrap the Linux app dir into a .deb package."""
    debian_dir = REPO_ROOT / "packaging" / "debian"
    control = debian_dir / "DEBIAN" / "control"
    if not control.exists():
        print(f"warning: debian control file not found at {control}; skipping .deb", file=sys.stderr)
        return

    dpkg_deb = shutil.which("dpkg-deb")
    if dpkg_deb is None:
        print(
            "warning: 'dpkg-deb' not found on PATH; skipping .deb packaging",
            file=sys.stderr,
        )
        return

    staging = output / "staging"
    if staging.exists():
        shutil.rmtree(staging)

    # /opt/eager/<app contents>
    opt_eager = staging / "opt" / "eager"
    opt_eager.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_dir, opt_eager / "eager")

    # /usr/bin/eager wrapper script
    usr_bin = staging / "usr" / "bin"
    usr_bin.mkdir(parents=True, exist_ok=True)
    wrapper = usr_bin / "eager"
    wrapper.write_text(
        "#!/bin/sh\nexec /opt/eager/eager/eager \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)

    # DEBIAN/control
    deb_control = staging / "DEBIAN"
    deb_control.mkdir(parents=True, exist_ok=True)
    shutil.copy2(control, deb_control / "control")

    output.parent.mkdir(parents=True, exist_ok=True)
    deb_file = output.with_suffix(".deb")
    if deb_file.exists():
        deb_file.unlink()

    rc = _run([dpkg_deb, "--build", str(staging), str(deb_file)])
    if rc != 0:
        raise SystemExit(f"dpkg-deb failed with exit code {rc}")

    print(f"\nDebian package at: {deb_file}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build standalone Eager exports for Windows and Debian."
    )
    parser.add_argument(
        "--platform",
        choices=["auto", "windows", "debian"],
        default="auto",
        help="Target platform (default: auto-detect from sys.platform).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: dist/<platform>).",
    )
    args = parser.parse_args(argv)

    # Detect platform
    if args.platform == "auto":
        if sys.platform.startswith("win"):
            platform = "windows"
        elif sys.platform.startswith("linux"):
            platform = "debian"
        else:
            platform = sys.platform
            print(f"warning: auto-detected platform '{platform}'; building generic export")
    else:
        platform = args.platform

    output = args.output or (REPO_ROOT / "dist" / platform)

    app_dir = build_pyinstaller(platform, output)

    if platform == "windows":
        package_windows(app_dir, REPO_ROOT / "dist" / "windows-installer")
    elif platform == "debian":
        package_debian(app_dir, REPO_ROOT / "dist" / "debian")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
