from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.project_repair_ingest import (
    ingest_project_repair_response,
)
from validation.tools.project_migration_project_repair_test_support import (
    materialized_repair_case,
)


class ProjectRepairWorkerSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-security-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "target/run"
        self.ledger = ProjectLedger(self.out / "state/project-migration.sqlite3")

    def test_unrelated_visible_record_cannot_be_removed(self) -> None:
        request, _, _, _ = materialized_repair_case(
            self.root, self.out, self.ledger, "unrelated-remove",
            additional_conflict=True,
        )
        result = self.ingest(request, [{
            "section": "public_api", "action": "remove",
            "record_id": "api-other-left-unrelated-remove", "changes": {},
        }])

        self.assertEqual("retry-ready", result["status"])
        self.assertEqual("invalid_project_repair_ir_candidate", result["error_code"])
        latest = self.ledger.load_latest_project_interface_receipt(run_id="run")
        self.assertEqual(1, latest[0])

    def test_terminal_replay_cannot_overwrite_response_evidence(self) -> None:
        request, _, _, duplicate_id = materialized_repair_case(
            self.root, self.out, self.ledger, "terminal-replay",
        )
        resolved = self.ingest(request, [{
            "section": "public_api", "action": "remove",
            "record_id": duplicate_id, "changes": {},
        }])
        response_path = self.root / Path(
            *resolved["artifacts"]["response"]["path"].split("/")
        )
        original = response_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "active attempt"):
            self.ingest(request, [{
                "section": "public_api", "action": "replace",
                "record_id": duplicate_id,
                "changes": {"signature": "fn()->u16"},
            }])

        self.assertEqual(original, response_path.read_bytes())
        self.assertEqual(
            1, len(list((self.out / "project-repair/responses").glob("*.json"))),
        )

    def test_ingest_rejects_out_root_alias_before_writing(self) -> None:
        request, _, _, duplicate_id = materialized_repair_case(
            self.root, self.out, self.ledger, "out-root-binding",
        )
        outside = self.root / "outside"
        outside.mkdir()
        with self.assertRaisesRegex(ValueError, "out_root/out_root_rel"):
            ingest_project_repair_response(
                request, self.response(request, [{
                    "section": "public_api", "action": "remove",
                    "record_id": duplicate_id, "changes": {},
                }]),
                ledger=self.ledger, harness_root=self.root,
                out_root=outside, out_root_rel="target/run",
            )
        self.assertEqual([], list(outside.iterdir()))

    def test_candidate_finalization_is_atomic_with_receipt_registration(self) -> None:
        request, _, _, duplicate_id = materialized_repair_case(
            self.root, self.out, self.ledger, "atomic-finalize",
        )
        with self.ledger.connect() as connection:
            connection.execute(
                """create trigger reject_project_repair_resolution
                   before update on project_repair_items
                   when new.status='resolved'
                   begin select raise(abort,'resolution rejected'); end"""
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "resolution rejected"):
            self.ingest(request, [{
                "section": "public_api", "action": "remove",
                "record_id": duplicate_id, "changes": {},
            }])

        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=request["project_repair_queue_sha256"],
            repair_id=request["repair_id"],
        )
        self.assertEqual(("running", 1), (projection.status, projection.version))
        latest = self.ledger.load_latest_project_interface_receipt(run_id="run")
        self.assertEqual(1, latest[0])

    def ingest(self, request: dict, operations: list[dict]) -> dict:
        return ingest_project_repair_response(
            request, self.response(request, operations), ledger=self.ledger,
            harness_root=self.root, out_root=self.out, out_root_rel="target/run",
        )

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
