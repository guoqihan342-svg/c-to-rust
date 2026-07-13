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
