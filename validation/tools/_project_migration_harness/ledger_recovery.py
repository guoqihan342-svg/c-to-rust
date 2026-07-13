from __future__ import annotations

import time

from .ledger_schema import _now_text, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import TransitionAuthority, load_unit_state
from .ledger_transition_policy import (
    TransitionCommand, UnitState, stable_transition_command_id,
    transition_evidence_sha256,
)


class LedgerRecoveryMixin:
    def recover_expired_attempts(
        self, *, run_id: str, now: int | None = None
    ) -> list[str]:
        clock = int(time.time()) if now is None else int(now)
        recovered: list[str] = []
        with self.connect() as connection, atomic(connection):
            run = connection.execute(
                "select status from project_runs where run_id=?", (run_id,)
            ).fetchone()
            if not run:
                raise LedgerError("run does not exist")
            if run["status"] != "active":
                return recovered
            rows = connection.execute(
                """select t.attempt_id,t.unit_id,t.worker_id,t.role,
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
                count = int(connection.execute(
                    """select count(*) from attempts where run_id=? and unit_id=?
                       and worker_id=? and role=?""",
                    (run_id, row["unit_id"], row["worker_id"], row["role"]),
                ).fetchone()[0])
                exhausted = count >= int(row["max_attempts"])
                next_status = "exhausted" if exhausted else "retry-ready"
                resumable = "exhausted" if exhausted else "retryable"
                unit_id = str(row["unit_id"])
                expected = load_unit_state(connection, run_id, unit_id)
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
                    TransitionCommand(
                        command_id=stable_transition_command_id(
                            "lease-expired-recovery", run_id, unit_id, row["attempt_id"],
                        ),
                        run_id=run_id, unit_id=unit_id, expected=expected,
                        target=UnitState(next_status, resumable),
                        reason="lease_expired_recovered",
                        evidence_sha256=transition_evidence_sha256({
                            "attempt_id": row["attempt_id"],
                            "lease_status": row["lease_status"],
                            "lease_expires_at": row["expires_at"],
                            "max_attempts": row["max_attempts"],
                            "attempt_count": count,
                        }),
                        attempt_id=str(row["attempt_id"]),
                    ),
                    created_at=timestamp,
                )
                recovered.append(str(row["attempt_id"]))
        return recovered


__all__ = ["LedgerRecoveryMixin"]
