from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .gate_authority import project_authority, require_portable_id
from .gate_evidence import (
    require_content_addressed_reference, require_host_raw_reference,
)
from .ledger_security import assert_no_secrets
from .project_diagnostic_shape import validate_project_diagnostic
from .runtime_security import assert_model_payload_safe
from .sandbox_execution_schema import is_sha256


PROJECT_DIAGNOSTIC_FAMILIES = frozenset({
    "compile", "link", "initialization", "feature", "abi",
})
PROJECT_DIAGNOSTIC_GATE_FAMILIES = {
    "cargo-check": frozenset({
        "compile", "link", "initialization", "feature", "abi",
    }),
    "cargo-test": frozenset({
        "compile", "link", "initialization", "feature", "abi",
    }),
    "integration": frozenset({"link", "initialization", "feature"}),
    "unsafe-alias-abi": frozenset({"abi"}),
}
MAX_PROJECT_DIAGNOSTIC_INTAKES = 16
MAX_PROJECT_DIAGNOSTICS_PER_INTAKE = 64
_INTAKE_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "run_id",
    "gate_kind", "gate_record_id", "gate_epoch", "gate_status",
    "verifier_id", "candidate_set_sha256", "rust_project_ir_sha256",
    "rust_project_interface_sha256", "project_input_sha256",
    "raw_observation", "verifier_receipt", "diagnostics", "claim_boundary",
}
_DETAIL_KEYS = {
    "family", "source_code", "stage", "message", "location",
    "project_diagnostic",
}
_LOCATION_KEYS = {"file", "line", "column"}
_CLAIM_BOUNDARY = {
    "candidate_only": True,
    "environment_failure_admitted": False,
    "semantic_gate": False,
    "semantic_pass": False,
    "translation_coverage_numerator": 0,
}


def project_diagnostic_intake_payload(
    *, run_id: str, gate_kind: str, gate_record_id: str, gate_epoch: int,
    candidate_set_sha256: str, rust_project_ir_sha256: str,
    rust_project_interface_sha256: str, project_input_sha256: str,
    raw_observation: Mapping[str, Any], verifier_receipt: Mapping[str, Any],
    diagnostics: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    verifier_id = project_authority(gate_kind)
    payload = {
        "schema_version": 1,
        "artifact_kind": "host-project-diagnostic-intake",
        "authority_id": "host.project-diagnostic-intake.v1",
        "run_id": require_portable_id(run_id, "run_id"),
        "gate_kind": gate_kind,
        "gate_record_id": require_portable_id(gate_record_id, "gate_record_id"),
        "gate_epoch": _positive_int(gate_epoch, "gate_epoch"),
        "gate_status": "failed",
        "verifier_id": verifier_id,
        "candidate_set_sha256": _sha(candidate_set_sha256, "candidate set"),
        "rust_project_ir_sha256": _sha(
            rust_project_ir_sha256, "RustProjectIR",
        ),
        "rust_project_interface_sha256": _sha(
            rust_project_interface_sha256, "RustProjectIR interface",
        ),
        "project_input_sha256": _sha(project_input_sha256, "project input"),
        "raw_observation": _reference(raw_observation, gate_kind, raw=True),
        "verifier_receipt": _reference(
            verifier_receipt, gate_kind, raw=False,
        ),
        "diagnostics": _diagnostics(diagnostics, gate_kind),
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    assert_no_secrets(payload, "project_diagnostic_intake")
    return payload


def validate_project_diagnostic_intake(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _INTAKE_KEYS:
        raise ValueError("project diagnostic intake fields are invalid")
    result = json.loads(canonical_json_bytes(value).decode("utf-8"))
    expected = project_diagnostic_intake_payload(
        run_id=result["run_id"], gate_kind=result["gate_kind"],
        gate_record_id=result["gate_record_id"], gate_epoch=result["gate_epoch"],
        candidate_set_sha256=result["candidate_set_sha256"],
        rust_project_ir_sha256=result["rust_project_ir_sha256"],
        rust_project_interface_sha256=result["rust_project_interface_sha256"],
        project_input_sha256=result["project_input_sha256"],
        raw_observation=result["raw_observation"],
        verifier_receipt=result["verifier_receipt"],
        diagnostics=result["diagnostics"],
    )
    if result != expected:
        raise ValueError("project diagnostic intake binding drifted")
    return result


def intake_project_diagnostics(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    intake = validate_project_diagnostic_intake(value)
    return [dict(item["project_diagnostic"]) for item in intake["diagnostics"]]


def intake_diagnostic_detail(
    value: Mapping[str, Any], diagnostic_sha256: str,
) -> dict[str, Any] | None:
    intake = validate_project_diagnostic_intake(value)
    matches = [
        item for item in intake["diagnostics"]
        if item["project_diagnostic"]["diagnostic_sha256"] == diagnostic_sha256
    ]
    if len(matches) > 1:
        raise ValueError("project diagnostic intake detail is ambiguous")
    return None if not matches else dict(matches[0])


def _diagnostics(value: Any, gate_kind: str) -> list[dict[str, Any]]:
    if (
        isinstance(value, (str, bytes)) or not isinstance(value, Sequence)
        or not 1 <= len(value) <= MAX_PROJECT_DIAGNOSTICS_PER_INTAKE
    ):
        raise ValueError("project diagnostic intake diagnostics are invalid")
    result = [_detail(item, gate_kind) for item in value]
    hashes = [item["project_diagnostic"]["diagnostic_sha256"] for item in result]
    if len(set(hashes)) != len(hashes):
        raise ValueError("project diagnostic intake diagnostics are duplicated")
    return sorted(result, key=lambda item: item["project_diagnostic"]["diagnostic_sha256"])


def _detail(value: Any, gate_kind: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _DETAIL_KEYS:
        raise ValueError("normalized project diagnostic fields are invalid")
    family = value.get("family")
    if family not in PROJECT_DIAGNOSTIC_GATE_FAMILIES.get(gate_kind, frozenset()):
        raise ValueError("project diagnostic family is not allowed for this gate")
    source_code = require_portable_id(str(value.get("source_code")), "source_code")
    if source_code != source_code.lower():
        raise ValueError("project diagnostic source code must be lowercase")
    stage = value.get("stage")
    if stage != gate_kind:
        raise ValueError("project diagnostic stage changed its gate binding")
    message = value.get("message")
    if not isinstance(message, str) or not message or len(message) > 512:
        raise ValueError("project diagnostic message is invalid")
    diagnostic = validate_project_diagnostic(value.get("project_diagnostic"))
    if (
        diagnostic["code"] != f"project-verifier-{source_code}"
        or source_code not in diagnostic["entity_ids"]
    ):
        raise ValueError("project diagnostic identity is not stable")
    result = {
        "family": family, "source_code": source_code, "stage": stage,
        "message": message, "location": _location(value.get("location")),
        "project_diagnostic": diagnostic,
    }
    assert_model_payload_safe(result, "project_diagnostic_detail")
    return result


def _location(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _LOCATION_KEYS:
        raise ValueError("project diagnostic location is invalid")
    file_value = value.get("file")
    if file_value is not None:
        file_value = checked_relative_path(file_value)
    result = {"file": file_value}
    for field in ("line", "column"):
        number = value.get(field)
        if number is not None:
            number = _positive_int(number, field)
        result[field] = number
    if file_value is None and any(result[field] is not None for field in ("line", "column")):
        raise ValueError("project diagnostic line/column require a file")
    return result


def _reference(
    value: Mapping[str, Any], gate_kind: str, *, raw: bool,
) -> dict[str, Any]:
    reference = dict(value)
    require_content_addressed_reference(reference)
    if raw:
        require_host_raw_reference(reference, gate_kind)
    else:
        parts = PurePosixPath(str(reference["path"])).parts
        expected = ("verification", "project", gate_kind)
        if not any(
            tuple(parts[index:index + 3]) == expected
            for index in range(len(parts) - 2)
        ):
            raise ValueError("project verifier receipt path is invalid")
    return reference


def _sha(value: Any, label: str) -> str:
    if not is_sha256(value):
        raise ValueError(f"{label} SHA-256 is invalid")
    return str(value)


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be positive")
    return value


__all__ = [
    "MAX_PROJECT_DIAGNOSTIC_INTAKES", "PROJECT_DIAGNOSTIC_FAMILIES",
    "PROJECT_DIAGNOSTIC_GATE_FAMILIES", "intake_diagnostic_detail",
    "intake_project_diagnostics", "project_diagnostic_intake_payload",
    "validate_project_diagnostic_intake",
]
