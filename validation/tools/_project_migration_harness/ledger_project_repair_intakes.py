from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .gate_candidate_sets import assert_current_candidate_set
from .ledger_project_diagnostics import load_bound_project_diagnostic_intakes
from .ledger_security import LedgerError
from .project_verifier_receipt import receipt_project_diagnostic_references


def load_receipt_project_diagnostic_intakes(
    connection: sqlite3.Connection, *, database_path: Path, run_id: str,
    receipt: Mapping[str, Any], rust_project_ir: Mapping[str, Any],
) -> list[dict[str, Any]]:
    references = receipt_project_diagnostic_references(receipt)
    if not references:
        return []
    wrappers = load_bound_project_diagnostic_intakes(
        connection, database_path=database_path, run_id=run_id,
        references=references,
        rust_project_ir_sha256=str(rust_project_ir["ir_sha256"]),
    )
    candidate_sets = {
        wrapper["intake"]["candidate_set_sha256"] for wrapper in wrappers
    }
    project_inputs = {
        wrapper["intake"]["project_input_sha256"] for wrapper in wrappers
    }
    interfaces = {
        wrapper["intake"]["rust_project_interface_sha256"] for wrapper in wrappers
    }
    if (
        len(candidate_sets) != 1 or len(project_inputs) != 1
        or interfaces != {rust_project_ir["interface_sha256"]}
    ):
        raise LedgerError("project diagnostic receipt intake cohort is inconsistent")
    assert_current_candidate_set(
        connection, run_id, next(iter(candidate_sets)),
        database_path=database_path,
    )
    return wrappers


__all__ = ["load_receipt_project_diagnostic_intakes"]
