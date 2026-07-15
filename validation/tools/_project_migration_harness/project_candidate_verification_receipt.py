from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .build_ir import is_sha256
from .gate_evidence import (
    read_content_addressed_json,
    require_content_addressed_reference,
)
from .ledger_security import LedgerError
from .project_candidate_domain import (
    candidate_domain_context_sha256,
    candidate_verification_context,
)
from .project_candidate_verification_evidence import (
    candidate_claim_boundary,
    candidate_verification_status,
)
from .project_cargo_evidence import (
    derive_project_cargo_status,
    verify_project_cargo_raw_outputs,
)
from .project_native_link_settlement_binding import (
    validate_project_native_link_settlement_binding,
)


_KEYS = {
    "schema_version", "artifact_kind", "status", "run_id",
    "run_context_sha256", "dag_sha256", "integration_manifest",
    "candidate_set_sha256", "candidate_set_manifest_sha256",
    "rust_project_ir_sha256", "rust_project_interface_sha256",
    "rust_project_binding_sha256", "candidate_domain_context_sha256",
    "build_ir_verification", "materialization", "execution",
    "cargo_observations", "cargo_statuses", "native_link_settlement",
    "state_effects", "claim_boundary", "verification_context_sha256",
}
_HASH_FIELDS = (
    "run_context_sha256", "dag_sha256", "candidate_set_sha256",
    "candidate_set_manifest_sha256", "rust_project_ir_sha256",
    "rust_project_interface_sha256", "rust_project_binding_sha256",
    "candidate_domain_context_sha256", "verification_context_sha256",
)
_STATE_EFFECTS = {
    "final_current_updated": False,
    "project_gate_records_written": 0,
    "candidate_only": True,
}


def validate_candidate_project_verification(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _KEYS:
        raise ValueError("candidate_project_verification_schema_invalid")
    receipt = dict(value)
    if (
        receipt.get("schema_version") != 1
        or receipt.get("artifact_kind") != "candidate-project-verification"
        or receipt.get("status") not in {"candidate-verified", "failed", "blocked"}
        or not isinstance(receipt.get("run_id"), str)
        or not receipt["run_id"]
        or any(not is_sha256(receipt.get(field)) for field in _HASH_FIELDS)
        or not _artifact_reference(receipt.get("integration_manifest"))
        or receipt.get("state_effects") != _STATE_EFFECTS
    ):
        raise ValueError("candidate_project_verification_identity_invalid")
    if candidate_domain_context_sha256(receipt) != receipt[
        "candidate_domain_context_sha256"
    ]:
        raise ValueError("candidate_project_domain_context_drifted")
    build_ir = _mapping(receipt, "build_ir_verification")
    materialization = _materialization(receipt)
    execution = _mapping(receipt, "execution")
    observations = _observations(receipt)
    statuses = {
        gate: derive_project_cargo_status(gate, observation)
        for gate, observation in observations.items()
    }
    if receipt.get("cargo_statuses") != statuses:
        raise ValueError("candidate_project_cargo_status_drifted")
    native = validate_project_native_link_settlement_binding(
        receipt.get("native_link_settlement")
    )
    native_required = native["requirement_count"] > 0
    expected_status = candidate_verification_status(
        execution, observations, statuses, native, native_required,
    )
    if receipt["status"] != expected_status:
        raise ValueError("candidate_project_verification_status_drifted")
    expected_claim = candidate_claim_boundary(
        expected_status == "candidate-verified"
    )
    if receipt.get("claim_boundary") != expected_claim:
        raise ValueError("candidate_project_verification_claim_invalid")
    expected_context = candidate_verification_context(
        receipt, build_ir, materialization, execution, observations, native,
    )
    if receipt["verification_context_sha256"] != expected_context:
        raise ValueError("candidate_project_verification_context_drifted")
    return receipt


def reopen_candidate_project_verification(
    ledger_path: Path, reference: Mapping[str, Any], *, run_id: str,
    candidate_set_sha256: str, rust_project_ir_sha256: str,
    rust_project_interface_sha256: str,
) -> dict[str, Any]:
    require_content_addressed_reference(reference)
    payload = read_content_addressed_json(
        Path(ledger_path), str(reference["path"]), str(reference["sha256"]),
    )
    if len(canonical_json_bytes(payload)) != reference["size_bytes"]:
        raise LedgerError("candidate project verification receipt size drifted")
    try:
        receipt = validate_candidate_project_verification(payload)
    except (TypeError, ValueError, LedgerError) as error:
        raise LedgerError("candidate project verification receipt is invalid") from error
    expected = {
        "run_id": run_id,
        "candidate_set_sha256": candidate_set_sha256,
        "rust_project_ir_sha256": rust_project_ir_sha256,
        "rust_project_interface_sha256": rust_project_interface_sha256,
    }
    if any(receipt.get(key) != item for key, item in expected.items()):
        raise LedgerError("candidate project verification receipt binding drifted")
    for gate, observation in receipt["cargo_observations"].items():
        verify_project_cargo_raw_outputs(
            Path(ledger_path), observation, gate_kind=gate,
        )
    return receipt


def _materialization(receipt: Mapping[str, Any]) -> dict[str, Any]:
    value = _mapping(receipt, "materialization")
    generation = value.get("generation")
    candidate_set = value.get("candidate_set")
    generation_manifest = value.get("generation_manifest_ref")
    valid = (
        value.get("status") == "materialized"
        and value.get("last_good_updated") is False
        and value.get("cargo_executed") is False
        and value.get("immutable") is True
        and value.get("rust_project_ir_scope") == "full-project"
        and value.get("rust_project_ir_sha256") == receipt["rust_project_ir_sha256"]
        and value.get("rust_project_interface_sha256")
        == receipt["rust_project_interface_sha256"]
        and isinstance(candidate_set, Mapping)
        and candidate_set.get("sha256") == receipt["candidate_set_sha256"]
        and isinstance(generation, Mapping)
        and generation.get("immutable") is True
        and is_sha256(generation.get("sha256"))
        and _artifact_reference(generation_manifest)
        and generation_manifest.get("sha256") == generation.get("sha256")
    )
    if not valid:
        raise ValueError("candidate_project_materialization_invalid")
    return value


def _observations(receipt: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    value = receipt.get("cargo_observations")
    if not isinstance(value, Mapping) or set(value) != {"cargo-check", "cargo-test"}:
        raise ValueError("candidate_project_cargo_observations_invalid")
    return {
        gate: dict(_mapping(value, gate)) for gate in ("cargo-check", "cargo-test")
    }


def _mapping(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"candidate_project_{key}_invalid")
    return dict(item)


def _artifact_reference(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "sha256", "size_bytes"}
        and isinstance(value.get("path"), str) and bool(value["path"])
        and is_sha256(value.get("sha256"))
        and type(value.get("size_bytes")) is int and value["size_bytes"] > 0
    )


__all__ = [
    "reopen_candidate_project_verification",
    "validate_candidate_project_verification",
]
