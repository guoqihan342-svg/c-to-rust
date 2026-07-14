from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest

from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_cargo_classification_receipt import (
    verify_cargo_classification_receipt,
    write_cargo_classification_receipt,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_cohort import (
    decide_cargo_diagnostic_cohort,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_intake import (
    CargoDiagnosticPartition, partition_cargo_diagnostics,
)
from validation.tools._project_migration_harness.sandbox_diagnostics import (
    cargo_check_diagnostics,
)
from validation.tools.project_migration_sandbox_test_support import (
    cargo_compiler_message,
)
from validation.tools.project_migration_cargo_classification_test_support import (
    classification_ir,
)


class ProjectMigrationCargoClassificationReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cargo-classification-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out_root = self.root / "target" / "run"
        self.database = self.out_root / "state" / "project.sqlite3"
        self.database.parent.mkdir(parents=True)
        self.member = {
            "unit_id": "unit-a", "artifact_id": "candidate-a",
            "content_sha256": "a" * 64,
        }
        self.ir = classification_ir(
            self.member, rust_path=f"src/unit_{'a' * 64}.rs",
        )

    def test_failed_check_without_test_has_recomputable_admission(self) -> None:
        reference, observation = self._write_receipt()
        receipt = self._verify(reference, observation)
        self.assertEqual("admitted", receipt["admission"]["status"])
        self.assertFalse(receipt["gates"][1]["executed"])

    def test_raw_stdout_tamper_is_rejected(self) -> None:
        reference, observation = self._write_receipt()
        raw = observation["check"]["stdout_ref"]
        self._target(raw["path"]).write_bytes(b"tampered\n")
        with self.assertRaisesRegex(LedgerError, "content binding"):
            self._verify(reference, observation)

    def test_observation_cannot_swap_classified_raw_reference(self) -> None:
        reference, observation = self._write_receipt()
        changed = json.loads(json.dumps(observation))
        changed["check"]["stdout_ref"] = changed["check"]["stderr_ref"]
        with self.assertRaisesRegex(LedgerError, "stdout_ref"):
            self._verify(reference, changed)

    def test_normalized_diagnostic_hash_is_recomputed(self) -> None:
        reference, observation = self._write_receipt()
        payload = json.loads(self._target(reference["path"]).read_text("utf-8"))
        payload["gates"][0]["normalized_diagnostics_sha256"] = "b" * 64
        changed = write_content_addressed_json(
            self.out_root, "project-diagnostic-classification", payload,
        )
        changed["path"] = f"target/run/{changed['path']}"
        with self.assertRaisesRegex(LedgerError, "diagnostics"):
            self._verify(changed, observation)

    def test_admission_cannot_be_self_reported(self) -> None:
        check, partition = self._failed_check()
        with self.assertRaisesRegex(LedgerError, "not recomputable"):
            self._write(
                check, partition,
                admission={
                    "schema_version": 1, "status": "blocked",
                    "blocker_code": "self-reported", "scope": "whole-candidate-cohort",
                },
            )

    def test_link_classification_reopens_from_raw_compiler_message(self) -> None:
        stdout = json.dumps({
            "reason": "compiler-message",
            "message": {
                "level": "error", "code": None,
                "message": "linking with `cc` failed: exit status: 1",
                "children": [{
                    "level": "note",
                    "message": "rust-lld: error: undefined symbol: shared_api",
                }],
            },
        }) + "\n"
        diagnostics = cargo_check_diagnostics(stdout, "check", 1)
        check = {
            "status": "failed", "returncode": 1,
            "diagnostics": diagnostics,
            "stdout_ref": self._raw("stdout", stdout.encode()),
            "stderr_ref": self._raw("stderr", b""),
        }
        link_ir = classification_ir(
            self.member, rust_path=f"src/unit_{'a' * 64}.rs",
            public_symbols=["shared_api"],
        )
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check", diagnostics=diagnostics,
            candidate_members=[self.member], rust_project_ir=link_ir,
        )
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed", checks={"cargo-check": check},
            observations={"cargo-check": {"outcome": "executed"}},
            partitions={"cargo-check": partition},
            candidate_members=[self.member],
        )
        reference = self._write(
            check, partition, admission=decision.payload(), rust_ir=link_ir,
        )
        observation = {"outcome": "executed", "check": {
            key: check[key] for key in (
                "status", "returncode", "stdout_ref", "stderr_ref",
            )
        }}
        receipt = self._verify(reference, observation, rust_ir=link_ir)
        self.assertEqual("admitted", receipt["admission"]["status"])
        self.assertEqual(1, len(receipt["gates"][0][
            "project_diagnostic_sha256s"
        ]))

    def _write_receipt(self) -> tuple[dict, dict]:
        check, partition = self._failed_check()
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed", checks={"cargo-check": check},
            observations={"cargo-check": {"outcome": "executed"}},
            partitions={"cargo-check": partition},
            candidate_members=[self.member],
        )
        reference = self._write(check, partition, admission=decision.payload())
        observation = {
            "outcome": "executed",
            "check": {
                key: check[key] for key in (
                    "status", "returncode", "stdout_ref", "stderr_ref",
                )
            },
        }
        return reference, observation

    def _failed_check(self) -> tuple[dict, CargoDiagnosticPartition]:
        stdout = cargo_compiler_message(
            code="E0308", message="mismatched types",
            file=f"src/unit_{'a' * 64}.rs",
        )
        diagnostics = cargo_check_diagnostics(stdout, "check", 1)
        check = {
            "status": "failed", "returncode": 1,
            "diagnostics": diagnostics,
            "stdout_ref": self._raw("stdout", stdout.encode("utf-8")),
            "stderr_ref": self._raw("stderr", b""),
        }
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check", diagnostics=diagnostics,
            candidate_members=[self.member], rust_project_ir=self.ir,
        )
        return check, partition

    def test_same_count_forged_unit_partition_is_rejected(self) -> None:
        check, _partition = self._failed_check()
        forged = dict(check["diagnostics"][0])
        forged["message"] = "forged diagnostic unrelated to raw output"
        partition = CargoDiagnosticPartition(
            {("unit-a", "candidate-a"): [forged]}, [], None,
        )
        with self.assertRaisesRegex(LedgerError, "partition"):
            self._write(
                check, partition,
                admission={
                    "schema_version": 1, "status": "admitted",
                    "blocker_code": None, "scope": "whole-candidate-cohort",
                },
            )

    def _write(
        self, check: dict, partition: CargoDiagnosticPartition, *, admission: dict,
        rust_ir: dict | None = None,
    ) -> dict:
        return write_cargo_classification_receipt(
            self.out_root, "target/run", run_id="run-a",
            candidate_set_sha256="b" * 64,
            project_input_sha256="c" * 64,
            rust_project_ir=rust_ir or self.ir,
            candidate_members=[self.member], checks={"cargo-check": check},
            partitions={"cargo-check": partition}, admission=admission,
        )

    def _verify(
        self, reference: dict, observation: dict, *, rust_ir: dict | None = None,
    ) -> dict:
        ir = rust_ir or self.ir
        return verify_cargo_classification_receipt(
            self.database, reference, run_id="run-a",
            candidate_set_sha256="b" * 64,
            project_input_sha256="c" * 64,
            observation=observation, gate_kind="cargo-check",
            rust_project_ir_sha256=ir["ir_sha256"],
            rust_project_interface_sha256=ir["interface_sha256"],
        )

    def _raw(self, stream: str, data: bytes) -> dict:
        return write_cargo_raw_output(
            self.out_root, "target/run", gate_kind="cargo-check",
            stream=stream, data=data,
        )

    def _target(self, value: str) -> Path:
        return self.root.joinpath(*PurePosixPath(value).parts)


if __name__ == "__main__":
    unittest.main()
