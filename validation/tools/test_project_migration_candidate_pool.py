from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.controller import (
    ingest_worker_result,
)
from validation.tools._project_migration_harness.controller_gates import (
    record_candidate_gate,
)
from validation.tools._project_migration_harness.candidate_pool_selection import (
    _select_candidate_score,
)
from validation.tools._project_migration_harness.gate_candidate_sets import (
    candidate_set_members,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.orchestration_facts import (
    build_gate_facts,
)
from validation.tools.project_migration_runtime_test_support import (
    RuntimeHarnessCase,
)


BOUNDARY_SOURCE = (
    "#define APPLY(x) ((x) + 1)\n"
    "int unit(void) { return APPLY(1); }\n"
)
CANDIDATE_A = "pub fn unit() -> i32 { 2 }\n"
CANDIDATE_B = "pub fn unit() -> i32 { 1 + 1 }\n"


class ProjectMigrationCandidatePoolTests(RuntimeHarnessCase):
    def test_all_failed_tie_break_is_insertion_order_independent(self) -> None:
        scores = [{
            "artifact_id": "candidate-b", "content_sha256": "b" * 64,
            "sequence": 1, "passed_gate_count": 1, "failed_gate_count": 1,
        }, {
            "artifact_id": "candidate-a", "content_sha256": "a" * 64,
            "sequence": 2, "passed_gate_count": 1, "failed_gate_count": 1,
        }]
        forward, reason = _select_candidate_score(scores)
        reverse, reverse_reason = _select_candidate_score(list(reversed(scores)))
        self.assertEqual("candidate-a", forward["artifact_id"])
        self.assertEqual(forward, reverse)
        self.assertEqual("best-host-gated-repair-base", reason)
        self.assertEqual(reason, reverse_reason)

    def test_failed_latest_candidate_falls_back_before_repair(self) -> None:
        plan = self.plan(BOUNDARY_SOURCE)
        ledger = self.ledger()
        self._record_planner(plan, ledger)
        first = self._record_candidate(plan, ledger, CANDIDATE_A)
        second = self._record_candidate(plan, ledger, CANDIDATE_B)

        second_review = self._next_request(plan, ledger, "reviewer")
        self.assertEqual(
            second["artifact"]["sha256"],
            second_review["input_facts"]["candidate_artifact_sha256"],
        )
        self._record_review(ledger, second_review)
        record_candidate_gate(
            ledger=ledger,
            out_root=self.out_root,
            out_root_rel="target/run",
            run_id=plan["run_id"],
            unit_id=second_review["unit_id"],
            candidate_artifact_id=second["artifact_id"],
            record_id="candidate-second-compile-failed",
            kind="verifier",
            gate_family="compile",
            status="failed",
            verifier_id="host-derived",
            diagnostics=[{"code": "compile-failed", "stage": "compile"}],
        )

        fallback_review = self._next_request(plan, ledger, "reviewer")
        self.assertEqual(
            first["artifact"]["sha256"],
            fallback_review["input_facts"]["candidate_artifact_sha256"],
        )
        self._record_review(ledger, fallback_review)
        candidate_set = ledger.bind_verification_candidate_set(
            run_id=plan["run_id"], scope="wave-provisional",
        )
        with ledger.connect() as connection:
            members = candidate_set_members(connection, plan["run_id"], candidate_set)
        self.assertEqual(first["artifact_id"], members[-1]["artifact_id"])

    def test_duplicate_candidate_sha_does_not_fill_pool_or_collide(self) -> None:
        plan = self.plan(BOUNDARY_SOURCE)
        ledger = self.ledger()
        self._record_planner(plan, ledger)
        first = self._record_candidate(plan, ledger, CANDIDATE_A)
        duplicate = self._record_candidate(plan, ledger, CANDIDATE_A)
        self.assertNotEqual(first["artifact"]["path"], duplicate["artifact"]["path"])

        facts = build_gate_facts(
            ledger, run_id=plan["run_id"], harness_root=self.harness,
        )
        pool = next(iter(facts.values()))["candidate_pool"]
        self.assertEqual(1, pool["unique_candidate_count"])
        self.assertEqual(1, pool["duplicate_candidate_count"])
        self.assertFalse(pool["pool_ready"])

        unique = self._record_candidate(plan, ledger, CANDIDATE_B)
        review = self._next_request(plan, ledger, "reviewer")
        self.assertEqual(
            unique["artifact"]["sha256"],
            review["input_facts"]["candidate_artifact_sha256"],
        )

    def _record_planner(self, plan: dict, ledger: ProjectLedger) -> None:
        request = self._next_request(plan, ledger, "planner")
        result = ingest_worker_result(
            self.common(request) | {
                "decision": "translate_with_context",
                "boundary_reason": None,
                "refusal_reason": None,
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=request["worker_id"],
        )
        self.assertEqual("recorded", result["status"])

    def _record_candidate(
        self, plan: dict, ledger: ProjectLedger, source: str,
    ) -> dict:
        request = self._next_request(plan, ledger, "translator")
        result = ingest_worker_result(
            self.common(request) | {"candidate_source": source},
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=request["worker_id"],
        )
        self.assertEqual("recorded", result["status"])
        return result

    def _record_review(self, ledger: ProjectLedger, request: dict) -> None:
        result = ingest_worker_result(
            self.common(request) | {
                "candidate_artifact_sha256": request["input_facts"][
                    "candidate_artifact_sha256"
                ],
                "findings": [],
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=request["run_id"],
            worker_id=request["worker_id"],
        )
        self.assertEqual("recorded", result["status"])

    def _next_request(
        self, plan: dict, ledger: ProjectLedger, expected_role: str,
    ) -> dict:
        dispatched = self.dispatch(plan, ledger)
        self.assertEqual(1, len(dispatched["launches"]))
        launch = dispatched["launches"][0]
        self.assertEqual(expected_role, launch["role"])
        return self.load(launch["request"])


if __name__ == "__main__":
    unittest.main()
