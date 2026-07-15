from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import content_sha256
from .gate_evidence import require_content_addressed_reference
from .ledger_security import LedgerError


_BINDING_KEYS = {
    "schema_version", "status", "reason_code", "context_sha256",
    "candidate_sha256", "requirement_count", "artifacts",
    "settlement_receipt_sha256", "resolution_gate", "semantic_gate",
    "binding_sha256",
}
_FULL_ARTIFACT_KEYS = {
    "trace", "actual_resolution", "order_evidence", "abi_evidence",
    "symbol_context", "symbol_candidate", "symbol_evidence", "settlement",
}
_CODE = re.compile(r"[a-z][a-z0-9_-]{0,95}\Z", re.ASCII)


def project_native_link_settlement_status(
    status: str,
    *,
    context: Mapping[str, Any] | None = None,
    candidate: Mapping[str, Any] | None = None,
    reason_code: str | None = None,
    artifacts: Mapping[str, Any] | None = None,
    settlement_receipt_sha256: str | None = None,
    resolution_gate: bool = False,
) -> dict[str, Any]:
    context_sha = context.get("context_sha256") if context is not None else None
    candidate_sha = (
        candidate.get("candidate_sha256") if candidate is not None else None
    )
    requirement_count = (
        int(context.get("requirement_count", 0)) if context is not None else 0
    )
    payload = {
        "schema_version": 1,
        "status": status,
        "reason_code": reason_code,
        "context_sha256": context_sha,
        "candidate_sha256": candidate_sha,
        "requirement_count": requirement_count,
        "artifacts": dict(artifacts or {}),
        "settlement_receipt_sha256": settlement_receipt_sha256,
        "resolution_gate": resolution_gate,
        "semantic_gate": False,
    }
    return validate_project_native_link_settlement_binding({
        **payload, "binding_sha256": content_sha256(payload),
    })


def validate_project_native_link_settlement_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_KEYS:
        raise ValueError("project_native_link_settlement_binding_invalid")
    result = dict(value)
    projection = {
        key: item for key, item in result.items() if key != "binding_sha256"
    }
    artifacts = result.get("artifacts")
    if (
        result.get("schema_version") != 1
        or result.get("status") not in {"not-required", "blocked", "resolved"}
        or type(result.get("requirement_count")) is not int
        or result["requirement_count"] < 0
        or not isinstance(artifacts, Mapping)
        or type(result.get("resolution_gate")) is not bool
        or result.get("semantic_gate") is not False
        or result.get("binding_sha256") != content_sha256(projection)
    ):
        raise ValueError("project_native_link_settlement_binding_invalid")
    _validate_binding_state(result, artifacts)
    return {**result, "artifacts": dict(artifacts)}


def _validate_binding_state(
    value: Mapping[str, Any], artifacts: Mapping[str, Any],
) -> None:
    status = value["status"]
    reason = value.get("reason_code")
    resolved = value["resolution_gate"]
    if reason is not None and (
        not isinstance(reason, str) or _CODE.fullmatch(reason) is None
    ):
        raise ValueError("project_native_link_settlement_reason_invalid")
    if status == "not-required":
        valid = (
            value["requirement_count"] == 0 and reason is None and not artifacts
            and value.get("candidate_sha256") is None and not resolved
            and value.get("settlement_receipt_sha256") is None
        )
    elif artifacts:
        valid = (
            set(artifacts) == _FULL_ARTIFACT_KEYS
            and value["requirement_count"] > 0
            and isinstance(value.get("context_sha256"), str)
            and isinstance(value.get("candidate_sha256"), str)
            and isinstance(value.get("settlement_receipt_sha256"), str)
            and ((status == "resolved" and reason is None and resolved)
                 or (status == "blocked" and reason is not None and not resolved))
        )
        if valid:
            _validate_artifact_references(artifacts)
    else:
        valid = (
            status == "blocked" and value["requirement_count"] >= 0
            and reason is not None and not resolved
            and value.get("settlement_receipt_sha256") is None
        )
    for field in (
        "context_sha256", "candidate_sha256", "settlement_receipt_sha256",
    ):
        digest = value.get(field)
        if digest is not None and (
            not isinstance(digest, str) or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            valid = False
    if not valid:
        raise ValueError("project_native_link_settlement_state_invalid")


def _validate_artifact_references(artifacts: Mapping[str, Any]) -> None:
    for key, reference in artifacts.items():
        if key == "symbol_candidate" and reference is None:
            continue
        try:
            require_content_addressed_reference(reference)
        except LedgerError as error:
            raise ValueError(
                "project_native_link_settlement_reference_invalid"
            ) from error


__all__ = [
    "project_native_link_settlement_status",
    "validate_project_native_link_settlement_binding",
]
