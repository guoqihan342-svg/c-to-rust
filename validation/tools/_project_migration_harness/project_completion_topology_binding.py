from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .ledger_security import LedgerError
from .project_rust_cargo_topology import reopen_project_rust_cargo_topology


def ready_rust_cargo_topology_reference(cargo: Mapping[str, object]):
    topology = cargo.get("rust_cargo_topology")
    if isinstance(topology, Mapping) and topology.get("status") == "ready":
        return topology.get("reference")
    return None


def validate_completion_rust_cargo_topology(
    out_root: Path, receipt: Mapping[str, object],
) -> None:
    if receipt.get("schema_version") != 3:
        return
    database = out_root.resolve(strict=True) / "state" / "project-migration.sqlite3"
    try:
        topology = reopen_project_rust_cargo_topology(
            ledger_path=database,
            reference=receipt["rust_cargo_topology_evidence"],
            run_id=str(receipt["run_id"]),
            candidate_set_sha256=str(receipt["candidate_set_sha256"]),
        )
    except (OSError, TypeError, ValueError, LedgerError) as error:
        raise LedgerError(
            "project completion Rust Cargo topology evidence drifted"
        ) from error
    if topology.get("status") != "ready":
        raise LedgerError(
            "project completion requires ready Rust Cargo topology evidence"
        )


__all__ = [
    "ready_rust_cargo_topology_reference",
    "validate_completion_rust_cargo_topology",
]
