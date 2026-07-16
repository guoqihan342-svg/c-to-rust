from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .gate_authority import candidate_authority
from .ledger_security import LedgerError
from .sandbox_contract import canonical_sha256
from .sandbox_execution_schema import (
    CHECK_EVIDENCE_KEYS as CHECK_KEYS,
    LEGACY_CHECK_EVIDENCE_KEYS as LEGACY_CHECK_KEYS,
    SANDBOX_EVIDENCE_KEYS as SANDBOX_KEYS,
    validate_sandbox_execution_evidence,
)
from .rust_project_cargo import SUPPORTED_GENERATORS


SHA256 = re.compile(r"^[0-9a-f]{64}$")
PAYLOAD_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id", "unit_id",
    "candidate_artifact_id", "candidate_sha256", "candidate_set_sha256",
    "candidate_source", "run_contract", "quarantine",
    "verification_context_sha256", "sandbox", "check",
    "project_state_unchanged",
}
REFERENCE_KEYS = {"path", "sha256", "size_bytes"}
RUN_CONTRACT_KEYS = {"context_sha256", "dag_sha256", "integration_manifest"}
QUARANTINE_KEYS = {
    "generation_sha256", "quarantine_manifest", "generation_manifest",
    "rust_project_ir", "rust_project_ir_sha256",
    "rust_project_interface_sha256", "rust_project_ir_scope", "generator",
}
FIXED_CARGO_CHECK = [
    "cargo", "check", "--all-targets", "--all-features", "--offline", "--locked",
    "--message-format=json",
]


def derive_compile_status(
    payload: Mapping[str, Any], *, run_id: str, unit_id: str,
    candidate_artifact_id: str, candidate_sha256: str,
    candidate_set_sha256: str,
) -> str:
    if not isinstance(payload, Mapping) or set(payload) != PAYLOAD_KEYS:
        raise LedgerError("candidate compile observation schema is invalid")
    expected = {
        "schema_version": 1,
        "artifact_kind": "host-candidate-compile-observation",
        "authority_id": candidate_authority("compile"),
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_sha256": candidate_sha256,
        "candidate_set_sha256": candidate_set_sha256,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise LedgerError("candidate compile observation binding is invalid")
    if not all(is_sha(payload.get(key)) for key in (
        "candidate_sha256", "candidate_set_sha256", "verification_context_sha256",
    )):
        raise LedgerError("candidate compile observation hash is invalid")
    sandbox = payload.get("sandbox")
    check = payload.get("check")
    candidate_source = payload.get("candidate_source")
    run_contract = payload.get("run_contract")
    quarantine = payload.get("quarantine")
    if (
        not isinstance(sandbox, Mapping) or set(sandbox) != SANDBOX_KEYS
        or not isinstance(check, Mapping)
        or frozenset(check) not in {
            frozenset(LEGACY_CHECK_KEYS), frozenset(CHECK_KEYS),
        }
        or not reference(candidate_source)
        or not isinstance(run_contract, Mapping) or set(run_contract) != RUN_CONTRACT_KEYS
        or not reference(run_contract.get("integration_manifest"))
        or not isinstance(quarantine, Mapping) or set(quarantine) != QUARANTINE_KEYS
        or not reference(quarantine.get("quarantine_manifest"))
        or not reference(quarantine.get("generation_manifest"))
        or not reference(quarantine.get("rust_project_ir"))
        or not is_sha(quarantine.get("generation_sha256"))
        or not is_sha(quarantine.get("rust_project_ir_sha256"))
        or not is_sha(quarantine.get("rust_project_interface_sha256"))
        or quarantine.get("rust_project_ir_scope") not in {
            "full-project", "verification-cohort",
        }
        or quarantine.get("generator") not in SUPPORTED_GENERATORS
        or quarantine["generation_manifest"].get("sha256")
        != quarantine.get("generation_sha256")
        or not is_sha(run_contract.get("context_sha256"))
        or not is_sha(run_contract.get("dag_sha256"))
        or payload.get("verification_context_sha256") != verification_context(payload)
    ):
        raise LedgerError("candidate compile execution schema is invalid")
    try:
        verified = validate_sandbox_execution_evidence(
            sandbox,
            check,
            expected_command=FIXED_CARGO_CHECK,
            expected_input_sha256=str(quarantine["generation_sha256"]),
            expected_purpose="cargo-check",
        )
    except (TypeError, ValueError) as error:
        raise LedgerError(
            "candidate compile execution was not proven in the fixed sandbox"
        ) from error
    if payload.get("project_state_unchanged") is not True:
        raise LedgerError("candidate compile managed generation changed")
    return verified.status


def cargo_check(execution: Mapping[str, Any]) -> Mapping[str, Any]:
    checks = execution.get("checks")
    if isinstance(checks, (str, bytes)) or not isinstance(checks, Sequence):
        raise LedgerError("candidate compile execution has no unique cargo check")
    matches = [
        item for item in checks
        if isinstance(item, Mapping)
        and isinstance(item.get("command"), list)
        and item["command"] == FIXED_CARGO_CHECK
    ]
    if len(matches) != 1:
        raise LedgerError("candidate compile execution has no unique cargo check")
    return matches[0]


def verification_context(payload: Mapping[str, Any]) -> str:
    check = payload.get("check")
    command = check.get("command") if isinstance(check, Mapping) else None
    return canonical_sha256({
        "candidate_artifact_id": payload.get("candidate_artifact_id"),
        "candidate_sha256": payload.get("candidate_sha256"),
        "candidate_set_sha256": payload.get("candidate_set_sha256"),
        "candidate_source": payload.get("candidate_source"),
        "run_contract": payload.get("run_contract"),
        "quarantine": payload.get("quarantine"),
        "sandbox": payload.get("sandbox"),
        "command": command,
    })


def is_sha(value: Any) -> bool:
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def reference(value: Any) -> bool:
    return (
        isinstance(value, Mapping) and set(value) == REFERENCE_KEYS
        and isinstance(value.get("path"), str) and bool(value.get("path"))
        and is_sha(value.get("sha256"))
        and positive_int(value.get("size_bytes"))
    )
