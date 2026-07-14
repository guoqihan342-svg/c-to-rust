from __future__ import annotations

import sqlite3
import hashlib
from pathlib import Path
import unittest

from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.project_diagnostic_shape import (
    build_project_diagnostic,
)
from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.gate_candidate_sets import (
    current_candidate_members,
)
from validation.tools._project_migration_harness.project_cargo_classification_receipt import (
    write_cargo_classification_receipt,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_intake import (
    partition_cargo_diagnostics,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_cohort import (
    decide_cargo_diagnostic_cohort,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    bind_project_cargo_classification,
)
from validation.tools._project_migration_harness.sandbox_diagnostics import (
    cargo_check_diagnostics,
)
from validation.tools._project_migration_harness.project_host_gates import (
    record_host_project_observation,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase, digest,
)
from validation.tools.project_migration_sandbox_test_support import (
    cargo_compiler_message,
)


class ProjectMigrationProjectDiagnosticIntakeTests(
    ProjectMigrationGateAuthorityCase,
):
    def setUp(self) -> None:
        super().setUp()
        self.promote_current_candidate()
        self.candidate_set = self.ledger.bind_current_candidate_set(run_id="run")
        self.rust_project_ir = self.register_project_interface_ready()

    def test_failed_executed_gate_records_bound_immutable_intake(self) -> None:
        observation, diagnostics = self._classified_observation()
        recorded = self._record(observation, diagnostics)
        reference = recorded["project_diagnostic_intake"]
        loaded = self.ledger.latest_project_diagnostic_intakes(
            run_id="run", candidate_set_sha256=self.candidate_set,
            rust_project_ir_sha256=self.rust_project_ir["ir_sha256"],
            project_input_sha256=digest("manifest"),
        )
        self.assertEqual([reference["sha256"]], [item["artifact"]["sha256"] for item in loaded])
        intake = loaded[0]["intake"]
        self.assertEqual(recorded["record_id"], intake["gate_record_id"])
        self.assertEqual("executed", observation["outcome"])
        with self.ledger.connect() as connection, self.assertRaisesRegex(
            sqlite3.IntegrityError, "immutable",
        ):
            connection.execute(
                "update project_diagnostic_intakes set diagnostic_count=2",
            )

    def test_blocked_environment_cannot_admit_or_record_intake(self) -> None:
        blocked = {
            "outcome": "blocked",
            "project_input_sha256": digest("manifest"),
            "project_state_unchanged": True,
            "blocker_code": "cargo_tool_unavailable",
            "sandbox": None,
            "check": None,
        }
        with self.assertRaisesRegex(ValueError, "v3 classification"):
            self._record(blocked, [_diagnostic()])
        with self.ledger.connect() as connection:
            gate_count = connection.execute(
                "select count(*) from project_gate_records",
            ).fetchone()[0]
            intake_count = connection.execute(
                "select count(*) from project_diagnostic_intakes",
            ).fetchone()[0]
        self.assertEqual(0, gate_count)
        self.assertEqual(0, intake_count)

    def test_intake_content_tamper_is_rejected_on_reopen(self) -> None:
        observation, diagnostics = self._classified_observation()
        recorded = self._record(observation, diagnostics)
        reference = recorded["project_diagnostic_intake"]
        target = self.harness.joinpath(*reference["path"].split("/"))
        target.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(LedgerError):
            self.ledger.latest_project_diagnostic_intakes(
                run_id="run", candidate_set_sha256=self.candidate_set,
                rust_project_ir_sha256=self.rust_project_ir["ir_sha256"],
                project_input_sha256=digest("manifest"),
            )

    def test_new_v2_intake_is_rejected_before_gate_recording(self) -> None:
        observation = self.project_observation_value("cargo-check", "failed")
        observation["schema_version"] = 2
        check = observation["check"]
        for stream, data in (("stdout", b"compiler-output"), ("stderr", b"")):
            reference = write_cargo_raw_output(
                self.out_root, "target/run", gate_kind="cargo-check",
                stream=stream, data=data,
            )
            check[f"{stream}_sha256"] = hashlib.sha256(data).hexdigest()
            check[f"{stream}_ref"] = reference
        with self.assertRaisesRegex(ValueError, "v3 classification"):
            self._record(observation, [_diagnostic()])
        with self.ledger.connect() as connection:
            self.assertEqual(0, connection.execute(
                "select count(*) from project_gate_records",
            ).fetchone()[0])
            self.assertEqual(0, connection.execute(
                "select count(*) from project_diagnostic_intakes",
            ).fetchone()[0])

    def test_v3_intake_must_match_classified_project_partition(self) -> None:
        observation, _classified = self._classified_observation()
        with self.assertRaisesRegex(LedgerError, "changed its classification"):
            self._record(observation, [_diagnostic(entity="not-classified")])

    def _classified_observation(self) -> tuple[dict, list[dict]]:
        observation = self.project_observation_value("cargo-check", "failed")
        observation["schema_version"] = 2
        stdout = cargo_compiler_message(
            code="E0308", message="mismatched project types",
            file="src/project.rs",
        )
        check = observation["check"]
        for stream, data in (("stdout", stdout.encode()), ("stderr", b"")):
            reference = write_cargo_raw_output(
                self.out_root, "target/run", gate_kind="cargo-check",
                stream=stream, data=data,
            )
            check[f"{stream}_sha256"] = reference["sha256"]
            check[f"{stream}_ref"] = reference
        diagnostics = cargo_check_diagnostics(stdout, "check", 1)
        with self.ledger.connect() as connection:
            members = current_candidate_members(connection, "run")
        partition = partition_cargo_diagnostics(
            gate_kind="cargo-check", diagnostics=diagnostics,
            candidate_members=members, rust_project_ir=self.rust_project_ir,
        )
        source_check = {
            "status": "failed", "returncode": 1,
            "stdout_ref": check["stdout_ref"],
            "stderr_ref": check["stderr_ref"], "diagnostics": diagnostics,
        }
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed", checks={"cargo-check": source_check},
            observations={"cargo-check": {"outcome": "executed"}},
            partitions={"cargo-check": partition}, candidate_members=members,
        )
        receipt = write_cargo_classification_receipt(
            self.out_root, "target/run", run_id="run",
            candidate_set_sha256=self.candidate_set,
            project_input_sha256=digest("manifest"),
            rust_project_ir=self.rust_project_ir,
            candidate_members=members, checks={"cargo-check": source_check},
            partitions={"cargo-check": partition}, admission=decision.payload(),
        )
        return (
            bind_project_cargo_classification(observation, receipt),
            partition.project_diagnostics,
        )

    def _record(self, observation: dict, diagnostics: list[dict]) -> dict:
        return record_host_project_observation(
            ledger=self.ledger, out_root=self.out_root,
            out_root_rel="target/run", run_id="run",
            gate_kind="cargo-check",
            candidate_set_sha256=self.candidate_set,
            observation=observation, diagnostic_codes=["e0432"],
            project_diagnostic_input={
                "rust_project_ir_sha256": self.rust_project_ir["ir_sha256"],
                "rust_project_interface_sha256": self.rust_project_ir[
                    "interface_sha256"
                ],
                "project_input_sha256": digest("manifest"),
                "diagnostics": diagnostics,
            },
        )


def _diagnostic(*, entity: str | None = None) -> dict:
    return {
        "family": "compile", "source_code": "e0432",
        "stage": "cargo-check", "message": "unresolved import `shared`",
        "location": {"file": "src/lib.rs", "line": 1, "column": 1},
        "project_diagnostic": build_project_diagnostic(
            code="project-verifier-e0432",
            entity_ids=["e0432", "file:src/lib.rs", *([entity] if entity else [])],
            affected_module_ids=[],
        ),
    }


if __name__ == "__main__":
    unittest.main()
