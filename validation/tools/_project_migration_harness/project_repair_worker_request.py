from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256, write_json_artifact
from .ledger_project_repair_registry import ProjectRepairRegistry
from .orchestration_facts import read_artifact_reference
from .project_repair_context import build_project_repair_context
from .project_repair_dispatch_permit import (
    ProjectRepairDispatchPermit, project_repair_dispatch_binding,
)
from .project_repair_generation_authority import (
    require_project_repair_source_generation,
)
from .project_repair_paths import require_bound_project_repair_out_root
from .project_repair_native_link import prepare_native_link_repair_context
from .project_verifier_receipt import (
    receipt_project_diagnostic_references, verifier_diagnostic_detail,
)
from .rust_project_ir import canonical_rust_project_ir_bytes
from .rust_project_ir_validation import validate_rust_project_ir


def materialize_project_repair_request(
    *, ledger: Any, run_id: str, queue_sha256: str, repair_id: str,
    worker_id: str, base_rust_project_ir: Mapping[str, Any],
    harness_root: Path, out_root: Path, out_root_rel: str,
    dispatch_permit: ProjectRepairDispatchPermit,
) -> dict[str, Any]:
    require_bound_project_repair_out_root(harness_root, out_root, out_root_rel)
    ir = read_bound_rust_project_ir(harness_root, base_rust_project_ir)
    receipt = ledger.load_project_interface_receipt(
        run_id=run_id, queue_sha256=queue_sha256,
    )
    with ledger.connect() as connection:
        receipt_epoch = ProjectRepairRegistry(connection, ledger.path).receipt_epoch(
            run_id=run_id, queue_sha256=queue_sha256,
        )
    latest = ledger.load_latest_project_interface_receipt(run_id=run_id)
    if (
        latest is None or latest[0] != receipt_epoch
        or latest[1]["project_repair_queue"]["project_repair_queue_sha256"]
        != queue_sha256
    ):
        raise ValueError("project repair request requires the latest receipt queue")
    projection = ledger.project_repair_projection(
        run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
    )
    if projection.status not in {"queued", "retry-ready"}:
        raise ValueError("project repair item is not dispatchable")
    dispatch_binding = project_repair_dispatch_binding(dispatch_permit)
    _validate_dispatch_binding(
        dispatch_binding, run_id=run_id, receipt_epoch=receipt_epoch,
        coordinator_receipt_sha256=receipt["coordinator_receipt_sha256"],
        queue_sha256=queue_sha256, repair_id=repair_id,
        status=projection.status, state_version=projection.version,
    )
    intake_references = receipt_project_diagnostic_references(receipt)
    intakes = ledger.bound_project_diagnostic_intakes(
        run_id=run_id, references=intake_references,
        rust_project_ir_sha256=str(ir["ir_sha256"]),
    )
    selected = next(
        item for item in receipt["project_repair_queue"]["items"]
        if item["repair_id"] == repair_id
    )
    if intakes and verifier_diagnostic_detail(
        intakes, selected["diagnostic_sha256"],
    ) is None:
        raise ValueError(
            "project verifier diagnostics must settle before static repair"
        )
    require_project_repair_source_generation(
        ledger=ledger, run_id=run_id, queue_sha256=queue_sha256,
        rust_project_ir=ir, out_root=out_root,
    )
    native_link_context = None
    native_link_reference = None
    if selected["diagnostic_code"] == "rust_project_ir_native_link_plan_missing":
        native_link_context, native_link_reference = (
            prepare_native_link_repair_context(
                ledger=ledger, run_id=run_id, rust_project_ir=ir,
                out_root=out_root, out_root_rel=out_root_rel,
            )
        )
    context = build_project_repair_context(
        ir, receipt, receipt_epoch=receipt_epoch, repair_id=repair_id,
        project_diagnostic_intakes=intakes,
        native_link_context=native_link_context,
    )
    context_ref = write_json_artifact(
        out_root,
        f"project-repair/contexts/{context['context_sha256']}.json",
        context,
    )
    bound_context = {
        **_prefix(context_ref, out_root_rel),
        "context_sha256": context["context_sha256"],
    }
    base_ref = {
        **dict(base_rust_project_ir),
        "ir_sha256": ir["ir_sha256"],
        "interface_sha256": ir["interface_sha256"],
    }
    worker_root = f"{out_root_rel}/project-repair/workers/{worker_id}"
    runtime_roots = {
        name: f"{worker_root}/{name}"
        for name in ("config", "data", "cache", "state", "tmp", "out")
    }
    request = {
        "schema_version": 1,
        "request_kind": "project_repair_worker",
        "run_id": run_id,
        "role": "project-repairer",
        "worker_id": worker_id,
        "runtime_roots": runtime_roots,
        "project_repair_queue_sha256": queue_sha256,
        "repair_id": repair_id,
        "coordinator_binding": {
            "receipt_epoch": receipt_epoch,
            "coordinator_receipt_sha256": context["coordinator_receipt_sha256"],
            "context_sha256": context["context_sha256"],
        },
        "base_rust_project_ir": base_ref,
        "project_repair_context": bound_context,
        "expected_projection": {
            "status": projection.status,
            "version": projection.version,
            "attempt_count": projection.attempt_count,
            "max_attempts": projection.max_attempts,
        },
        "preflight_binding": dict(dispatch_binding),
        "model_input_policy": {
            "complete_repository": "withheld",
            "candidate_source_bodies": "withheld",
            "oracle_values": "withheld",
            "context_loading": "single-hash-bound-project-repair-context",
        },
        "output_contract": {
            "kind": context["allowed_output"]["kind"],
            "max_operations": context["allowed_output"]["max_operations"],
            "host_rebuilds_complete_ir": True,
            "semantic_acceptance": False,
        },
    }
    if native_link_reference is not None:
        request["native_link_context"] = native_link_reference
    request["effective_input_sha256"] = content_sha256(request)
    start_command = f"project-repair-start-{request['effective_input_sha256'][:24]}"
    started = ledger.start_project_repair_attempt(
        run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
        command_id=start_command, expected_status=projection.status,
        expected_version=projection.version, worker_id=worker_id,
        input_sha256=request["effective_input_sha256"],
        metadata={
            "artifact_root": f"{out_root_rel}/project-repair",
            "base_ir_sha256": ir["ir_sha256"],
            "coordinator_receipt_sha256": context["coordinator_receipt_sha256"],
            "context_sha256": context["context_sha256"],
            "preflight_sha256": dispatch_binding["preflight"]["sha256"],
            "dispatch_permit_sha256": dispatch_binding["permit_sha256"],
        },
    )
    binding = {
        "attempt_id": started.attempt_id,
        "fencing_token": started.current.version,
        "start_command_id": start_command,
        "started_state_version": started.current.version,
        "effective_input_sha256": request["effective_input_sha256"],
    }
    bound_request = {
        **request,
        "execution_binding": {**binding, "binding_sha256": content_sha256(binding)},
    }
    try:
        request_ref = write_json_artifact(
            out_root,
            f"project-repair/requests/{started.attempt_id}.json",
            bound_request,
        )
        ledger.record_project_repair_artifact(
            attempt_id=str(started.attempt_id),
            artifact_id=f"project-repair-context-{context_ref['sha256'][:24]}",
            kind="project-repair-context",
            repo_rel_path=bound_context["path"],
            content_sha256=str(context_ref["sha256"]), status="diagnostic",
            metadata={"context_sha256": context["context_sha256"]},
        )
        ledger.record_project_repair_artifact(
            attempt_id=str(started.attempt_id),
            artifact_id=f"project-repair-request-{request_ref['sha256'][:24]}",
            kind="project-repair-request",
            repo_rel_path=f"{out_root_rel}/{request_ref['path']}",
            content_sha256=str(request_ref["sha256"]), status="written",
            metadata={"effective_input_sha256": request["effective_input_sha256"]},
        )
        if native_link_reference is not None:
            ledger.record_project_repair_artifact(
                attempt_id=str(started.attempt_id),
                artifact_id=(
                    "native-link-context-"
                    + str(native_link_reference["sha256"])[:24]
                ),
                kind="native-link-context",
                repo_rel_path=str(native_link_reference["path"]),
                content_sha256=str(native_link_reference["sha256"]),
                status="diagnostic",
                metadata={
                    "context_sha256": native_link_reference["context_sha256"],
                },
            )
    except BaseException:
        ledger.recover_project_repair_attempt(
            attempt_id=str(started.attempt_id),
            command_id=f"project-repair-prelaunch-recover-{started.attempt_id}",
            expected_version=started.current.version,
            worker_id=worker_id,
            evidence_sha256=content_sha256({
                "stage": "project-repair-request-materialization",
                "attempt_id": started.attempt_id,
            }),
        )
        raise
    return {
        "schema_version": 1, "status": "attempt-started",
        "run_id": run_id, "repair_id": repair_id,
        "attempt_id": started.attempt_id,
        "attempt_applied": started.applied,
        "effective_input_sha256": request["effective_input_sha256"],
        "request": _prefix(request_ref, out_root_rel),
        "context": bound_context,
        "model_launched": False,
    }


def _validate_dispatch_binding(
    value: Mapping[str, Any], *, run_id: str, receipt_epoch: int,
    coordinator_receipt_sha256: str, queue_sha256: str, repair_id: str,
    status: str, state_version: int,
) -> None:
    payload = {key: item for key, item in value.items() if key != "permit_sha256"}
    expected = {
        "run_id": run_id, "receipt_epoch": receipt_epoch,
        "coordinator_receipt_sha256": coordinator_receipt_sha256,
        "project_repair_queue_sha256": queue_sha256,
        "repair_id": repair_id, "expected_status": status,
        "expected_state_version": state_version,
    }
    if (
        content_sha256(payload) != value.get("permit_sha256")
        or any(value.get(key) != item for key, item in expected.items())
        or not isinstance(value.get("preflight"), Mapping)
    ):
        raise ValueError("project repair dispatch permit is stale or invalid")


def read_bound_rust_project_ir(
    root: Path, reference: Mapping[str, Any],
) -> dict[str, Any]:
    data = read_artifact_reference(root, reference)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("base RustProjectIR is not UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("base RustProjectIR must be an object")
    validate_rust_project_ir(value)
    if canonical_rust_project_ir_bytes(value) != data:
        raise ValueError("base RustProjectIR artifact is not canonical")
    return value


def _prefix(reference: Mapping[str, Any], root: str) -> dict[str, Any]:
    return {**dict(reference), "path": f"{root}/{reference['path']}"}


__all__ = ["materialize_project_repair_request", "read_bound_rust_project_ir"]
