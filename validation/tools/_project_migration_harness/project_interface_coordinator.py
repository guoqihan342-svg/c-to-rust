from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .project_interface_diagnostics import collect_project_interface_diagnostics
from .rust_project_ir_validation import validate_rust_project_ir


COORDINATOR_ID = "deterministic-project-interface-coordinator-v1"
COORDINATOR_RECEIPT_SHA256_FIELD = "coordinator_receipt_sha256"
PROJECT_REPAIR_QUEUE_SHA256_FIELD = "project_repair_queue_sha256"
DEFAULT_MAX_REPAIRS = 32
MAX_REPAIRS = 64
MAX_DIAGNOSTICS = 256


def coordinate_project_interfaces(
    rust_project_ir: Mapping[str, Any], *, max_repairs: int = DEFAULT_MAX_REPAIRS,
    max_attempts_per_item: int = 3,
) -> dict[str, Any]:
    """Diagnose project assembly conflicts without generating or accepting Rust."""
    validate_rust_project_ir(rust_project_ir)
    _validate_bounds(max_repairs, max_attempts_per_item)
    diagnostics = collect_project_interface_diagnostics(rust_project_ir)
    diagnostics.sort(key=lambda item: (
        item["code"], item["entity_ids"], item["affected_module_ids"],
    ))
    diagnostic_overflow = max(0, len(diagnostics) - MAX_DIAGNOSTICS)
    published = diagnostics[:MAX_DIAGNOSTICS]
    repairs = [
        _repair_item(item, rust_project_ir, max_attempts_per_item)
        for item in published[:max_repairs]
    ]
    queue = {
        "schema_version": 1,
        "scope": "project",
        "rust_project_ir_sha256": rust_project_ir["ir_sha256"],
        "rust_project_interface_sha256": rust_project_ir["interface_sha256"],
        "max_items": max_repairs,
        "item_count": len(repairs),
        "overflow_count": max(0, len(published) - max_repairs) + diagnostic_overflow,
        "max_attempts_per_item": max_attempts_per_item,
        "items": repairs,
        "policy": {
            "assignment": "project-only",
            "allowed_output": "rust-project-ir-candidate",
            "generated_glue_allowed": False,
            "fixture_specific_shim_allowed": False,
        },
    }
    queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD] = content_sha256(
        project_repair_queue_projection(queue)
    )
    receipt = {
        "schema_version": 1,
        "coordinator": COORDINATOR_ID,
        "rust_project_ir_sha256": rust_project_ir["ir_sha256"],
        "rust_project_interface_sha256": rust_project_ir["interface_sha256"],
        "status": "repair-required" if diagnostics else "candidate-ready",
        "diagnostics": published,
        "diagnostic_overflow_count": diagnostic_overflow,
        "project_repair_queue": queue,
        "claim_boundary": {
            "artifact_role": "project-interface-diagnostic",
            "semantic_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }
    receipt[COORDINATOR_RECEIPT_SHA256_FIELD] = content_sha256(
        coordinator_receipt_projection(receipt)
    )
    return receipt


def coordinator_receipt_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item for key, item in value.items()
        if key != COORDINATOR_RECEIPT_SHA256_FIELD
    }


def project_repair_queue_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item for key, item in value.items()
        if key != PROJECT_REPAIR_QUEUE_SHA256_FIELD
    }


def _validate_bounds(max_repairs: int, max_attempts_per_item: int) -> None:
    if (
        isinstance(max_repairs, bool) or not isinstance(max_repairs, int)
        or not 1 <= max_repairs <= MAX_REPAIRS
        or isinstance(max_attempts_per_item, bool)
        or not isinstance(max_attempts_per_item, int)
        or not 1 <= max_attempts_per_item <= 5
    ):
        raise ValueError("project repair bounds are invalid")


def _repair_item(
    diagnostic: Mapping[str, Any], ir: Mapping[str, Any], max_attempts: int,
) -> dict[str, Any]:
    unit_by_module = {item["module_id"]: item["unit_id"] for item in ir["modules"]}
    units = sorted({
        unit_by_module[module_id]
        for module_id in diagnostic["affected_module_ids"]
        if module_id in unit_by_module
    })
    unresolved_modules = sorted(
        set(diagnostic["affected_module_ids"]) - set(unit_by_module)
    )
    return {
        "repair_id": f"project-repair-{diagnostic['diagnostic_sha256'][:24]}",
        "scope": "project",
        "assigned_unit_id": None,
        "diagnostic_code": diagnostic["code"],
        "rust_project_ir_sha256": ir["ir_sha256"],
        "rust_project_interface_sha256": ir["interface_sha256"],
        "diagnostic_sha256": diagnostic["diagnostic_sha256"],
        "affected_module_ids": list(diagnostic["affected_module_ids"]),
        "affected_unit_ids": units,
        "unresolved_module_ids": unresolved_modules,
        "max_attempts": max_attempts,
        "candidate_only": True,
    }


__all__ = [
    "COORDINATOR_ID", "COORDINATOR_RECEIPT_SHA256_FIELD",
    "DEFAULT_MAX_REPAIRS", "MAX_REPAIRS", "PROJECT_REPAIR_QUEUE_SHA256_FIELD",
    "coordinate_project_interfaces", "coordinator_receipt_projection",
    "project_repair_queue_projection",
]
