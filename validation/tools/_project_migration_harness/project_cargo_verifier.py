from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .controller_gates import record_candidate_gate
from .gate_candidate_sets import current_candidate_members
from .integration_generation import GenerationCommitError
from .ledger import ProjectLedger
from .project_cargo_evidence import project_cargo_observation
from .project_cargo_diagnostic_intake import (
    CargoDiagnosticPartition, partition_cargo_diagnostics,
)
from .project_cargo_diagnostic_cohort import decide_cargo_diagnostic_cohort
from .project_generation_context import load_managed_project_context
from .project_host_gates import record_host_project_observation
from .project_verification import run_cargo_project_gates


def verify_project_cargo(
    *, ledger: ProjectLedger, run_id: str, project_root: Path,
    runtime_root: Path, out_root: Path, out_root_rel: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    candidate_set = ledger.bind_current_candidate_set(run_id=run_id)
    with ledger.connect() as connection:
        members = current_candidate_members(connection, run_id)
    try:
        context = load_managed_project_context(project_root, members)
    except (GenerationCommitError, OSError, UnicodeError, ValueError):
        context = None
    execution = run_cargo_project_gates(
        project_root,
        runtime_root=runtime_root,
        cargo_command="cargo",
        timeout_seconds=timeout_seconds,
    )
    raw_checks = execution.get("checks")
    checks: dict[str, dict[str, Any]] = {}
    if isinstance(raw_checks, list):
        for command in ("check", "test"):
            matches = [
                item for item in raw_checks
                if isinstance(item, dict) and _command_stage(item) == command
            ]
            if len(matches) == 1:
                checks[command] = matches[0]
    project_input_sha256 = (
        str(context["project_input_sha256"])
        if context is not None else None
    )
    partitions: dict[str, CargoDiagnosticPartition] = {}
    observations: dict[str, dict[str, Any]] = {}
    gate_checks: dict[str, dict[str, Any]] = {}
    for gate_kind, command in (("cargo-check", "check"), ("cargo-test", "test")):
        check = checks.get(command)
        observation = project_cargo_observation(
            execution,
            check,
            gate_kind=gate_kind,
            expected_input_sha256=project_input_sha256,
        )
        partition = _partition_diagnostics(
            gate_kind=gate_kind, check=check, observation=observation,
            members=members, context=context,
        )
        observations[gate_kind] = observation
        partitions[gate_kind] = partition
        if check is not None:
            gate_checks[gate_kind] = check
    admission = decide_cargo_diagnostic_cohort(
        execution_status=execution.get("status"),
        checks=gate_checks,
        observations=observations,
        partitions=partitions,
        candidate_members=members,
    )
    records = []
    for gate_kind, command in (("cargo-check", "check"), ("cargo-test", "test")):
        check = checks.get(command)
        diagnostic_input = (
            _project_diagnostic_input(context, partitions[gate_kind])
            if admission.admits_repairs else None
        )
        records.append(record_host_project_observation(
            ledger=ledger,
            out_root=out_root,
            out_root_rel=out_root_rel,
            run_id=run_id,
            gate_kind=gate_kind,
            candidate_set_sha256=candidate_set,
            observation=observations[gate_kind],
            diagnostic_codes=_diagnostic_codes(execution, check, gate_kind),
            project_diagnostic_input=diagnostic_input,
        ))
    repairs = []
    if admission.admits_repairs:
        for gate_kind, project_record in zip(
            ("cargo-check", "cargo-test"), records, strict=True,
        ):
            repairs.extend(_bridge_compile_failures(
                ledger=ledger, run_id=run_id, out_root=out_root,
                out_root_rel=out_root_rel, members=members,
                candidate_set_sha256=candidate_set,
                partition=partitions[gate_kind], project_record=project_record,
            ))
    return {
        "schema_version": 1,
        "status": (
            "passed" if all(item["gate_status"] == "passed" for item in records)
            else "blocked" if execution.get("status") == "blocked"
            else "failed"
        ),
        "run_id": run_id,
        "candidate_set_sha256": candidate_set,
        "records": records,
        "candidate_repair_gates": repairs,
        "project_diagnostic_intakes": [
            record["project_diagnostic_intake"] for record in records
            if "project_diagnostic_intake" in record
        ],
        "diagnostic_admission": admission.payload(),
        "execution": execution,
        "semantic_gate": False,
    }


def _command_stage(check: dict[str, Any]) -> str | None:
    command = check.get("command")
    if (
        not isinstance(command, list)
        or len(command) < 2
        or command[0] != "cargo"
        or command[1] not in {"check", "test"}
    ):
        return None
    return str(command[1])


def _diagnostic_codes(
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


def _bridge_compile_failures(
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
            ledger=ledger,
            out_root=out_root,
            out_root_rel=out_root_rel,
            run_id=run_id,
            unit_id=member["unit_id"],
            candidate_artifact_id=member["artifact_id"],
            record_id=record_id,
            kind="verifier",
            gate_family="compile",
            status="failed",
            verifier_id="host-derived",
            diagnostics=values[:32],
            candidate_set_sha256=candidate_set_sha256,
            project_record_id=project_record["record_id"],
        ))
    return results


def _partition_diagnostics(
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


def _project_diagnostic_input(
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


__all__ = ["verify_project_cargo"]
