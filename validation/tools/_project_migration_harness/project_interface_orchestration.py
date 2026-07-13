from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .ledger import ProjectLedger
from .project_interface_coordinator import coordinate_project_interfaces
from .project_repair_authoritative_ir import (
    load_authoritative_project_ir, persist_authoritative_project_ir,
)
from .project_repair_coordinator import resume_latest_project_repair
from .project_repair_dispatch_permit import ProjectRepairDispatchPermit


@dataclass(frozen=True, slots=True)
class ProjectInterfacePreparation:
    rust_project_ir: dict[str, Any]
    rust_project_ir_reference: dict[str, Any]
    coordinator_action: dict[str, Any]


def prepare_project_interfaces(
    initial_rust_project_ir: Mapping[str, Any], *, ledger: ProjectLedger,
    run_id: str, harness_root: Path, out_root: Path, out_root_rel: str,
    repair_dispatch_permit: ProjectRepairDispatchPermit | None = None,
) -> ProjectInterfacePreparation:
    initial = dict(initial_rust_project_ir)
    latest = ledger.load_latest_project_interface_receipt(run_id=run_id)
    selected = initial
    reference: dict[str, Any]
    reuse_latest = False
    if latest is not None:
        latest_ir_sha = str(latest[1]["rust_project_ir_sha256"])
        if latest_ir_sha == initial["ir_sha256"]:
            reference = persist_authoritative_project_ir(
                initial, out_root=out_root, out_root_rel=out_root_rel,
            )
            reuse_latest = True
        else:
            latest_ir, latest_reference = load_authoritative_project_ir(
                latest_ir_sha, harness_root=harness_root, out_root=out_root,
                out_root_rel=out_root_rel,
            )
            if candidate_cohort_matches(initial, latest_ir):
                selected, reference = latest_ir, latest_reference
                reuse_latest = True
    if not reuse_latest:
        reference = persist_authoritative_project_ir(
            initial, out_root=out_root, out_root_rel=out_root_rel,
        )
        receipt = coordinate_project_interfaces(initial)
        ledger.register_project_interface_receipt(
            run_id=run_id, receipt=receipt, rust_project_ir=initial,
        )
    action = resume_latest_project_repair(
        ledger=ledger, run_id=run_id, base_rust_project_ir=reference,
        harness_root=harness_root, out_root=out_root,
        out_root_rel=out_root_rel,
        dispatch_permit=repair_dispatch_permit,
    )
    return ProjectInterfacePreparation(selected, reference, action)


def candidate_cohort_matches(
    left: Mapping[str, Any], right: Mapping[str, Any],
) -> bool:
    return canonical_json_bytes(left.get("bindings")) == canonical_json_bytes(
        right.get("bindings")
    )


__all__ = [
    "ProjectInterfacePreparation", "candidate_cohort_matches",
    "prepare_project_interfaces",
]
