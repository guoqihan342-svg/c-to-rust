from __future__ import annotations

from typing import Any

from .ledger_security import LedgerError


def require_active_completion(
    connection: Any, run_id: str, *, action: str,
) -> None:
    row = connection.execute(
        "select status,completion_status from project_runs where run_id=?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise LedgerError(f"{action} requires an existing run")
    if row["status"] != "active" or row["completion_status"] != "active":
        raise LedgerError(f"{action} requires an active completion state")


__all__ = ["require_active_completion"]
