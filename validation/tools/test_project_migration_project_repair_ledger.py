from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_project_repair_authority import ProjectRepairAuthority
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
    coordinator_receipt_projection,
    project_repair_queue_projection,
)
from validation.tools.project_migration_project_repair_test_support import coordinated_case, sha


class ProjectRepairLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-ledger-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger = ProjectLedger(self.root / "ledger.sqlite3")
        self.ledger.create_run(
            run_id="run", project_key="generic-project", source_commit="commit",
            dag_sha256=sha("dag"),
            units=[{
                "unit_id": "unit-a", "group_id": "unit-a", "wave_index": 0,
                "content_sha256": sha("unit-a"),
            }],
            assignments=[],
            max_concurrency=2, max_attempts=3,
        )

    def register(
        self, case: tuple[dict, dict] | None = None,
    ) -> tuple[dict, dict, str, str]:
        rust_project_ir, value = case or coordinated_case("base")
        result = self.ledger.register_project_interface_receipt(
            run_id="run", receipt=value, rust_project_ir=rust_project_ir,
        )
        queue = value["project_repair_queue"]
        return (
            rust_project_ir, value,
            queue["project_repair_queue_sha256"], queue["items"][0]["repair_id"],
        )

    def test_receipt_and_project_only_queue_registration_are_idempotent(self) -> None:
        rust_project_ir, value, queue_sha, repair_id = self.register()
        replay = self.ledger.register_project_interface_receipt(
            run_id="run", receipt=value, rust_project_ir=rust_project_ir,
        )
        self.assertFalse(replay.applied)
        reopened = self.ledger.load_project_interface_receipt(
            run_id="run", queue_sha256=queue_sha,
        )
        self.assertEqual(value, reopened)
        projection = self.ledger.project_repair_projection(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
        )
        self.assertEqual(("queued", 0, 0, None), (
            projection.status, projection.version,
            projection.attempt_count, projection.active_attempt_id,
        ))
        with self.ledger.connect() as connection:
            columns = {
                row[1] for row in connection.execute(
                    "pragma table_info(project_repair_items)"
                )
            }
        self.assertNotIn("unit_id", columns)
        self.assertNotIn("assigned_unit_id", columns)

    def test_receipt_rejects_ir_unit_domain_and_recomputation_drift(self) -> None:
        foreign_ir, foreign_receipt = coordinated_case(
            "foreign-unit", unit_id="unit-b",
        )
        with self.assertRaisesRegex(LedgerError, "unit domain"):
            self.ledger.register_project_interface_receipt(
                run_id="run", receipt=foreign_receipt,
                rust_project_ir=foreign_ir,
            )

        wrong_dag_ir, wrong_dag_receipt = coordinated_case(
            "wrong-dag", dag_sha256=sha("wrong-dag"),
        )
        with self.assertRaisesRegex(LedgerError, "run DAG"):
            self.ledger.register_project_interface_receipt(
                run_id="run", receipt=wrong_dag_receipt,
                rust_project_ir=wrong_dag_ir,
            )

        rust_project_ir, receipt = coordinated_case("recomputation-drift")
        queue = receipt["project_repair_queue"]
        queue["items"][0]["affected_unit_ids"] = []
        queue["project_repair_queue_sha256"] = content_sha256(
            project_repair_queue_projection(queue)
        )
        receipt["coordinator_receipt_sha256"] = content_sha256(
            coordinator_receipt_projection(receipt)
        )
        with self.assertRaisesRegex(LedgerError, "recomputable"):
            self.ledger.register_project_interface_receipt(
                run_id="run", receipt=receipt,
                rust_project_ir=rust_project_ir,
            )

    def test_attempt_completion_and_conflict_free_recoordination_replay(self) -> None:
        _, _, queue_sha, repair_id = self.register()
        clear_ir, clear = coordinated_case("clear", conflict=False)
        started = self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id="start-1", expected_status="queued", expected_version=0,
            worker_id="project-repairer-1", input_sha256=sha("minimal-context"),
            metadata=self._metadata(), lease_ttl_seconds=60, now_epoch=1_000,
        )
        self.assertEqual(("running", 1, 1), (
            started.current.status, started.current.version,
            started.current.attempt_count,
        ))
        self._artifact(started.attempt_id, sha("worker-output"), "worker-output")
        self._candidate_artifact(started.attempt_id, clear_ir["ir_sha256"])
        completed = self.ledger.finish_project_repair_attempt(
            attempt_id=started.attempt_id, command_id="finish-1",
            expected_version=1, worker_id="project-repairer-1",
            outcome="completed", evidence_sha256=sha("worker-output"),
            output_ir_sha256=clear_ir["ir_sha256"],
        )
        self.assertEqual("candidate-ready", completed.current.status)
        self.assertFalse(self.ledger.finish_project_repair_attempt(
            attempt_id=started.attempt_id, command_id="finish-1",
            expected_version=1, worker_id="project-repairer-1",
            outcome="completed", evidence_sha256=sha("worker-output"),
            output_ir_sha256=clear_ir["ir_sha256"],
        ).applied)
        clear_registration = self.ledger.register_project_interface_receipt(
            run_id="run", receipt=clear, rust_project_ir=clear_ir,
        )
        resolved = self.ledger.resolve_project_repair_candidate(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id="resolve-1", expected_version=2,
            coordinator_receipt_sha256=clear_registration.coordinator_receipt_sha256,
        )
        self.assertEqual("resolved", resolved.current.status)
        self.assertFalse(self.ledger.resolve_project_repair_candidate(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id="resolve-1", expected_version=2,
            coordinator_receipt_sha256=clear_registration.coordinator_receipt_sha256,
        ).applied)
        self.assertFalse(self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id="start-1", expected_status="queued", expected_version=0,
            worker_id="project-repairer-1", input_sha256=sha("minimal-context"),
            metadata=self._metadata(), lease_ttl_seconds=60,
        ).applied)
        with self.assertRaisesRegex(LedgerError, "replay changed"):
            self.ledger.start_project_repair_attempt(
                run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
                command_id="start-1", expected_status="queued", expected_version=0,
                worker_id="project-repairer-1",
                input_sha256=sha("minimal-context"),
                metadata={"artifact_root": "target/run/other"},
                lease_ttl_seconds=60,
            )
        with self.assertRaisesRegex(LedgerError, "replay changed"):
            self.ledger.start_project_repair_attempt(
                run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
                command_id="start-1", expected_status="queued", expected_version=0,
                worker_id="project-repairer-1",
                input_sha256=sha("minimal-context"),
                metadata=self._metadata(), lease_ttl_seconds=120,
            )

    def test_new_receipt_cannot_bypass_a_running_project_repair(self) -> None:
        rust_project_ir, _, queue_sha, repair_id = self.register()
        self._start(queue_sha, repair_id, "start", "queued", 0)
        alternate = coordinate_project_interfaces(
            rust_project_ir, max_repairs=16, max_attempts_per_item=2,
        )
        with self.assertRaisesRegex(LedgerError, "cannot advance"):
            self.ledger.register_project_interface_receipt(
                run_id="run", receipt=alternate,
                rust_project_ir=rust_project_ir,
            )

    def test_projection_tamper_and_partial_transaction_fail_closed(self) -> None:
        _, _, queue_sha, repair_id = self.register()
        with self.ledger.connect() as connection:
            connection.execute(
                """update project_repair_items set status='failed'
                   where run_id='run' and project_repair_queue_sha256=? and repair_id=?""",
                (queue_sha, repair_id),
            )
        with self.assertRaisesRegex(LedgerError, "drifted"):
            self.ledger.project_repair_projection(
                run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            )

        clean = coordinated_case("atomic")
        _, _, clean_queue, clean_repair = self.register(clean)
        with self.ledger.connect() as connection:
            connection.execute(
                """create temp trigger reject_project_repair_projection
                   before update on project_repair_items
                   begin select raise(abort,'projection rejected'); end"""
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "projection rejected"):
                ProjectRepairAuthority(connection).start_attempt(
                    run_id="run", queue_sha256=clean_queue,
                    repair_id=clean_repair, command_id="atomic-start",
                    expected_status="queued", expected_version=0,
                    worker_id="project-repairer-1", input_sha256=sha("atomic-input"),
                )
            self.assertEqual(0, connection.execute(
                """select count(*) from project_repair_events
                   where project_repair_queue_sha256=?""", (clean_queue,),
            ).fetchone()[0])
            self.assertEqual(0, connection.execute(
                """select count(*) from project_repair_attempts
                   where project_repair_queue_sha256=?""", (clean_queue,),
            ).fetchone()[0])

    def test_receipt_and_event_rows_are_immutable(self) -> None:
        _, _, queue_sha, repair_id = self.register()
        started = self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id="start", expected_status="queued", expected_version=0,
            worker_id="project-repairer-1", input_sha256=sha("start"),
            metadata={"artifact_root": "target/run/project-repair"},
        )
        self.ledger.record_project_repair_artifact(
            attempt_id=started.attempt_id, artifact_id="artifact-1",
            kind="provider-prompt",
            repo_rel_path="target/run/project-repair/prompts/prompt.json",
            content_sha256=sha("prompt"), status="written",
        )
        with self.ledger.connect() as connection:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    """update project_interface_receipts set status='candidate-ready'
                       where run_id='run' and project_repair_queue_sha256=?""",
                    (queue_sha,),
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "update project_repair_events set reason='changed' where run_id='run'"
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "update project_repair_artifacts set status='failed' where run_id='run'"
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "delete from project_repair_artifacts where run_id='run'"
                )

    def _start(
        self, queue_sha: str, repair_id: str, command_id: str,
        status: str, version: int,
    ):
        return self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id=command_id, expected_status=status, expected_version=version,
            worker_id="project-repairer-1", input_sha256=sha(command_id),
            metadata=self._metadata(), lease_ttl_seconds=60, now_epoch=1_000,
        )

    @staticmethod
    def _metadata() -> dict[str, str]:
        return {"artifact_root": "target/run/project-repair"}

    def _artifact(self, attempt_id: str, digest: str, label: str) -> None:
        self.ledger.record_project_repair_artifact(
            attempt_id=attempt_id,
            artifact_id=f"evidence-{label}-{digest[:16]}",
            kind="test-evidence",
            repo_rel_path=f"target/run/project-repair/evidence/{attempt_id}-{label}.json",
            content_sha256=digest, status="diagnostic",
        )

    def _candidate_artifact(self, attempt_id: str, ir_sha256: str) -> None:
        self.ledger.record_project_repair_artifact(
            attempt_id=attempt_id,
            artifact_id=f"candidate-{ir_sha256[:24]}",
            kind="rust-project-ir-candidate",
            repo_rel_path=(
                f"target/run/project-repair/ir-candidates/{ir_sha256}.json"
            ),
            content_sha256=sha(f"candidate-content-{ir_sha256}"),
            status="candidate", metadata={"ir_sha256": ir_sha256},
        )


if __name__ == "__main__":
    unittest.main()
