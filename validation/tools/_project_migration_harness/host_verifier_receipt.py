from __future__ import annotations

"""Failure/block envelopes with no coordinator, gate, or ledger authority."""

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .bounded_artifact_io import BoundedArtifactIOError, read_bounded_artifact
from .gate_evidence import MAX_GATE_EVIDENCE_BYTES
from .host_verifier_contract import (
    HOST_VERIFIER_ARTIFACT_KIND, HOST_VERIFIER_ISSUER,
    HOST_VERIFIER_SCHEMA_VERSION, HOST_VERIFIER_STATUSES,
    HOST_VERIFIER_TERMINATIONS, HostVerifierEnvelopeBindings, bounded_text,
    command_value, content_addressed_json_reference, gate_kind_value,
    sha256_value, verification_plan_payload,
)
from .host_verifier_raw_evidence import (
    read_host_verifier_raw_evidence,
    validate_host_verifier_raw_evidence_reference,
)
from .sandbox_contract import canonical_sha256


_RECEIPT_KEYS = {
    "schema_version", "artifact_kind", "gate_kind",
    "run_capability_sha256", "issuer", "nonce", "run_id",
    "cohort_sha256", "generation_sha256", "rust_project_ir_sha256",
    "rust_project_interface_sha256", "verification_plan",
    "verification_plan_sha256", "toolchain_sha256", "sandbox_receipt",
    "stdout_ref", "stderr_ref", "argv", "exit_code", "termination",
    "status", "semantic_gate", "translation_coverage_numerator",
    "receipt_sha256",
}


def build_host_verifier_receipt(
    bindings: HostVerifierEnvelopeBindings, *,
    stdout_ref: Mapping[str, Any], stderr_ref: Mapping[str, Any],
    exit_code: int | None, termination: str, status: str,
) -> dict[str, Any]:
    if type(bindings) is not HostVerifierEnvelopeBindings:
        raise TypeError("host verifier envelope bindings are required")
    stdout = validate_host_verifier_raw_evidence_reference(
        stdout_ref, gate_kind=bindings.gate_kind, stream="stdout",
        evidence_root=bindings.evidence_root,
    )
    stderr = validate_host_verifier_raw_evidence_reference(
        stderr_ref, gate_kind=bindings.gate_kind, stream="stderr",
        evidence_root=bindings.evidence_root,
    )
    payload = {
        "schema_version": HOST_VERIFIER_SCHEMA_VERSION,
        "artifact_kind": HOST_VERIFIER_ARTIFACT_KIND,
        "gate_kind": bindings.gate_kind,
        "run_capability_sha256": bindings.run_capability_sha256,
        "issuer": HOST_VERIFIER_ISSUER,
        "nonce": bindings.nonce,
        "run_id": bindings.run_id,
        "cohort_sha256": bindings.cohort_sha256,
        "generation_sha256": bindings.generation_sha256,
        "rust_project_ir_sha256": bindings.rust_project_ir_sha256,
        "rust_project_interface_sha256": (
            bindings.rust_project_interface_sha256
        ),
        "verification_plan": bindings.verification_plan.payload(),
        "verification_plan_sha256": bindings.verification_plan.sha256,
        "toolchain_sha256": bindings.toolchain_sha256,
        "sandbox_receipt": dict(bindings.sandbox_receipt),
        "stdout_ref": stdout,
        "stderr_ref": stderr,
        "argv": list(bindings.verification_plan.command),
        "exit_code": exit_code,
        "termination": termination,
        "status": status,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    receipt = {**payload, "receipt_sha256": content_sha256(payload)}
    return validate_host_verifier_receipt(receipt, bindings)


def validate_host_verifier_receipt_schema(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RECEIPT_KEYS:
        raise ValueError("host verifier receipt fields are invalid")
    try:
        receipt = json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (TypeError, ValueError) as error:
        raise ValueError("host verifier receipt is not canonical JSON") from error
    if (
        receipt.get("schema_version") != HOST_VERIFIER_SCHEMA_VERSION
        or receipt.get("artifact_kind") != HOST_VERIFIER_ARTIFACT_KIND
        or receipt.get("issuer") != HOST_VERIFIER_ISSUER
    ):
        raise ValueError("host verifier receipt identity is invalid")
    gate_kind = gate_kind_value(receipt.get("gate_kind"))
    bounded_text(receipt.get("run_id"), "run_id")
    for field in (
        "run_capability_sha256", "nonce", "cohort_sha256",
        "generation_sha256", "rust_project_ir_sha256",
        "rust_project_interface_sha256", "verification_plan_sha256",
        "toolchain_sha256", "receipt_sha256",
    ):
        sha256_value(receipt.get(field), field)
    plan = verification_plan_payload(receipt.get("verification_plan"))
    if (
        plan["purpose"] != gate_kind
        or plan["input_sha256"] != receipt["generation_sha256"]
        or receipt["verification_plan_sha256"] != canonical_sha256(plan)
    ):
        raise ValueError("host verifier VerificationPlan binding drifted")
    content_addressed_json_reference(receipt.get("sandbox_receipt"))
    for stream in ("stdout", "stderr"):
        validate_host_verifier_raw_evidence_reference(
            receipt.get(f"{stream}_ref"), gate_kind=gate_kind, stream=stream,
        )
    if command_value(receipt.get("argv")) != plan["command"]:
        raise ValueError("host verifier fixed argv binding drifted")
    if (
        receipt.get("status") not in HOST_VERIFIER_STATUSES
        or receipt.get("semantic_gate") is not False
        or type(receipt.get("translation_coverage_numerator")) is not int
        or receipt.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("host verifier receipt claim boundary is invalid")
    _execution_result(receipt)
    if host_verifier_receipt_sha256(receipt) != receipt["receipt_sha256"]:
        raise ValueError("host verifier receipt content binding drifted")
    return receipt


def validate_host_verifier_receipt(
    value: Any, bindings: HostVerifierEnvelopeBindings,
) -> dict[str, Any]:
    if type(bindings) is not HostVerifierEnvelopeBindings:
        raise TypeError("host verifier envelope bindings are required")
    receipt = validate_host_verifier_receipt_schema(value)
    expected = {
        "gate_kind": bindings.gate_kind,
        "run_capability_sha256": bindings.run_capability_sha256,
        "issuer": HOST_VERIFIER_ISSUER,
        "nonce": bindings.nonce,
        "run_id": bindings.run_id,
        "cohort_sha256": bindings.cohort_sha256,
        "generation_sha256": bindings.generation_sha256,
        "rust_project_ir_sha256": bindings.rust_project_ir_sha256,
        "rust_project_interface_sha256": (
            bindings.rust_project_interface_sha256
        ),
        "verification_plan": bindings.verification_plan.payload(),
        "verification_plan_sha256": bindings.verification_plan.sha256,
        "toolchain_sha256": bindings.toolchain_sha256,
        "sandbox_receipt": dict(bindings.sandbox_receipt),
        "argv": list(bindings.verification_plan.command),
    }
    changed = next(
        (field for field, expected_value in expected.items()
         if receipt.get(field) != expected_value),
        None,
    )
    if changed is not None:
        raise ValueError(f"host verifier receipt stale binding: {changed}")
    for stream in ("stdout", "stderr"):
        validate_host_verifier_raw_evidence_reference(
            receipt[f"{stream}_ref"], gate_kind=bindings.gate_kind,
            stream=stream, evidence_root=bindings.evidence_root,
        )
    return receipt


def reopen_and_validate_host_verifier_receipt(
    repository_root: Path, value: Any,
    bindings: HostVerifierEnvelopeBindings,
) -> dict[str, Any]:
    receipt = validate_host_verifier_receipt(value, bindings)
    _reopen_json_reference(repository_root, receipt["sandbox_receipt"])
    for stream in ("stdout", "stderr"):
        read_host_verifier_raw_evidence(
            repository_root, receipt[f"{stream}_ref"],
            gate_kind=bindings.gate_kind, stream=stream,
            evidence_root=bindings.evidence_root,
        )
    return receipt


def host_verifier_receipt_sha256(value: Mapping[str, Any]) -> str:
    projection = {
        key: item for key, item in value.items() if key != "receipt_sha256"
    }
    return content_sha256(projection)


def _execution_result(receipt: Mapping[str, Any]) -> None:
    termination = receipt.get("termination")
    exit_code = receipt.get("exit_code")
    status = receipt.get("status")
    if termination not in HOST_VERIFIER_TERMINATIONS:
        raise ValueError("host verifier termination is invalid")
    if status == "failed":
        if termination != "exited" or type(exit_code) is not int or exit_code == 0:
            raise ValueError(
                "host verifier failed status/termination/exit code is inconsistent"
            )
    elif (
        status != "blocked" or termination == "exited" or exit_code is not None
    ):
        raise ValueError(
            "host verifier blocked status/termination/exit code is inconsistent"
        )


def _reopen_json_reference(
    repository_root: Path, value: Mapping[str, Any],
) -> dict[str, Any]:
    reference = content_addressed_json_reference(value)
    try:
        root = Path(repository_root).resolve(strict=True)
    except OSError as error:
        raise ValueError("host verifier repository root is unavailable") from error
    if not root.is_dir():
        raise ValueError("host verifier repository root is invalid")
    target = root.joinpath(*PurePosixPath(reference["path"]).parts)
    try:
        data = read_bounded_artifact(root, target, MAX_GATE_EVIDENCE_BYTES)
    except BoundedArtifactIOError as error:
        raise ValueError("host verifier sandbox receipt is not safely readable") from error
    if (
        len(data) != reference["size_bytes"]
        or hashlib.sha256(data).hexdigest() != reference["sha256"]
    ):
        raise ValueError("host verifier sandbox receipt content binding drifted")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("host verifier sandbox receipt is invalid JSON") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        raise ValueError("host verifier sandbox receipt is not canonical JSON")
    return payload


__all__ = [
    "build_host_verifier_receipt", "host_verifier_receipt_sha256",
    "reopen_and_validate_host_verifier_receipt",
    "validate_host_verifier_receipt", "validate_host_verifier_receipt_schema",
]
