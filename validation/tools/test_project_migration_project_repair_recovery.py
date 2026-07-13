from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools.project_migration_project_repair_test_support import (
    coordinated_case,
    sha,
)


class ProjectRepairRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-repair-recovery-")
        self.addCleanup(temporary.cleanup)
        self.ledger = ProjectLedger(Path(temporary.name) / "ledger.sqlite3")
        self.ledger.create_run(
            run_id="run", project_key="generic-project", source_commit="commit",
            dag_sha256=sha("dag"),
            units=[{
                "unit_id": "unit-a", "group_id": "unit-a", "wave_index": 0,
                "content_sha256": sha("unit-a"),
            }],
            assignments=[], max_concurrency=2, max_attempts=3,
        )

    def test_recovery_retry_and_budget_exhaustion_are_replayable(self) -> None:
        queue_sha, repair_id = self.register("budget", max_attempts=2)
        first = self.start(queue_sha, repair_id, "start-1", "queued", 0)
        recovered = self.ledger.recover_project_repair_attempt(
            attempt_id=first.attempt_id, command_id="recover-1",
            expected_version=1, evidence_sha256=sha("crash-proof"),
            worker_id="project-repairer-1", recovered_at_epoch=1_001,
        )
        self.assertEqual("retry-ready", recovered.current.status)
        self.assertFalse(self.ledger.recover_project_repair_attempt(
            attempt_id=first.attempt_id, command_id="recover-1",
            expected_version=1, evidence_sha256=sha("crash-proof"),
            worker_id="project-repairer-1", recovered_at_epoch=1_001,
        ).applied)

        second = self.start(queue_sha, repair_id, "start-2", "retry-ready", 2)
        self.artifact(second.attempt_id, sha("failed-gate"), "failed-gate")
        exhausted = self.ledger.finish_project_repair_attempt(
            attempt_id=second.attempt_id, command_id="finish-2",
            expected_version=3, worker_id="project-repairer-1",
            outcome="failed", evidence_sha256=sha("failed-gate"),
            error_key="compile_failed",
        )
        self.assertEqual("exhausted", exhausted.current.status)
        with self.assertRaisesRegex(LedgerError, "replay changed"):
            self.ledger.finish_project_repair_attempt(
                attempt_id=second.attempt_id, command_id="finish-2",
                expected_version=3, worker_id="project-repairer-1",
                outcome="failed", evidence_sha256=sha("failed-gate"),
                error_key="different_failure",
            )

    def test_rollback_and_command_binding_are_strict(self) -> None:
        queue_sha, repair_id = self.register("rollback")
        started = self.start(queue_sha, repair_id, "start", "queued", 0)
        self.artifact(started.attempt_id, sha("finish"), "finish")
        self.artifact(
            started.attempt_id, sha("failed-recoordination"),
            "failed-recoordination",
        )
        self.candidate_artifact(started.attempt_id, sha("candidate"))
        self.ledger.finish_project_repair_attempt(
            attempt_id=started.attempt_id, command_id="finish", expected_version=1,
            worker_id="project-repairer-1", outcome="completed",
            evidence_sha256=sha("finish"), output_ir_sha256=sha("candidate"),
        )
        rolled = self.ledger.rollback_project_repair_candidate(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id="rollback", expected_version=2,
            evidence_sha256=sha("failed-recoordination"),
        )
        self.assertEqual(("retry-ready", None), (
            rolled.current.status, rolled.current.candidate_ir_sha256,
        ))
        with self.assertRaises(LedgerError):
            self.ledger.start_project_repair_attempt(
                run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
                command_id="start", expected_status="queued", expected_version=0,
                worker_id="project-repairer-1", input_sha256=sha("changed-input"),
                metadata=self.metadata(), lease_ttl_seconds=60,
            )

    def test_started_unknown_result_requires_terminal_evidence(self) -> None:
        queue_sha, repair_id = self.register("lease-and-evidence")
        started = self.start(queue_sha, repair_id, "start", "queued", 0)
        with self.assertRaisesRegex(LedgerError, "lease is still active"):
            self.ledger.recover_project_repair_attempt(
                attempt_id=started.attempt_id, command_id="recover-too-early",
                expected_version=1, evidence_sha256=sha("expired-worker"),
                recovered_at_epoch=1_059,
            )
        with self.assertRaisesRegex(LedgerError, "worker binding"):
            self.ledger.recover_project_repair_attempt(
                attempt_id=started.attempt_id, command_id="recover-wrong-worker",
                expected_version=1, evidence_sha256=sha("wrong-worker"),
                worker_id="another-worker", recovered_at_epoch=1_001,
            )
        self.assertTrue(self.ledger.mark_project_repair_command_started(
            attempt_id=started.attempt_id, worker_id="project-repairer-1",
            expected_version=1,
        ))
        with self.assertRaisesRegex(LedgerError, "requires reconciliation"):
            self.ledger.recover_project_repair_attempt(
                attempt_id=started.attempt_id, command_id="recover-expired-unknown",
                expected_version=1, evidence_sha256=sha("expired-unknown"),
                recovered_at_epoch=1_060,
            )
        with self.assertRaisesRegex(LedgerError, "immutable artifact"):
            self.ledger.recover_project_repair_attempt(
                attempt_id=started.attempt_id, command_id="recover-known-no-evidence",
                expected_version=1, evidence_sha256=sha("known-result"),
                worker_id="project-repairer-1", result_known=True,
                recovered_at_epoch=1_001,
            )
        with self.assertRaisesRegex(LedgerError, "immutable artifact"):
            self.ledger.finish_project_repair_attempt(
                attempt_id=started.attempt_id, command_id="unknown-without-evidence",
                expected_version=1, worker_id="project-repairer-1",
                outcome="unknown", evidence_sha256=sha("unknown-result"),
                error_key="project_repair_provider_result_unknown",
            )
        self.artifact(started.attempt_id, sha("unknown-result"), "unknown-result")
        terminal = self.ledger.finish_project_repair_attempt(
            attempt_id=started.attempt_id, command_id="unknown-result",
            expected_version=1, worker_id="project-repairer-1",
            outcome="unknown", evidence_sha256=sha("unknown-result"),
            error_key="project_repair_provider_result_unknown",
        )
        self.assertEqual("failed", terminal.current.status)

    def test_expired_unstarted_attempt_allows_external_recovery(self) -> None:
        queue_sha, repair_id = self.register("expired-recovery")
        started = self.start(queue_sha, repair_id, "start", "queued", 0)
        recovered = self.ledger.recover_project_repair_attempt(
            attempt_id=started.attempt_id, command_id="recover-expired",
            expected_version=1, evidence_sha256=sha("expired-recovery"),
            recovered_at_epoch=1_060,
        )
        self.assertEqual("retry-ready", recovered.current.status)

    def register(self, label: str, *, max_attempts: int = 2) -> tuple[str, str]:
        rust_project_ir, receipt = coordinated_case(
            label, max_attempts=max_attempts,
        )
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=receipt, rust_project_ir=rust_project_ir,
        )
        queue = receipt["project_repair_queue"]
        return queue["project_repair_queue_sha256"], queue["items"][0]["repair_id"]

    def start(
        self, queue_sha: str, repair_id: str, command_id: str,
        status: str, version: int,
    ):
        return self.ledger.start_project_repair_attempt(
            run_id="run", queue_sha256=queue_sha, repair_id=repair_id,
            command_id=command_id, expected_status=status, expected_version=version,
            worker_id="project-repairer-1", input_sha256=sha(command_id),
            metadata=self.metadata(), lease_ttl_seconds=60, now_epoch=1_000,
        )

    @staticmethod
    def metadata() -> dict[str, str]:
        return {"artifact_root": "target/run/project-repair"}

    def artifact(self, attempt_id: str, digest: str, label: str) -> None:
        self.ledger.record_project_repair_artifact(
            attempt_id=attempt_id, artifact_id=f"evidence-{label}-{digest[:16]}",
            kind="test-evidence",
            repo_rel_path=f"target/run/project-repair/evidence/{attempt_id}-{label}.json",
            content_sha256=digest, status="diagnostic",
        )

    def candidate_artifact(self, attempt_id: str, ir_sha256: str) -> None:
        self.ledger.record_project_repair_artifact(
            attempt_id=attempt_id, artifact_id=f"candidate-{ir_sha256[:24]}",
            kind="rust-project-ir-candidate",
            repo_rel_path=f"target/run/project-repair/ir-candidates/{ir_sha256}.json",
            content_sha256=sha(f"candidate-content-{ir_sha256}"),
            status="candidate", metadata={"ir_sha256": ir_sha256},
        )


if __name__ == "__main__":
    unittest.main()
