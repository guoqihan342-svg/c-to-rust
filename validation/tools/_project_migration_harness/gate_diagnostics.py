from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from validation.tools._ai_candidate_harness_parts.context_security import (
    redact_metadata_text,
)


GATE_FAMILIES = {
    "compile", "link", "test", "oracle-replay-diff", "schema-diff",
    "negative", "unsafe-alias", "abi-layout", "integration",
    "final-verification",
}
VALUE_SENSITIVE_FAMILIES = {
    "test", "oracle-replay-diff", "schema-diff", "negative",
}
MAX_DIAGNOSTICS = 32
MAX_MESSAGE_BYTES = 512
CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
STAGE = re.compile(r"^[a-z][a-z0-9_.-]{0,47}$")
VALUE_LANGUAGE = re.compile(
    r"\b(?:expected|actual|observed|received|got|oracle|fixture|output)\b",
    re.IGNORECASE,
)


def normalize_gate_evidence(
    *, gate_family: str, status: str, candidate_artifact_id: str,
    candidate_sha256: str, diagnostics: Any,
) -> dict[str, Any]:
    if gate_family not in GATE_FAMILIES or status not in {"passed", "failed"}:
        raise ValueError("gate family/status is invalid")
    if not isinstance(diagnostics, list) or len(diagnostics) > MAX_DIAGNOSTICS:
        raise ValueError("gate diagnostics exceed the bounded count")
    normalized = [
        _diagnostic(item, gate_family=gate_family) for item in diagnostics
    ]
    if status == "passed" and normalized:
        raise ValueError("passed gate evidence must not carry failure diagnostics")
    if status == "failed" and not normalized:
        raise ValueError("failed gate evidence requires at least one diagnostic")
    return {
        "schema_version": 1,
        "artifact_kind": "model-safe-gate-evidence",
        "model_input_safe": True,
        "gate_family": gate_family,
        "status": status,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_artifact_sha256": candidate_sha256,
        "diagnostics": normalized,
        "withheld_fields": [
            "expected", "actual", "oracle_values", "fixture_values", "raw_output",
        ],
        "semantic_acceptance": status == "passed",
    }


def validate_model_safe_gate_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("gate evidence must be a JSON object")
    expected_keys = {
        "schema_version", "artifact_kind", "model_input_safe", "gate_family",
        "status", "candidate_artifact_id", "candidate_artifact_sha256",
        "diagnostics", "withheld_fields", "semantic_acceptance",
    }
    if set(value) != expected_keys:
        raise ValueError("gate evidence fields are invalid")
    rebuilt = normalize_gate_evidence(
        gate_family=str(value.get("gate_family")),
        status=str(value.get("status")),
        candidate_artifact_id=str(value.get("candidate_artifact_id")),
        candidate_sha256=str(value.get("candidate_artifact_sha256")),
        diagnostics=value.get("diagnostics"),
    )
    if dict(value) != rebuilt:
        raise ValueError("gate evidence does not match its canonical safe projection")
    return rebuilt


def _diagnostic(value: Any, *, gate_family: str) -> dict[str, Any]:
    allowed = {"code", "stage", "message", "file", "line", "column"}
    if not isinstance(value, Mapping) or set(value) - allowed:
        raise ValueError("gate diagnostic fields are invalid")
    code = value.get("code")
    stage = value.get("stage")
    if not isinstance(code, str) or CODE.fullmatch(code) is None:
        raise ValueError("gate diagnostic code is invalid")
    if not isinstance(stage, str) or STAGE.fullmatch(stage) is None:
        raise ValueError("gate diagnostic stage is invalid")
    result: dict[str, Any] = {"code": code, "stage": stage}
    file = value.get("file")
    if file is not None:
        if (
            not isinstance(file, str)
            or not file
            or "\\" in file
            or file.startswith(("/", "~"))
            or ".." in file.split("/")
            or ":" in file.split("/")[0]
        ):
            raise ValueError("gate diagnostic file must be repository-relative")
        result["file"] = file
    for key in ("line", "column"):
        number = value.get(key)
        if number is not None:
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                raise ValueError(f"gate diagnostic {key} is invalid")
            result[key] = number
    message = value.get("message")
    if message is not None and gate_family not in VALUE_SENSITIVE_FAMILIES:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("gate diagnostic message is invalid")
        sanitized = redact_metadata_text(message).strip()
        if VALUE_LANGUAGE.search(sanitized):
            sanitized = "<value-bearing diagnostic withheld>"
        if len(sanitized.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ValueError("gate diagnostic message exceeds its bounded size")
        result["message"] = sanitized
    return result


__all__ = [
    "GATE_FAMILIES",
    "normalize_gate_evidence",
    "validate_model_safe_gate_evidence",
]
