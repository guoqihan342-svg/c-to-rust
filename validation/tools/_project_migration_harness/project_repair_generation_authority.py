from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .gate_candidate_sets import current_candidate_members
from .integration_generation import GenerationCommitError
from .ledger_security import LedgerError
from .project_generation_context import (
    load_managed_project_context, managed_project_root,
)
from .project_verifier_receipt import receipt_project_diagnostic_references


def require_project_repair_source_generation(
    *, ledger: Any, run_id: str, queue_sha256: str,
    rust_project_ir: Mapping[str, Any], out_root: Path,
) -> dict[str, Any] | None:
    receipt = ledger.load_project_interface_receipt(
        run_id=run_id, queue_sha256=queue_sha256,
    )
    references = receipt_project_diagnostic_references(receipt)
    if not references:
        return None
    wrappers = ledger.bound_project_diagnostic_intakes(
        run_id=run_id, references=references,
        rust_project_ir_sha256=str(rust_project_ir["ir_sha256"]),
    )
    with ledger.connect() as connection:
        members = current_candidate_members(connection, run_id)
    try:
        context = load_managed_project_context(
            managed_project_root(out_root), members,
        )
    except (GenerationCommitError, OSError, TypeError, ValueError) as error:
        raise LedgerError(
            "project repair source generation cannot be reopened"
        ) from error
    project_inputs = {
        wrapper["intake"]["project_input_sha256"] for wrapper in wrappers
    }
    managed_ir = context["rust_project_ir"]
    if (
        len(project_inputs) != 1
        or context["project_input_sha256"] != next(iter(project_inputs))
        or managed_ir["ir_sha256"] != rust_project_ir["ir_sha256"]
        or managed_ir["interface_sha256"] != rust_project_ir["interface_sha256"]
    ):
        raise LedgerError("project repair source generation binding drifted")
    return {
        "project_input_sha256": context["project_input_sha256"],
        "rust_project_ir_sha256": managed_ir["ir_sha256"],
        "rust_project_interface_sha256": managed_ir["interface_sha256"],
    }


__all__ = ["require_project_repair_source_generation"]
