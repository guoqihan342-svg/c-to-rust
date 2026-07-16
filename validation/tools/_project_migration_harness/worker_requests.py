from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .artifacts import content_sha256, write_json_artifact
from .candidate_admission import candidate_admission_metadata


def materialize_worker_requests(
    schedule: Mapping[str, Any],
    *,
    out_root: Path,
    out_root_rel: str,
    context_materialization: Mapping[str, Any],
) -> list[dict[str, Any]]:
    ready = schedule.get("ready")
    if not isinstance(ready, list):
        raise ValueError("schedule.ready must be an array")
    if (
        not isinstance(context_materialization, Mapping)
        or set(context_materialization) != {"path", "sha256", "size_bytes"}
    ):
        raise ValueError("context materialization reference is invalid")
    results = []
    for item in ready:
        if not isinstance(item, Mapping) or not isinstance(item.get("assignment"), Mapping):
            raise ValueError("ready schedule entry must bind an assignment")
        assignment = dict(item["assignment"])
        worker_id = _portable_id(assignment.get("worker_id"), "worker_id")
        role = _portable_id(assignment.get("role"), "role")
        launch_policy = assignment.get("launch_policy")
        request = {
            "schema_version": 1,
            "request_kind": "project_migration_worker",
            "run_id": assignment.get("run_id"),
            "worker_id": worker_id,
            "role": role,
            "group_id": assignment.get("group_id"),
            "unit_id": assignment.get("unit_id"),
            "wave_index": assignment.get("wave_index"),
            "assignment_binding": {
                "assignment_sha256": content_sha256(assignment),
                "group_sha256": assignment.get("group_sha256"),
                "ledger_binding_sha256": assignment.get("ledger_binding", {}).get(
                    "binding_sha256"
                ),
            },
            "dependencies": assignment.get("dependencies", []),
            "context": item.get("effective_context", assignment.get("context")),
            "context_materialization": dict(context_materialization),
            "context_frontier": item.get("context_frontier"),
            "launch_claim": item.get("launch_claim"),
            "schedule_sha256": schedule.get("schedule_sha256"),
            "launch_policy": launch_policy,
            "repair_mode": item.get("repair_mode"),
            "input_facts": item.get("input_facts", {}),
            "runtime_roots": assignment.get("runtime_roots"),
            "max_attempts": assignment.get("max_attempts"),
            "authority": assignment.get("authority"),
            "model_input_policy": {
                "oracle_values": "withheld",
                "expected_actual": "withheld",
                "context_loading": "hash_bound_pages_only",
                "test_contract": "shape_and_input_dependencies_only",
            },
            "output_contract": _output_contract(role, launch_policy),
        }
        request["effective_input_sha256"] = content_sha256(request)
        base = f"harness/assignments/{worker_id}"
        assignment_ref = write_json_artifact(out_root, f"{base}.json", assignment)
        request_ref = write_json_artifact(out_root, f"{base}-request.json", request)
        results.append({
            "worker_id": worker_id,
            "role": role,
            "assignment": _prefix(assignment_ref, out_root_rel),
            "request": _prefix(request_ref, out_root_rel),
            "effective_input_sha256": request["effective_input_sha256"],
        })
    return results


def _output_contract(role: str, launch_policy: Any) -> dict[str, Any]:
    if role == "planner":
        contract = {
            "kind": "hash_bound_boundary_route_decision",
            "required": ["decision"],
            "allowed_decisions": [
                "translate_with_context",
                "preserve_ffi_boundary",
                "refuse_with_reason",
            ],
            "semantic_acceptance": False,
        }
    if role == "translator":
        contract = {
            "kind": "complete_group_candidate",
            "required": ["candidate_source"],
            "host_derived": [
                "public_symbols", "required_symbols", "unsafe_count",
                "boundary_manifest",
            ],
            "semantic_acceptance": False,
        }
    if role == "reviewer":
        contract = {
            "kind": "bounded_structural_review",
            "required": ["candidate_artifact_sha256", "findings"],
            "semantic_acceptance": False,
        }
    if role == "repairer":
        contract = {
            "kind": "complete_group_candidate_replacement",
            "required": ["failed_gate_result_sha256", "candidate_source"],
            "host_derived": [
                "public_symbols", "required_symbols", "unsafe_count",
                "boundary_manifest",
            ],
            "semantic_acceptance": False,
        }
    if role not in {"planner", "translator", "reviewer", "repairer"}:
        raise ValueError("unsupported worker role")
    contract.update(candidate_admission_metadata(launch_policy))
    return contract


def _portable_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or any(
        not (char.isascii() and (char.isalnum() or char in "-_")) for char in value
    ):
        raise ValueError(f"{field} must be a portable identifier")
    return value


def _prefix(reference: Mapping[str, Any], root: str) -> dict[str, Any]:
    return {**dict(reference), "path": f"{root}/{reference['path']}"}


def bind_attempt_request(
    request: Mapping[str, Any], *, attempt_id: str, fencing_token: int,
    lease_ttl_seconds: int,
) -> dict[str, Any]:
    if "execution_binding" in request:
        raise ValueError("worker request is already attempt-bound")
    if not attempt_id or fencing_token < 1 or lease_ttl_seconds < 30:
        raise ValueError("attempt execution binding is invalid")
    effective = request.get("effective_input_sha256")
    if not isinstance(effective, str):
        raise ValueError("worker request effective input binding is missing")
    payload = {
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "lease_ttl_seconds": lease_ttl_seconds,
        "effective_input_sha256": effective,
    }
    return {
        **dict(request),
        "execution_binding": {**payload, "binding_sha256": content_sha256(payload)},
    }


__all__ = ["bind_attempt_request", "materialize_worker_requests"]
