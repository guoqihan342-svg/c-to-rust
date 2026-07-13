from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.gate_candidate_sets import (
    candidate_set_members,
)
from validation.tools._project_migration_harness.ledger import LedgerError, ProjectLedger
from validation.tools._project_migration_harness.ledger_transition_authority import (
    TransitionAuthority, load_unit_projection,
)
from validation.tools._project_migration_harness.ledger_transition_commands import (
    attempt_finished_command, attempt_started_command,
    host_verification_failed_command, host_verifier_promoted_command,
)
from validation.tools._project_migration_harness.ledger_transition_policy import (
    UnitState, stable_transition_command_id,
)
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
        self.promote("base", self.base_id)

    def test_partial_wave_binds_last_good_dependencies_and_active_candidate(self) -> None:
        digest = self.ledger.bind_verification_candidate_set(run_id="run")
        with self.ledger.connect() as connection:
            members = candidate_set_members(connection, "run", digest)
        self.assertEqual(["base", "leaf"], [item["unit_id"] for item in members])
        self.assertEqual(self.base_id, members[0]["artifact_id"])
        self.assertEqual(self.leaf_id, members[1]["artifact_id"])
        self.assertNotIn("future", {item["unit_id"] for item in members})

    def test_retry_ready_failed_candidate_is_not_reused_as_active(self) -> None:
        self.fail_candidate("leaf", self.leaf_id)
        with self.assertRaisesRegex(LedgerError, "active candidate"):
            self.ledger.bind_verification_candidate_set(run_id="run")

    def test_active_roots_must_be_transitively_independent(self) -> None:
        future_id = self.add_candidate("future", "future-v1")
        self.add_candidate("base", "base-v2")
        self.promote("leaf", self.leaf_id)
        self.assertTrue(future_id)
        with self.assertRaisesRegex(LedgerError, "dependency-independent"):
            self.ledger.bind_verification_candidate_set(run_id="run")

    def add_candidate(self, unit_id: str, label: str) -> str:
        artifact_id = f"candidate-{label}"
        digest = content_sha256(label)
        worker = f"worker-{unit_id}"
        with self.ledger.connect() as connection:
            ordinal = int(connection.execute(
                """select count(*)+1 from attempts where run_id='run'
                   and unit_id=?""", (unit_id,),
            ).fetchone()[0])
            attempt = f"run:{unit_id}:{worker}:{ordinal}"
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,worker_id,
                   status,fencing_token,input_sha256,output_sha256,error_key,started_at,
                   finished_at,metadata_json)
                   values (?,?,?,'translator',?,?,'completed',?,?,?,null,?,?, '{}')""",
                (attempt, "run", unit_id, ordinal, worker, ordinal,
                 content_sha256(f"input-{label}"),
                 digest, "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"),
            )
            connection.execute(
                """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,worker_id,
                   fencing_token,kind,repo_rel_path,content_sha256,status,created_at,metadata_json)
                   values ('run',?,?,?,?,?,'rust-candidate',?,?,'candidate',?, '{}')""",
                (artifact_id, unit_id, attempt, worker, ordinal,
                 f"target/run/workers/{unit_id}/{label}.rs", digest,
                 "2026-01-01T00:00:01Z"),
            )
            authority = TransitionAuthority(connection)
            authority.apply(attempt_started_command(
                run_id="run", unit_id=unit_id, attempt_id=attempt,
                fencing_token=ordinal,
                expected=load_unit_projection(connection, "run", unit_id),
                input_sha256=content_sha256(f"input-{label}"),
            ))
            authority.apply(attempt_finished_command(
                run_id="run", unit_id=unit_id, attempt_id=attempt,
                fencing_token=ordinal,
                expected=load_unit_projection(connection, "run", unit_id),
                target=UnitState("candidate-ready", "awaiting_gate"),
                reason="attempt_completed", evidence_sha256=digest,
            ))
        return artifact_id

    def promote(self, unit_id: str, artifact_id: str) -> None:
        with self.ledger.connect() as connection:
            attempt = connection.execute(
                """select attempt_id from artifacts where run_id='run'
                   and unit_id=? and artifact_id=?""", (unit_id, artifact_id),
            ).fetchone()[0]
            command_id = stable_transition_command_id(
                "test-promote", "run", unit_id, artifact_id,
            )
            TransitionAuthority(connection).apply(host_verifier_promoted_command(
                command_id=command_id, run_id="run", unit_id=unit_id,
                expected=load_unit_projection(connection, "run", unit_id),
                evidence_sha256=content_sha256(f"promote-{artifact_id}"),
                attempt_id=str(attempt), candidate_artifact_id=artifact_id,
            ))

    def fail_candidate(self, unit_id: str, artifact_id: str) -> None:
        with self.ledger.connect() as connection:
            attempt = connection.execute(
                """select attempt_id from artifacts where run_id='run'
                   and unit_id=? and artifact_id=?""", (unit_id, artifact_id),
            ).fetchone()[0]
            command_id = stable_transition_command_id(
                "test-fail", "run", unit_id, artifact_id,
            )
            TransitionAuthority(connection).apply(host_verification_failed_command(
                command_id=command_id, run_id="run", unit_id=unit_id,
                expected=load_unit_projection(connection, "run", unit_id),
                evidence_sha256=content_sha256(f"fail-{artifact_id}"),
                attempt_id=str(attempt), candidate_artifact_id=artifact_id,
            ))


if __name__ == "__main__":
    unittest.main()
