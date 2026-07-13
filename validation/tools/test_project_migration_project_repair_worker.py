from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_repair_ingest import (
    ingest_project_repair_response,
)
from validation.tools._project_migration_harness.project_repair_prompt import (
    render_project_repair_prompt,
)
from validation.tools._project_migration_harness.project_repair_worker_request import (
    materialize_project_repair_request,
)
from validation.tools.project_migration_project_repair_test_support import (
    materialized_repair_case,
)


class ProjectRepairWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-worker-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        self.ledger = ProjectLedger(self.out / "state/project-migration.sqlite3")

    def test_minimal_prompt_patch_rebuild_and_recoordination_resolve(self) -> None:
        request, base, duplicate_id = self.case("resolve")
        prompt = json.loads(render_project_repair_prompt(
            request, harness_root=self.root,
        ))
        context = prompt["project_repair_context"]
        serialized = json.dumps(context, sort_keys=True)
        self.assertNotIn('"bindings"', serialized)
        self.assertNotIn('"candidate_source":', serialized)
        self.assertEqual(2, len(context["visible_records"]["public_api"]))

        response = self.response(request, [{
            "section": "public_api", "action": "remove",
            "record_id": duplicate_id, "changes": {},
        }])
        result = ingest_project_repair_response(
            request, response, ledger=self.ledger, harness_root=self.root,
            out_root=self.out, out_root_rel="target/run",
        )

        self.assertEqual("resolved", result["status"])
        self.assertEqual("candidate-ready", result["coordinator_status"])
        self.assertNotEqual(base["ir_sha256"], result["candidate_ir_sha256"])
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual(("resolved", 3, 1), (
            projection.status, projection.version, projection.attempt_count,
        ))
        latest = self.ledger.load_latest_project_interface_receipt(run_id="run")
        self.assertEqual(2, latest[0])
        self.assertEqual("candidate-ready", latest[1]["status"])

    def test_non_allowlisted_model_patch_is_recorded_as_retryable_failure(self) -> None:
        request, _, duplicate_id = self.case("invalid")
        response = self.response(request, [{
            "section": "public_api", "action": "replace",
            "record_id": duplicate_id,
            "changes": {"evidence": {"semantic_pass": True}},
        }])

        result = ingest_project_repair_response(
            request, response, ledger=self.ledger, harness_root=self.root,
            out_root=self.out, out_root_rel="target/run",
        )

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("invalid_project_repair_response", result["error_code"])
        self.assertNotIn("evidence", json.dumps(result, sort_keys=True))
        retried = materialize_project_repair_request(
            ledger=self.ledger, run_id="run",
            queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"], worker_id="project-repairer-2",
            base_rust_project_ir=request["base_rust_project_ir"],
            harness_root=self.root, out_root=self.out,
            out_root_rel="target/run",
        )
        self.assertEqual("attempt-started", retried["status"])
        with self.ledger.connect() as connection:
            context_rows = connection.execute(
                """select count(*) from project_repair_artifacts
                   where run_id='run' and kind='project-repair-context'"""
            ).fetchone()[0]
        self.assertEqual(2, context_rows)

    def test_last_budget_candidate_with_remaining_conflict_becomes_exhausted(self) -> None:
        request, base, duplicate_id = self.case("exhaust", max_attempts=1)
        original_signature = base["public_api"][0]["signature"]
        response = self.response(request, [{
            "section": "public_api", "action": "replace",
            "record_id": duplicate_id,
            "changes": {"signature": original_signature},
        }])

        result = ingest_project_repair_response(
            request, response, ledger=self.ledger, harness_root=self.root,
            out_root=self.out, out_root_rel="target/run",
        )

        self.assertEqual("exhausted", result["status"])
        self.assertEqual("repair-required", result["coordinator_status"])
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual(("exhausted", 3, 1), (
            projection.status, projection.version, projection.attempt_count,
        ))
        latest = self.ledger.load_latest_project_interface_receipt(run_id="run")
        self.assertEqual(1, latest[0])
        self.assertEqual(base["ir_sha256"], latest[1]["rust_project_ir_sha256"])

    def test_target_reduction_advances_to_remaining_project_conflict(self) -> None:
        request, _, base, duplicate_id = materialized_repair_case(
            self.root, self.out, self.ledger, "partial-progress",
            additional_conflict=True,
        )
        response = self.response(request, [{
            "section": "public_api", "action": "remove",
            "record_id": duplicate_id, "changes": {},
        }])

        result = ingest_project_repair_response(
            request, response, ledger=self.ledger, harness_root=self.root,
            out_root=self.out, out_root_rel="target/run",
        )

        self.assertEqual("resolved", result["status"])
        self.assertEqual("repair-required", result["coordinator_status"])
        self.assertNotEqual(base["ir_sha256"], result["candidate_ir_sha256"])
        latest = self.ledger.load_latest_project_interface_receipt(run_id="run")
        self.assertEqual(2, latest[0])
        self.assertEqual(1, latest[1]["project_repair_queue"]["item_count"])
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual("resolved", projection.status)
        old_receipt = self.ledger.load_project_interface_receipt(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
        )
        remaining = next(
            item for item in old_receipt["project_repair_queue"]["items"]
            if item["repair_id"] != request["repair_id"]
        )
        with self.assertRaisesRegex(ValueError, "latest receipt"):
            materialize_project_repair_request(
                ledger=self.ledger, run_id="run",
                queue_sha256=request["project_repair_queue_sha256"],
                repair_id=remaining["repair_id"], worker_id="stale-worker",
                base_rust_project_ir=request["base_rust_project_ir"],
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run",
            )

    def test_project_repair_attempts_are_serialized_per_run(self) -> None:
        request, _, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "serialized",
            additional_conflict=True,
        )
        receipt = self.ledger.load_project_interface_receipt(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
        )
        other = next(
            item for item in receipt["project_repair_queue"]["items"]
            if item["repair_id"] != request["repair_id"]
        )
        with self.assertRaisesRegex(LedgerError, "already running"):
            materialize_project_repair_request(
                ledger=self.ledger, run_id="run",
                queue_sha256=request["project_repair_queue_sha256"],
                repair_id=other["repair_id"], worker_id="second-repairer",
                base_rust_project_ir=request["base_rust_project_ir"],
                harness_root=self.root, out_root=self.out,
                out_root_rel="target/run",
            )

    def case(
        self, label: str, *, max_attempts: int = 2,
    ) -> tuple[dict, dict, str]:
        request, _, base, duplicate_id = materialized_repair_case(
            self.root, self.out, self.ledger, label,
            max_attempts=max_attempts,
        )
        return request, base, duplicate_id

    @staticmethod
    def response(request: dict, operations: list[dict]) -> dict:
        return {
            "schema_version": 1, "run_id": request["run_id"],
            "role": "project-repairer",
            "project_repair_queue_sha256": request["project_repair_queue_sha256"],
            "repair_id": request["repair_id"],
            "attempt_id": request["execution_binding"]["attempt_id"],
            "effective_input_sha256": request["effective_input_sha256"],
            "base_rust_project_ir_sha256": request["base_rust_project_ir"]["ir_sha256"],
            "context_sha256": request["project_repair_context"]["context_sha256"],
            "operations": operations,
        }

if __name__ == "__main__":
    unittest.main()
