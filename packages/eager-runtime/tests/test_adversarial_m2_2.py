"""Adversarial stress harness for eager-runtime corrupt save handling and API sealing (M2 Challenger 2 / Hardened).

Probes:
1. SaveManager.load_slot() corruption resilience against 0-byte, incomplete JSON, non-dict roots,
   binary garbage, and valid JSON with invalid types/missing fields.
2. SaveManager.list_slots() and get_slot_metadata() resilience against corrupt metadata payloads.
3. API sealing and namespace leak prevention across all 15 submodules and root eager_runtime exports.
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, ClassVar

from eager_runtime.saves import SaveManager, SaveMetadata
from eager_runtime.state import Checkpoint


class TestSaveCorruptionAdversarial:
    """Stress testing SaveManager.load_slot() corruption resilience and forensic backups."""

    def test_zero_byte_slot_file(self) -> None:
        """A 0-byte empty file must safely return None and create a .corrupt.bak backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))
            slot_path = sm._slot_path("slot_zero")
            slot_path.write_bytes(b"")

            res = sm.load_slot("slot_zero")
            assert res is None

            bak_path = slot_path.with_name(slot_path.name + ".corrupt.bak")
            assert bak_path.exists()
            assert bak_path.read_bytes() == b""

    def test_incomplete_json_stream(self) -> None:
        """Incomplete / truncated JSON must safely return None and create a .corrupt.bak backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))
            slot_path = sm._slot_path("slot_trunc")
            slot_path.write_text('{"schema_version": 2, ', encoding="utf-8")

            res = sm.load_slot("slot_trunc")
            assert res is None

            bak_path = slot_path.with_name(slot_path.name + ".corrupt.bak")
            assert bak_path.exists()
            assert bak_path.read_text(encoding="utf-8") == '{"schema_version": 2, '

    def test_binary_garbage_payload(self) -> None:
        """Non-UTF-8 binary garbage must safely return None and create a .corrupt.bak backup."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))
            slot_path = sm._slot_path("slot_bin")
            garbage = b"\x00\xff\xfe\xca\xfe"
            slot_path.write_bytes(garbage)

            res = sm.load_slot("slot_bin")
            assert res is None

            bak_path = slot_path.with_name(slot_path.name + ".corrupt.bak")
            assert bak_path.exists()
            assert bak_path.read_bytes() == garbage

    def test_corrupt_bak_collision_overwrite(self) -> None:
        """If a .corrupt.bak already exists, a subsequent corruption must overwrite it cleanly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))
            slot_path = sm._slot_path("slot_col")
            bak_path = slot_path.with_name(slot_path.name + ".corrupt.bak")

            # Pre-existing backup from an earlier event
            bak_path.write_text("prior_backup_data", encoding="utf-8")

            # New corrupted file
            slot_path.write_text("{second_corrupt_attempt", encoding="utf-8")

            res = sm.load_slot("slot_col")
            assert res is None
            assert bak_path.exists()
            assert bak_path.read_text(encoding="utf-8") == "{second_corrupt_attempt"

    def test_non_dict_json_root_empirical_gap(self) -> None:
        """Non-dict JSON roots (list, str, int) must safely return None and create .corrupt.bak."""
        test_cases: list[tuple[str, str]] = [
            ("slot_array", "[1, 2, 3]"),
            ("slot_string", '"plain string root"'),
            ("slot_number", "42"),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))
            for slot_name, payload in test_cases:
                slot_path = sm._slot_path(slot_name)
                slot_path.write_text(payload, encoding="utf-8")

                res = sm.load_slot(slot_name)
                assert res is None

                bak_path = slot_path.with_name(slot_path.name + ".corrupt.bak")
                assert bak_path.exists(), f"Backup missing for non-dict root: {slot_name}"
                assert bak_path.read_text(encoding="utf-8") == payload

    def test_missing_checkpoint_field_returns_none(self) -> None:
        """Valid JSON missing 'checkpoint' key returns None and creates .corrupt.bak."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))
            slot_path = sm._slot_path("slot_no_cp")
            payload = json.dumps({"version": 1, "metadata": {}})
            slot_path.write_text(payload, encoding="utf-8")

            res = sm.load_slot("slot_no_cp")
            assert res is None

            bak_path = slot_path.with_name(slot_path.name + ".corrupt.bak")
            assert bak_path.exists()
            assert bak_path.read_text(encoding="utf-8") == payload

    def test_invalid_types_empirical_crashes(self) -> None:
        """Invalid field types must safely return None and create .corrupt.bak without crashing."""
        test_cases: list[tuple[str, str]] = [
            # 1. Checkpoint invalid types: None, 123, "string", []
            ("slot_null_cp", json.dumps({"version": 1, "checkpoint": None})),
            ("slot_int_cp", json.dumps({"version": 1, "checkpoint": 123})),
            ("slot_str_cp", json.dumps({"version": 1, "checkpoint": "not_a_dict"})),
            ("slot_list_cp", json.dumps({"version": 1, "checkpoint": [1, 2, 3]})),
            # 2. Metadata invalid types: 123, "string"
            ("slot_int_meta", json.dumps({"version": 1, "metadata": 123, "checkpoint": {}})),
            ("slot_str_meta", json.dumps({"version": 1, "metadata": "not_a_dict", "checkpoint": {}})),
            # 3. Invalid version: "bad_ver"
            ("slot_str_ver", json.dumps({"version": "bad_ver", "checkpoint": {}})),
            # 4. Invalid backlog length: "not_int"
            ("slot_str_backlog", json.dumps({"version": 1, "checkpoint": {"backlog_len": "not_int"}})),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))
            for slot_name, payload in test_cases:
                slot_path = sm._slot_path(slot_name)
                slot_path.write_text(payload, encoding="utf-8")

                res = sm.load_slot(slot_name)
                assert res is None

                bak_path = slot_path.with_name(slot_path.name + ".corrupt.bak")
                assert bak_path.exists(), f"Backup missing for invalid type payload: {slot_name}"
                assert bak_path.read_text(encoding="utf-8") == payload

    def test_list_slots_skips_corrupted_metadata_cleanly(self) -> None:
        """list_slots() and get_slot_metadata() must cleanly handle corrupt metadata without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SaveManager(Path(tmpdir))

            # Populate valid slots
            cp1 = Checkpoint(story={"current_scene": "scene_1"}, visual={}, audio={}, backlog_len=0, ui={})
            cp2 = Checkpoint(story={"current_scene": "scene_2"}, visual={}, audio={}, backlog_len=0, ui={})
            _ = sm.save_slot("valid_1", cp1)
            _ = sm.save_slot("valid_2", cp2)

            # Populate corrupted metadata slots
            corrupt_cases: list[tuple[str, str]] = [
                ("slot_broken_ver", json.dumps({"metadata": {"version": "corrupted"}, "checkpoint": {}})),
                ("slot_broken_playtime", json.dumps({"metadata": {"playtime_seconds": "not_float"}, "checkpoint": {}})),
                ("slot_int_meta", json.dumps({"metadata": 123, "checkpoint": {}})),
                ("slot_str_meta", json.dumps({"metadata": "not_a_dict", "checkpoint": {}})),
                ("slot_syntax_err", '{"metadata": {"incomplete'),
                ("slot_root_array", "[1, 2, 3]"),
            ]
            for slot_name, payload in corrupt_cases:
                slot_path = sm._slot_path(slot_name)
                slot_path.write_text(payload, encoding="utf-8")

            # get_slot_metadata returns None for corrupted slots without crashing
            for slot_name, _ in corrupt_cases:
                meta = sm.get_slot_metadata(slot_name)
                assert meta is None, f"Expected None for get_slot_metadata({slot_name})"

            # get_slot_metadata returns SaveMetadata for valid slots
            valid_meta = sm.get_slot_metadata("valid_1")
            assert valid_meta is not None
            assert isinstance(valid_meta, SaveMetadata)
            assert valid_meta.slot_name == "valid_1"

            # list_slots() returns only valid slots, cleanly skipping corrupt ones
            slots = sm.list_slots()
            assert len(slots) == 2
            slot_names = {s.slot_name for s in slots}
            assert slot_names == {"valid_1", "valid_2"}
            assert all(isinstance(s, SaveMetadata) for s in slots)


class TestApiSealingAdversarial:
    """Stress testing API sealing, __all__ declarations, and namespace leaks across eager_runtime."""

    SUBMODULES: ClassVar[list[str]] = [
        "assets",
        "backlog",
        "cli",
        "dispatcher",
        "headless",
        "i18n",
        "persistent",
        "player",
        "preferences",
        "project",
        "runtime",
        "saves",
        "session",
        "state",
        "watcher",
    ]

    def test_all_15_submodules_define_all(self) -> None:
        """Every submodule in eager_runtime must define __all__ as a list or tuple of strings."""
        for sub in self.SUBMODULES:
            mod = importlib.import_module(f"eager_runtime.{sub}")
            assert hasattr(mod, "__all__"), f"eager_runtime.{sub} is missing __all__"
            all_list = getattr(mod, "__all__", None)
            assert isinstance(all_list, (list, tuple)), f"eager_runtime.{sub}.__all__ is not a list/tuple"
            assert all(isinstance(s, str) for s in all_list), f"eager_runtime.{sub}.__all__ contains non-strings"
            assert list(all_list) == sorted(all_list), f"eager_runtime.{sub}.__all__ is not strictly sorted: {all_list}"

    def test_all_symbols_in_submodule_all_exist(self) -> None:
        """Every symbol listed in __all__ must exist in the module."""
        for sub in self.SUBMODULES:
            mod = importlib.import_module(f"eager_runtime.{sub}")
            all_list = getattr(mod, "__all__", [])
            for sym in all_list:
                assert hasattr(mod, sym), f"Symbol {sym!r} in eager_runtime.{sub}.__all__ not found in module"

    def test_submodule_wildcard_import_matches_all_exactly(self) -> None:
        """Wildcard import from eager_runtime.<submodule> must export ONLY symbols in __all__."""
        for sub in self.SUBMODULES:
            ns: dict[str, Any] = {}
            exec(f"from eager_runtime.{sub} import *", ns)  # noqa: S102
            ns.pop("__builtins__", None)
            mod = importlib.import_module(f"eager_runtime.{sub}")
            expected = set(getattr(mod, "__all__", []))
            actual = set(ns.keys())
            assert actual == expected, f"Wildcard mismatch in eager_runtime.{sub}: diff={actual.symmetric_difference(expected)}"

    def test_root_package_exports_and_resolution(self) -> None:
        """eager_runtime.__all__ must export project loader APIs and resolve them cleanly."""
        import eager_runtime

        expected_symbols = [
            "ProjectConfig",
            "load_project_graph",
            "resolve_project_scripts",
            "merge_graphs",
        ]
        for sym in expected_symbols:
            assert sym in eager_runtime.__all__, f"{sym} not in eager_runtime.__all__"
            val = getattr(eager_runtime, sym, None)
            assert val is not None, f"eager_runtime.{sym} failed to resolve"

        # Wildcard import of root matches __all__
        ns_root: dict[str, Any] = {}
        exec("from eager_runtime import *", ns_root)  # noqa: S102
        ns_root.pop("__builtins__", None)
        assert set(ns_root.keys()) == set(eager_runtime.__all__)

    def test_headless_isolation_no_graphics_imported(self) -> None:
        """Importing eager_runtime in a clean process must not load any graphics or windowing modules."""
        import subprocess

        code = (
            "import sys, eager_runtime; "
            "leaked = [m for m in sys.modules if any(k in m for k in ('eager_graphics', 'pyglet', 'PIL'))]; "
            "assert not leaked, f'Leaked graphics modules: {leaked}'"
        )
        cmd = [sys.executable, "-c", code]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, f"Headless check failed in subprocess:\n{proc.stderr}"
