from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from .ledger_project_repair_budget import ProjectRepairBudgetAuthority
from .ledger_project_repair_budget_audit import (
    assert_project_repair_budget_projection,
)
from .ledger_schema import _json, _now_text, atomic
from .ledger_security import LedgerError, assert_no_secrets
from .project_interface_contract import validate_coordinator_receipt
from .project_interface_coordinator import (
    COORDINATOR_RECEIPT_SHA256_FIELD, PROJECT_REPAIR_QUEUE_SHA256_FIELD,
    coordinate_project_interfaces,
)
from .project_repair_run_domain import assert_project_repair_run_domain
from .rust_project_ir_validation import validate_rust_project_ir


@dataclass(frozen=True, slots=True)
class ProjectRepairRegistration:
    applied: bool
    receipt_epoch: int
    coordinator_receipt_sha256: str
    project_repair_queue_sha256: str
    item_count: int


class ProjectRepairRegistry:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def register(
        self, *, run_id: str, receipt: Mapping[str, Any],
        rust_project_ir: Mapping[str, Any],
        created_at: str | None = None,
    ) -> ProjectRepairRegistration:
        value = validate_coordinator_receipt(receipt)
        validate_rust_project_ir(rust_project_ir)
        queue = value["project_repair_queue"]
        recomputed = coordinate_project_interfaces(
            rust_project_ir, max_repairs=queue["max_items"],
            max_attempts_per_item=queue["max_attempts_per_item"],
        )
        if recomputed != value:
            raise LedgerError("project interface receipt is not recomputable from RustProjectIR")
        assert_no_secrets(value, "project_interface_receipt")
        receipt_sha = value[COORDINATOR_RECEIPT_SHA256_FIELD]
        queue_sha = queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD]
        with atomic(self.connection):
            run = self.connection.execute(
                "select status,dag_sha256 from project_runs where run_id=?", (run_id,),
            ).fetchone()
            if run is None:
                raise LedgerError("project repair receipt run does not exist")
            assert_project_repair_run_domain(
                self.connection, run_id=run_id, rust_project_ir=rust_project_ir,
            )
            existing = self.connection.execute(
                """select * from project_interface_receipts where run_id=?
                   and project_repair_queue_sha256=?""",
                (run_id, queue_sha),
            ).fetchone()
            if existing is not None:
                self._assert_replay(existing, value)
                self._assert_items(run_id, queue_sha, queue["items"])
                assert_project_repair_budget_projection(
                    self.connection, run_id=run_id,
                )
                return ProjectRepairRegistration(
                    False, int(existing["receipt_epoch"]), receipt_sha,
                    queue_sha, len(queue["items"]),
                )
            if run["status"] != "active":
                raise LedgerError("project repair receipt requires an active run")
            running = self.connection.execute(
                """select attempt_id from project_repair_attempts
                   where run_id=? and status='running' limit 1""", (run_id,),
            ).fetchone()
            if running is not None:
                raise LedgerError(
                    "project interface receipt cannot advance during a repair attempt"
                )
            timestamp = created_at or _now_text()
            receipt_epoch = 1 + int(self.connection.execute(
                """select coalesce(max(receipt_epoch),0)
                   from project_interface_receipts where run_id=?""",
                (run_id,),
            ).fetchone()[0])
            self.connection.execute(
                """insert into project_interface_receipts(
                   run_id,receipt_epoch,coordinator_receipt_sha256,
                   project_repair_queue_sha256,
                   rust_project_ir_sha256,rust_project_interface_sha256,status,
                   diagnostic_count,queue_item_count,receipt_json,queue_json,created_at)
                   values (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, receipt_epoch, receipt_sha, queue_sha,
                    value["rust_project_ir_sha256"],
                    value["rust_project_interface_sha256"], value["status"],
                    len(value["diagnostics"]) + value["diagnostic_overflow_count"],
                    len(queue["items"]), _json(value), _json(queue), timestamp,
                ),
            )
            inherited = ProjectRepairBudgetAuthority(
                self.connection
            ).register_receipt(
                run_id=run_id, receipt_epoch=receipt_epoch,
                diagnostics=value["diagnostics"], rust_project_ir=rust_project_ir,
                max_attempts=queue["max_attempts_per_item"],
            )
            for item in queue["items"]:
                lineage_id, inherited_count, initial_status = inherited[
                    item["diagnostic_sha256"]
                ]
                self.connection.execute(
                    """insert into project_repair_items(
                       run_id,project_repair_queue_sha256,repair_id,
                       diagnostic_code,diagnostic_sha256,diagnostic_lineage_id,
                       max_attempts,item_json,
                       initial_status,status,state_version,
                       inherited_attempt_count,attempt_count,
                       active_attempt_id,candidate_ir_sha256,updated_at)
                       values (?,?,?,?,?,?,?,?,?,?,0,?,?,null,null,?)""",
                    (
                        run_id, queue_sha, item["repair_id"],
                        item["diagnostic_code"], item["diagnostic_sha256"],
                        lineage_id, item["max_attempts"], _json(item),
                        initial_status, initial_status, inherited_count,
                        inherited_count, timestamp,
                    ),
                )
            self._assert_items(run_id, queue_sha, queue["items"])
            assert_project_repair_budget_projection(
                self.connection, run_id=run_id,
            )
            return ProjectRepairRegistration(
                True, receipt_epoch, receipt_sha, queue_sha, len(queue["items"]),
            )

    def load_receipt(
        self, *, run_id: str, queue_sha256: str,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """select * from project_interface_receipts where run_id=?
               and project_repair_queue_sha256=?""",
            (run_id, queue_sha256),
        ).fetchone()
        if row is None:
            raise LedgerError("project repair queue does not exist")
        try:
            value = validate_coordinator_receipt(json.loads(row["receipt_json"]))
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise LedgerError("stored project interface receipt is invalid") from error
        self._assert_replay(row, value)
        self._assert_items(
            run_id, queue_sha256, value["project_repair_queue"]["items"],
        )
        assert_project_repair_budget_projection(
            self.connection, run_id=run_id,
        )
        return value

    def load_latest_receipt(
        self, *, run_id: str,
    ) -> tuple[int, dict[str, Any]] | None:
        row = self.connection.execute(
            """select receipt_epoch,project_repair_queue_sha256
               from project_interface_receipts where run_id=?
               order by receipt_epoch desc limit 1""",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return int(row["receipt_epoch"]), self.load_receipt(
            run_id=run_id, queue_sha256=str(row["project_repair_queue_sha256"]),
        )

    def receipt_epoch(self, *, run_id: str, queue_sha256: str) -> int:
        row = self.connection.execute(
            """select receipt_epoch from project_interface_receipts
               where run_id=? and project_repair_queue_sha256=?""",
            (run_id, queue_sha256),
        ).fetchone()
        if row is None:
            raise LedgerError("project repair queue does not exist")
        return int(row["receipt_epoch"])

    @staticmethod
    def _assert_replay(row: sqlite3.Row, receipt: Mapping[str, Any]) -> None:
        queue = receipt["project_repair_queue"]
        expected = (
            receipt[COORDINATOR_RECEIPT_SHA256_FIELD],
            queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD],
            receipt["rust_project_ir_sha256"],
            receipt["rust_project_interface_sha256"], receipt["status"],
            len(receipt["diagnostics"]) + receipt["diagnostic_overflow_count"],
            len(queue["items"]), _json(receipt), _json(queue),
        )
        actual = tuple(row[key] for key in (
            "coordinator_receipt_sha256", "project_repair_queue_sha256",
            "rust_project_ir_sha256", "rust_project_interface_sha256", "status",
            "diagnostic_count", "queue_item_count", "receipt_json", "queue_json",
        ))
        if actual != expected:
            raise LedgerError("project repair queue replay changed its receipt binding")

    def _assert_items(
        self, run_id: str, queue_sha256: str, items: list[Mapping[str, Any]],
    ) -> None:
        rows = self.connection.execute(
            """select repair_id,diagnostic_code,diagnostic_sha256,max_attempts,item_json
               from project_repair_items where run_id=?
               and project_repair_queue_sha256=? order by repair_id""",
            (run_id, queue_sha256),
        ).fetchall()
        expected = sorted((
            item["repair_id"], item["diagnostic_code"], item["diagnostic_sha256"],
            item["max_attempts"], _json(item),
        ) for item in items)
        if [tuple(row) for row in rows] != expected:
            raise LedgerError("project repair queue item projection drifted")


__all__ = [
    "ProjectRepairRegistration", "ProjectRepairRegistry",
]
