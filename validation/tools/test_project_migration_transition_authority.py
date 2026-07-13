from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.ledger_recovery import LedgerRecoveryMixin
from validation.tools._project_migration_harness.ledger_schema import atomic
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.ledger_transition_authority import (
    TransitionAuthority,
)
from validation.tools._project_migration_harness.ledger_transition_policy import (
    TransitionCommand, UnitState,
)


def digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


class ProjectMigrationTransitionAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-transition-authority-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.ledger = ProjectLedger(self.root / "ledger.sqlite3")
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

    def test_illegal_transition_is_rejected_without_a_log_entry(self) -> None:
        command = self.command(
            command_id="illegal:one",
            expected=UnitState("completed", "terminal"),
            target=UnitState("running", "in_progress"),
        )
        with self.ledger.connect() as connection:
            with self.assertRaisesRegex(ValueError, "not permitted"):
                TransitionAuthority(connection).apply(command)
            self.assertEqual(0, self.transition_count(connection))
            self.assertEqual(("pending", "ready"), self.unit_state(connection))

    def test_stale_expected_state_is_rejected_without_projection(self) -> None:
        command = self.command(
            command_id="stale:one",
            expected=UnitState("retry-ready", "retryable"),
            target=UnitState("running", "in_progress"),
        )
        with self.ledger.connect() as connection:
            with self.assertRaisesRegex(LedgerError, "expected unit state/version is stale"):
                TransitionAuthority(connection).apply(command)
            self.assertEqual(0, self.transition_count(connection))
            self.assertEqual(("pending", "ready"), self.unit_state(connection))

    def test_duplicate_command_is_idempotent_and_evidence_bound(self) -> None:
        first = self.command(
            command_id="attempt-started:one",
            expected=UnitState("pending", "ready"),
            target=UnitState("running", "in_progress"),
        )
        replay = self.command(
            command_id=first.command_id,
            expected=first.expected,
            target=first.target,
        )
        expected_drift = self.command(
            command_id=first.command_id,
            expected=UnitState("running", "in_progress"),
            target=first.target,
        )
        unit_drift = TransitionCommand(
            command_kind=first.command_kind, command_id=first.command_id,
            run_id="run", unit_id="other-unit", expected=first.expected,
            expected_version=first.expected_version, target=first.target,
            reason=first.reason, evidence_sha256=first.evidence_sha256,
            attempt_id=first.attempt_id, fencing_token=first.fencing_token,
        )
        drift = self.command(
            command_id=first.command_id,
            expected=first.expected,
            target=first.target,
            evidence_sha256=digest("different-evidence"),
        )
        with self.ledger.connect() as connection:
            applied = TransitionAuthority(connection).apply(first)
            duplicate = TransitionAuthority(connection).apply(replay)
            self.assertTrue(applied.applied)
            self.assertFalse(duplicate.applied)
            self.assertEqual(applied.transition_id, duplicate.transition_id)
            self.assertEqual(1, self.transition_count(connection))
            with self.assertRaisesRegex(LedgerError, "changed its evidence binding"):
                TransitionAuthority(connection).apply(expected_drift)
            with self.assertRaisesRegex(LedgerError, "changed its evidence binding"):
                TransitionAuthority(connection).apply(unit_drift)
            with self.assertRaisesRegex(LedgerError, "changed its evidence binding"):
                TransitionAuthority(connection).apply(drift)
            self.assertEqual(1, self.transition_count(connection))
            event = connection.execute(
                """select command_kind,command_id,evidence_sha256
                   from transitions where transition_id=?""",
                (applied.transition_id,),
            ).fetchone()
            self.assertEqual("attempt_started", event["command_kind"])
            self.assertEqual(first.command_id, event["command_id"])
            self.assertEqual(first.evidence_sha256, event["evidence_sha256"])

    def test_outer_transaction_rollback_removes_log_and_projection(self) -> None:
        command = self.command(
            command_id="rollback:one",
            expected=UnitState("pending", "ready"),
            target=UnitState("running", "in_progress"),
        )
        with self.ledger.connect() as connection:
            with self.assertRaisesRegex(RuntimeError, "force rollback"):
                with atomic(connection):
                    TransitionAuthority(connection).apply(command)
                    raise RuntimeError("force rollback")
        with self.ledger.connect() as connection:
            self.assertEqual(0, self.transition_count(connection))
            self.assertEqual(("pending", "ready"), self.unit_state(connection))

    def test_projection_failure_rolls_back_the_appended_transition(self) -> None:
        command = self.command(
            command_id="projection-failure:one",
            expected=UnitState("pending", "ready"),
            target=UnitState("running", "in_progress"),
        )
        with self.ledger.connect() as connection:
            connection.execute(
                """create temp trigger reject_unit_projection
                   before update on migration_units
                   begin select raise(abort,'projection rejected'); end"""
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "projection rejected"):
                TransitionAuthority(connection).apply(command)
            self.assertEqual(0, self.transition_count(connection))
            self.assertEqual(("pending", "ready"), self.unit_state(connection))

    def test_recovery_mixin_projects_expired_attempt_through_authority(self) -> None:
        self.ledger.create_run(
            run_id="recovery", project_key="project", source_commit="commit",
            dag_sha256=digest("recovery-dag"),
            units=[{
                "unit_id": "recoverable", "group_id": "recoverable", "wave_index": 0,
                "content_sha256": digest("recoverable"),
            }],
            assignments=[{
                "unit_id": "recoverable", "worker_id": "worker", "role": "translator",
                "out_root": "target/workers/worker/out", "max_attempts": 2,
            }],
            max_concurrency=1, max_attempts=2,
        )
        token = self.ledger.acquire_lease(
            run_id="recovery", unit_id="recoverable", owner="worker", ttl_seconds=120,
        )
        attempt = self.ledger.start_attempt(
            run_id="recovery", unit_id="recoverable", role="translator",
            worker_id="worker", fencing_token=token, input_sha256=digest("input"),
        )
        clock = int(time.time())
        with self.ledger.connect() as connection:
            connection.execute(
                """update leases set expires_at=? where run_id='recovery'
                   and unit_id='recoverable'""",
                (clock - 1,),
            )
        recovered = LedgerRecoveryMixin.recover_expired_attempts(
            self.ledger, run_id="recovery", now=clock,
        )
        self.assertEqual([attempt], recovered)
        with self.ledger.connect() as connection:
            unit = connection.execute(
                """select status,resumable_status from migration_units
                   where run_id='recovery' and unit_id='recoverable'"""
            ).fetchone()
            attempt_status = connection.execute(
                "select status from attempts where attempt_id=?", (attempt,),
            ).fetchone()[0]
            event = connection.execute(
                """select command_kind,reason from transitions where run_id='recovery'
                   order by transition_id desc limit 1"""
            ).fetchone()
        self.assertEqual(("retry-ready", "retryable"), tuple(unit))
        self.assertEqual("failed", attempt_status)
        self.assertEqual("lease_expired_recovery", event["command_kind"])
        self.assertEqual("lease_expired_recovered", event["reason"])

    def test_started_attempt_recovery_projects_unit_and_run_terminal_states(self) -> None:
        self.ledger.create_run(
            run_id="terminal-recovery", project_key="project", source_commit="commit",
            dag_sha256=digest("terminal-recovery-dag"),
            units=[{
                "unit_id": "terminal", "group_id": "terminal", "wave_index": 0,
                "content_sha256": digest("terminal"),
            }],
            assignments=[{
                "unit_id": "terminal", "worker_id": "worker-terminal",
                "role": "translator", "out_root": "target/workers/terminal/out",
                "max_attempts": 2,
            }],
            max_concurrency=1, max_attempts=2,
        )
        token = self.ledger.acquire_lease(
            run_id="terminal-recovery", unit_id="terminal",
            owner="worker-terminal", ttl_seconds=120,
        )
        attempt = self.ledger.start_attempt(
            run_id="terminal-recovery", unit_id="terminal", role="translator",
            worker_id="worker-terminal", fencing_token=token,
            input_sha256=digest("terminal-input"),
        )
        self.ledger.mark_command_started(
            attempt_id=attempt, owner="worker-terminal", fencing_token=token,
        )
        clock = int(time.time())
        with self.ledger.connect() as connection:
            connection.execute(
                """update leases set expires_at=? where run_id='terminal-recovery'
                   and unit_id='terminal'""", (clock - 1,),
            )
        self.assertEqual(
            [attempt], self.ledger.recover_expired_attempts(
                run_id="terminal-recovery", now=clock,
            ),
        )
        with self.ledger.connect() as connection:
            unit = connection.execute(
                """select status,resumable_status from migration_units
                   where run_id='terminal-recovery' and unit_id='terminal'"""
            ).fetchone()
            run_status = connection.execute(
                "select status from project_runs where run_id='terminal-recovery'"
            ).fetchone()[0]
            kinds = [tuple(row) for row in connection.execute(
                "select scope,command_kind from transitions where run_id='terminal-recovery'"
            )]
        self.assertEqual(("blocked", "terminal"), tuple(unit))
        self.assertEqual("failed", run_status)
        self.assertIn(("run", "lease_recovery_run_failed"), kinds)

    @staticmethod
    def command(
        *, command_id: str, expected: UnitState, target: UnitState,
        evidence_sha256: str | None = None,
    ) -> TransitionCommand:
        return TransitionCommand(
            command_kind="attempt_started", command_id=command_id,
            run_id="run", unit_id="unit", expected=expected,
            expected_version=0, target=target, reason="attempt_started",
            evidence_sha256=evidence_sha256 or digest("evidence"),
            attempt_id="attempt", fencing_token=1,
        )

    @staticmethod
    def transition_count(connection: object) -> int:
        return int(connection.execute(
            "select count(*) from transitions where run_id='run' and unit_id='unit'"
        ).fetchone()[0])

    @staticmethod
    def unit_state(connection: object) -> tuple[str, str]:
        row = connection.execute(
            """select status,resumable_status from migration_units
               where run_id='run' and unit_id='unit'"""
        ).fetchone()
        return str(row["status"]), str(row["resumable_status"])


if __name__ == "__main__":
    unittest.main()
