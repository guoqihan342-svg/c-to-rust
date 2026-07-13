from __future__ import annotations

from typing import Any, Mapping

from .ledger_project_repair_authority import ProjectRepairAuthority
from .ledger_project_repair_finalize import ProjectRepairFinalizer
from .ledger_project_repair_registry import ProjectRepairRegistry
from .ledger_project_repair_replay import assert_project_repair_projection


class ProjectRepairLedgerMixin:
    def register_project_interface_receipt(
        self, *, run_id: str, receipt: Mapping[str, Any],
        rust_project_ir: Mapping[str, Any],
    ) -> Any:
        with self.connect() as connection:
            return ProjectRepairRegistry(connection).register(
                run_id=run_id, receipt=receipt, rust_project_ir=rust_project_ir,
            )

    def load_project_interface_receipt(
        self, *, run_id: str, queue_sha256: str,
    ) -> dict[str, Any]:
        with self.connect() as connection:
            return ProjectRepairRegistry(connection).load_receipt(
                run_id=run_id, queue_sha256=queue_sha256,
            )

    def load_latest_project_interface_receipt(
        self, *, run_id: str,
    ) -> Any:
        with self.connect() as connection:
            return ProjectRepairRegistry(connection).load_latest_receipt(run_id=run_id)

    def project_repair_projection(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
    ) -> Any:
        with self.connect() as connection:
            return assert_project_repair_projection(
                connection, run_id=run_id, queue_sha256=queue_sha256,
                repair_id=repair_id,
            )

    def start_project_repair_attempt(self, **values: Any) -> Any:
        with self.connect() as connection:
            return ProjectRepairAuthority(connection).start_attempt(**values)

    def finish_project_repair_attempt(self, **values: Any) -> Any:
        with self.connect() as connection:
            return ProjectRepairAuthority(connection).finish_attempt(**values)

    def mark_project_repair_command_started(self, **values: Any) -> Any:
        with self.connect() as connection:
            return ProjectRepairAuthority(connection).mark_command_started(**values)

    def recover_project_repair_attempt(self, **values: Any) -> Any:
        with self.connect() as connection:
            return ProjectRepairAuthority(connection).recover_attempt(**values)

    def rollback_project_repair_candidate(self, **values: Any) -> Any:
        with self.connect() as connection:
            return ProjectRepairAuthority(connection).rollback_candidate(**values)

    def finalize_project_repair_candidate(self, **values: Any) -> Any:
        with self.connect() as connection:
            return ProjectRepairFinalizer(connection).finalize(**values)

    def resolve_project_repair_candidate(self, **values: Any) -> Any:
        with self.connect() as connection:
            return ProjectRepairAuthority(connection).resolve_candidate(**values)


__all__ = ["ProjectRepairLedgerMixin"]
