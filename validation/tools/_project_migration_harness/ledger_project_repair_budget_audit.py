from __future__ import annotations

import sqlite3

from .ledger_security import LedgerError


def assert_project_repair_budget_projection(
    connection: sqlite3.Connection, *, run_id: str,
) -> None:
    from .ledger_project_repair_budget import (
        DEFAULT_MAX_PROVIDER_CALLS, DEFAULT_MAX_RECEIPT_EPOCHS,
    )

    budget = connection.execute(
        """select max_provider_calls,provider_calls,
           max_receipt_epochs,receipt_epochs
           from project_repair_run_budgets where run_id=?""",
        (run_id,),
    ).fetchone()
    receipts = int(connection.execute(
        "select count(*) from project_interface_receipts where run_id=?",
        (run_id,),
    ).fetchone()[0])
    if receipts == 0:
        if budget is not None:
            raise LedgerError("project repair run budget exists without receipts")
        return
    if budget is None:
        raise LedgerError("project repair run budget is missing")
    launched = int(connection.execute(
        """select count(*) from project_repair_attempts
           where run_id=? and command_started=1""",
        (run_id,),
    ).fetchone()[0])
    if (
        int(budget[0]) != DEFAULT_MAX_PROVIDER_CALLS
        or int(budget[1]) != launched
        or int(budget[2]) != DEFAULT_MAX_RECEIPT_EPOCHS
        or int(budget[3]) != receipts
    ):
        raise LedgerError("project repair run budget projection drifted")
    _audit_diagnostic_budgets(connection, run_id)
    _audit_item_inheritance(connection, run_id)


def _audit_diagnostic_budgets(connection: sqlite3.Connection, run_id: str) -> None:
    rows = connection.execute(
        """select budgets.diagnostic_lineage_id,
           budgets.lineage_projection_sha256,
           budgets.latest_diagnostic_sha256,budgets.max_attempts,
           budgets.attempt_count,budgets.first_receipt_epoch,
           budgets.last_receipt_epoch,count(attempts.attempt_id) as attempts
           from project_repair_diagnostic_budgets budgets
           left join project_repair_items items
            on items.run_id=budgets.run_id
            and items.diagnostic_lineage_id=budgets.diagnostic_lineage_id
           left join project_repair_attempts attempts
             on attempts.run_id=items.run_id
            and attempts.project_repair_queue_sha256=
                items.project_repair_queue_sha256
            and attempts.repair_id=items.repair_id
           where budgets.run_id=? group by budgets.diagnostic_lineage_id""",
        (run_id,),
    ).fetchall()
    for row in rows:
        bounds = connection.execute(
            """select min(receipt_epoch),max(receipt_epoch),
               min(max_attempts),max(max_attempts),
               min(lineage_projection_sha256),max(lineage_projection_sha256)
               from project_repair_diagnostic_observations
               where run_id=? and diagnostic_lineage_id=?""",
            (run_id, row["diagnostic_lineage_id"]),
        ).fetchone()
        latest = connection.execute(
            """select diagnostic_sha256
               from project_repair_diagnostic_observations
               where run_id=? and diagnostic_lineage_id=?
               order by receipt_epoch desc limit 1""",
            (run_id, row["diagnostic_lineage_id"]),
        ).fetchone()
        if (
            int(row["attempt_count"]) != int(row["attempts"])
            or int(row["first_receipt_epoch"]) != int(bounds[0])
            or int(row["last_receipt_epoch"]) != int(bounds[1])
            or int(row["max_attempts"]) != int(bounds[2])
            or int(bounds[2]) != int(bounds[3])
            or bounds[4] != bounds[5]
            or row["lineage_projection_sha256"] != bounds[4]
            or latest is None
            or row["latest_diagnostic_sha256"] != latest[0]
        ):
            raise LedgerError("project repair diagnostic budget projection drifted")


def _audit_item_inheritance(connection: sqlite3.Connection, run_id: str) -> None:
    rows = connection.execute(
        """select items.*,receipts.receipt_epoch from project_repair_items items
           join project_interface_receipts receipts
             on receipts.run_id=items.run_id
            and receipts.project_repair_queue_sha256=
                items.project_repair_queue_sha256
           where items.run_id=? order by receipts.receipt_epoch,items.repair_id""",
        (run_id,),
    ).fetchall()
    seen: dict[str, int] = {}
    for row in rows:
        lineage_id = str(row["diagnostic_lineage_id"])
        inherited = seen.get(lineage_id, 0)
        local = int(connection.execute(
            """select count(*) from project_repair_attempts where run_id=?
               and project_repair_queue_sha256=? and repair_id=?""",
            (run_id, row["project_repair_queue_sha256"], row["repair_id"]),
        ).fetchone()[0])
        initial = "exhausted" if inherited >= int(row["max_attempts"]) else "queued"
        if (
            int(row["inherited_attempt_count"]) != inherited
            or int(row["attempt_count"]) != inherited + local
            or row["initial_status"] != initial
        ):
            raise LedgerError("project repair item budget inheritance drifted")
        seen[lineage_id] = inherited + local


__all__ = ["assert_project_repair_budget_projection"]
