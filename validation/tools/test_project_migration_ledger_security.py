from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import time
import unittest

from validation.tools._project_migration_harness.ledger import (
    LedgerError,
    LeaseConflict,
    ProjectLedger,
    StaleFence,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationLedgerSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-ledger-security-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.ledger = ProjectLedger(self.root / "ledger.sqlite3")

    @staticmethod
    def unit(unit_id: str) -> dict[str, object]:
        return {
            "unit_id": unit_id,
            "group_id": unit_id,
            "wave_index": 0,
            "content_sha256": digest(unit_id),
        }

    @staticmethod
    def assignment(unit_id: str, worker_id: str, role: str, *, attempts: int = 2) -> dict[str, object]:
        return {
            "unit_id": unit_id,
            "worker_id": worker_id,
            "role": role,
            "out_root": f"target/project/workers/{worker_id}/out",
            "max_attempts": attempts,
        }

    def create_run(
        self, units: list[str], assignments: list[dict[str, object]], *,
        run_id: str = "run-security", max_concurrency: int = 4, max_attempts: int = 2,
    ) -> None:
        self.ledger.create_run(
            run_id=run_id,
            project_key=f"project-{run_id}",
            source_commit="source-commit",
            dag_sha256=digest(f"dag-{run_id}"),
            units=[self.unit(item) for item in units],
            assignments=assignments,
            max_concurrency=max_concurrency,
            max_attempts=max_attempts,
        )

    def start(self, unit_id: str, worker_id: str, role: str) -> tuple[int, str]:
        token = self.ledger.acquire_lease(
            run_id="run-security", unit_id=unit_id, owner=worker_id, ttl_seconds=120,
        )
        attempt = self.ledger.start_attempt(
            run_id="run-security", unit_id=unit_id, role=role, worker_id=worker_id,
            fencing_token=token, input_sha256=digest(f"input-{unit_id}-{role}"),
        )
        return token, attempt

    def candidate(self, unit_id: str, worker_id: str, token: int, attempt: str, name: str) -> str:
        content = digest(name)
        self.ledger.record_artifact(
            run_id="run-security", unit_id=unit_id, owner=worker_id, fencing_token=token,
            artifact_id=name, attempt_id=attempt, kind="rust-candidate",
            repo_rel_path=f"target/project/workers/{worker_id}/out/{name}.rs",
            content_sha256=content, status="candidate",
        )
        return content

    def test_attempt_finish_and_artifact_write_require_bound_identity_and_current_fence(self) -> None:
        self.create_run(["unit-a"], [self.assignment("unit-a", "worker-a", "translator")])
        token, attempt = self.start("unit-a", "worker-a", "translator")

        with self.assertRaises(StaleFence):
            self.ledger.finish_attempt(
                attempt_id=attempt, owner="worker-b", fencing_token=token,
                status="failed", next_status="retry-ready", error_key="worker_failed",
            )
        with self.assertRaises(LeaseConflict):
            self.ledger.acquire_lease(
                run_id="run-security", unit_id="unit-a", owner="worker-a", ttl_seconds=120,
            )
        self.ledger.release_lease(
            run_id="run-security", unit_id="unit-a", owner="worker-a", fencing_token=token,
        )
        newer = self.ledger.acquire_lease(
            run_id="run-security", unit_id="unit-a", owner="worker-a", ttl_seconds=120,
        )
        with self.assertRaises(StaleFence):
            self.ledger.record_artifact(
                run_id="run-security", unit_id="unit-a", owner="worker-a", fencing_token=newer,
                artifact_id="wrong-fence", attempt_id=attempt, kind="candidate",
                repo_rel_path="target/project/workers/worker-a/out/wrong.rs",
                content_sha256=digest("wrong"), status="candidate",
            )
        with self.assertRaises(StaleFence):
            self.ledger.finish_attempt(
                attempt_id=attempt, owner="worker-a", fencing_token=token,
                status="failed", next_status="retry-ready", error_key="stale_fence",
            )

    def test_no_worker_role_can_write_semantic_acceptance_state(self) -> None:
        roles = ("planner", "translator", "reviewer", "repairer")
        units = [f"unit-{role}" for role in roles]
        assignments = [self.assignment(f"unit-{role}", f"worker-{role}", role) for role in roles]
        self.create_run(units, assignments)
        for role in roles:
            unit_id, worker_id = f"unit-{role}", f"worker-{role}"
            token, attempt = self.start(unit_id, worker_id, role)
            for forbidden in ("semantic_pass", "gate-passed", "verified", "accepted", "passed"):
                with self.subTest(role=role, forbidden=forbidden):
                    with self.assertRaises(ValueError):
                        self.ledger.finish_attempt(
                            attempt_id=attempt, owner=worker_id, fencing_token=token,
                            status="completed", next_status=forbidden, output_sha256=digest("output"),
                        )
                    with self.assertRaises(ValueError):
                        self.ledger.record_artifact(
                            run_id="run-security", unit_id=unit_id, owner=worker_id,
                            fencing_token=token, artifact_id=f"artifact-{forbidden}",
                            attempt_id=attempt, kind="candidate",
                            repo_rel_path=f"target/project/workers/{worker_id}/out/{forbidden}.json",
                            content_sha256=digest(forbidden), status=forbidden,
                        )
            with self.assertRaises(ValueError):
                self.ledger.record_artifact(
                    run_id="run-security", unit_id=unit_id, owner=worker_id,
                    fencing_token=token, artifact_id="metadata-claim", attempt_id=attempt,
                    kind="candidate", repo_rel_path=f"target/project/workers/{worker_id}/out/claim.json",
                    content_sha256=digest("metadata-claim"), status="candidate",
                    metadata={"semantic_pass": True},
                )
            with self.assertRaises(LedgerError):
                self.ledger.point_last_good(
                    run_id="run-security", unit_id=unit_id, owner=worker_id,
                    fencing_token=token, artifact_id="anything",
                )

    def test_assignments_enforce_role_out_root_attempt_limit_and_run_concurrency(self) -> None:
        assignments = [
            self.assignment("unit-a", "worker-a", "translator", attempts=1),
            self.assignment("unit-b", "worker-b", "translator", attempts=1),
        ]
        self.create_run(["unit-a", "unit-b"], assignments, max_concurrency=1, max_attempts=1)
        token = self.ledger.acquire_lease(
            run_id="run-security", unit_id="unit-a", owner="worker-a", ttl_seconds=120,
        )
        with self.assertRaises(LeaseConflict):
            self.ledger.acquire_lease(
                run_id="run-security", unit_id="unit-b", owner="worker-b", ttl_seconds=120,
            )
        with self.assertRaises(LeaseConflict):
            self.ledger.acquire_lease(
                run_id="run-security", unit_id="unit-a", owner="unassigned", ttl_seconds=120,
            )
        with self.assertRaises(LedgerError):
            self.ledger.start_attempt(
                run_id="run-security", unit_id="unit-a", role="reviewer", worker_id="worker-a",
                fencing_token=token, input_sha256=digest("bad-role"),
            )
        attempt = self.ledger.start_attempt(
            run_id="run-security", unit_id="unit-a", role="translator", worker_id="worker-a",
            fencing_token=token, input_sha256=digest("good-role"),
        )
        with self.assertRaises(LedgerError):
            self.ledger.record_artifact(
                run_id="run-security", unit_id="unit-a", owner="worker-a", fencing_token=token,
                artifact_id="escape", attempt_id=attempt, kind="candidate",
                repo_rel_path="target/project/other/escape.rs",
                content_sha256=digest("escape"), status="candidate",
            )
        self.ledger.finish_attempt(
            attempt_id=attempt, owner="worker-a", fencing_token=token,
            status="failed", next_status="retry-ready", error_key="translation_failed",
        )
        self.ledger.release_lease(
            run_id="run-security", unit_id="unit-a", owner="worker-a", fencing_token=token,
        )
        next_token = self.ledger.acquire_lease(
            run_id="run-security", unit_id="unit-a", owner="worker-a", ttl_seconds=120,
        )
        with self.assertRaises(LedgerError):
            self.ledger.start_attempt(
                run_id="run-security", unit_id="unit-a", role="translator", worker_id="worker-a",
                fencing_token=next_token, input_sha256=digest("exhausted"),
            )

    def test_resume_excludes_active_lease_running_terminal_exhausted_and_inactive_run(self) -> None:
        units = ["ready", "leased", "running", "terminal", "exhausted"]
        assignments = [self.assignment(unit, f"worker-{unit}", "translator", attempts=1) for unit in units]
        self.create_run(units, assignments, max_concurrency=5, max_attempts=1)
        self.ledger.acquire_lease(
            run_id="run-security", unit_id="leased", owner="worker-leased", ttl_seconds=120,
        )
        running_token, _ = self.start("running", "worker-running", "translator")
        with self.ledger.connect() as connection:
            connection.execute(
                "update leases set status='expired',expires_at=? where run_id=? and unit_id=?",
                (int(time.time()) - 1, "run-security", "running"),
            )
        terminal_token, terminal_attempt = self.start("terminal", "worker-terminal", "translator")
        self.ledger.finish_attempt(
            attempt_id=terminal_attempt, owner="worker-terminal", fencing_token=terminal_token,
            status="blocked", next_status="blocked", error_key="terminal_block",
        )
        self.ledger.release_lease(
            run_id="run-security", unit_id="terminal", owner="worker-terminal",
            fencing_token=terminal_token,
        )
        exhausted_token, exhausted_attempt = self.start("exhausted", "worker-exhausted", "translator")
        self.ledger.finish_attempt(
            attempt_id=exhausted_attempt, owner="worker-exhausted", fencing_token=exhausted_token,
            status="failed", next_status="retry-ready", error_key="attempt_failed",
        )
        self.ledger.release_lease(
            run_id="run-security", unit_id="exhausted", owner="worker-exhausted",
            fencing_token=exhausted_token,
        )
        self.assertEqual(["ready"], [row["unit_id"] for row in self.ledger.resume_units("run-security")])
        with self.ledger.connect() as connection:
            connection.execute("update project_runs set status='completed' where run_id='run-security'")
        self.assertEqual([], self.ledger.resume_units("run-security"))
        self.assertGreater(running_token, 0)

if __name__ == "__main__":
    unittest.main()
