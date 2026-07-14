from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger import ProjectLedger
from .project_repair_worker_request import read_bound_rust_project_ir
from .project_verifier_repair_flow import (
    register_project_diagnostic_repairs,
    settle_pending_project_verifier_repair,
)


def advance_project_verifier_phase(
    *, ledger: ProjectLedger, run_id: str, harness_root: Path,
    integration: Mapping[str, Any], cargo_result: Mapping[str, Any],
) -> dict[str, Any] | None:
    pending = integration.get("project_repair_verification")
    references = cargo_result.get("project_diagnostic_intakes")
    has_intakes = isinstance(references, list) and bool(references)
    if not isinstance(pending, Mapping) and not has_intakes:
        return None
    ir_reference = integration.get("authoritative_rust_project_ir")
    if not isinstance(ir_reference, Mapping):
        raise ValueError("project verifier phase lost authoritative RustProjectIR")
    rust_project_ir = read_bound_rust_project_ir(harness_root, ir_reference)
    if isinstance(pending, Mapping):
        outcome = settle_pending_project_verifier_repair(
            ledger=ledger, run_id=run_id, rust_project_ir=rust_project_ir,
            pending=pending, cargo_result=cargo_result,
        )
        status = "waiting" if outcome["status"] in {
            "verified", "repair-required",
        } else "blocked"
        return {
            "status": status,
            "stage": (
                "project-repair-verifier-state-advanced"
                if status == "waiting" else str(outcome.get("stage"))
            ),
            "blockers": [] if status == "waiting" else [
                "project-repair-verifier-recheck-blocked",
            ],
            "project_repair": outcome,
        }
    outcome = register_project_diagnostic_repairs(
        ledger=ledger, run_id=run_id, rust_project_ir=rust_project_ir,
        intake_references=references,
    )
    return {
        "status": "waiting", "stage": "project-diagnostic-intake-registered",
        "blockers": [], "project_repair": outcome,
    }


__all__ = ["advance_project_verifier_phase"]
