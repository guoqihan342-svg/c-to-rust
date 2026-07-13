from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from .ledger_project_repair_authority import ProjectRepairAuthority
from .ledger_project_repair_core import ProjectRepairTransitionResult
from .ledger_project_repair_registry import (
    ProjectRepairRegistration,
    ProjectRepairRegistry,
)
from .ledger_security import LedgerError
from .ledger_schema import atomic
from .artifacts import content_sha256
from .project_interface_contract import (
    coordinator_receipt_accepts_repair_candidate, validate_coordinator_receipt,
)
from .project_interface_coordinator import coordinate_project_interfaces
from .rust_project_ir_validation import validate_rust_project_ir


@dataclass(frozen=True, slots=True)
class ProjectRepairFinalization:
    accepted: bool
    finished: ProjectRepairTransitionResult
    terminal: ProjectRepairTransitionResult
    registration: ProjectRepairRegistration | None


class ProjectRepairFinalizer:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def finalize(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
        attempt_id: str, expected_version: int, worker_id: str,
        response_sha256: str, rust_project_ir: Mapping[str, Any],
        receipt: Mapping[str, Any], coordinator_evidence_sha256: str,
    ) -> ProjectRepairFinalization:
        registry = ProjectRepairRegistry(self.connection)
        authority = ProjectRepairAuthority(self.connection)
        with atomic(self.connection):
            attempt = self.connection.execute(
                """select run_id,project_repair_queue_sha256,repair_id,worker_id
                   from project_repair_attempts where attempt_id=?""", (attempt_id,),
            ).fetchone()
            if (
                attempt is None or attempt["run_id"] != run_id
                or attempt["project_repair_queue_sha256"] != queue_sha256
                or attempt["repair_id"] != repair_id
                or attempt["worker_id"] != worker_id
            ):
                raise LedgerError("project repair finalization changed attempt scope")
            latest = self.connection.execute(
                """select project_repair_queue_sha256
                   from project_interface_receipts where run_id=?
                   order by receipt_epoch desc limit 1""", (run_id,),
            ).fetchone()
            if latest is None or latest[0] != queue_sha256:
                raise LedgerError(
                    "project repair finalization requires the latest receipt queue"
                )
            validate_rust_project_ir(rust_project_ir)
            coordinated = validate_coordinator_receipt(receipt)
            queue = coordinated["project_repair_queue"]
            if coordinate_project_interfaces(
                rust_project_ir, max_repairs=queue["max_items"],
                max_attempts_per_item=queue["max_attempts_per_item"],
            ) != coordinated:
                raise LedgerError(
                    "project repair finalization receipt is not recomputable"
                )
            ledger_units = {
                str(row["unit_id"]) for row in self.connection.execute(
                    "select unit_id from migration_units where run_id=?", (run_id,),
                ).fetchall()
            }
            ir_units = {
                str(value["unit_id"])
                for value in rust_project_ir["bindings"]["candidates"]
            }
            if ledger_units != ir_units:
                raise LedgerError(
                    "project repair finalization changed the run unit domain"
                )
            run_dag = self.connection.execute(
                "select dag_sha256 from project_runs where run_id=?", (run_id,),
            ).fetchone()
            if (
                run_dag is None
                or run_dag[0]
                != rust_project_ir["bindings"]["migration_dag"]["sha256"]
            ):
                raise LedgerError("project repair finalization changed the run DAG")
            original = registry.load_receipt(
                run_id=run_id, queue_sha256=queue_sha256,
            )
            item = next(
                value for value in original["project_repair_queue"]["items"]
                if value["repair_id"] == repair_id
            )
            accepted = coordinator_receipt_accepts_repair_candidate(
                original, coordinated,
                diagnostic_sha256=item["diagnostic_sha256"],
            )
            authority._require_artifact_evidence(
                run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
                evidence_sha256=coordinator_evidence_sha256,
                attempt_id=attempt_id,
            )
            finished = authority.finish_attempt(
                attempt_id=attempt_id,
                command_id=f"project-repair-finish-{response_sha256[:24]}",
                expected_version=expected_version, worker_id=worker_id,
                outcome="completed", evidence_sha256=response_sha256,
                output_ir_sha256=str(rust_project_ir["ir_sha256"]),
            )
            receipt_sha = str(coordinated["coordinator_receipt_sha256"])
            terminal_command = content_sha256({
                "repair_id": repair_id,
                "coordinator_receipt_sha256": receipt_sha,
                "coordinator_evidence_sha256": coordinator_evidence_sha256,
            })[:24]
            registration = None
            if accepted:
                registration = registry.register(
                    run_id=run_id, receipt=coordinated,
                    rust_project_ir=rust_project_ir,
                )
                terminal = authority.resolve_candidate(
                    run_id=run_id, queue_sha256=queue_sha256,
                    repair_id=repair_id,
                    command_id=f"project-repair-resolve-{terminal_command}",
                    expected_version=finished.current.version,
                    coordinator_receipt_sha256=receipt_sha,
                )
            else:
                terminal = authority.rollback_candidate(
                    run_id=run_id, queue_sha256=queue_sha256,
                    repair_id=repair_id,
                    command_id=f"project-repair-rollback-{terminal_command}",
                    expected_version=finished.current.version,
                    evidence_sha256=coordinator_evidence_sha256,
                )
            return ProjectRepairFinalization(
                accepted, finished, terminal, registration,
            )


__all__ = ["ProjectRepairFinalization", "ProjectRepairFinalizer"]
