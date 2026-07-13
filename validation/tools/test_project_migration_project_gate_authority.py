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
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


class ProjectMigrationProjectGateAuthorityTests(ProjectMigrationGateAuthorityCase):
    def test_project_status_is_derived_and_latest_final_must_be_fresh(self) -> None:
        self.promote_current_candidate()
        candidate_set = self.ledger.bind_current_candidate_set(run_id="run")
        observation = {
            "schema_version": 1,
            "artifact_kind": "host-project-gate-observation",
            "authority_id": project_authority("cargo-check"),
            "run_id": "run",
            "gate_kind": "cargo-check",
            "candidate_set_sha256": candidate_set,
            "observation": {
                "executed": True,
                "returncode": 1,
                "timed_out": False,
                "sandbox_profile": "os-isolated-v1",
            },
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
            "observation": {**observation["observation"], "returncode": 0},
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


if __name__ == "__main__":
    unittest.main()
