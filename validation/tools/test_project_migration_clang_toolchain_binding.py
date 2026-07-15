from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.c_toolchain_probe import ProbeExecution
from validation.tools._project_migration_harness.c_toolchain_test_support import FakeToolchain, resign
from validation.tools._project_migration_harness import clang_fact_commands
from validation.tools._project_migration_harness.clang_toolchain_binding import (
    collect_clang_host_evidence,
    collect_clang_toolchain_binding,
    persist_clang_toolchain_binding,
    reopen_clang_toolchain_binding,
    validate_clang_toolchain_binding,
    validate_clang_toolchain_receipt,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError


class ProjectMigrationClangToolchainBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="clang-binding-")
        self.root = Path(self.temporary.name)
        self.out_root = self.root / "target" / "run"
        self.ledger = self.out_root / "state" / "project-migration.sqlite3"
        self.ledger.parent.mkdir(parents=True)
        self.ledger.touch()
        self.fake = FakeToolchain(self.root / "host")
        self.environment = {
            "PATH": str(self.root / "private-bin"),
            "CPATH": str(self.root / "private-include"),
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def kwargs(self) -> dict:
        return {
            "profile": "development", "environment": self.environment,
            "resolver": self.fake.resolver, "runner": self.fake.runner,
        }

    def raw(self) -> dict:
        return collect_clang_host_evidence(**self.kwargs())

    def receipt(self) -> dict:
        return persist_clang_toolchain_binding(self.out_root, **self.kwargs())

    def reopen(self, receipt: dict) -> dict:
        return reopen_clang_toolchain_binding(
            self.ledger, receipt, environment=self.environment,
            resolver=self.fake.resolver, runner=self.fake.runner,
        )

    def test_portable_schema_roundtrip_and_host_path_separation(self) -> None:
        portable = collect_clang_toolchain_binding(**self.kwargs())
        self.assertEqual(portable, validate_clang_toolchain_binding(portable))
        self.assertEqual(clang_fact_commands.CLANG_TOOLCHAIN_BINDING_KIND,
                         portable["artifact_kind"])
        self.assertEqual({
            "schema_version", "artifact_kind", "status", "family", "basename",
            "binary", "version", "target", "resource_dir", "sysroot",
            "binding_sha256",
        }, set(portable))
        self.assertEqual("clang-compiler", portable["family"])
        self.assertEqual({"status", "value", "stdout_sha256", "stderr_sha256"},
                         set(portable["version"]))
        self.assertEqual({"status", "stdout_sha256", "stderr_sha256"},
                         set(portable["resource_dir"]))
        clang_fact_commands._clang_toolchain(portable)

        receipt = self.receipt()
        self.assertEqual(receipt, validate_clang_toolchain_receipt(receipt))
        self.assertEqual(receipt, self.reopen(receipt))
        self.assertEqual(portable, receipt["portable_binding"])
        self.assertFalse(receipt["section_closure"])
        self.assertFalse(receipt["semantic_gate"])
        self.assertEqual(0, receipt["translation_coverage_numerator"])
        public = json.dumps(receipt, sort_keys=True)
        self.assertNotIn(str(self.fake.paths["clang"]), public)
        self.assertNotIn(self.environment["PATH"], public)
        self.assertNotIn("/opt/llvm/lib/clang/18", public)
        reference = receipt["host_evidence"]
        raw_path = self.out_root.joinpath(*PurePosixPath(reference["path"]).parts)
        private = json.loads(raw_path.read_text(encoding="utf-8"))
        driver = private["tools"][0]
        self.assertEqual(str(self.fake.paths["clang"]), driver["resolved_path"])
        resource = next(item for item in driver["probes"]
                        if item["kind"] == "resource-dir")
        self.assertEqual("/opt/llvm/lib/clang/18", resource["value"])

    def test_gcc_disguise_blocked_duplicate_and_unknown_tools_are_rejected(self) -> None:
        def gcc_resolver(token: str, **_: object) -> str:
            return str(self.fake.paths["gcc"])

        with self.assertRaisesRegex(ValueError, "ready_clang"):
            collect_clang_host_evidence(
                profile="development", environment=self.environment,
                resolver=gcc_resolver, runner=self.fake.runner,
            )
        self.fake.special[("--no-default-config", "--version")] = ProbeExecution(
            0, b"gcc (Ubuntu) 13.3.0\n", b"",
        )
        with self.assertRaisesRegex(ValueError, "version_family"):
            self.raw()
        self.fake.special[("--no-default-config", "--version")] = ProbeExecution(
            1, b"", b"failed",
        )
        with self.assertRaisesRegex(ValueError, "ready_clang"):
            self.raw()
        self.fake.special.clear()

        raw = self.raw()
        duplicate = copy.deepcopy(raw)
        duplicate["tools"].append(copy.deepcopy(duplicate["tools"][0]))
        resign(duplicate)
        with self.assertRaises(ValueError):
            persist_clang_toolchain_binding(self.out_root, duplicate)
        unknown = copy.deepcopy(raw)
        extra = copy.deepcopy(unknown["tools"][0])
        extra.update({"token": "gcc", "basename": "gcc", "family": "gnu-compiler"})
        unknown["tools"].append(extra)
        unknown["tools"].sort(key=lambda item: item["token"])
        resign(unknown)
        with self.assertRaises(ValueError):
            persist_clang_toolchain_binding(self.out_root, unknown)

    def test_live_binary_version_target_and_resource_drift_fail_closed(self) -> None:
        receipt = self.receipt()
        original = self.fake.paths["clang"].read_bytes()
        self.fake.paths["clang"].write_bytes(b"changed-clang")
        with self.assertRaisesRegex(LedgerError, "drifted"):
            self.reopen(receipt)
        self.fake.paths["clang"].write_bytes(original)
        self.fake.paths["clang"].chmod(0o755)
        cases = {
            ("--no-default-config", "--version"): b"clang version 19.0.0\n",
            ("--no-default-config", "-print-target-triple"): b"aarch64-linux-gnu\n",
            ("--no-default-config", "-print-resource-dir"): b"/other/clang/18\n",
        }
        for arguments, output in cases.items():
            self.fake.special.clear()
            self.fake.special[arguments] = ProbeExecution(0, output, b"")
            with self.subTest(arguments=arguments), self.assertRaisesRegex(
                LedgerError, "drifted",
            ):
                self.reopen(receipt)

    def test_portable_binary_and_all_probe_drift_is_rejected(self) -> None:
        receipt = self.receipt()
        fields = ("binary", "version", "target", "resource_dir", "sysroot")
        for field in fields:
            changed = copy.deepcopy(receipt)
            portable = changed["portable_binding"]
            if field == "binary":
                portable["binary"]["sha256"] = "0" * 64
            elif field in {"version", "target"}:
                portable[field]["stdout_sha256"] = "0" * 64
            else:
                portable[field]["status"] = (
                    "reported-empty/default" if field == "resource_dir" else "reported"
                )
            _resign_portable(portable)
            _resign_receipt(changed)
            with self.subTest(field=field), self.assertRaises(
                (ValueError, LedgerError),
            ):
                self.reopen(changed)

    def test_raw_reference_hash_size_path_and_fixed_ledger_drift(self) -> None:
        receipt = self.receipt()
        reference = receipt["host_evidence"]
        raw_path = self.out_root.joinpath(*PurePosixPath(reference["path"]).parts)
        original = raw_path.read_bytes()
        raw_path.write_bytes(original + b" ")
        with self.assertRaisesRegex(LedgerError, "hash changed"):
            self.reopen(receipt)
        raw_path.write_bytes(original)

        changed = copy.deepcopy(receipt)
        changed["host_evidence"]["size_bytes"] += 1
        _resign_receipt(changed)
        with self.assertRaisesRegex(LedgerError, "size drifted"):
            self.reopen(changed)
        for field in ("hash", "path"):
            changed = copy.deepcopy(receipt)
            if field == "hash":
                changed["host_evidence"]["sha256"] = "0" * 64
            else:
                changed["host_evidence"]["path"] = (
                    "verification/raw/other/" + reference["sha256"] + ".json"
                )
            _resign_receipt(changed)
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_clang_toolchain_receipt(changed)
        with self.assertRaisesRegex(LedgerError, "fixed ledger"):
            reopen_clang_toolchain_binding(
                self.out_root / "other.sqlite3", receipt,
                environment=self.environment, resolver=self.fake.resolver,
                runner=self.fake.runner,
            )


def _resign_portable(value: dict) -> None:
    core = {key: item for key, item in value.items() if key != "binding_sha256"}
    value["binding_sha256"] = content_sha256(core)


def _resign_receipt(value: dict) -> None:
    core = {key: item for key, item in value.items() if key != "receipt_sha256"}
    value["receipt_sha256"] = content_sha256(core)


if __name__ == "__main__":
    unittest.main()
