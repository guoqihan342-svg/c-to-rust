from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .ledger_security import LedgerError


def assert_project_repair_run_domain(
    connection: Any, *, run_id: str, rust_project_ir: Mapping[str, Any],
) -> None:
    run = connection.execute(
        "select dag_sha256,metadata_json from project_runs where run_id=?",
        (run_id,),
    ).fetchone()
    if run is None:
        raise LedgerError("project repair run does not exist")
    ledger_units = {
        str(row["unit_id"]) for row in connection.execute(
            "select unit_id from migration_units where run_id=?", (run_id,),
        ).fetchall()
    }
    ir_units = {
        str(value["unit_id"])
        for value in rust_project_ir["bindings"]["candidates"]
    }
    if ledger_units != ir_units:
        raise LedgerError("project repair RustProjectIR changed the run unit domain")
    allowed_dag_sha256s: set[str]
    try:
        metadata = json.loads(str(run["metadata_json"]))
    except json.JSONDecodeError as error:
        raise LedgerError("project repair run metadata is invalid") from error
    contract = metadata.get("migration_contract") if isinstance(metadata, dict) else None
    manifest = contract.get("integration_manifest") \
        if isinstance(contract, Mapping) else None
    if contract is not None and (
        not isinstance(manifest, Mapping)
        or not isinstance(manifest.get("sha256"), str)
    ):
        raise LedgerError("project repair migration contract is invalid")
    if isinstance(manifest, Mapping):
        allowed_dag_sha256s = {str(manifest["sha256"])}
    else:
        allowed_dag_sha256s = {str(run["dag_sha256"])}
    bound = str(rust_project_ir["bindings"]["migration_dag"]["sha256"])
    if bound not in allowed_dag_sha256s:
        raise LedgerError("project repair RustProjectIR changed the run DAG domain")


__all__ = ["assert_project_repair_run_domain"]
