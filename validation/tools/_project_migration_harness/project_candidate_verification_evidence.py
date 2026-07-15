from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .cargo_raw_output_evidence import persist_captured_cargo_outputs
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
    dict[str, dict[str, Any]], dict[str, str],
]:
    persisted = persist_captured_cargo_outputs(
        persist_captured_native_link_trace(
            execution, out_root=out_root, required=native_required,
        ),
        out_root=out_root,
        out_root_rel=out_root_rel,
    )
    checks = _checks(persisted)
    observations = _observations(persisted, checks)
    statuses = {
        gate: derive_project_cargo_status(gate, observation)
        for gate, observation in observations.items()
    }
    return persisted, checks, observations, statuses


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


__all__ = [
    "bind_candidate_cargo_evidence", "candidate_claim_boundary",
    "candidate_verification_status", "settle_candidate_native_links",
]
