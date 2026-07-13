from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from validation.tools._ai_candidate_harness_parts.provider_response import (
    assistant_text_from_jsonl,
    extract_single_json_text,
)

from .gate_evidence import read_content_addressed_json
from .ledger_security import LedgerError, assert_no_secrets
from .orchestration_facts import read_artifact_reference
from .project_preflight import validate_project_worker_preflight
from .project_receipt_validation import validate_project_invocation_receipt


REPORT_KEYS = {
    "schema_version", "artifact_kind", "status", "run_id", "worker_id", "role",
    "attempt_id", "fencing_epoch", "request", "preflight", "model",
    "runtime_input_sha256", "identity", "artifacts", "semantic_gate",
}


def validate_provider_execution_evidence(
    ledger_path: Path, artifact: Mapping[str, Any], *,
    run_id: str, unit_id: str, attempt_id: str,
    worker_id: str, fencing_token: int, role: str,
) -> None:
    report = read_content_addressed_json(
        ledger_path,
        str(artifact.get("repo_rel_path")),
        str(artifact.get("content_sha256")),
    )
    assert_no_secrets(report, "provider_execution")
    if (
        set(report) != REPORT_KEYS
        or report.get("schema_version") != 1
        or report.get("artifact_kind") != "project-opencode-execution"
        or report.get("status") != "generated"
        or report.get("run_id") != run_id
        or report.get("worker_id") != worker_id
        or report.get("role") != role
        or report.get("attempt_id") != attempt_id
        or report.get("fencing_epoch") != fencing_token
        or report.get("semantic_gate") is not False
    ):
        raise LedgerError("provider execution report identity is invalid")
    root = _artifact_root(ledger_path, report.get("request"))
    request = _json_reference(root, report.get("request"), "worker request")
    binding = request.get("execution_binding")
    if (
        request.get("run_id") != run_id
        or request.get("unit_id") != unit_id
        or request.get("worker_id") != worker_id
        or request.get("role") != role
        or not isinstance(binding, Mapping)
        or binding.get("attempt_id") != attempt_id
        or binding.get("fencing_token") != fencing_token
    ):
        raise LedgerError("provider execution request binding is invalid")
    model = report.get("model")
    if not isinstance(model, Mapping) or set(model) != {
        "logical", "resolved", "agent", "variant",
    }:
        raise LedgerError("provider execution model binding is invalid")
    preflight = validate_project_worker_preflight(
        _reference(report.get("preflight")),
        harness_root=root,
        run_id=run_id,
        logical_model=str(model.get("logical")),
        resolved_model=str(model.get("resolved")),
        opencode_command="opencode",
        agent=str(model.get("agent")),
        variant=str(model.get("variant")),
    )
    if report.get("runtime_input_sha256") != preflight["runtime_input_sha256"]:
        raise LedgerError("provider execution runtime inputs drifted from preflight")
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) not in (
        {"prompt", "raw_response", "invocation_receipt", "parsed_response"},
        {
            "prompt", "raw_response", "invocation_receipt", "parsed_response",
            "session_identity",
        },
    ):
        raise LedgerError("provider execution artifact set is invalid")
    prompt_path = _bound_path(root, artifacts["prompt"])
    response_path = _bound_path(root, artifacts["raw_response"])
    receipt_path = _bound_path(root, artifacts["invocation_receipt"])
    parsed = _json_reference(root, artifacts["parsed_response"], "parsed response")
    identity = validate_project_invocation_receipt(
        receipt_path,
        prompt_path=prompt_path,
        response_path=response_path,
        resolved_model=str(model["resolved"]),
        agent=str(model["agent"]),
        variant=str(model["variant"]),
        require_export=preflight["proof_scope"] == "competition-model-preflight",
    )
    if report.get("identity") != identity:
        raise LedgerError("provider execution identity does not match its receipt")
    raw = read_artifact_reference(root, _reference(artifacts["raw_response"]))
    try:
        projected = json.loads(extract_single_json_text(
            assistant_text_from_jsonl(raw.decode("utf-8"))
        ))
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise LedgerError("provider execution raw response is not replayable") from error
    if projected != parsed:
        raise LedgerError("provider execution parsed response drifted from raw JSONL")
    if "session_identity" in artifacts:
        _bound_path(root, artifacts["session_identity"])


def _artifact_root(ledger_path: Path, reference: Any) -> Path:
    ref = _reference(reference)
    relative = PurePosixPath(str(ref["path"]))
    matches = []
    database = ledger_path.resolve()
    for candidate in (database.parent, *database.parents):
        try:
            read_artifact_reference(candidate, ref)
        except (OSError, ValueError):
            continue
        matches.append(candidate.resolve())
    unique = list(dict.fromkeys(matches))
    if len(unique) != 1:
        raise LedgerError("provider execution repository root is missing or ambiguous")
    _ = relative
    return unique[0]


def _bound_path(root: Path, reference: Any) -> Path:
    ref = _reference(reference)
    read_artifact_reference(root, ref)
    return root.joinpath(*PurePosixPath(str(ref["path"])).parts).resolve(strict=True)


def _json_reference(root: Path, reference: Any, label: str) -> dict[str, Any]:
    data = read_artifact_reference(root, _reference(reference))
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LedgerError(f"provider execution {label} is invalid") from error
    if not isinstance(payload, dict):
        raise LedgerError(f"provider execution {label} must be an object")
    return payload


def _reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) not in (
        {"path", "sha256"}, {"path", "sha256", "size_bytes"},
    ):
        raise LedgerError("provider execution artifact reference is invalid")
    return dict(value)


__all__ = ["validate_provider_execution_evidence"]
