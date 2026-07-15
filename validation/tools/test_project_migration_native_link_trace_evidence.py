from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    persist_captured_cargo_outputs,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.native_link_trace_evidence import (
    persist_captured_native_link_trace,
    reopen_native_link_trace_evidence,
    validate_native_link_trace_binding,
)


class ProjectMigrationNativeLinkTraceEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="native-link-trace-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out_root = self.root / "target" / "run"
        self.database = self.out_root / "state" / "project.sqlite3"
        self.database.parent.mkdir(parents=True)

    def test_trace_is_persisted_and_reopened_against_raw_stdout(self) -> None:
        source = _cargo_stream()
        execution = _execution(source, trace=True)
        traced = persist_captured_native_link_trace(
            execution, out_root=self.out_root, required=True,
        )
        persisted = persist_captured_cargo_outputs(
            traced, out_root=self.out_root, out_root_rel="target/run",
        )
        binding = persisted["native_link_trace"]
        trace = reopen_native_link_trace_evidence(
            self.database, binding, persisted["checks"][0], persisted["sandbox"],
        )
        self.assertEqual("passed", binding["status"])
        self.assertEqual("/usr/lib/example.so", trace["entries"][0]["path"])

    def test_source_and_trace_artifact_tamper_fail_closed(self) -> None:
        source = _cargo_stream()
        persisted = persist_captured_cargo_outputs(
            persist_captured_native_link_trace(
                _execution(source, trace=True), out_root=self.out_root,
                required=True,
            ),
            out_root=self.out_root, out_root_rel="target/run",
        )
        binding = persisted["native_link_trace"]
        changed = deepcopy(binding)
        changed["source_stdout_sha256"] = "0" * 64
        with self.assertRaisesRegex(LedgerError, "source binding"):
            reopen_native_link_trace_evidence(
                self.database, changed, persisted["checks"][0],
                persisted["sandbox"],
            )
        reference = binding["artifact"]
        target = self.out_root.joinpath(*Path(reference["path"]).parts)
        target.write_bytes(b"{}")
        with self.assertRaises(LedgerError):
            reopen_native_link_trace_evidence(
                self.database, binding, persisted["checks"][0],
                persisted["sandbox"],
            )

    def test_valid_but_different_native_linker_contract_fails_reopen(self) -> None:
        persisted = persist_captured_cargo_outputs(
            persist_captured_native_link_trace(
                _execution(_cargo_stream(), trace=True),
                out_root=self.out_root,
                required=True,
            ),
            out_root=self.out_root,
            out_root_rel="target/run",
        )
        different_sandbox = deepcopy(persisted["sandbox"])
        different_sandbox["contract"]["native_linker"] = _linker_contract(
            linker_sha="3" * 64,
        )
        with self.assertRaisesRegex(LedgerError, "toolchain binding"):
            reopen_native_link_trace_evidence(
                self.database,
                persisted["native_link_trace"],
                persisted["checks"][0],
                different_sandbox,
            )

    def test_missing_or_invalid_trace_blocks_execution(self) -> None:
        for source in (b"", b"not-json\n"):
            with self.subTest(source=source):
                result = persist_captured_native_link_trace(
                    _execution(source, trace=True), out_root=self.out_root,
                    required=True,
                )
                self.assertEqual("blocked", result["status"])
                self.assertEqual("blocked", result["native_link_trace"]["status"])

    def test_non_native_execution_records_not_required(self) -> None:
        result = persist_captured_native_link_trace(
            _execution(b"", trace=False), out_root=self.out_root,
            required=False,
        )
        self.assertEqual("not-required", result["native_link_trace"]["status"])
        validate_native_link_trace_binding(
            result["native_link_trace"], required=False,
        )
        with self.assertRaisesRegex(ValueError, "required_evidence_missing"):
            validate_native_link_trace_binding(
                result["native_link_trace"], required=True,
            )
        missing = persist_captured_native_link_trace(
            _execution(b"", trace=False), out_root=self.out_root,
            required=True,
        )
        self.assertEqual("blocked", missing["native_link_trace"]["status"])


def _execution(source: bytes, *, trace: bool) -> dict:
    return {
        "status": "passed",
        "diagnostics": [],
        "sandbox": {"contract": {"native_linker": _linker_contract()}},
        "checks": [{
            "command": ["cargo", "test"],
            "status": "passed",
            "cargo_executed": True,
            "stdout_sha256": hashlib.sha256(source).hexdigest(),
            "stderr_sha256": hashlib.sha256(b"").hexdigest(),
            "stdout_ref": None,
            "stderr_ref": None,
            "_captured_stdout": source,
            "_captured_stderr": b"",
            "sandbox_verification_plan": {"native_link_trace": trace},
        }],
    }


def _linker_contract(*, linker_sha: str = "2" * 64) -> dict:
    binding = {
        "driver": {
            "basename": "cc", "family": "gnu-compiler",
            "sha256": "1" * 64,
        },
        "linker": {
            "basename": "ld", "family": "linker", "sha256": linker_sha,
        },
        "target_triple": "x86_64-unknown-linux-gnu",
    }
    return {
        "schema_version": 1,
        **binding,
        "binding_sha256": content_sha256(binding),
    }


def _cargo_stream() -> bytes:
    message = {
        "reason": "compiler-message",
        "message": {
            "level": "warning",
            "code": {"code": "linker_messages"},
            "message": "linker stdout: /usr/lib/example.so\n",
        },
    }
    finished = {"reason": "build-finished", "success": True}
    return b"".join(
        json.dumps(item, separators=(",", ":")).encode() + b"\n"
        for item in (message, finished)
    )


if __name__ == "__main__":
    unittest.main()
