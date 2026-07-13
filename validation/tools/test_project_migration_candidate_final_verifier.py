from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.candidate_final_verifier import (
    verify_candidate_final,
)
from validation.tools._project_migration_harness.controller_gates import (
    promote_current_verified_candidate,
)
from validation.tools._project_migration_harness.gate_authority import (
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    candidate_verdict_payload,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)
from validation.tools.project_migration_semantic_test_support import (
    passed_semantic_observation,
)


class ProjectMigrationCandidateFinalVerifierTests(ProjectMigrationGateAuthorityCase):
    def test_host_derives_final_bundle_and_promotion_records(self) -> None:
        ordered = ["compile", *sorted(CANDIDATE_REQUIRED_GATES - {"compile"})]
        for family in ordered:
            self.record_candidate_host_gate(family, "passed", f"pass-{family}")
        final = verify_candidate_final(
            ledger=self.ledger, out_root=self.out_root, out_root_rel="target/run",
            run_id="run", unit_id="unit", candidate_artifact_id=self.candidate_id,
        )
        self.assertEqual("passed", final["gate_status"])
        payload = self.harness.joinpath(*final["evidence"]["path"].split("/"))
        import json
        verdict = json.loads(payload.read_text(encoding="utf-8"))
        self.assertEqual(5, len(verdict["source_evidence"]))
        promoted = promote_current_verified_candidate(
            ledger=self.ledger, run_id="run", unit_id="unit",
            candidate_artifact_id=self.candidate_id,
        )
        self.assertEqual("last-good", promoted["status"])
        self.assertEqual("last_good", self.ledger.unit_states("run")[0]["resumable_status"])

    def test_latest_candidate_cannot_reuse_previous_prerequisites(self) -> None:
        ordered = ["compile", *sorted(CANDIDATE_REQUIRED_GATES - {"compile"})]
        for family in ordered:
            self.record_candidate_host_gate(family, "passed", f"old-{family}")
        self.candidate_id, self.candidate_sha = self.make_candidate("candidate-two")
        with self.assertRaisesRegex(LedgerError, "every latest prerequisite"):
            verify_candidate_final(
                ledger=self.ledger, out_root=self.out_root,
                out_root_rel="target/run", run_id="run", unit_id="unit",
                candidate_artifact_id=self.candidate_id,
            )

    def test_legacy_semantic_observations_cannot_reach_final(self) -> None:
        self.record_candidate_host_gate("compile", "passed", "strict-compile")
        for family in sorted(CANDIDATE_REQUIRED_GATES - {"compile"}):
            self._record_legacy_semantic(family)
        with self.assertRaisesRegex(LedgerError, "strict host semantic evidence"):
            verify_candidate_final(
                ledger=self.ledger, out_root=self.out_root,
                out_root_rel="target/run", run_id="run", unit_id="unit",
                candidate_artifact_id=self.candidate_id,
            )

    def _record_legacy_semantic(self, family: str) -> None:
        candidate_set = self.ledger.bind_verification_candidate_set(run_id="run")
        raw = passed_semantic_observation(
            family, run_id="run", unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            candidate_sha256=self.candidate_sha,
            candidate_set_sha256=candidate_set,
        )
        raw_ref = write_content_addressed_json(
            self.out_root, f"raw/candidate/{family}", raw,
        )
        source = {**raw_ref, "path": f"target/run/{raw_ref['path']}"}
        verdict = candidate_verdict_payload(
            run_id="run", unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            candidate_sha256=self.candidate_sha, gate_family=family,
            status="passed", diagnostics=[],
            candidate_set_sha256=candidate_set, source_evidence=[source],
        )
        verdict_ref = write_content_addressed_json(
            self.out_root, f"candidate/{family}", verdict,
        )
        self.ledger._record_derived_verification(
            record_id=f"legacy-{family}", run_id="run", unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            kind=candidate_kind(family), status="passed",
            verifier_id=candidate_authority(family),
            evidence_path=f"target/run/{verdict_ref['path']}",
            evidence_sha256=str(verdict_ref["sha256"]), gate_family=family,
        )


if __name__ == "__main__":
    unittest.main()
