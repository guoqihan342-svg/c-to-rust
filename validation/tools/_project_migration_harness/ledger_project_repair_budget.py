from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .ledger_security import LedgerError
from .project_repair_lineage import derive_project_repair_diagnostic_lineage


DEFAULT_MAX_PROVIDER_CALLS = 64
DEFAULT_MAX_RECEIPT_EPOCHS = 65


@dataclass(frozen=True, slots=True)
class ProjectRepairRunBudget:
    max_provider_calls: int
    provider_calls: int
    max_receipt_epochs: int
    receipt_epochs: int


class ProjectRepairBudgetAuthority:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def register_receipt(
        self, *, run_id: str, receipt_epoch: int,
        diagnostics: Sequence[Mapping[str, Any]],
        rust_project_ir: Mapping[str, Any], max_attempts: int,
    ) -> dict[str, tuple[str, int, str]]:
        self.connection.execute(
            """insert into project_repair_run_budgets(
               run_id,max_provider_calls,provider_calls,
               max_receipt_epochs,receipt_epochs)
               values (?,?,0,?,0) on conflict(run_id) do nothing""",
            (run_id, DEFAULT_MAX_PROVIDER_CALLS, DEFAULT_MAX_RECEIPT_EPOCHS),
        )
        run_budget = self._run_budget(run_id)
        if receipt_epoch != run_budget.receipt_epochs + 1:
            raise LedgerError("project repair receipt budget epoch is not contiguous")
        if receipt_epoch > run_budget.max_receipt_epochs:
            raise LedgerError("project repair receipt epoch budget is exhausted")
        updated = self.connection.execute(
            """update project_repair_run_budgets set receipt_epochs=?
               where run_id=? and receipt_epochs=?""",
            (receipt_epoch, run_id, run_budget.receipt_epochs),
        )
        if updated.rowcount != 1:
            raise LedgerError("project repair receipt budget lost its CAS")
        inherited: dict[str, tuple[str, int, str]] = {}
        receipt_lineages: set[str] = set()
        for diagnostic in diagnostics:
            diagnostic_sha = str(diagnostic["diagnostic_sha256"])
            lineage_id, projection_sha = derive_project_repair_diagnostic_lineage(
                diagnostic, rust_project_ir,
            )
            if lineage_id in receipt_lineages:
                raise LedgerError("project repair receipt has ambiguous diagnostic lineage")
            receipt_lineages.add(lineage_id)
            row = self.connection.execute(
                """select lineage_projection_sha256,max_attempts,attempt_count,
                   last_receipt_epoch
                   from project_repair_diagnostic_budgets
                   where run_id=? and diagnostic_lineage_id=?""",
                (run_id, lineage_id),
            ).fetchone()
            if row is None:
                count = 0
                self.connection.execute(
                    """insert into project_repair_diagnostic_budgets(
                       run_id,diagnostic_lineage_id,lineage_projection_sha256,
                       latest_diagnostic_sha256,max_attempts,attempt_count,
                       first_receipt_epoch,last_receipt_epoch)
                       values (?,?,?,?,?,0,?,?)""",
                    (
                        run_id, lineage_id, projection_sha, diagnostic_sha,
                        max_attempts, receipt_epoch, receipt_epoch,
                    ),
                )
            else:
                if (
                    row["lineage_projection_sha256"] != projection_sha
                    or int(row["max_attempts"]) != max_attempts
                ):
                    raise LedgerError("project repair diagnostic budget changed")
                if int(row["last_receipt_epoch"]) >= receipt_epoch:
                    raise LedgerError("project repair diagnostic epoch did not advance")
                count = int(row["attempt_count"])
                self.connection.execute(
                    """update project_repair_diagnostic_budgets
                       set last_receipt_epoch=?,latest_diagnostic_sha256=?
                       where run_id=? and diagnostic_lineage_id=?
                         and last_receipt_epoch=?""",
                    (
                        receipt_epoch, diagnostic_sha, run_id, lineage_id,
                        int(row["last_receipt_epoch"]),
                    ),
                )
            self.connection.execute(
                """insert into project_repair_diagnostic_observations(
                   run_id,receipt_epoch,diagnostic_sha256,
                   diagnostic_lineage_id,lineage_projection_sha256,max_attempts)
                   values (?,?,?,?,?,?)""",
                (
                    run_id, receipt_epoch, diagnostic_sha, lineage_id,
                    projection_sha, max_attempts,
                ),
            )
            inherited[diagnostic_sha] = (
                lineage_id, count,
                "exhausted" if count >= max_attempts else "queued",
            )
        return inherited

    def start_attempt(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
        expected_attempt_count: int,
    ) -> None:
        row = self.connection.execute(
            """select items.diagnostic_lineage_id,items.max_attempts,
               budgets.attempt_count from project_repair_items items
               join project_repair_diagnostic_budgets budgets
                 on budgets.run_id=items.run_id
                and budgets.diagnostic_lineage_id=items.diagnostic_lineage_id
               where items.run_id=? and items.project_repair_queue_sha256=?
                 and items.repair_id=?""",
            (run_id, queue_sha256, repair_id),
        ).fetchone()
        if row is None or int(row["attempt_count"]) != expected_attempt_count:
            raise LedgerError("project repair diagnostic budget projection drifted")
        if expected_attempt_count >= int(row["max_attempts"]):
            raise LedgerError("project repair diagnostic budget is exhausted")
        updated = self.connection.execute(
            """update project_repair_diagnostic_budgets
               set attempt_count=attempt_count+1
               where run_id=? and diagnostic_lineage_id=? and attempt_count=?""",
            (
                run_id, str(row["diagnostic_lineage_id"]),
                expected_attempt_count,
            ),
        )
        if updated.rowcount != 1:
            raise LedgerError("project repair diagnostic budget lost its CAS")

    def claim_provider_call(self, *, run_id: str) -> int:
        budget = self._run_budget(run_id)
        if budget.receipt_epochs >= budget.max_receipt_epochs:
            raise LedgerError("project repair successor receipt budget is exhausted")
        if budget.provider_calls >= budget.max_provider_calls:
            raise LedgerError("project repair provider-call budget is exhausted")
        updated = self.connection.execute(
            """update project_repair_run_budgets
               set provider_calls=provider_calls+1
               where run_id=? and provider_calls=?""",
            (run_id, budget.provider_calls),
        )
        if updated.rowcount != 1:
            raise LedgerError("project repair provider-call budget lost its CAS")
        return budget.provider_calls + 1

    def load(self, *, run_id: str) -> ProjectRepairRunBudget:
        from .ledger_project_repair_budget_audit import (
            assert_project_repair_budget_projection,
        )
        assert_project_repair_budget_projection(self.connection, run_id=run_id)
        return self._run_budget(run_id)

    def _run_budget(self, run_id: str) -> ProjectRepairRunBudget:
        row = self.connection.execute(
            """select max_provider_calls,provider_calls,
               max_receipt_epochs,receipt_epochs
               from project_repair_run_budgets where run_id=?""",
            (run_id,),
        ).fetchone()
        if row is None:
            raise LedgerError("project repair run budget is missing")
        return ProjectRepairRunBudget(*(int(value) for value in row))
__all__ = [
    "DEFAULT_MAX_PROVIDER_CALLS", "DEFAULT_MAX_RECEIPT_EPOCHS",
    "ProjectRepairBudgetAuthority", "ProjectRepairRunBudget",
]
