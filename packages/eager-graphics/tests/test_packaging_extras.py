"""Packaging metadata for the optional software-rendering backends.

These checks do not import Pillow/Pillow-SIMD; they only assert that the
opt-in SIMD extra stays wired to ``pillow-simd`` while the default ``software``
and ``all`` extras keep using the regular, wheel-provided ``Pillow``.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from typing import Any

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _optional_dependencies() -> dict[str, list[str]]:
    data: dict[str, Any] = tomllib.loads((_PACKAGE_ROOT / "pyproject.toml").read_text("utf-8"))
    return data["project"]["optional-dependencies"]


def _requirement_names(requirements: list[str]) -> set[str]:
    """Return normalized distribution names from PEP 508 requirement strings."""
    names = set()
    for requirement in requirements:
        name = requirement.split(";", 1)[0].strip()
        for separator in (">=", "<=", "==", "!=", "~=", ">", "<", "[", " "):
            name = name.split(separator, 1)[0]
        names.add(name.strip().lower().replace("_", "-"))
    return names


def test_simd_extra_installs_pillow_simd() -> None:
    extras = _optional_dependencies()
    assert "software-simd" in extras
    assert "pillow-simd" in _requirement_names(extras["software-simd"])


def test_default_software_extras_keep_regular_pillow() -> None:
    extras = _optional_dependencies()
    for extra in ("software", "all"):
        names = _requirement_names(extras[extra])
        assert "pillow" in names, extra
        assert "pillow-simd" not in names, extra


def _load_install_script() -> Any:
    path = _REPO_ROOT / "scripts" / "install_pillow_simd.py"
    spec = importlib.util.spec_from_file_location("install_pillow_simd", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_avx2_flag_adds_mavx2_to_compiler() -> None:
    module = _load_install_script()
    env = module._build_env("avx2")
    assert "-mavx2" in env["CC"]

    sse4 = module._build_env("sse4")
    assert "-mavx2" not in sse4.get("CC", "")


def test_deps_probe_returns_status_without_raising() -> None:
    module = _load_install_script()
    ok, detail = module._check_native_deps("sse4")
    assert isinstance(ok, bool)
    assert isinstance(detail, str)


def test_freetype_cflags_returns_string_list() -> None:
    module = _load_install_script()
    flags = module._freetype_cflags()
    assert isinstance(flags, list)
    assert all(isinstance(flag, str) for flag in flags)


def test_installer_commands_swap_pillow_for_pillow_simd() -> None:
    module = _load_install_script()

    for installer in ("pip", "uv"):
        uninstall = module._uninstall_cmd(installer, "python")
        install = module._install_cmd(installer, "python")
        restore = module._restore_cmd(installer, "python")

        assert "uninstall" in uninstall and "pillow" in uninstall
        assert "pillow-simd" in install
        assert "pillow-simd>=10.0.0" in install
        assert "--no-binary" in install
        assert any(part.startswith("Pillow>=10.0.0") for part in restore)


def test_resolve_installer_honours_explicit_choice() -> None:
    module = _load_install_script()
    assert module._resolve_installer("pip") == "pip"
    assert module._resolve_installer("uv") == "uv"
    assert module._resolve_installer("auto") in ("pip", "uv")


def test_workspace_venv_detection() -> None:
    module = _load_install_script()
    repo_venv_python = _REPO_ROOT / ".venv" / "bin" / "python"
    assert module._is_workspace_venv(str(repo_venv_python)) is True
    assert module._is_workspace_venv(str(_REPO_ROOT / "elsewhere" / "bin" / "python")) is False
