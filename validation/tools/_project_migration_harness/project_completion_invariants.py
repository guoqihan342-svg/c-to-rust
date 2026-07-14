from __future__ import annotations

from typing import Any

from .ledger_security import LedgerError
from .ledger_transition_replay import audit_transition_projections


def require_quiescent_last_good_run(
    connection: Any, run_id: str,
) -> None:
    audit_transition_projections(connection, run_id)
    run = connection.execute(
        "select status from project_runs where run_id=?", (run_id,),
    ).fetchone()
    if run is None or run["status"] != "active":
        raise LedgerError("project completion requires an active run")
    units = connection.execute(
        """select unit_id,status,resumable_status,last_good_artifact_id
           from migration_units where run_id=? order by unit_id""",
        (run_id,),
    ).fetchall()
    if not units:
        raise LedgerError("project completion requires migration units")
    if any(
        row["status"] != "resume-ready"
        or row["resumable_status"] != "last_good"
        or not row["last_good_artifact_id"]
        for row in units
    ):
        raise LedgerError(
            "project completion requires every unit to be quiescent last-good"
        )
    running = connection.execute(
        "select count(*) from attempts where run_id=? and status='running'",
        (run_id,),
    ).fetchone()
    if running is None or int(running[0]) != 0:
        raise LedgerError("project completion rejects running worker attempts")
    leases = connection.execute(
        "select count(*) from leases where run_id=? and status='active'",
        (run_id,),
    ).fetchone()
    if leases is None or int(leases[0]) != 0:
        raise LedgerError("project completion rejects active worker leases")


def require_project_interface_ready(connection: Any, run_id: str) -> None:
    receipt = connection.execute(
        """select status,queue_item_count from project_interface_receipts
           where run_id=? order by receipt_epoch desc limit 1""",
        (run_id,),
    ).fetchone()
    if (
        receipt is None or receipt["status"] != "candidate-ready"
        or int(receipt["queue_item_count"]) != 0
    ):
        raise LedgerError(
            "project completion requires a latest candidate-ready interface receipt"
        )
    running = connection.execute(
        """select count(*) from project_repair_attempts
           where run_id=? and status='running'""",
        (run_id,),
    ).fetchone()
    if running is None or int(running[0]) != 0:
        raise LedgerError("project completion rejects running project repair attempts")
    unsettled = connection.execute(
        """select count(*) from project_repair_items
           where run_id=? and status not in ('resolved','cancelled')""",
        (run_id,),
    ).fetchone()
    if unsettled is None or int(unsettled[0]) != 0:
        raise LedgerError(
            "project completion rejects unsettled historical repair obligations"
        )


__all__ = ["require_project_interface_ready", "require_quiescent_last_good_run"]
