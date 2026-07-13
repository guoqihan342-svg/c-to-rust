from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .candidate_compile_bindings import verify_compile_bindings
from .candidate_compile_schema import (
    CHECK_KEYS,
    FIXED_CARGO_CHECK,
    cargo_check,
    derive_compile_status,
    verification_context,
)
from .gate_authority import candidate_authority
from .ledger_security import LedgerError


def compile_observation_payload(
    *, run_id: str, unit_id: str, candidate_artifact_id: str,
    candidate_sha256: str, candidate_set_sha256: str,
    candidate_source: Mapping[str, Any], run_contract: Mapping[str, Any],
    quarantine: Mapping[str, Any], execution: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(execution, Mapping):
        raise LedgerError("candidate compile execution schema is invalid")
    check = cargo_check(execution)
    sandbox = execution.get("sandbox")
    contract = sandbox.get("contract") if isinstance(sandbox, Mapping) else None
    if not isinstance(contract, Mapping):
        raise LedgerError("candidate compile sandbox contract is missing")
    source = _mapping(candidate_source, "candidate compile source is invalid")
    run = _mapping(run_contract, "candidate compile run contract is invalid")
    integration_manifest = _mapping(
        run.get("integration_manifest"),
        "candidate compile integration manifest reference is invalid",
    )
    detached = _mapping(quarantine, "candidate compile quarantine is invalid")
    quarantine_manifest = _mapping(
        detached.get("quarantine_manifest"),
        "candidate compile quarantine manifest reference is invalid",
    )
    generation_manifest = _mapping(
        detached.get("generation_manifest"),
        "candidate compile generation manifest reference is invalid",
    )
    payload = {
        "schema_version": 1,
        "artifact_kind": "host-candidate-compile-observation",
        "authority_id": candidate_authority("compile"),
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_sha256": candidate_sha256,
        "candidate_set_sha256": candidate_set_sha256,
        "candidate_source": source,
        "run_contract": {
            "context_sha256": run.get("context_sha256"),
            "dag_sha256": run.get("dag_sha256"),
            "integration_manifest": integration_manifest,
        },
        "quarantine": {
            "generation_sha256": detached.get("generation_sha256"),
            "quarantine_manifest": quarantine_manifest,
            "generation_manifest": generation_manifest,
            "rust_project_ir": _mapping(
                detached.get("rust_project_ir"),
                "candidate compile RustProjectIR reference is invalid",
            ),
            "rust_project_ir_sha256": detached.get("rust_project_ir_sha256"),
            "rust_project_interface_sha256": detached.get(
                "rust_project_interface_sha256"
            ),
            "rust_project_ir_scope": detached.get("rust_project_ir_scope"),
            "generator": detached.get("generator"),
        },
        "sandbox": {
            "contract": dict(contract),
            "contract_sha256": sandbox.get("contract_sha256"),
            "probe_receipt": sandbox.get("probe_receipt"),
            "probe_receipt_sha256": sandbox.get("probe_receipt_sha256"),
            "cleanup_verified": sandbox.get("cleanup_verified"),
        },
        "check": {key: check.get(key) for key in CHECK_KEYS},
        "project_state_unchanged": execution.get("project_state_unchanged"),
    }
    payload["verification_context_sha256"] = verification_context(payload)
    derive_compile_status(
        payload, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=candidate_sha256,
        candidate_set_sha256=candidate_set_sha256,
    )
    return payload


def _mapping(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LedgerError(message)
    return dict(value)


__all__ = [
    "FIXED_CARGO_CHECK", "compile_observation_payload", "derive_compile_status",
    "verify_compile_bindings",
]
