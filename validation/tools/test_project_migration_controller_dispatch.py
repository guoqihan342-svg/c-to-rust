from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.controller import (
    ingest_worker_result,
    record_candidate_gate,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


class ProjectMigrationControllerDispatchTests(ProjectMigrationControllerCase):
    def test_boundary_planner_unlocks_translation_without_accepting_semantics(self) -> None:
        plan = self.plan(
            "#define PICK(x) ((x) + 1)\n#if FEATURE\n"
            "int unit(void) { return PICK(1); }\n#endif\n"
        )
        ledger = self.ledger()
        planner = self.dispatch(plan, ledger)["launches"][0]
        self.assertEqual("planner", planner["role"])
        request = self.request(planner)
        response = self.common(request) | {"decision": "translate_with_context"}
        recorded = ingest_worker_result(
            response,
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=planner["worker_id"],
        )
        self.assertEqual("candidate-ready", recorded["next_status"])
        next_launch = self.dispatch(plan, ledger)["launches"][0]
        self.assertEqual("translator", next_launch["role"])
        self.assertFalse(recorded["semantic_gate"])

    def test_failed_first_candidate_dispatches_repair_without_last_good(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        translator = self.dispatch(plan, ledger)["launches"][0]
        request = self.request(translator)
        recorded = ingest_worker_result(
            self.common(request) | {
                "candidate_source": "pub fn unit() -> i32 { 2 }\n",
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=translator["worker_id"],
        )
        record_candidate_gate(
            ledger=ledger,
            out_root=self.out_root,
            out_root_rel="target/run",
            run_id=plan["run_id"],
            unit_id=translator["unit_id"],
            candidate_artifact_id=recorded["artifact_id"],
            record_id="failed-compile",
            kind="verifier",
            gate_family="compile",
            status="failed",
            verifier_id="rustc-host",
            diagnostics=[{
                "code": "rustc-type-error",
                "stage": "compile",
                "message": "type mismatch",
                "file": "src/unit.rs",
                "line": 1,
                "column": 1,
            }],
        )
        repairer = self.dispatch(plan, ledger)["launches"][0]
        self.assertEqual("repairer", repairer["role"])
        repair_request = self.request(repairer)
        self.assertNotIn("last_good_artifact_id", repair_request["input_facts"])
        self.assertEqual("candidate_repair", repair_request["repair_mode"])


if __name__ == "__main__":
    unittest.main()
