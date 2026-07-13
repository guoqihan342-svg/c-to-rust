from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.gate_candidate_sets import (
    candidate_set_members,
)
from validation.tools._project_migration_harness.ledger import LedgerError, ProjectLedger
from validation.tools.project_migration_run_contract_test_support import (
    migration_run_metadata,
)


class ProjectMigrationVerificationCandidateSetTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="verification-candidate-set-")
        self.addCleanup(temporary.cleanup)
        self.out_root = Path(temporary.name) / "target" / "run"
        self.database = self.out_root / "state" / "project-migration.sqlite3"
        self.ledger = ProjectLedger(self.database)
        units = [
            {"unit_id": name, "group_id": name, "wave_index": wave,
             "content_sha256": content_sha256(f"unit-{name}")}
            for name, wave in (("base", 0), ("leaf", 1), ("future", 2))
        ]
        assignments = [
            {"unit_id": name, "worker_id": f"worker-{name}", "role": "translator",
             "out_root": f"target/run/workers/{name}", "max_attempts": 3}
            for name in ("base", "leaf", "future")
        ]
        dag_sha256 = content_sha256("dag")
        self.ledger.create_run(
            run_id="run", project_key="neutral", source_commit="commit",
            dag_sha256=dag_sha256, units=units, assignments=assignments,
            max_concurrency=3, max_attempts=3,
            metadata=migration_run_metadata(
                self.out_root, self.database, run_id="run", dag_sha256=dag_sha256,
                units=units,
                dependencies={"base": [], "leaf": ["base"], "future": ["leaf"]},
            ),
        )
        self.base_id = self.add_candidate("base", "base-v1")
        self.leaf_id = self.add_candidate("leaf", "leaf-v1")
        with self.ledger.connect() as connection:
            connection.execute(
                """update migration_units set status='resume-ready',
                   resumable_status='last_good',last_good_artifact_id=?
                   where run_id='run' and unit_id='base'""",
                (self.base_id,),
            )
            connection.execute(
                """update migration_units set status='candidate-ready',
                   resumable_status='awaiting_gate'
                   where run_id='run' and unit_id='leaf'"""
            )

    def test_partial_wave_binds_last_good_dependencies_and_active_candidate(self) -> None:
        digest = self.ledger.bind_verification_candidate_set(run_id="run")
        with self.ledger.connect() as connection:
            members = candidate_set_members(connection, "run", digest)
        self.assertEqual(["base", "leaf"], [item["unit_id"] for item in members])
        self.assertEqual(self.base_id, members[0]["artifact_id"])
        self.assertEqual(self.leaf_id, members[1]["artifact_id"])
        self.assertNotIn("future", {item["unit_id"] for item in members})

    def test_retry_ready_failed_candidate_is_not_reused_as_active(self) -> None:
        with self.ledger.connect() as connection:
            connection.execute(
                """update migration_units set status='retry-ready',resumable_status='retryable'
                   where run_id='run' and unit_id='leaf'"""
            )
        with self.assertRaisesRegex(LedgerError, "active candidate"):
            self.ledger.bind_verification_candidate_set(run_id="run")

    def test_active_roots_must_be_transitively_independent(self) -> None:
        future_id = self.add_candidate("future", "future-v1")
        with self.ledger.connect() as connection:
            connection.execute(
                """update migration_units set status='candidate-ready',
                   resumable_status='awaiting_gate' where run_id='run' and unit_id='base'"""
            )
            connection.execute(
                """update migration_units set status='resume-ready',
                   resumable_status='last_good',last_good_artifact_id=?
                   where run_id='run' and unit_id='leaf'""",
                (self.leaf_id,),
            )
            connection.execute(
                """update migration_units set status='candidate-ready',
                   resumable_status='awaiting_gate' where run_id='run' and unit_id='future'"""
            )
        self.assertTrue(future_id)
        with self.assertRaisesRegex(LedgerError, "dependency-independent"):
            self.ledger.bind_verification_candidate_set(run_id="run")

    def add_candidate(self, unit_id: str, label: str) -> str:
        artifact_id = f"candidate-{label}"
        digest = content_sha256(label)
        worker = f"worker-{unit_id}"
        attempt = f"run:{unit_id}:{worker}:1"
        with self.ledger.connect() as connection:
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,worker_id,
                   status,fencing_token,input_sha256,output_sha256,error_key,started_at,
                   finished_at,metadata_json)
                   values (?,?,?,'translator',1,?,'completed',1,?,?,null,?,?, '{}')""",
                (attempt, "run", unit_id, worker, content_sha256(f"input-{label}"),
                 digest, "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"),
            )
            connection.execute(
                """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,worker_id,
                   fencing_token,kind,repo_rel_path,content_sha256,status,created_at,metadata_json)
                   values ('run',?,?,?,?,1,'rust-candidate',?,?,'candidate',?, '{}')""",
                (artifact_id, unit_id, attempt, worker,
                 f"target/run/workers/{unit_id}/{label}.rs", digest,
                 "2026-01-01T00:00:01Z"),
            )
        return artifact_id


if __name__ == "__main__":
    unittest.main()
