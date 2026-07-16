from __future__ import annotations

import time
from typing import Any

from .ledger_security import LedgerError
from .ledger_frontier_gate import context_frontier_for_unit_state


class LedgerViewMixin:
    def resume_units(self, run_id: str, *, now: int | None = None) -> list[dict[str, Any]]:
        clock = int(time.time()) if now is None else int(now)
        with self.connect() as connection:
            rows = connection.execute(
                """select u.*,r.max_attempts from migration_units u join project_runs r using(run_id)
                   left join context_frontiers f on f.run_id=u.run_id and f.unit_id=u.unit_id
                   where u.run_id=? and r.status='active'
                   and r.completion_status='active' and u.status not in
                   ('running','completed','cancelled','exhausted')
                   and u.resumable_status not in ('terminal','exhausted')
                   and (f.unit_id is null or f.status='ready')
                   and not exists (select 1 from leases l where l.run_id=u.run_id and l.unit_id=u.unit_id
                                   and l.status='active' and l.expires_at>?)
                   and not exists (select 1 from attempts t where t.run_id=u.run_id and t.unit_id=u.unit_id
                                   and t.status='running')
                   and (not exists (select 1 from assignments x where x.run_id=u.run_id and x.unit_id=u.unit_id)
                        or exists (select 1 from assignments a where a.run_id=u.run_id and a.unit_id=u.unit_id
                                   and a.status='active' and (select count(*) from attempts q
                                       where q.run_id=a.run_id and q.unit_id=a.unit_id
                                       and q.worker_id=a.worker_id and q.role=a.role
                                       and q.status<>'cancelled') < a.max_attempts))
                   order by u.wave_index,u.group_id,u.unit_id""", (run_id, clock),
            ).fetchall()
        return [dict(row) for row in rows]

    def unit_states(self, run_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """select u.*,r.max_attempts,r.max_concurrency,
                          r.completion_status as run_status
                   from migration_units u join project_runs r using(run_id)
                   where u.run_id=? order by u.wave_index,u.group_id,u.unit_id""",
                (run_id,),
            ).fetchall()
            if rows and rows[0]["run_status"] == "completed":
                self.reopen_completed_project_run(run_id=run_id)
            result = []
            for row in rows:
                state = dict(row)
                frontier = context_frontier_for_unit_state(
                    connection, run_id=run_id, unit_id=str(row["unit_id"]),
                )
                if frontier is not None:
                    state["context_frontier"] = frontier
                result.append(state)
        return result

    def running_attempt_for_worker(
        self, *, run_id: str, worker_id: str
    ) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                """select t.*,a.out_root,l.expires_at,l.status as lease_status
                   from attempts t join assignments a
                     on a.run_id=t.run_id and a.unit_id=t.unit_id
                     and a.worker_id=t.worker_id and a.role=t.role
                   join leases l on l.run_id=t.run_id and l.unit_id=t.unit_id
                   where t.run_id=? and t.worker_id=? and t.status='running'""",
                (run_id, worker_id),
            ).fetchall()
        if len(rows) != 1:
            raise LedgerError("worker must have exactly one running attempt")
        return dict(rows[0])

    def orchestration_rows(self, run_id: str) -> dict[str, list[dict[str, Any]]]:
        with self.connect() as connection:
            artifacts = connection.execute(
                """select rowid as sequence,* from artifacts where run_id=?
                   order by rowid""",
                (run_id,),
            ).fetchall()
            verifications = connection.execute(
                """select rowid as sequence,* from verifier_records where run_id=?
                   order by rowid""",
                (run_id,),
            ).fetchall()
        return {
            "artifacts": [dict(row) for row in artifacts],
            "verifications": [dict(row) for row in verifications],
        }


__all__ = ["LedgerViewMixin"]
