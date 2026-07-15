from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .controller_gates import record_candidate_gate
from .ledger import ProjectLedger
from .project_cargo_diagnostic_intake import CargoDiagnosticPartition
from .project_cargo_diagnostic_intake import partition_cargo_diagnostics


def classification_required(
    context: dict[str, Any] | None,
    checks: dict[str, dict[str, Any]],
    observations: dict[str, dict[str, Any]],
) -> bool:
    check_observation = observations.get("cargo-check", {})
    return (
        context is not None
        and "cargo-check" in checks
        and check_observation.get("schema_version") == 2
        and check_observation.get("outcome") == "executed"
        and all(
            item.get("status") in {"passed", "failed"}
            and observations.get(gate, {}).get("outcome") == "executed"
            for gate, item in checks.items()
        )
    )


def native_link_trace_required(context: dict[str, Any] | None) -> bool:
    if context is None:
        return False
    rust_project_ir = context.get("rust_project_ir")
    if not isinstance(rust_project_ir, dict):
        return False
    requirements = rust_project_ir.get("native_link_requirements")
    return isinstance(requirements, list) and bool(requirements)


def command_stage(check: dict[str, Any]) -> str | None:
    command = check.get("command")
    if (
        not isinstance(command, list)
        or len(command) < 2
        or command[0] != "cargo"
        or command[1] not in {"check", "test"}
    ):
        return None
    return str(command[1])


def diagnostic_codes(
    execution: dict[str, Any], check: Any, gate_kind: str,
) -> list[str]:
    diagnostics = check.get("diagnostics") if isinstance(check, dict) else None
    if not isinstance(diagnostics, list):
        diagnostics = execution.get("diagnostics")
    codes = {
        str(item.get("code"))
        for item in diagnostics or []
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    if not codes:
        codes.add(f"{gate_kind}-not-executed")
    return sorted(codes)[:64]


def bridge_compile_failures(
    *, ledger: ProjectLedger, run_id: str, out_root: Path, out_root_rel: str,
    members: list[dict[str, str]], candidate_set_sha256: str,
    partition: CargoDiagnosticPartition, project_record: dict[str, Any],
) -> list[dict[str, Any]]:
    if project_record.get("gate_status") != "failed" or partition.admission_blocker:
        return []
    by_identity = {
        (item["unit_id"], item["artifact_id"]): item for item in members
    }
    results = []
    for identity, values in sorted(partition.unit_diagnostics.items()):
        member = by_identity[identity]
        record_id = "host-compile-" + content_sha256({
            "run_id": run_id,
            "unit_id": member["unit_id"],
            "candidate_artifact_id": member["artifact_id"],
            "project_record_id": project_record["record_id"],
        })[:24]
        results.append(record_candidate_gate(
            ledger=ledger, out_root=out_root, out_root_rel=out_root_rel,
            run_id=run_id, unit_id=member["unit_id"],
            candidate_artifact_id=member["artifact_id"], record_id=record_id,
            kind="verifier", gate_family="compile", status="failed",
            verifier_id="host-derived", diagnostics=values[:32],
            candidate_set_sha256=candidate_set_sha256,
            project_record_id=project_record["record_id"],
        ))
    return results


def partition_diagnostics(
    *, gate_kind: str, check: Any, observation: dict[str, Any],
    members: list[dict[str, str]], context: dict[str, Any] | None,
) -> CargoDiagnosticPartition:
    if (
        context is None or not isinstance(check, dict)
        or check.get("status") != "failed"
        or observation.get("outcome") != "executed"
    ):
        return CargoDiagnosticPartition({}, [], None)
    return partition_cargo_diagnostics(
        gate_kind=gate_kind, diagnostics=check.get("diagnostics"),
        candidate_members=members, rust_project_ir=context["rust_project_ir"],
    )


def project_diagnostic_input(
    context: dict[str, Any] | None, partition: CargoDiagnosticPartition,
) -> dict[str, Any] | None:
    if context is None or partition.admission_blocker or not partition.project_diagnostics:
        return None
    ir = context["rust_project_ir"]
    return {
        "rust_project_ir_sha256": ir["ir_sha256"],
        "rust_project_interface_sha256": ir["interface_sha256"],
        "project_input_sha256": context["project_input_sha256"],
        "diagnostics": partition.project_diagnostics,
    }


__all__ = [
    "bridge_compile_failures", "classification_required", "command_stage",
    "diagnostic_codes", "native_link_trace_required", "partition_diagnostics",
    "project_diagnostic_input",
]
