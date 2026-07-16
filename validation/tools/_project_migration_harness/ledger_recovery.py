from __future__ import annotations

import time

from .ledger_attempt_budget import consumed_attempt_count
from .ledger_schema import _now_text, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import TransitionAuthority, load_unit_projection
from .ledger_transition_commands import lease_recovery_command
from .ledger_transition_policy import UnitState


class LedgerRecoveryMixin:
    def recover_expired_attempts(
        self, *, run_id: str, now: int | None = None
    ) -> list[str]:
        clock = int(time.time()) if now is None else int(now)
        recovered: list[str] = []
        with self.connect() as connection, atomic(connection):
            run = connection.execute(
                "select completion_status as status from project_runs where run_id=?",
                (run_id,),
            ).fetchone()
            if not run:
                raise LedgerError("run does not exist")
            if run["status"] != "active":
                return recovered
            rows = connection.execute(
                """select t.attempt_id,t.unit_id,t.worker_id,t.role,t.fencing_token,
                          a.max_attempts,l.status as lease_status,l.expires_at
                   from attempts t join assignments a
                     on a.run_id=t.run_id and a.unit_id=t.unit_id
                     and a.worker_id=t.worker_id and a.role=t.role
                   left join leases l on l.run_id=t.run_id and l.unit_id=t.unit_id
                   where t.run_id=? and t.status='running'
                     and (l.run_id is null or l.status<>'active' or l.expires_at<=?)
                   order by t.started_at,t.attempt_id""",
                (run_id, clock),
            ).fetchall()
            timestamp = _now_text()
            for row in rows:
                count = consumed_attempt_count(
                    connection, run_id=run_id, unit_id=str(row["unit_id"]),
                    worker_id=str(row["worker_id"]), role=str(row["role"]),
                )
                exhausted = count >= int(row["max_attempts"])
                next_status = "exhausted" if exhausted else "retry-ready"
                resumable = "exhausted" if exhausted else "retryable"
                unit_id = str(row["unit_id"])
                expected = load_unit_projection(connection, run_id, unit_id)
                connection.execute(
                    """update attempts set status='failed',error_key='lease_expired',
                       finished_at=? where attempt_id=?""",
                    (timestamp, row["attempt_id"]),
                )
                connection.execute(
                    """update leases set status='expired',heartbeat_at=?
                       where run_id=? and unit_id=?""",
                    (clock, run_id, row["unit_id"]),
                )
                TransitionAuthority(connection).apply(
                    lease_recovery_command(
                        run_id=run_id, unit_id=unit_id, row=row,
                        attempt_count=count, started=False, expected=expected,
                        target=UnitState(next_status, resumable),
                    ),
                    created_at=timestamp,
                )
                recovered.append(str(row["attempt_id"]))
        return recovered


__all__ = ["LedgerRecoveryMixin"]
