from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .candidate_cargo_fact_binding import (
    parse_captured_candidate_cargo_facts,
    write_candidate_cargo_fact_binding,
)
from .cargo_compiler_artifact_evidence import CargoCompilerArtifactEvidenceError
from .cargo_metadata_fact_evidence import CargoMetadataFactEvidenceError
from .cargo_raw_output_evidence import (
    persist_captured_cargo_outputs,
    validate_cargo_raw_output_reference,
)
from .ledger_security import LedgerError
from .native_link_trace_evidence import persist_captured_native_link_trace
from .project_cargo_evidence import (
    derive_project_cargo_status,
    project_cargo_observation,
)
from .project_native_link_settlement import settle_project_native_links
from .project_native_link_settlement_binding import (
    project_native_link_settlement_status,
)
from .project_native_link_state import recover_project_native_link_state


def bind_candidate_cargo_evidence(
    execution: Mapping[str, Any], *, native_required: bool,
    out_root: Path, out_root_rel: str,
) -> tuple[
    dict[str, Any], dict[str, dict[str, Any]],
    dict[str, dict[str, Any]], dict[str, str], dict[str, Any],
]:
    captured = persist_captured_native_link_trace(
        execution, out_root=out_root, required=native_required,
    )
    persisted = persist_captured_cargo_outputs(
        captured,
        out_root=out_root,
        out_root_rel=out_root_rel,
    )
    checks = _checks(persisted)
    observations = _observations(persisted, checks)
    statuses = {
        gate: derive_project_cargo_status(gate, observation)
        for gate, observation in observations.items()
    }
    raw_output_bound = _raw_outputs_bound(persisted)
    if persisted.get("status") != "passed" or not raw_output_bound:
        return (
            persisted, checks, observations, statuses,
            _blocked_cargo_facts(
                _execution_block_reason(persisted, raw_output_bound),
                raw_output_bound=raw_output_bound,
            ),
        )
    if any(status != "passed" for status in statuses.values()):
        return (
            persisted, checks, observations, statuses,
            _blocked_cargo_facts(
                "candidate_cargo_fact_source_failed", raw_output_bound=True,
            ),
        )
    try:
        parsed_facts = parse_captured_candidate_cargo_facts(captured)
        facts = write_candidate_cargo_fact_binding(
            parsed=parsed_facts,
            execution=persisted,
            observations=observations,
            out_root=out_root,
            out_root_rel=out_root_rel,
        )
    except (
        CargoCompilerArtifactEvidenceError, CargoMetadataFactEvidenceError,
        OSError, LedgerError,
    ):
        facts = _blocked_cargo_facts(
            "candidate_cargo_fact_derivation_failed", raw_output_bound=True,
        )
    return persisted, checks, observations, statuses, facts


def settle_candidate_native_links(
    *, rust_project_ir: Mapping[str, Any],
    migration_manifest: Mapping[str, Any], artifact_root: Path,
    ledger_path: Path, out_root: Path, execution: Mapping[str, Any],
    checks: Mapping[str, Mapping[str, Any]],
    observations: Mapping[str, Mapping[str, Any]],
    symbol_candidate: Mapping[str, Any] | None, cargo_passed: bool,
) -> dict[str, Any]:
    requirements = rust_project_ir["native_link_requirements"]
    if not requirements:
        return project_native_link_settlement_status("not-required")
    if not cargo_passed:
        return _blocked_native(
            len(requirements), "native_link_candidate_cargo_failed",
        )
    try:
        state = recover_project_native_link_state(
            rust_project_ir, migration_manifest, artifact_root,
        )
        return settle_project_native_links(
            ledger_path=ledger_path,
            out_root=out_root,
            native_state=state,
            rust_project_ir=rust_project_ir,
            execution=execution,
            checks=checks,
            observations=observations,
            symbol_candidate=symbol_candidate,
        )
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, LedgerError):
        return _blocked_native(
            len(requirements), "native_link_settlement_evidence_unavailable",
        )


def candidate_verification_status(
    execution: Mapping[str, Any],
    observations: Mapping[str, Mapping[str, Any]],
    cargo: Mapping[str, str],
    native: Mapping[str, Any], native_required: bool,
    cargo_facts: Mapping[str, Any],
) -> str:
    if execution.get("status") == "blocked":
        return "blocked"
    if set(observations) != {"cargo-check", "cargo-test"} or any(
        item.get("outcome") != "executed" for item in observations.values()
    ):
        return "blocked"
    if "failed" in cargo.values() or execution.get("status") == "failed":
        return "failed"
    if set(cargo) != {"cargo-check", "cargo-test"} or any(
        value != "passed" for value in cargo.values()
    ):
        return "blocked"
    if cargo_facts.get("status") != "ready":
        return "blocked"
    if native_required and native.get("status") != "resolved":
        return "blocked"
    return "candidate-verified"


def candidate_claim_boundary(candidate_verified: bool) -> dict[str, Any]:
    return {
        "candidate_project_gate": candidate_verified,
        "final_project_gate": False,
        "updates_final_current": False,
        "writes_project_gate_records": False,
        "semantic_gate": False,
        "semantic_pass": False,
        "translation_coverage_numerator": 0,
    }


def _checks(execution: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    values = execution.get("checks")
    for item in values if isinstance(values, list) else []:
        command = item.get("command") if isinstance(item, Mapping) else None
        stage = command[1] if isinstance(command, list) and len(command) > 1 else None
        if stage not in {"check", "test"}:
            continue
        if stage in result:
            duplicates.add(str(stage))
        result[str(stage)] = dict(item)
    for stage in duplicates:
        result.pop(stage, None)
    return result


def _observations(
    execution: Mapping[str, Any], checks: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    project_input = execution.get("project_input_sha256")
    return {
        gate: project_cargo_observation(
            execution,
            checks.get(command),
            gate_kind=gate,
            expected_input_sha256=(
                project_input if isinstance(project_input, str) else None
            ),
        )
        for gate, command in (("cargo-check", "check"), ("cargo-test", "test"))
    }


def _blocked_native(count: int, reason: str) -> dict[str, Any]:
    return project_native_link_settlement_status(
        "blocked",
        context={"context_sha256": None, "requirement_count": count},
        reason_code=reason,
    )


def _blocked_cargo_facts(
    reason: str, *, raw_output_bound: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "blocked",
        "reason_code": reason,
        "raw_output_bound": raw_output_bound,
        "claim_boundary": {
            "interface_closure": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }


def _raw_outputs_bound(execution: Mapping[str, Any]) -> bool:
    checks = execution.get("checks")
    probes = execution.get("fact_probes")
    if not isinstance(checks, list) or not isinstance(probes, Mapping):
        return False
    values = [*checks, *probes.values()]
    executed = 0
    for check in values:
        if not isinstance(check, Mapping):
            return False
        if check.get("cargo_executed") is not True:
            continue
        executed += 1
        command = check.get("command")
        stage = command[1] if isinstance(command, list) and len(command) > 1 else None
        if stage not in {"metadata", "check", "test"}:
            return False
        for stream in ("stdout", "stderr"):
            try:
                validate_cargo_raw_output_reference(
                    check.get(f"{stream}_ref"),
                    gate_kind=f"cargo-{stage}", stream=stream,
                    expected_sha256=str(check.get(f"{stream}_sha256")),
                )
            except (TypeError, ValueError):
                return False
    return executed > 0


def _execution_block_reason(
    execution: Mapping[str, Any], raw_output_bound: bool,
) -> str:
    if not raw_output_bound:
        return "candidate_cargo_raw_output_unavailable"
    native = execution.get("native_link_trace")
    if isinstance(native, Mapping) and native.get("status") == "blocked":
        return "candidate_native_link_trace_blocked"
    if execution.get("status") == "failed":
        return "candidate_cargo_fact_source_failed"
    return "candidate_cargo_execution_blocked"


__all__ = [
    "bind_candidate_cargo_evidence", "candidate_claim_boundary",
    "candidate_verification_status", "settle_candidate_native_links",
]
