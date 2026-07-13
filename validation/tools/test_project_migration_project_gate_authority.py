from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.controller_project_gates import (
    record_project_gate_summary,
)
from validation.tools._project_migration_harness.gate_authority import (
    PROJECT_GATE_KINDS,
    project_authority,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.sandbox_contract import (
    canonical_sha256,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase, digest,
)
from validation.tools.project_migration_final_barrier_test_support import (
    record_project_final_candidate_bundle,
)


class ProjectMigrationProjectGateAuthorityTests(ProjectMigrationGateAuthorityCase):
    def test_project_status_is_derived_and_latest_final_must_be_fresh(self) -> None:
        self.promote_current_candidate()
        candidate_set = self.ledger.bind_current_candidate_set(run_id="run")
        with self.assertRaisesRegex(LedgerError, "candidate gate"):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=candidate_set
            )
        self.assertEqual(
            candidate_set, record_project_final_candidate_bundle(self),
        )
        observation = {
            "schema_version": 1,
            "artifact_kind": "host-project-gate-observation",
            "authority_id": project_authority("cargo-check"),
            "run_id": "run",
            "gate_kind": "cargo-check",
            "candidate_set_sha256": candidate_set,
            "observation": self.project_observation_value(
                "cargo-check", "failed",
            ),
        }
        raw = write_content_addressed_json(
            self.out_root, "raw/cargo-check", observation
        )
        derived = record_project_gate_summary(
            ledger=self.ledger,
            out_root=self.out_root,
            out_root_rel="target/run",
            run_id="run",
            record_id="cargo-derived",
            gate_kind="cargo-check",
            status="passed",
            candidate_set_sha256=candidate_set,
            verifier_id="caller-controlled",
            source_evidence=[{**raw, "path": f"target/run/{raw['path']}"}],
        )
        self.assertEqual("failed", derived["gate_status"])
        self.assertEqual(project_authority("cargo-check"), derived["authority_id"])
        passing_observation = {
            **observation,
            "observation": self.project_observation_value(
                "cargo-check", "passed",
            ),
        }
        forged = write_content_addressed_json(
            self.out_root, "raw/cargo-check", passing_observation
        )
        with self.assertRaisesRegex(LedgerError, "cannot grant a pass"):
            record_project_gate_summary(
                ledger=self.ledger,
                out_root=self.out_root,
                out_root_rel="target/run",
                run_id="run",
                record_id="cargo-forged-pass",
                gate_kind="cargo-check",
                status="failed",
                candidate_set_sha256=candidate_set,
                verifier_id="caller-controlled",
                source_evidence=[{**forged, "path": f"target/run/{forged['path']}"}],
            )
        for kind in sorted(PROJECT_GATE_KINDS - {"final-verification"}):
            self.record_project_host_gate(kind, "passed", f"{kind}-pass", candidate_set)
        self.record_project_final("project-final-one", candidate_set)
        self.record_project_host_gate(
            "cargo-test", "failed", "cargo-test-late-fail", candidate_set
        )
        with self.assertRaisesRegex(LedgerError, "latest project gate"):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=candidate_set
            )
        self.record_project_host_gate(
            "cargo-test", "passed", "cargo-test-repass", candidate_set
        )
        with self.assertRaisesRegex(LedgerError, "predates"):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=candidate_set
            )
        self.record_project_final("project-final-two", candidate_set)
        self.ledger.complete_project_run(
            run_id="run", candidate_set_sha256=candidate_set
        )

    def test_completion_rejects_gate_bundle_for_stale_candidate_set(self) -> None:
        self.promote_current_candidate()
        first_set = self.ledger.bind_current_candidate_set(run_id="run")
        self.candidate_id, self.candidate_sha = self.make_candidate("candidate-two")
        self.promote_current_candidate()
        second_set = self.ledger.bind_current_candidate_set(run_id="run")
        self.assertNotEqual(first_set, second_set)
        with self.assertRaisesRegex(LedgerError, "current last-good candidate set"):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=first_set
            )

    def test_completion_rejects_a_running_worker_attempt(self) -> None:
        self.promote_current_candidate()
        candidate_set = record_project_final_candidate_bundle(self)
        with self.ledger.connect() as connection:
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,worker_id,
                   status,fencing_token,input_sha256,output_sha256,error_key,started_at,
                   finished_at,metadata_json)
                   values ('running-final','run','unit','translator',99,'translator',
                           'running',99,?,null,null,?,null,'{}')""",
                ("a" * 64, "2026-01-01T00:00:59Z"),
            )
        with self.assertRaisesRegex(LedgerError, "running worker"):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=candidate_set,
            )

    def test_project_cargo_input_must_match_latest_integration(self) -> None:
        self.promote_current_candidate()
        candidate_set = record_project_final_candidate_bundle(self)
        mismatch = self.project_observation_value("cargo-check", "passed")
        mismatched_input = digest("different-managed-generation")
        mismatch["project_input_sha256"] = mismatched_input
        check = mismatch["check"]
        plan = check["sandbox_verification_plan"]
        plan["input_sha256"] = mismatched_input
        check["sandbox_verification_plan_sha256"] = canonical_sha256(plan)
        raw_payload = {
            "schema_version": 1,
            "artifact_kind": "host-project-gate-observation",
            "authority_id": project_authority("cargo-check"),
            "run_id": "run",
            "gate_kind": "cargo-check",
            "candidate_set_sha256": candidate_set,
            "observation": mismatch,
        }
        raw = write_content_addressed_json(
            self.out_root, "raw/cargo-check", raw_payload,
        )
        mismatch_source = {**raw, "path": f"target/run/{raw['path']}"}
        for kind in sorted(PROJECT_GATE_KINDS - {"final-verification"}):
            self.record_project_host_gate(
                kind,
                "passed",
                f"{kind}-input-binding",
                candidate_set,
                [mismatch_source] if kind == "cargo-check" else None,
            )
        with self.assertRaisesRegex(LedgerError, "latest integrated generation"):
            self.record_project_final("project-final-input-drift", candidate_set)


if __name__ == "__main__":
    unittest.main()
