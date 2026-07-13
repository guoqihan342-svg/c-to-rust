from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.project_repair_authoritative_ir import (
    persist_authoritative_project_ir,
)
from validation.tools._project_migration_harness.project_repair_coordinator import (
    resume_latest_project_repair,
)
from validation.tools.project_migration_project_repair_test_support import (
    coordinated_case,
    project_repair_test_dispatch_permit,
    sha,
)


class ProjectRepairCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-coordinator-")
        self.addCleanup(temporary.cleanup)
        self.harness = Path(temporary.name)
        self.out_root = self.harness / "target" / "run"
        self.out_root.mkdir(parents=True)
        self.ledger = ProjectLedger(
            self.out_root / "state" / "project-migration.sqlite3"
        )
        self.ledger.create_run(
            run_id="run", project_key="generic-project", source_commit="commit",
            dag_sha256=sha("dag"),
            units=[{
                "unit_id": "unit-a", "group_id": "unit-a", "wave_index": 0,
                "content_sha256": sha("unit-a"),
            }], assignments=[], max_concurrency=2, max_attempts=3,
        )

    def test_candidate_ready_never_completes_the_project(self) -> None:
        _ir, _receipt, reference = self.case("clear", conflict=False)
        result = self.resume(reference)
        self.assertEqual("ready-for-project-final", result["status"])
        self.assertFalse(result["semantic_gate"])
        self.assertFalse(result["model_launched"])
        with self.ledger.connect() as connection:
            status = connection.execute(
                "select status from project_runs where run_id='run'"
            ).fetchone()[0]
            attempts = connection.execute(
                "select count(*) from project_repair_attempts"
            ).fetchone()[0]
        self.assertEqual("active", status)
        self.assertEqual(0, attempts)

    def test_dispatch_materializes_one_request_without_launching_a_model(self) -> None:
        _ir, receipt, reference = self.case("dispatch")
        result = self.resume(reference)
        item = receipt["project_repair_queue"]["items"][0]
        self.assertEqual("repair-dispatched", result["status"])
        self.assertEqual(item["repair_id"], result["repair_id"])
        self.assertFalse(result["model_launched"])
        self.assertTrue((self.harness / result["request"]["path"]).is_file())

    def test_preflight_boundary_does_not_materialize_an_attempt(self) -> None:
        _ir, _receipt, reference = self.case("preflight-boundary")
        result = resume_latest_project_repair(
            ledger=self.ledger, run_id="run",
            base_rust_project_ir=reference, harness_root=self.harness,
            out_root=self.out_root, out_root_rel="target/run",
        )
        self.assertEqual("preflight-required", result["status"])
        with self.ledger.connect() as connection:
            attempts = connection.execute(
                "select count(*) from project_repair_attempts"
            ).fetchone()[0]
        self.assertEqual(0, attempts)

    def test_exhausted_receipt_budget_blocks_before_preflight_or_attempt(self) -> None:
        _ir, _receipt, reference = self.case("receipt-budget")
        exhausted = SimpleNamespace(
            max_provider_calls=64, provider_calls=0,
            max_receipt_epochs=1, receipt_epochs=1,
        )
        with mock.patch.object(
            self.ledger, "project_repair_budget", return_value=exhausted,
        ):
            result = resume_latest_project_repair(
                ledger=self.ledger, run_id="run",
                base_rust_project_ir=reference, harness_root=self.harness,
                out_root=self.out_root, out_root_rel="target/run",
            )
        self.assertEqual("blocked", result["status"])
        self.assertEqual("project-repair-receipt-budget-exhausted", result["stage"])
        with self.ledger.connect() as connection:
            attempts = connection.execute(
                "select count(*) from project_repair_attempts"
            ).fetchone()[0]
        self.assertEqual(0, attempts)

    def test_two_coordinators_create_only_one_running_attempt(self) -> None:
        _ir, _receipt, reference = self.case("concurrent")
        permit = project_repair_test_dispatch_permit(
            self.harness, self.out_root, self.ledger, reference,
        )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                lambda _index: self._resume_with_permit(reference, permit),
                range(2),
            ))
        self.assertCountEqual(
            ["repair-dispatched", "waiting"],
            [value["status"] for value in results],
        )
        with self.ledger.connect() as connection:
            rows = connection.execute(
                "select attempt_id,status from project_repair_attempts"
            ).fetchall()
        self.assertEqual(1, len(rows))
        self.assertEqual("running", rows[0]["status"])

    def test_stale_permit_cannot_dispatch_a_new_receipt_epoch(self) -> None:
        _first_ir, _first_receipt, first_reference = self.case("permit-first")
        first_action = resume_latest_project_repair(
            ledger=self.ledger, run_id="run",
            base_rust_project_ir=first_reference, harness_root=self.harness,
            out_root=self.out_root, out_root_rel="target/run",
        )
        stale = project_repair_test_dispatch_permit(
            self.harness, self.out_root, self.ledger, first_reference,
            action=first_action,
        )
        _second_ir, _second_receipt, second_reference = self.case(
            "permit-second", additional_conflict=True,
        )
        result = self._resume_with_permit(second_reference, stale)
        self.assertEqual("waiting", result["status"])
        self.assertEqual("project-repair-state-advanced", result["stage"])
        with self.ledger.connect() as connection:
            attempts = connection.execute(
                "select count(*) from project_repair_attempts"
            ).fetchone()[0]
        self.assertEqual(0, attempts)

    def test_expired_unstarted_attempt_is_recovered_before_redispatch(self) -> None:
        _ir, receipt, reference = self.case("expired")
        queue = receipt["project_repair_queue"]
        repair_id = queue["items"][0]["repair_id"]
        started = self.start(queue, repair_id, now_epoch=1_000)
        waiting = self.resume(reference, now_epoch=1_059)
        self.assertEqual("waiting", waiting["status"])
        result = self.resume(reference, now_epoch=1_060)
        self.assertEqual("repair-dispatched", result["status"])
        self.assertEqual([started.attempt_id], result["recovered_attempts"])
        self.assertNotEqual(started.attempt_id, result["attempt_id"])

    def test_started_unknown_attempt_requires_manual_reconciliation(self) -> None:
        _ir, receipt, reference = self.case("unknown")
        queue = receipt["project_repair_queue"]
        repair_id = queue["items"][0]["repair_id"]
        started = self.start(queue, repair_id, now_epoch=1_000)
        self.ledger.mark_project_repair_command_started(
            attempt_id=started.attempt_id, worker_id="project-repairer-test",
            expected_version=started.current.version,
        )
        result = self.resume(reference, now_epoch=2_000)
        self.assertEqual("blocked", result["status"])
        self.assertEqual("project-repair-manual-reconcile", result["stage"])
        self.assertEqual(
            ["launched-command-outcome-is-unknown"], result["blockers"],
        )

    def test_exhausted_item_is_a_finite_terminal_blocker(self) -> None:
        _ir, receipt, reference = self.case("exhausted", max_attempts=1)
        queue = receipt["project_repair_queue"]
        repair_id = queue["items"][0]["repair_id"]
        started = self.start(queue, repair_id, now_epoch=1_000)
        evidence = sha("repair-failed")
        self.ledger.record_project_repair_artifact(
            attempt_id=started.attempt_id, artifact_id="repair-failed-evidence",
            kind="test-evidence",
            repo_rel_path="target/run/project-repair/failed.json",
            content_sha256=evidence, status="failed",
        )
        self.ledger.finish_project_repair_attempt(
            attempt_id=started.attempt_id, command_id="finish-failed",
            expected_version=started.current.version,
            worker_id="project-repairer-test", outcome="failed",
            evidence_sha256=evidence, error_key="bounded_repair_failed",
        )
        result = self.resume(reference)
        self.assertEqual("blocked", result["status"])
        self.assertEqual("project-repair-terminal-blocker", result["stage"])
        self.assertEqual(["project-repair-item-exhausted"], result["blockers"])

    def test_only_latest_receipt_queue_can_be_dispatched(self) -> None:
        _first_ir, first_receipt, _first_reference = self.case("first")
        _second_ir, second_receipt, second_reference = self.case(
            "second", additional_conflict=True,
        )
        result = self.resume(second_reference)
        self.assertEqual(
            second_receipt["project_repair_queue"]["project_repair_queue_sha256"],
            result["project_repair_queue_sha256"],
        )
        self.assertNotEqual(
            first_receipt["project_repair_queue"]["project_repair_queue_sha256"],
            result["project_repair_queue_sha256"],
        )

    def case(
        self, label: str, *, conflict: bool = True, max_attempts: int = 2,
        additional_conflict: bool = False,
    ) -> tuple[dict, dict, dict]:
        ir, receipt = coordinated_case(
            label, conflict=conflict, max_attempts=max_attempts,
            additional_conflict=additional_conflict,
        )
        reference = persist_authoritative_project_ir(
            ir, out_root=self.out_root, out_root_rel="target/run",
        )
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=receipt, rust_project_ir=ir,
        )
        return ir, receipt, reference

    def resume(self, reference: dict, *, now_epoch: int | None = None) -> dict:
        observed = resume_latest_project_repair(
            ledger=self.ledger, run_id="run", base_rust_project_ir=reference,
            harness_root=self.harness, out_root=self.out_root,
            out_root_rel="target/run", now_epoch=now_epoch,
        )
        if observed["status"] != "preflight-required":
            return observed
        permit = project_repair_test_dispatch_permit(
            self.harness, self.out_root, self.ledger, reference,
            action=observed,
        )
        return self._resume_with_permit(reference, permit, now_epoch=now_epoch)

    def _resume_with_permit(
        self, reference: dict, permit, *, now_epoch: int | None = None,
    ) -> dict:
        return resume_latest_project_repair(
            ledger=self.ledger, run_id="run", base_rust_project_ir=reference,
            harness_root=self.harness, out_root=self.out_root,
            out_root_rel="target/run", now_epoch=now_epoch,
            dispatch_permit=permit,
        )

    def start(self, queue: dict, repair_id: str, *, now_epoch: int):
        return self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue["project_repair_queue_sha256"],
            repair_id=repair_id, command_id=f"manual-start-{repair_id}",
            expected_status="queued", expected_version=0,
            worker_id="project-repairer-test", input_sha256=sha(repair_id),
            metadata={"artifact_root": "target/run/project-repair"},
            lease_ttl_seconds=60, now_epoch=now_epoch,
        )


if __name__ == "__main__":
    unittest.main()
