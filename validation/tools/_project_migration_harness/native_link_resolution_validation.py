from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256, validate_artifact_reference
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate


NATIVE_LINK_RESOLUTION_SCHEMA_VERSION = 1
NATIVE_LINK_RESOLUTION_KIND = "native-link-resolution-receipt"
NATIVE_LINK_HOST_EVIDENCE_KIND = "native-link-host-evidence"
NATIVE_LINK_RESOLUTION_ISSUER = "native-link-host-verifier-v1"

_REFERENCE_KEYS = {"path", "sha256", "size_bytes"}
_EVIDENCE_KEYS = {
    "schema_version", "artifact_kind", "issuer", "context_sha256",
    "candidate_sha256", "build_ir_semantic_sha256", "toolchain_abi_sha256",
    "project_input_sha256", "cargo", "requirements",
}
_RECEIPT_KEYS = {
    "schema_version", "artifact_kind", "issuer", "context_sha256",
    "candidate_sha256", "build_ir_semantic_sha256", "toolchain_abi_sha256",
    "project_input_sha256", "host_evidence_sha256", "cargo", "resolutions",
    "requirement_count", "status", "semantic_gate", "receipt_sha256",
}
_CARGO_KEYS = {"status", "exit_code", "stdout", "stderr"}
_REQUIREMENT_EVIDENCE_KEYS = {
    "requirement_id", "toolchain", "abi", "linker_trace", "actual_artifact",
}
_GATE_KEYS = {"status", "artifact"}
_ACTUAL_ARTIFACT_KEYS = {"status", "artifact", "portable_metadata"}
_PORTABLE_METADATA_KEYS = {
    "portable_name", "library_format", "file_name", "target_triple",
}
_GATE_STATUSES = {"passed", "failed", "blocked"}
_PORTABLE_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}\Z")
_TARGET_TRIPLE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\Z")


def validate_native_link_host_evidence(
    value: Mapping[str, Any], context: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    evidence = _json_object(
        value, _EVIDENCE_KEYS, "native_link_host_evidence_schema_invalid",
    )
    _validate_identity(
        evidence, NATIVE_LINK_HOST_EVIDENCE_KIND, context, candidate,
        "native_link_host_evidence_binding_invalid",
    )
    if not is_sha256(evidence.get("project_input_sha256")):
        raise ValueError("native_link_host_evidence_project_input_invalid")
    evidence["cargo"] = _validate_cargo(evidence.get("cargo"))
    raw_requirements = evidence.get("requirements")
    if not isinstance(raw_requirements, list):
        raise ValueError("native_link_host_evidence_coverage_invalid")
    expected = {item["requirement_id"]: item for item in context["requirements"]}
    normalized = []
    for raw in raw_requirements:
        identifier = raw.get("requirement_id") if isinstance(raw, Mapping) else None
        requirement = expected.get(identifier)
        if requirement is None:
            raise ValueError("native_link_host_evidence_coverage_invalid")
        normalized.append(_validate_requirement_evidence(raw, requirement))
    _validate_coverage(normalized, expected, "native_link_host_evidence")
    evidence["requirements"] = normalized
    return evidence


def validate_native_link_resolution_receipt(
    value: Mapping[str, Any], context: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    receipt = _json_object(
        value, _RECEIPT_KEYS, "native_link_resolution_schema_invalid",
    )
    _validate_identity(
        receipt, NATIVE_LINK_RESOLUTION_KIND, context, candidate,
        "native_link_resolution_binding_drift",
    )
    if not is_sha256(receipt.get("project_input_sha256")):
        raise ValueError("native_link_resolution_project_input_invalid")
    cargo = _validate_cargo(receipt.get("cargo"))
    raw_resolutions = receipt.get("resolutions")
    if not isinstance(raw_resolutions, list):
        raise ValueError("native_link_resolution_coverage_invalid")
    requirements = {item["requirement_id"]: item for item in context["requirements"]}
    normalized = []
    for raw in raw_resolutions:
        expected_keys = _REQUIREMENT_EVIDENCE_KEYS | {"status"}
        if not isinstance(raw, Mapping) or set(raw) != expected_keys:
            raise ValueError("native_link_resolution_requirement_schema_invalid")
        evidence_item = {key: raw[key] for key in _REQUIREMENT_EVIDENCE_KEYS}
        requirement = requirements.get(evidence_item.get("requirement_id"))
        if requirement is None:
            raise ValueError("native_link_resolution_coverage_invalid")
        item = _validate_requirement_evidence(evidence_item, requirement)
        expected_status = _requirement_status(item, cargo["status"])
        if raw.get("status") != expected_status:
            raise ValueError("native_link_resolution_status_not_host_derived")
        normalized.append({**item, "status": expected_status})
    _validate_coverage(normalized, requirements, "native_link_resolution")
    if receipt.get("requirement_count") != len(requirements):
        raise ValueError("native_link_resolution_coverage_invalid")
    overall = derived_resolution_status([item["status"] for item in normalized])
    if receipt.get("status") != overall:
        raise ValueError("native_link_resolution_status_not_host_derived")
    if receipt.get("semantic_gate") is not False:
        raise ValueError("native_link_resolution_semantic_gate_invalid")
    evidence = _evidence_projection(receipt, normalized, cargo)
    if content_sha256(evidence) != receipt.get("host_evidence_sha256"):
        raise ValueError("native_link_resolution_host_evidence_sha256_drift")
    if _receipt_sha256(receipt) != receipt.get("receipt_sha256"):
        raise ValueError("native_link_resolution_receipt_sha256_drift")
    return receipt


def derived_resolution_status(statuses: list[str]) -> str:
    if "failed" in statuses or "rejected" in statuses:
        return "rejected"
    if "blocked" in statuses:
        return "blocked"
    return "resolved"


def _validate_identity(
    value: Mapping[str, Any], artifact_kind: str,
    context: Mapping[str, Any], candidate: Mapping[str, Any], code: str,
) -> None:
    expected = {
        "schema_version": NATIVE_LINK_RESOLUTION_SCHEMA_VERSION,
        "artifact_kind": artifact_kind,
        "issuer": NATIVE_LINK_RESOLUTION_ISSUER,
        "context_sha256": context["context_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "build_ir_semantic_sha256": context["build_ir_binding"]["semantic_sha256"],
        "toolchain_abi_sha256": context["build_ir_binding"]["toolchain_abi_sha256"],
    }
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        raise ValueError(code)


def _validate_requirement_evidence(
    value: Any, requirement: Mapping[str, Any],
) -> dict[str, Any]:
    item = _json_object(
        value, _REQUIREMENT_EVIDENCE_KEYS,
        "native_link_requirement_evidence_schema_invalid",
    )
    if item.get("requirement_id") != requirement["requirement_id"]:
        raise ValueError("native_link_requirement_evidence_identity_invalid")
    for field in ("toolchain", "abi", "linker_trace"):
        item[field] = _validate_gate(item.get(field), field)
    actual = _json_object(
        item.get("actual_artifact"), _ACTUAL_ARTIFACT_KEYS,
        "native_link_actual_artifact_schema_invalid",
    )
    status = _gate_status(actual.get("status"), "actual_artifact")
    if status == "passed":
        actual["artifact"] = _reference(actual.get("artifact"), "actual_artifact")
        actual["portable_metadata"] = _portable_metadata(
            actual.get("portable_metadata"), requirement,
        )
    elif actual.get("artifact") is not None or actual.get("portable_metadata") is not None:
        raise ValueError("native_link_actual_artifact_unverified_claim")
    item["actual_artifact"] = actual
    return item


def _validate_cargo(value: Any) -> dict[str, Any]:
    cargo = _json_object(
        value, _CARGO_KEYS, "native_link_cargo_evidence_schema_invalid",
    )
    status = _gate_status(cargo.get("status"), "cargo")
    cargo["stdout"] = _reference(cargo.get("stdout"), "cargo_stdout")
    cargo["stderr"] = _reference(cargo.get("stderr"), "cargo_stderr")
    code = cargo.get("exit_code")
    if (
        (status == "passed" and (type(code) is not int or code != 0))
        or (status == "failed" and (type(code) is not int or code == 0))
        or (status == "blocked" and code is not None)
    ):
        raise ValueError("native_link_cargo_status_invalid")
    return cargo


def _validate_gate(value: Any, field: str) -> dict[str, Any]:
    gate = _json_object(
        value, _GATE_KEYS, f"native_link_{field}_evidence_schema_invalid",
    )
    _gate_status(gate.get("status"), field)
    gate["artifact"] = _reference(gate.get("artifact"), field)
    return gate


def _portable_metadata(value: Any, requirement: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _json_object(
        value, _PORTABLE_METADATA_KEYS, "native_link_portable_metadata_schema_invalid",
    )
    file_name, target = metadata.get("file_name"), metadata.get("target_triple")
    if (
        metadata.get("portable_name") != requirement["portable_name"]
        or metadata.get("library_format") != requirement["library_format"]
        or not isinstance(file_name, str) or _PORTABLE_VALUE.fullmatch(file_name) is None
        or file_name.startswith(("-", ".")) or ".." in file_name
        or not isinstance(target, str) or _TARGET_TRIPLE.fullmatch(target) is None
    ):
        raise ValueError("native_link_portable_metadata_invalid")
    return metadata


def _validate_coverage(
    values: list[dict[str, Any]], expected: Mapping[str, Any], prefix: str,
) -> None:
    identifiers = [item["requirement_id"] for item in values]
    if (
        identifiers != sorted(identifiers)
        or len(identifiers) != len(set(identifiers))
        or set(identifiers) != set(expected)
    ):
        raise ValueError(f"{prefix}_coverage_invalid")


def _requirement_status(item: Mapping[str, Any], cargo_status: str) -> str:
    return derived_resolution_status([cargo_status] + [
        item[field]["status"]
        for field in ("toolchain", "abi", "linker_trace", "actual_artifact")
    ])


def _reference(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REFERENCE_KEYS:
        raise ValueError(f"native_link_{field}_reference_invalid")
    validate_artifact_reference(value, f"native_link_{field}_reference_invalid")
    return dict(value)


def _gate_status(value: Any, field: str) -> str:
    if value not in _GATE_STATUSES:
        raise ValueError(f"native_link_{field}_status_invalid")
    return str(value)


def _evidence_projection(
    receipt: Mapping[str, Any], resolutions: list[dict[str, Any]],
    cargo: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": NATIVE_LINK_RESOLUTION_SCHEMA_VERSION,
        "artifact_kind": NATIVE_LINK_HOST_EVIDENCE_KIND,
        "issuer": NATIVE_LINK_RESOLUTION_ISSUER,
        "context_sha256": receipt["context_sha256"],
        "candidate_sha256": receipt["candidate_sha256"],
        "build_ir_semantic_sha256": receipt["build_ir_semantic_sha256"],
        "toolchain_abi_sha256": receipt["toolchain_abi_sha256"],
        "project_input_sha256": receipt["project_input_sha256"],
        "cargo": cargo,
        "requirements": [
            {key: item[key] for key in _REQUIREMENT_EVIDENCE_KEYS}
            for item in resolutions
        ],
    }


def _receipt_sha256(value: Mapping[str, Any]) -> str:
    return content_sha256({
        key: item for key, item in value.items() if key != "receipt_sha256"
    })


def _json_object(value: Any, keys: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(code)
    try:
        result = json.loads(canonical_json_bytes(value).decode("utf-8"))
    except (TypeError, ValueError) as error:
        raise ValueError(code) from error
    return result


__all__ = [
    "NATIVE_LINK_HOST_EVIDENCE_KIND", "NATIVE_LINK_RESOLUTION_ISSUER",
    "NATIVE_LINK_RESOLUTION_KIND", "NATIVE_LINK_RESOLUTION_SCHEMA_VERSION",
    "derived_resolution_status", "validate_native_link_host_evidence",
    "validate_native_link_resolution_receipt",
]
