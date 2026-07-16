from __future__ import annotations

from pathlib import Path
from typing import Any

from .cargo_raw_output_evidence import persist_captured_cargo_outputs
from .gate_candidate_sets import current_candidate_members
from .integration_generation import GenerationCommitError
from .ledger import ProjectLedger
from .ledger_security import LedgerError
from .ledger_run_contract import load_migration_contract
from .native_link_trace_evidence import persist_captured_native_link_trace
from .project_cargo_classification_receipt import (
    write_cargo_classification_receipt,
)
from .project_cargo_evidence import (
    bind_project_cargo_classification, blocked_project_cargo_observation,
    project_cargo_observation,
)
from .project_cargo_diagnostic_intake import (
    CargoDiagnosticPartition,
)
from .project_cargo_diagnostic_cohort import (
    CargoDiagnosticCohortDecision, decide_cargo_diagnostic_cohort,
)
from .project_cargo_native_link import settle_cargo_native_links
from .project_generation_context import load_managed_project_context
from .project_cargo_verifier_support import (
    bridge_compile_failures as _bridge_compile_failures,
    classification_required as _classification_required,
    command_stage as _command_stage,
    diagnostic_codes as _diagnostic_codes,
    native_link_trace_required as _native_link_trace_required,
    partition_diagnostics as _partition_diagnostics,
    project_diagnostic_input as _project_diagnostic_input,
)
from .project_host_gates import record_host_project_observation
from .project_rust_cargo_topology import (
    materialize_project_rust_cargo_topology,
)
from .project_verification import run_cargo_project_gates
from .rust_product_evidence import persist_captured_rust_products


def verify_project_cargo(
    *, ledger: ProjectLedger, run_id: str, project_root: Path,
    runtime_root: Path, out_root: Path, out_root_rel: str,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    candidate_set = ledger.bind_current_candidate_set(run_id=run_id)
    with ledger.connect() as connection:
        members = current_candidate_members(connection, run_id)
        try:
            _contract, migration_manifest = load_migration_contract(
                ledger.path, connection, run_id,
            )
        except LedgerError:
            migration_manifest = None
    try:
        context = load_managed_project_context(project_root, members)
    except (GenerationCommitError, OSError, UnicodeError, ValueError):
        context = None
    native_link_trace_required = _native_link_trace_required(context)
    context_ir = context.get("rust_project_ir") if context is not None else None
    topology_required = bool(
        isinstance(context_ir, dict) and context_ir.get("schema_version") == 3
    )
    captured_execution = run_cargo_project_gates(
        project_root,
        runtime_root=runtime_root,
        cargo_command="cargo",
        timeout_seconds=timeout_seconds,
        capture_raw_output=True,
        capture_native_link_trace=native_link_trace_required,
        capture_cargo_facts=topology_required,
        capture_cargo_structure=topology_required,
    )
    captured_execution = persist_captured_rust_products(
        captured_execution, out_root=out_root, required=topology_required,
    )
    execution = persist_captured_cargo_outputs(
        persist_captured_native_link_trace(
            captured_execution, out_root=out_root,
            required=native_link_trace_required,
        ),
        out_root=out_root, out_root_rel=out_root_rel,
    )
    topology: dict[str, Any] = {
        "status": "not-required", "semantic_gate": False,
    }
    if topology_required:
        try:
            topology = materialize_project_rust_cargo_topology(
                ledger_path=ledger.path, out_root=out_root, run_id=run_id,
                candidate_set_sha256=candidate_set, context=context,
                execution=execution,
            )
        except (KeyError, OSError, TypeError, ValueError, LedgerError):
            topology = {
                "status": "blocked",
                "blockers": ["rust-cargo-topology-evidence-unavailable"],
                "semantic_gate": False,
            }
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
    classification_receipt = None
    if _classification_required(context, gate_checks, observations):
        try:
            ir = context["rust_project_ir"]
            classification_receipt = write_cargo_classification_receipt(
                out_root, out_root_rel, run_id=run_id,
                candidate_set_sha256=candidate_set,
                project_input_sha256=str(context["project_input_sha256"]),
                rust_project_ir=ir,
                candidate_members=members, checks=gate_checks,
                partitions=partitions, admission=admission.payload(),
            )
            bound = {
                gate: bind_project_cargo_classification(
                    observation, classification_receipt,
                )
                for gate, observation in observations.items()
            }
        except (KeyError, OSError, TypeError, ValueError, LedgerError):
            classification_receipt = None
            admission = CargoDiagnosticCohortDecision(
                "blocked", "classification-receipt-unavailable",
            )
            observations = {
                gate: blocked_project_cargo_observation(
                    project_input_sha256,
                    unchanged=execution.get("project_state_unchanged") is True,
                    blocker_code="classification-receipt-unavailable",
                )
                for gate in observations
            }
        else:
            observations = bound
    native_link_settlement = settle_cargo_native_links(
        ledger_path=ledger.path, out_root=out_root, context=context,
        migration_manifest=migration_manifest, execution=execution,
        checks=checks, observations=observations,
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
    status = (
        "passed" if all(item["gate_status"] == "passed" for item in records)
        else "blocked" if execution.get("status") == "blocked"
        else "failed"
    )
    if (
        status == "passed" and native_link_trace_required
        and native_link_settlement["status"] != "resolved"
    ):
        status = "blocked"
    if status == "passed" and topology_required \
            and topology.get("status") != "ready":
        status = "blocked"
    return {
        "schema_version": 1,
        "status": status,
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
        "native_link_settlement": native_link_settlement,
        "rust_cargo_topology": topology,
        "semantic_gate": False,
        **(
            {"classification_receipt": classification_receipt}
            if classification_receipt is not None else {}
        ),
    }


__all__ = ["verify_project_cargo"]
