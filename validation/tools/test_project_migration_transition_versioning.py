from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.ledger_transition_authority import (
    TransitionAuthority,
)
from validation.tools._project_migration_harness.ledger_transition_policy import (
    RunTransitionCommand, TransitionCommand, UnitState,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationTransitionVersioningTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="transition-versioning-")
        self.addCleanup(temporary.cleanup)
        self.ledger = ProjectLedger(Path(temporary.name) / "ledger.sqlite3")
        self.ledger.create_run(
            run_id="run", project_key="project", source_commit="commit",
            dag_sha256=digest("dag"),
            units=[{
                "unit_id": "unit", "group_id": "unit", "wave_index": 0,
                "content_sha256": digest("unit"),
            }],
            assignments=[{
                "unit_id": "unit", "worker_id": "worker", "role": "translator",
                "out_root": "target/workers/worker/out", "max_attempts": 2,
            }],
            max_concurrency=1, max_attempts=2,
        )
        with self.ledger.connect() as connection:
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,
                   worker_id,status,fencing_token,input_sha256,started_at,metadata_json)
                   values ('attempt','run','unit','translator',1,'worker','running',1,?,?,?)""",
                (digest("input"), "2026-07-13T00:00:00Z", "{}"),
            )

    def test_run_transition_is_typed_idempotent_and_version_bound(self) -> None:
        first = self.run_command(expected_status="active", expected_version=0)
        expected_drift = self.run_command(
            expected_status="failed", expected_version=1,
        )
        with self.ledger.connect() as connection:
            authority = TransitionAuthority(connection)
            applied = authority.apply_run(first)
            replay = authority.apply_run(first)
            self.assertTrue(applied.applied)
            self.assertFalse(replay.applied)
            self.assertEqual((0, 1), (
                applied.previous.version, applied.current.version,
            ))
            with self.assertRaisesRegex(LedgerError, "changed its evidence binding"):
                authority.apply_run(expected_drift)

    def test_state_version_rejects_aba_even_when_status_matches_again(self) -> None:
        start = self.unit_command(
            command_id="attempt-started:aba", expected=UnitState("pending", "ready"),
            expected_version=0, target=UnitState("running", "in_progress"),
            kind="attempt_started", reason="attempt_started",
        )
        cancel = self.unit_command(
            command_id="prelaunch-cancelled:aba",
            expected=UnitState("running", "in_progress"), expected_version=1,
            target=UnitState("pending", "ready"),
            kind="prelaunch_attempt_cancelled",
            reason="prelaunch_attempt_cancelled",
        )
        stale = self.unit_command(
            command_id="attempt-started:stale-aba",
            expected=UnitState("pending", "ready"), expected_version=0,
            target=UnitState("running", "in_progress"),
            kind="attempt_started", reason="attempt_started",
        )
        with self.ledger.connect() as connection:
            authority = TransitionAuthority(connection)
            authority.apply(start)
            authority.apply(cancel)
            with self.assertRaisesRegex(LedgerError, "state/version is stale"):
                authority.apply(stale)
            row = connection.execute(
                "select status,resumable_status,state_version from migration_units"
            ).fetchone()
            self.assertEqual(("pending", "ready", 2), tuple(row))
            self.assertEqual(
                [(0, 1), (1, 2)],
                [tuple(row) for row in connection.execute(
                    "select from_version,to_version from transitions order by transition_id"
                )],
            )

    def test_transition_events_cannot_be_updated_or_deleted(self) -> None:
        command = self.unit_command(
            command_id="attempt-started:immutable",
            expected=UnitState("pending", "ready"), expected_version=0,
            target=UnitState("running", "in_progress"),
            kind="attempt_started", reason="attempt_started",
        )
        with self.ledger.connect() as connection:
            TransitionAuthority(connection).apply(command)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "update transitions set reason='changed' where transition_id=1"
                )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute("delete from transitions where transition_id=1")

    def test_replay_detects_projection_drift_from_immutable_events(self) -> None:
        command = self.unit_command(
            command_id="attempt-started:projection-drift",
            expected=UnitState("pending", "ready"), expected_version=0,
            target=UnitState("running", "in_progress"),
            kind="attempt_started", reason="attempt_started",
        )
        with self.ledger.connect() as connection:
            authority = TransitionAuthority(connection)
            authority.apply(command)
            connection.execute(
                """update migration_units set status='pending',resumable_status='ready'
                   where run_id='run' and unit_id='unit'"""
            )
            with self.assertRaisesRegex(LedgerError, "does not match immutable events"):
                authority.apply(command)

    def test_transition_audit_rejects_unrecorded_last_good_pointer(self) -> None:
        command = self.unit_command(
            command_id="attempt-started:last-good-drift",
            expected=UnitState("pending", "ready"), expected_version=0,
            target=UnitState("running", "in_progress"),
            kind="attempt_started", reason="attempt_started",
        )
        with self.ledger.connect() as connection:
            connection.execute(
                """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,
                   worker_id,fencing_token,kind,repo_rel_path,content_sha256,status,
                   created_at,metadata_json) values
                   ('run','candidate','unit','attempt','worker',1,'rust-candidate',
                    'target/candidate.rs',?,'candidate',?,'{}')""",
                (digest("candidate"), "2026-07-13T00:00:01Z"),
            )
            connection.execute(
                """update migration_units set last_good_artifact_id='candidate'
                   where run_id='run' and unit_id='unit'"""
            )
            with self.assertRaisesRegex(LedgerError, "last-good projection"):
                TransitionAuthority(connection).apply(command)

    def test_wrong_command_kind_cannot_complete_a_run(self) -> None:
        forged = RunTransitionCommand(
            command_kind="terminal_worker_run_failed",
            command_id="forged-completion:one", run_id="run",
            anchor_unit_id="unit", expected_status="active", expected_version=0,
            target_status="completed", reason="terminal_worker_result",
            evidence_sha256=digest("forged"),
            attempt_id="attempt", fencing_token=1,
        )
        with self.ledger.connect() as connection:
            with self.assertRaisesRegex(ValueError, "not permitted for its command kind"):
                TransitionAuthority(connection).apply_run(forged)
            self.assertEqual(0, connection.execute(
                "select count(*) from transitions"
            ).fetchone()[0])

    def test_cancelled_prelaunch_attempt_does_not_consume_budget(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cancelled-attempt-budget-") as root:
            ledger = ProjectLedger(Path(root) / "ledger.sqlite3")
            ledger.create_run(
                run_id="budget", project_key="project", source_commit="commit",
                dag_sha256=digest("budget-dag"),
                units=[{
                    "unit_id": "unit", "group_id": "unit", "wave_index": 0,
                    "content_sha256": digest("budget-unit"),
                }],
                assignments=[{
                    "unit_id": "unit", "worker_id": "worker", "role": "translator",
                    "out_root": "target/workers/worker/out", "max_attempts": 1,
                }],
                max_concurrency=1, max_attempts=1,
            )
            token = ledger.acquire_lease(
                run_id="budget", unit_id="unit", owner="worker", ttl_seconds=120,
            )
            metadata = {
                "command_started": False,
                "previous_status": "resume-ready",
                "previous_resumable_status": "last_good",
            }
            first = ledger.start_attempt(
                run_id="budget", unit_id="unit", role="translator",
                worker_id="worker", fencing_token=token,
                input_sha256=digest("first"), metadata=metadata,
            )
            ledger.cancel_prelaunch_attempt(
                attempt_id=first, owner="worker", fencing_token=token,
            )
            with ledger.connect() as connection:
                state = connection.execute(
                    "select status,resumable_status from migration_units"
                ).fetchone()
                self.assertEqual(("pending", "ready"), tuple(state))
            second_token = ledger.acquire_lease(
                run_id="budget", unit_id="unit", owner="worker", ttl_seconds=120,
            )
            second = ledger.start_attempt(
                run_id="budget", unit_id="unit", role="translator",
                worker_id="worker", fencing_token=second_token,
                input_sha256=digest("second"), metadata=metadata,
            )
            self.assertTrue(second.endswith(":2"))
            with ledger.connect() as connection:
                self.assertEqual(
                    [(1, "cancelled"), (2, "running")],
                    [tuple(row) for row in connection.execute(
                        "select ordinal,status from attempts order by ordinal"
                    )],
                )

    @staticmethod
    def unit_command(
        *, command_id: str, expected: UnitState, expected_version: int,
        target: UnitState, kind: str, reason: str,
    ) -> TransitionCommand:
        return TransitionCommand(
            command_kind=kind, command_id=command_id, run_id="run", unit_id="unit",
            expected=expected, expected_version=expected_version, target=target,
            reason=reason, evidence_sha256=digest(command_id),
            attempt_id="attempt", fencing_token=1,
        )

    @staticmethod
    def run_command(
        *, expected_status: str, expected_version: int,
    ) -> RunTransitionCommand:
        return RunTransitionCommand(
            command_kind="terminal_worker_run_failed", command_id="run-failed:one",
            run_id="run", anchor_unit_id="unit", expected_status=expected_status,
            expected_version=expected_version, target_status="failed",
            reason="terminal_worker_result", evidence_sha256=digest("run-evidence"),
            attempt_id="attempt", fencing_token=1,
        )


if __name__ == "__main__":
    unittest.main()
