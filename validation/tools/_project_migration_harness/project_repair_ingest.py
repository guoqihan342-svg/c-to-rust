from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256, write_json_artifact
from .orchestration_facts import read_artifact_reference
from .project_interface_coordinator import coordinate_project_interfaces
from .project_repair_context import validate_project_repair_context
from .project_repair_authoritative_ir import persist_authoritative_project_ir
from .project_repair_patch import (
    apply_project_repair_operations, normalize_project_repair_response,
)
from .project_repair_paths import require_bound_project_repair_out_root
from .project_repair_prompt import render_project_repair_prompt
from .project_repair_worker_request import read_bound_rust_project_ir
from .rust_project_ir_validation import reopen_rust_project_ir_bindings


MAX_PROJECT_REPAIR_RESPONSE_BYTES = 2 * 1024 * 1024


def ingest_project_repair_response(
    request: Mapping[str, Any], response: Mapping[str, Any], *, ledger: Any,
    harness_root: Path, out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    require_bound_project_repair_out_root(harness_root, out_root, out_root_rel)
    render_project_repair_prompt(request, harness_root=harness_root)
    attempt_id = str(request["execution_binding"]["attempt_id"])
    projection = ledger.project_repair_projection(
        run_id=str(request["run_id"]),
        queue_sha256=str(request["project_repair_queue_sha256"]),
        repair_id=str(request["repair_id"]),
    )
    if (
        projection.status != "running"
        or projection.active_attempt_id != attempt_id
        or projection.version != request["execution_binding"]["fencing_token"]
    ):
        raise ValueError("project repair response requires its active attempt")
    response_bytes = canonical_json_bytes(response)
    if len(response_bytes) > MAX_PROJECT_REPAIR_RESPONSE_BYTES:
        return _record_failure(
            request, response_bytes, ledger=ledger, out_root=out_root,
            out_root_rel=out_root_rel, error_code="project_repair_response_too_large",
        )
    try:
        normalized = normalize_project_repair_response(request, response)
    except (TypeError, ValueError):
        return _record_failure(
            request, response_bytes, ledger=ledger, out_root=out_root,
            out_root_rel=out_root_rel, error_code="invalid_project_repair_response",
        )
    base_ir = read_bound_rust_project_ir(
        harness_root, request["base_rust_project_ir"],
    )
    context = _read_context(harness_root, request["project_repair_context"])
    try:
        candidate = apply_project_repair_operations(base_ir, context, normalized)
        _reopen_candidate_bindings(candidate, out_root, harness_root)
    except (OSError, TypeError, ValueError):
        return _record_failure(
            request, response_bytes, ledger=ledger, out_root=out_root,
            out_root_rel=out_root_rel, error_code="invalid_project_repair_ir_candidate",
        )
    original_receipt = ledger.load_project_interface_receipt(
        run_id=str(request["run_id"]),
        queue_sha256=str(request["project_repair_queue_sha256"]),
    )
    original_queue = original_receipt["project_repair_queue"]
    receipt = coordinate_project_interfaces(
        candidate, max_repairs=original_queue["max_items"],
        max_attempts_per_item=original_queue["max_attempts_per_item"],
    )
    response_ref = write_json_artifact(
        out_root,
        f"project-repair/responses/{attempt_id}-{content_sha256(normalized)}.json",
        normalized,
    )
    candidate_ref = write_json_artifact(
        out_root,
        f"project-repair/ir-candidates/{candidate['ir_sha256']}.json",
        candidate,
    )
    authoritative_ref = persist_authoritative_project_ir(
        candidate, out_root=out_root, out_root_rel=out_root_rel,
    )
    receipt_ref = write_json_artifact(
        out_root,
        f"project-repair/coordinator/{receipt['coordinator_receipt_sha256']}.json",
        receipt,
    )
    persisted_response = _read_json_artifact(
        harness_root, _prefix(response_ref, out_root_rel),
    )
    persisted_candidate = read_bound_rust_project_ir(
        harness_root, _prefix(candidate_ref, out_root_rel),
    )
    persisted_receipt = _read_json_artifact(
        harness_root, _prefix(receipt_ref, out_root_rel),
    )
    if (
        persisted_response != normalized or persisted_candidate != candidate
        or persisted_receipt != receipt
    ):
        raise ValueError("project repair persisted candidate evidence drifted")
    for kind, reference, status, metadata in (
        ("project-repair-response", response_ref, "written", {}),
        ("rust-project-ir-candidate", candidate_ref, "candidate", {
            "ir_sha256": candidate["ir_sha256"],
        }),
        ("project-interface-receipt", receipt_ref, "diagnostic", {
            "coordinator_receipt_sha256": receipt["coordinator_receipt_sha256"],
        }),
    ):
        ledger.record_project_repair_artifact(
            attempt_id=attempt_id,
            artifact_id=f"{kind}-{reference['sha256'][:24]}", kind=kind,
            repo_rel_path=f"{out_root_rel}/{reference['path']}",
            content_sha256=str(reference["sha256"]), status=status,
            metadata=metadata,
        )
    ledger.record_project_repair_artifact(
        attempt_id=attempt_id,
        artifact_id=f"rust-project-ir-authoritative-{authoritative_ref['sha256'][:24]}",
        kind="rust-project-ir-authoritative",
        repo_rel_path=str(authoritative_ref["path"]),
        content_sha256=str(authoritative_ref["sha256"]), status="candidate",
        metadata={"ir_sha256": candidate["ir_sha256"]},
    )
    finalized = ledger.finalize_project_repair_candidate(
        run_id=str(request["run_id"]),
        queue_sha256=str(request["project_repair_queue_sha256"]),
        repair_id=str(request["repair_id"]), attempt_id=attempt_id,
        expected_version=int(request["execution_binding"]["started_state_version"]),
        worker_id=str(request["worker_id"]),
        response_sha256=str(response_ref["sha256"]),
        rust_project_ir=candidate, receipt=receipt,
        coordinator_evidence_sha256=str(receipt_ref["sha256"]),
    )
    terminal = finalized.terminal
    public_status = (
        "pending-reverification"
        if finalized.requires_reverification else terminal.current.status
    )
    report = {
        "schema_version": 1, "status": public_status,
        "run_id": request["run_id"], "repair_id": request["repair_id"],
        "attempt_id": attempt_id, "candidate_ir_sha256": candidate["ir_sha256"],
        "coordinator_status": receipt["status"],
        "artifacts": {
            "response": _prefix(response_ref, out_root_rel),
            "rust_project_ir_candidate": _prefix(candidate_ref, out_root_rel),
            "rust_project_ir_authoritative": authoritative_ref,
            "coordinator_receipt": _prefix(receipt_ref, out_root_rel),
        },
        "claim_boundary": {
            "model_semantic_acceptance": False,
            "host_coordinator_rerun": True,
            "project_final_gate": False,
        },
    }
    if finalized.requires_reverification:
        report["ledger_status"] = terminal.current.status
    report["ingest_sha256"] = content_sha256(report)
    return report


def _record_failure(
    request: Mapping[str, Any], response_bytes: bytes, *, ledger: Any,
    out_root: Path, out_root_rel: str, error_code: str,
) -> dict[str, Any]:
    attempt_id = str(request["execution_binding"]["attempt_id"])
    payload = {
        "schema_version": 1, "run_id": request["run_id"],
        "repair_id": request["repair_id"], "attempt_id": attempt_id,
        "error_code": error_code,
        "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
        "claim_boundary": {"semantic_acceptance": False},
    }
    reference = write_json_artifact(
        out_root,
        f"project-repair/failures/{attempt_id}-{content_sha256(payload)}.json",
        payload,
    )
    ledger.record_project_repair_artifact(
        attempt_id=attempt_id,
        artifact_id=f"project-repair-failure-{reference['sha256'][:24]}",
        kind="project-repair-failure",
        repo_rel_path=f"{out_root_rel}/{reference['path']}",
        content_sha256=str(reference["sha256"]), status="failed",
        metadata={"error_code": error_code},
    )
    finished = ledger.finish_project_repair_attempt(
        attempt_id=attempt_id,
        command_id=f"project-repair-fail-{reference['sha256'][:24]}",
        expected_version=int(request["execution_binding"]["started_state_version"]),
        worker_id=str(request["worker_id"]), outcome="failed",
        evidence_sha256=str(reference["sha256"]), error_key=error_code,
    )
    return {
        **payload, "status": finished.current.status,
        "failure": _prefix(reference, out_root_rel),
    }


def _reopen_candidate_bindings(
    candidate: Mapping[str, Any], out_root: Path, harness_root: Path,
) -> None:
    failures = []
    for root in dict.fromkeys((out_root.resolve(), harness_root.resolve())):
        try:
            reopen_rust_project_ir_bindings(candidate, root)
            return
        except (OSError, TypeError, ValueError) as error:
            failures.append(error)
    raise ValueError("project repair candidate bindings cannot be reopened") from failures[-1]


def _read_context(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    data = read_artifact_reference(root, reference)
    try:
        return validate_project_repair_context(json.loads(data.decode("utf-8")))
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("bound project repair context is invalid") from error


def _read_json_artifact(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(read_artifact_reference(root, reference).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("project repair evidence is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("project repair evidence must be a JSON object")
    return value


def _prefix(reference: Mapping[str, Any], root: str) -> dict[str, Any]:
    return {**dict(reference), "path": f"{root}/{reference['path']}"}


__all__ = ["MAX_PROJECT_REPAIR_RESPONSE_BYTES", "ingest_project_repair_response"]
