from __future__ import annotations

import json
import unittest

from validation.tools._project_migration_harness.candidate_strategy import (
    select_candidate_strategy,
    validate_candidate_strategy,
)
from validation.tools._project_migration_harness.controller import ingest_worker_result
from validation.tools._project_migration_harness.project_prompt import (
    render_project_worker_prompt,
)
from validation.tools.project_migration_runtime_test_support import RuntimeHarnessCase


class ProjectMigrationCandidateStrategyTests(RuntimeHarnessCase):
    def test_gate_driven_variants_are_deterministic_and_content_bound(self) -> None:
        first = select_candidate_strategy(
            gate_family="compile", attempt_count=1,
            failure_fingerprint_sha256="a" * 64,
        )
        second = select_candidate_strategy(
            gate_family="compile", attempt_count=2,
            failure_fingerprint_sha256="a" * 64,
        )
        self.assertNotEqual(first["strategy_id"], second["strategy_id"])
        self.assertEqual(first, validate_candidate_strategy(first))

        drifted = dict(first)
        drifted["model_self_score_allowed"] = True
        with self.assertRaisesRegex(ValueError, "binding"):
            validate_candidate_strategy(drifted)

    def test_initial_strategy_reaches_real_worker_prompt(self) -> None:
        plan = self.plan()
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.load(launch["request"])
        prompt = json.loads(render_project_worker_prompt(
            request, harness_root=self.harness,
        ))
        strategy = prompt["bound_inputs"]["candidate_strategy"]
        self.assertEqual("host-strategy-planner-v1", strategy["authority"])
        self.assertFalse(strategy["model_self_score_allowed"])
        self.assertFalse(strategy["semantic_acceptance"])
        ingest_worker_result(
            self.common(request) | {
                "candidate_source": "pub fn unit() -> i32 { 1 }\n",
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=launch["worker_id"],
        )
        artifact = ledger.completed_orchestration_rows(plan["run_id"])["artifacts"][-1]
        metadata = json.loads(artifact["metadata_json"])
        self.assertEqual(strategy["strategy_id"], metadata["candidate_strategy_id"])
        self.assertEqual(strategy["strategy_sha256"], metadata["candidate_strategy_sha256"])


if __name__ == "__main__":
    unittest.main()
