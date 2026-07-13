from __future__ import annotations

import sqlite3

from .ledger_security import LedgerError


def consumed_attempt_count(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str,
    worker_id: str, role: str,
) -> int:
    return int(connection.execute(
        """select count(*) from attempts where run_id=? and unit_id=?
           and worker_id=? and role=? and status<>'cancelled'""",
        (run_id, unit_id, worker_id, role),
    ).fetchone()[0])


def next_attempt_ordinal(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str,
    worker_id: str, role: str, max_attempts: int,
) -> int:
    consumed = consumed_attempt_count(
        connection, run_id=run_id, unit_id=unit_id,
        worker_id=worker_id, role=role,
    )
    if consumed >= max_attempts:
        raise LedgerError(f"attempt limit reached for {run_id}/{unit_id}/{worker_id}")
    return int(connection.execute(
        """select coalesce(max(ordinal),0)+1 from attempts
           where run_id=? and unit_id=? and worker_id=? and role=?""",
        (run_id, unit_id, worker_id, role),
    ).fetchone()[0])


__all__ = ["consumed_attempt_count", "next_attempt_ordinal"]
