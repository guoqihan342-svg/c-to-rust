from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from validation.tools._ai_candidate_harness_parts.context_security import (
    redact_metadata_text,
)

from .artifacts import content_sha256
from .ledger_security import assert_no_semantic_claims
from .portfolio_roles import PLANNER_DECISIONS
from .runtime_security import (
    assert_model_payload_safe,
    derive_boundary_manifest,
    derive_rust_metadata,
    reject_value_bearing_text,
)


MAX_CANDIDATE_BYTES = 2 * 1024 * 1024
MAX_FINDINGS = 32
MAX_MESSAGE_BYTES = 512
CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMON = {
    "schema_version", "run_id", "worker_id", "group_id", "role",
    "effective_input_sha256",
}


def normalize_worker_result(
    request: Mapping[str, Any], response: Mapping[str, Any]
) -> dict[str, Any]:
    if not isinstance(response, Mapping) or response.get("schema_version") != 1:
        raise ValueError("worker response schema_version must be 1")
    role = _request_string(request, "role")
    expected_common = {
        "schema_version": 1,
        "run_id": _request_string(request, "run_id"),
        "worker_id": _request_string(request, "worker_id"),
        "group_id": _request_string(request, "group_id"),
        "role": role,
        "effective_input_sha256": _request_sha(request, "effective_input_sha256"),
    }
    for key, expected in expected_common.items():
        if response.get(key) != expected:
            raise ValueError(f"worker response {key} does not match its request")
    assert_no_semantic_claims(response)
    assert_model_payload_safe(response, "worker_response")
    if role == "planner":
        return _planner(request, response, expected_common)
    if role in {"translator", "repairer"}:
        return _candidate(request, response, expected_common, role)
    if role == "reviewer":
        return _review(request, response, expected_common)
    raise ValueError("worker response role is unsupported")


def _planner(
    request: Mapping[str, Any], response: Mapping[str, Any], common: Mapping[str, Any]
) -> dict[str, Any]:
    decision = response.get("decision")
    allowed = COMMON | {"decision", "boundary_reason", "refusal_reason"}
    if set(response) - allowed or decision not in PLANNER_DECISIONS:
        raise ValueError("planner response fields or decision are invalid")
    if decision == "preserve_ffi_boundary":
        reason = _bounded_text(response.get("boundary_reason"), "boundary_reason")
    elif decision == "refuse_with_reason":
        reason = _bounded_text(response.get("refusal_reason"), "refusal_reason")
    else:
        if response.get("boundary_reason") is not None or response.get("refusal_reason") is not None:
            raise ValueError("translation planner decision must not carry terminal reasons")
        reason = None
    assignment = request.get("assignment_binding")
    context = request.get("context")
    if not isinstance(assignment, Mapping) or not isinstance(context, Mapping):
        raise ValueError("planner request is missing assignment/context bindings")
    decision_payload = {
        "run_id": common["run_id"],
        "group_id": common["group_id"],
        "group_sha256": assignment.get("group_sha256"),
        "context_pack_sha256": context.get("sha256"),
        "decision": decision,
    }
    artifact = {**common, "planner_decision": decision_payload}
    if reason is not None:
        artifact["reason"] = reason
    terminal = decision == "refuse_with_reason"
    return {
        "artifact_kind": "planner-decision",
        "artifact_status": "diagnostic",
        "artifact_payload": artifact,
        "planner_decision": decision_payload,
        "planner_decision_sha256": content_sha256(decision_payload),
        "next_status": "failed" if terminal else "candidate-ready",
        "terminal": terminal,
        "fail_run": terminal,
    }


def _candidate(
    request: Mapping[str, Any], response: Mapping[str, Any],
    common: Mapping[str, Any], role: str,
) -> dict[str, Any]:
    allowed = COMMON | {"candidate_source"}
    if role == "repairer":
        allowed.add("failed_gate_result_sha256")
    required = COMMON | {"candidate_source"}
    if role == "repairer":
        required.add("failed_gate_result_sha256")
    if set(response) - allowed or not required <= set(response):
        raise ValueError(f"{role} response fields are invalid")
    source = response.get("candidate_source")
    if not isinstance(source, str) or not source.strip() or "\x00" in source:
        raise ValueError("candidate_source must be non-empty NUL-free text")
    encoded = source.encode("utf-8")
    if len(encoded) > MAX_CANDIDATE_BYTES:
        raise ValueError("candidate_source exceeds the bounded response size")
    if role == "repairer":
        expected = _request_input_sha(request, "failed_gate_result_sha256")
        if response.get("failed_gate_result_sha256") != expected:
            raise ValueError("repair response does not bind the failed gate result")
    digest = hashlib.sha256(encoded).hexdigest()
    derived = derive_rust_metadata(source)
    decision = _planner_decision(request)
    boundary = (
        derive_boundary_manifest(source, digest)
        if decision == "preserve_ffi_boundary"
        else None
    )
    candidate_metadata = {**common, **derived}
    if boundary is not None:
        candidate_metadata["boundary_manifest_payload"] = boundary
    return {
        "artifact_kind": "rust-candidate",
        "artifact_status": "candidate",
        "candidate_source": encoded,
        "candidate_sha256": digest,
        "candidate_metadata": candidate_metadata,
        "boundary_manifest": boundary,
        "next_status": "candidate-ready",
        "terminal": False,
    }


def _review(
    request: Mapping[str, Any], response: Mapping[str, Any], common: Mapping[str, Any]
) -> dict[str, Any]:
    if set(response) != COMMON | {"candidate_artifact_sha256", "findings"}:
        raise ValueError("reviewer response fields are invalid")
    candidate_sha = _request_input_sha(request, "candidate_artifact_sha256")
    if response.get("candidate_artifact_sha256") != candidate_sha:
        raise ValueError("review response does not bind the candidate")
    findings = response.get("findings")
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise ValueError("review findings exceed the bounded count")
    normalized = [_finding(item) for item in findings]
    return {
        "artifact_kind": "structural-review",
        "artifact_status": "reviewed",
        "artifact_payload": {
            **common,
            "candidate_artifact_sha256": candidate_sha,
            "findings": normalized,
            "semantic_acceptance": False,
        },
        "next_status": "gate-pending",
        "terminal": False,
    }


def _finding(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"severity", "code", "message"}:
        raise ValueError("review finding fields are invalid")
    severity = value.get("severity")
    code = value.get("code")
    if severity not in {"info", "warning", "error"} or not isinstance(code, str) or not CODE.fullmatch(code):
        raise ValueError("review finding severity/code is invalid")
    return {
        "severity": str(severity),
        "code": code,
        "message": _bounded_text(value.get("message"), "finding.message"),
    }


def _bounded_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    sanitized = redact_metadata_text(value).strip()
    reject_value_bearing_text(sanitized, label)
    if not sanitized or len(sanitized.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError(f"{label} exceeds its safe bounded size")
    return sanitized


def _request_string(request: Mapping[str, Any], key: str) -> str:
    value = request.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"worker request {key} is invalid")
    return value


def _request_sha(request: Mapping[str, Any], key: str) -> str:
    value = _request_string(request, key)
    if SHA256.fullmatch(value) is None:
        raise ValueError(f"worker request {key} is not a SHA-256")
    return value


def _request_input_sha(request: Mapping[str, Any], key: str) -> str:
    facts = request.get("input_facts")
    if not isinstance(facts, Mapping):
        raise ValueError("worker request input_facts are invalid")
    value = facts.get(key)
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise ValueError(f"worker request input fact {key} is invalid")
    return value


def _planner_decision(request: Mapping[str, Any]) -> str | None:
    facts = request.get("input_facts")
    raw = facts.get("planner_decision") if isinstance(facts, Mapping) else None
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or raw.get("decision") not in PLANNER_DECISIONS:
        raise ValueError("worker request planner decision is invalid")
    return str(raw["decision"])


__all__ = ["MAX_CANDIDATE_BYTES", "normalize_worker_result"]
