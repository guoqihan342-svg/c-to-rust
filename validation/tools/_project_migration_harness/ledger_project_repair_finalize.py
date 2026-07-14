from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .ledger_project_repair_authority import ProjectRepairAuthority
from .ledger_project_repair_core import ProjectRepairTransitionResult
from .ledger_project_repair_registry import (
    ProjectRepairRegistration,
    ProjectRepairRegistry,
)
from .ledger_project_repair_intakes import (
    load_receipt_project_diagnostic_intakes,
)
from .ledger_project_repair_supersession import (
    cancel_superseded_items, receipt_repair_ids,
)
from .ledger_security import LedgerError
from .ledger_schema import atomic
from .artifacts import content_sha256
from .project_interface_contract import (
    coordinator_receipt_accepts_repair_candidate, validate_coordinator_receipt,
)
from .project_interface_coordinator import coordinate_project_interfaces
from .project_repair_run_domain import assert_project_repair_run_domain
from .rust_project_ir_validation import validate_rust_project_ir
from .project_verifier_receipt import verifier_diagnostic_detail


@dataclass(frozen=True, slots=True)
class ProjectRepairFinalization:
    accepted: bool
    requires_reverification: bool
    finished: ProjectRepairTransitionResult
    terminal: ProjectRepairTransitionResult
    registration: ProjectRepairRegistration | None


class ProjectRepairFinalizer:
    def __init__(self, connection: sqlite3.Connection, database_path: Path) -> None:
        self.connection = connection
        self.database_path = database_path

    def finalize(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
        attempt_id: str, expected_version: int, worker_id: str,
        response_sha256: str, rust_project_ir: Mapping[str, Any],
        receipt: Mapping[str, Any], coordinator_evidence_sha256: str,
    ) -> ProjectRepairFinalization:
        registry = ProjectRepairRegistry(self.connection, self.database_path)
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
            assert_project_repair_run_domain(
                self.connection, run_id=run_id, rust_project_ir=rust_project_ir,
            )
            original = registry.load_receipt(
                run_id=run_id, queue_sha256=queue_sha256,
            )
            item = next(
                value for value in original["project_repair_queue"]["items"]
                if value["repair_id"] == repair_id
            )
            intakes = load_receipt_project_diagnostic_intakes(
                self.connection, database_path=self.database_path, run_id=run_id,
                receipt=original, rust_project_ir={
                    "ir_sha256": original["rust_project_ir_sha256"],
                    "interface_sha256": original["rust_project_interface_sha256"],
                },
            )
            verifier_origin = verifier_diagnostic_detail(
                intakes, item["diagnostic_sha256"],
            ) is not None
            if intakes and not verifier_origin:
                raise LedgerError(
                    "static repair cannot bypass verifier-origin obligations"
                )
            pending_verifier = (
                verifier_origin and coordinated["status"] == "candidate-ready"
            )
            accepted = (
                False if verifier_origin else
                coordinator_receipt_accepts_repair_candidate(
                    original, coordinated,
                    diagnostic_sha256=item["diagnostic_sha256"],
                )
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
            if pending_verifier:
                terminal = finished
            elif accepted:
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
                cancel_superseded_items(
                    authority, run_id=run_id, queue_sha256=queue_sha256,
                    repair_ids=receipt_repair_ids(original),
                    successor_receipt_sha256=receipt_sha,
                    excluded=[repair_id],
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
                accepted, pending_verifier, finished, terminal, registration,
            )


__all__ = ["ProjectRepairFinalization", "ProjectRepairFinalizer"]
