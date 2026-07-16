from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import (
    ProjectLedger,
    SchemaVersionError,
)
from validation.tools._project_migration_harness.ledger_schema import _SCHEMA_V8
from validation.tools._project_migration_harness.schema_integrity import (
    assert_schema_integrity,
)
from validation.tools._project_migration_harness.ledger_transition_replay import (
    assert_run_event_projection,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationLedgerSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-ledger-schema-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_recursive_secrets_are_rejected_and_error_keys_are_redacted(self) -> None:
        ledger = ProjectLedger(self.root / "secret.sqlite3")
        with self.assertRaisesRegex(ValueError, "secret-bearing value"):
            ledger.create_run(
                run_id="secret-run",
                project_key="secret-project",
                source_commit="commit",
                dag_sha256=digest("secret-dag"),
                units=[],
                assignments=[],
                max_concurrency=1,
                max_attempts=1,
                metadata={"notes": [{"message": "Bearer abcdefghijklmnop"}]},
            )
        self.create_run(ledger)
        token = ledger.acquire_lease(
            run_id="run", unit_id="unit", owner="worker", ttl_seconds=120
        )
        attempt = ledger.start_attempt(
            run_id="run",
            unit_id="unit",
            role="translator",
            worker_id="worker",
            fencing_token=token,
            input_sha256=digest("input"),
        )
        ledger.finish_attempt(
            attempt_id=attempt,
            owner="worker",
            fencing_token=token,
            status="failed",
            next_status="retry-ready",
            error_key="password=hunter2",
        )
        with ledger.connect() as connection:
            stored = connection.execute(
                "select error_key from attempts where attempt_id=?", (attempt,)
            ).fetchone()[0]
        self.assertEqual("redacted_sensitive_error", stored)

    def test_schema_version_and_cross_unit_foreign_keys_are_strict(self) -> None:
        stale_path = self.root / "stale.sqlite3"
        connection = sqlite3.connect(stale_path)
        connection.execute(
            "create table schema_migrations(version integer primary key, applied_at text not null)"
        )
        connection.execute(
            "insert into schema_migrations(version,applied_at) values (1,'old')"
        )
        connection.execute("pragma user_version=1")
        connection.commit()
        connection.close()
        with self.assertRaises(SchemaVersionError):
            ProjectLedger(stale_path)

        ledger = ProjectLedger(self.root / "constraints.sqlite3")
        ledger.create_run(
            run_id="run",
            project_key="project",
            source_commit="commit",
            dag_sha256=digest("dag"),
            units=[self.unit("one"), self.unit("two")],
            assignments=[self.assignment("one", "worker-one")],
            max_concurrency=1,
            max_attempts=2,
        )
        token = ledger.acquire_lease(
            run_id="run", unit_id="one", owner="worker-one", ttl_seconds=120
        )
        attempt = ledger.start_attempt(
            run_id="run", unit_id="one", role="translator", worker_id="worker-one",
            fencing_token=token, input_sha256=digest("input"),
        )
        with ledger.connect() as current, self.assertRaises(sqlite3.IntegrityError):
            current.execute(
                """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,worker_id,
                   fencing_token,kind,repo_rel_path,content_sha256,status,created_at,metadata_json)
                   values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                ("run", "cross", "two", attempt, "worker-one", token, "candidate",
                 "target/workers/worker-one/out/cross.rs", digest("cross"), "candidate",
                 "2026-01-01T00:00:00Z", "{}"),
            )

    def test_v8_database_is_migrated_without_losing_legacy_state(self) -> None:
        path = self.root / "v8.sqlite3"
        connection = sqlite3.connect(path)
        connection.execute("pragma foreign_keys=on")
        for statement in _SCHEMA_V8:
            connection.execute(statement)
        fingerprint = assert_schema_integrity(connection, _SCHEMA_V8)
        connection.execute(
            """insert into project_runs(
               run_id,project_key,source_commit,dag_sha256,initial_status,status,
               max_concurrency,max_attempts,created_at,updated_at,state_version,
               metadata_json) values
               ('legacy-run','project','commit',?,'active','active',1,1,
                '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z',0,'{}')""",
            (digest("legacy-dag"),),
        )
        connection.execute(
            """insert into project_runs(
               run_id,project_key,source_commit,dag_sha256,initial_status,status,
               max_concurrency,max_attempts,created_at,updated_at,state_version,
               metadata_json) values
               ('legacy-completed','project','commit',?,'active','completed',1,1,
                '2026-01-01T00:00:00Z','2026-01-01T00:00:01Z',1,'{}')""",
            (digest("legacy-completed-dag"),),
        )
        connection.execute(
            """insert into migration_units(
               run_id,unit_id,group_id,wave_index,initial_status,
               initial_resumable_status,status,resumable_status,state_version,
               content_sha256,last_good_artifact_id,updated_at) values
               ('legacy-completed','unit','unit',0,'pending','ready',
                'pending','ready',0,?,null,'2026-01-01T00:00:00Z')""",
            (digest("legacy-completed-unit"),),
        )
        connection.execute(
            """insert into transitions(
               run_id,unit_id,scope,command_kind,command_id,from_status,to_status,
               from_resumable_status,to_resumable_status,from_version,to_version,
               reason,evidence_sha256,attempt_id,fencing_token,
               clear_last_good_if,set_last_good_artifact_id,created_at) values
               ('legacy-completed','unit','run','project_run_completed',
                'project-run-completed:legacy','active','completed',null,null,0,1,
                'project_gate_bundle_passed',?,null,null,null,null,
                '2026-01-01T00:00:01Z')""",
            (digest("legacy-receipt"),),
        )
        connection.execute(
            """insert into schema_migrations(version,applied_at,schema_sha256)
               values (8,'2026-01-01T00:00:00Z',?)""", (fingerprint,),
        )
        connection.execute("pragma user_version=8")
        connection.commit()
        connection.close()

        ledger = ProjectLedger(path)
        with ledger.connect() as migrated:
            self.assertEqual(9, migrated.execute(
                "pragma user_version"
            ).fetchone()[0])
            columns = {
                row[1] for row in migrated.execute("pragma table_info(project_runs)")
            }
            transition_columns = {
                row[1] for row in migrated.execute("pragma table_info(transitions)")
            }
            legacy = migrated.execute(
                """select status,completion_status,completion_epoch
                   from project_runs where run_id='legacy-run'""",
            ).fetchone()
            legacy_completed = assert_run_event_projection(
                migrated, "legacy-completed",
            )
        self.assertTrue({
            "completion_status", "completion_epoch",
            "completion_cohort_sha256", "completion_generation_sha256",
            "completion_gate_bundle_sha256", "completion_invariant_sha256",
            "completion_receipt_sha256",
        }.issubset(columns))
        self.assertTrue({
            "from_completion_json", "to_completion_json",
        }.issubset(transition_columns))
        self.assertEqual(("active", "active", 0), tuple(legacy))
        self.assertEqual(("completed", 1, 0), (
            legacy_completed.status, legacy_completed.version,
            legacy_completed.completion.epoch,
        ))

    def test_production_files_are_bounded_and_use_explicit_insert_columns(self) -> None:
        harness = Path(__file__).parent / "_project_migration_harness"
        for path in harness.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertLessEqual(len(source.splitlines()), 300)
                self.assertIsNone(
                    re.search(r"insert\s+into\s+\w+\s+values\s*\(", source, re.IGNORECASE)
                )

    def test_unit_initial_state_pair_is_validated_before_insert(self) -> None:
        ledger = ProjectLedger(self.root / "invalid-unit-state.sqlite3")
        unit = {
            **self.unit("unit"),
            "status": "pending",
            "resumable_status": "terminal",
        }
        with self.assertRaisesRegex(ValueError, "pair is invalid"):
            ledger.create_run(
                run_id="run", project_key="project", source_commit="commit",
                dag_sha256=digest("dag"), units=[unit], assignments=[],
                max_concurrency=1, max_attempts=1,
            )
        with ledger.connect() as connection:
            self.assertEqual(0, connection.execute(
                "select count(*) from project_runs"
            ).fetchone()[0])

    @staticmethod
    def unit(unit_id: str) -> dict:
        return {
            "unit_id": unit_id,
            "group_id": unit_id,
            "wave_index": 0,
            "content_sha256": digest(unit_id),
        }

    @staticmethod
    def assignment(unit_id: str, worker_id: str) -> dict:
        return {
            "unit_id": unit_id,
            "worker_id": worker_id,
            "role": "translator",
            "out_root": f"target/workers/{worker_id}/out",
            "max_attempts": 2,
        }

    def create_run(self, ledger: ProjectLedger) -> None:
        ledger.create_run(
            run_id="run",
            project_key="project",
            source_commit="commit",
            dag_sha256=digest("dag"),
            units=[self.unit("unit")],
            assignments=[self.assignment("unit", "worker")],
            max_concurrency=1,
            max_attempts=2,
        )


if __name__ == "__main__":
    unittest.main()
