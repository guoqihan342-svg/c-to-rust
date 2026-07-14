from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .ledger import ProjectLedger
from .orchestration_facts import read_artifact_reference
from .project_interface_model_context import build_model_coordinator_context
from .context_frontier_overlay_runtime import resolve_request_effective_context


def bound_worker_request(
    reference: Mapping[str, Any], *, ledger: ProjectLedger, harness_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    request, attempt = _bound_request_identity(
        reference, ledger=ledger, harness_root=harness_root,
    )
    metadata = attempt["metadata"]
    assignment_ref = {
        "path": metadata.get("assignment_path"),
        "sha256": metadata.get("assignment_sha256"),
    }
    try:
        assignment = json.loads(
            read_artifact_reference(harness_root, assignment_ref).decode("utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("worker assignment is unreadable") from error
    if not isinstance(assignment, Mapping):
        raise ValueError("worker assignment must be an object")
    if content_sha256(assignment) != metadata.get("assignment_sha256"):
        raise ValueError("worker assignment digest drifted")
    _validate_request_fields(
        request, assignment, attempt, harness_root=harness_root,
    )
    _validate_latest_coordinator_context(request, ledger)
    return request, attempt


def cancel_invalid_bound_worker_request(
    reference: Mapping[str, Any], *, ledger: ProjectLedger, harness_root: Path,
) -> dict[str, Any] | None:
    try:
        request, attempt = _bound_request_identity(
            reference, ledger=ledger, harness_root=harness_root,
        )
        metadata = attempt.get("metadata")
        if not isinstance(metadata, Mapping) or metadata.get("command_started") is True:
            return None
        execution = request["execution_binding"]
        ledger.cancel_prelaunch_attempt(
            attempt_id=str(execution["attempt_id"]),
            owner=str(request["worker_id"]),
            fencing_token=int(execution["fencing_token"]),
        )
    except (KeyError, OSError, TypeError, ValueError):
        return None
    return attempt


def _bound_request_identity(
    reference: Mapping[str, Any], *, ledger: ProjectLedger, harness_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        request = json.loads(read_artifact_reference(harness_root, reference).decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("worker request is unreadable") from error
    if not isinstance(request, dict):
        raise ValueError("worker request must be an object")
    execution = request.get("execution_binding")
    if not isinstance(execution, Mapping):
        raise ValueError("worker request has no attempt/fence binding")
    attempt_id = execution.get("attempt_id")
    token = execution.get("fencing_token")
    worker_id = request.get("worker_id")
    if not isinstance(attempt_id, str) or not isinstance(token, int) or not isinstance(worker_id, str):
        raise ValueError("worker request execution identity is invalid")
    attempt = ledger.bound_attempt(
        attempt_id=attempt_id, owner=worker_id, fencing_token=token
    )
    metadata = attempt["metadata"]
    if (
        reference.get("path") != metadata.get("request_path")
        or reference.get("sha256") != metadata.get("request_sha256")
    ):
        raise ValueError("worker request reference is not bound to the running attempt")
    return request, attempt


def _validate_request_fields(
    request: Mapping[str, Any], assignment: Mapping[str, Any], attempt: Mapping[str, Any],
    *, harness_root: Path,
) -> None:
    fields = (
        "run_id", "worker_id", "role", "group_id", "unit_id", "wave_index",
        "dependencies", "launch_policy", "runtime_roots",
        "max_attempts", "authority",
    )
    if any(request.get(key) != assignment.get(key) for key in fields):
        raise ValueError("worker request fields drifted from its assignment")
    frontier = request.get("context_frontier")
    if (
        not isinstance(frontier, Mapping)
        or request.get("context") != resolve_request_effective_context(
            assignment, frontier, harness_root=harness_root,
        )
    ):
        raise ValueError("worker request effective context drifted")
    if request.get("group_id") != request.get("unit_id"):
        raise ValueError("worker request group/unit identity drifted")
    if (
        request.get("run_id") != attempt.get("run_id")
        or request.get("worker_id") != attempt.get("worker_id")
        or request.get("role") != attempt.get("role")
        or request.get("unit_id") != attempt.get("unit_id")
        or request.get("runtime_roots", {}).get("out") != attempt.get("out_root")
    ):
        raise ValueError("worker request does not match the running attempt")
    binding = request.get("assignment_binding")
    ledger_binding = assignment.get("ledger_binding")
    if (
        not isinstance(binding, Mapping) or not isinstance(ledger_binding, Mapping)
        or binding.get("assignment_sha256") != content_sha256(assignment)
        or binding.get("group_sha256") != assignment.get("group_sha256")
        or binding.get("ledger_binding_sha256") != ledger_binding.get("binding_sha256")
    ):
        raise ValueError("worker request assignment binding drifted")
    metadata = attempt.get("metadata")
    if (
        not isinstance(metadata, Mapping)
        or request.get("context_frontier")
        != metadata.get("launch_claim", {}).get("context_frontier")
        or request.get("launch_claim") != metadata.get("launch_claim")
        or request.get("schedule_sha256") != metadata.get("schedule_sha256")
    ):
        raise ValueError("worker request context frontier launch binding drifted")
    execution = request["execution_binding"]
    execution_payload = {
        key: value for key, value in execution.items() if key != "binding_sha256"
    }
    if content_sha256(execution_payload) != execution.get("binding_sha256"):
        raise ValueError("worker execution binding SHA-256 drifted")
    base = {key: value for key, value in request.items() if key != "execution_binding"}
    effective = base.pop("effective_input_sha256", None)
    if (
        content_sha256(base) != effective
        or effective != attempt.get("input_sha256")
        or effective != execution.get("effective_input_sha256")
    ):
        raise ValueError("worker effective input binding drifted")


def _validate_latest_coordinator_context(
    request: Mapping[str, Any], ledger: ProjectLedger,
) -> None:
    facts = request.get("input_facts")
    context = facts.get("coordinator_context") if isinstance(facts, Mapping) else None
    latest = ledger.load_latest_project_interface_receipt(
        run_id=str(request["run_id"]),
    )
    if context is None:
        if (
            latest is not None
            and request.get("role") in {"planner", "translator", "repairer"}
        ):
            raise ValueError("worker coordinator context is missing the latest receipt")
        return
    if not isinstance(context, Mapping):
        raise ValueError("worker coordinator context is invalid")
    if latest is None:
        raise ValueError("worker coordinator context has no ledger receipt")
    expected = build_model_coordinator_context(
        latest[1], receipt_epoch=int(latest[0]),
        subject_unit_ids=context.get("subject_unit_ids"),
    )
    if dict(context) != expected:
        raise ValueError("worker coordinator context is stale")


__all__ = ["bound_worker_request", "cancel_invalid_bound_worker_request"]
