from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OVERLAY_KEYS = {
    "schema_version", "artifact_kind", "run_id", "unit_id", "query_epoch",
    "plan_sha256", "assignment_digests", "assignment_set_sha256",
    "base_frontier", "refresh_bundle", "effective_context",
    "selection_receipt_sha256", "materialized_page_set_sha256",
    "selection_materialization_sha256", "context_sha256", "claim_boundary",
}
_ASSIGNMENT_DIGEST_KEYS = {"unit_id", "role", "worker_id", "assignment_sha256"}
_BASE_FRONTIER_KEYS = {"state_version", "head_sha256", "catalog"}
_REFERENCE_KEYS = {"path", "sha256", "size_bytes"}
_OUTPUT_SHA_FIELDS = (
    "selection_receipt_sha256", "materialized_page_set_sha256",
    "selection_materialization_sha256")
_CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}


def build_context_frontier_overlay(
    assignments: Sequence[Mapping[str, Any]], base_frontier: Mapping[str, Any], *,
    plan_sha256: str, refresh_bundle: Mapping[str, Any],
    effective_context: Mapping[str, Any],
    query_epoch: int | None = None,
) -> dict[str, Any]:
    records, run_id, unit_id = _assignment_records(assignments)
    base = _base_frontier(base_frontier)
    frontier_epoch = _nonnegative_int(
        base_frontier.get("query_epoch"), "base frontier query_epoch",
    )
    epoch = frontier_epoch if query_epoch is None else _nonnegative_int(
        query_epoch, "query_epoch",
    )
    if epoch != frontier_epoch:
        raise ValueError("context frontier overlay query epoch drifted")
    if "run_id" in base_frontier and base_frontier.get("run_id") != run_id:
        raise ValueError("context frontier overlay run binding drifted")
    if "unit_id" in base_frontier and base_frontier.get("unit_id") != unit_id:
        raise ValueError("context frontier overlay unit binding drifted")
    context = _json_object(effective_context, "effective_context")
    _reference(context.get("catalog"), "effective context catalog")
    outputs = _context_outputs(context)
    payload = {
        "schema_version": 1,
        "artifact_kind": "context-frontier-overlay",
        "run_id": run_id,
        "unit_id": unit_id,
        "query_epoch": epoch,
        "plan_sha256": _sha256(plan_sha256, "plan_sha256"),
        "assignment_digests": records,
        "assignment_set_sha256": content_sha256(records),
        "base_frontier": base,
        "refresh_bundle": _reference(refresh_bundle, "refresh_bundle"),
        "effective_context": context,
        **outputs,
        "context_sha256": content_sha256(context),
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return validate_context_frontier_overlay(payload)

def validate_context_frontier_overlay(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _OVERLAY_KEYS:
        raise ValueError("context frontier overlay fields are invalid")
    overlay = _json_object(value, "context frontier overlay")
    schema = overlay["schema_version"]
    if (
        isinstance(schema, bool) or schema != 1
        or overlay["artifact_kind"] != "context-frontier-overlay"
    ):
        raise ValueError("context frontier overlay identity is invalid")
    _text(overlay["run_id"], "run_id")
    unit_id = _text(overlay["unit_id"], "unit_id")
    _nonnegative_int(overlay["query_epoch"], "query_epoch")
    _sha256(overlay["plan_sha256"], "plan_sha256")

    records = _validate_assignment_records(overlay["assignment_digests"], unit_id)
    assignment_set = _sha256(overlay["assignment_set_sha256"], "assignment_set_sha256")
    if assignment_set != content_sha256(records):
        raise ValueError("context frontier overlay assignment set SHA-256 drifted")

    if not isinstance(overlay["base_frontier"], Mapping) or set(overlay["base_frontier"]) != _BASE_FRONTIER_KEYS:
        raise ValueError("context frontier overlay base frontier fields are invalid")
    base = _base_frontier(overlay["base_frontier"])
    refresh = _reference(overlay["refresh_bundle"], "refresh_bundle")
    context = _json_object(overlay["effective_context"], "effective_context")
    _reference(context.get("catalog"), "effective context catalog")
    outputs = _context_outputs(context)
    for field in _OUTPUT_SHA_FIELDS:
        claimed = _sha256(overlay[field], field)
        if claimed != outputs[field]:
            raise ValueError(f"context frontier overlay {field} drifted")
    context_sha = _sha256(overlay["context_sha256"], "context_sha256")
    if context_sha != content_sha256(context):
        raise ValueError("context frontier overlay effective context SHA-256 drifted")
    if not _valid_claim_boundary(overlay["claim_boundary"]):
        raise ValueError("context frontier overlay claim boundary is invalid")
    return {
        **overlay,
        "assignment_digests": records,
        "base_frontier": base,
        "refresh_bundle": refresh,
        "effective_context": context,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }

def resolve_effective_context(
    assignment: Mapping[str, Any], frontier: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    value = validate_context_frontier_overlay(overlay)
    if not isinstance(assignment, Mapping):
        raise ValueError("context frontier overlay assignment is invalid")
    run_id = _text(assignment.get("run_id"), "assignment run_id")
    unit_id = _text(assignment.get("unit_id"), "assignment unit_id")
    role = _text(assignment.get("role"), "assignment role")
    worker_id = _text(assignment.get("worker_id"), "assignment worker_id")
    if run_id != value["run_id"] or unit_id != value["unit_id"]:
        raise ValueError("context frontier overlay assignment unit binding drifted")
    if "group_id" in assignment and assignment.get("group_id") != unit_id:
        raise ValueError("context frontier overlay assignment group binding drifted")
    record = {
        "unit_id": unit_id,
        "role": role,
        "worker_id": worker_id,
        "assignment_sha256": content_sha256(dict(assignment)),
    }
    if record not in value["assignment_digests"]:
        raise ValueError("context frontier overlay assignment digest is not allowed")

    if not isinstance(frontier, Mapping):
        raise ValueError("context frontier overlay frontier is invalid")
    overlay_ref = _reference(frontier.get("context_overlay"), "context_overlay")
    encoded = canonical_json_bytes(value)
    if (
        overlay_ref["sha256"] != content_sha256(value)
        or overlay_ref["size_bytes"] != len(encoded)
    ):
        raise ValueError("context frontier overlay reference identity drifted")
    _validate_frontier_binding(frontier, value)
    return _json_object(value["effective_context"], "effective_context")

def _assignment_records(assignments: Sequence[Mapping[str, Any]]) -> tuple[
    list[dict[str, str]], str, str,
]:
    if (
        isinstance(assignments, (str, bytes, Mapping))
        or not isinstance(assignments, Sequence) or not assignments
    ):
        raise ValueError("context frontier overlay assignments are invalid")
    records: list[dict[str, str]] = []
    run_id: str | None = None
    unit_id: str | None = None
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise ValueError("context frontier overlay assignment is invalid")
        current_run = _text(assignment.get("run_id"), "assignment run_id")
        current_unit = _text(assignment.get("unit_id"), "assignment unit_id")
        if run_id is None:
            run_id, unit_id = current_run, current_unit
        if current_run != run_id or current_unit != unit_id:
            raise ValueError("context frontier overlay assignments span units")
        if "group_id" in assignment and assignment.get("group_id") != current_unit:
            raise ValueError("context frontier overlay assignment group binding drifted")
        records.append({
            "unit_id": current_unit,
            "role": _text(assignment.get("role"), "assignment role"),
            "worker_id": _text(assignment.get("worker_id"), "assignment worker_id"),
            "assignment_sha256": content_sha256(dict(assignment)),
        })
    records.sort(key=lambda item: (item["role"], item["worker_id"]))
    normalized = _validate_assignment_records(records, unit_id)
    assert run_id is not None and unit_id is not None
    return normalized, run_id, unit_id

def _validate_assignment_records(value: Any, unit_id: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("context frontier overlay assignment digests are invalid")
    records: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _ASSIGNMENT_DIGEST_KEYS:
            raise ValueError("context frontier overlay assignment digest fields are invalid")
        records.append({
            "unit_id": _text(item.get("unit_id"), "assignment digest unit_id"),
            "role": _text(item.get("role"), "assignment digest role"),
            "worker_id": _text(item.get("worker_id"), "assignment digest worker_id"),
            "assignment_sha256": _sha256(
                item.get("assignment_sha256"), "assignment_sha256",
            ),
        })
    keys = [(item["role"], item["worker_id"]) for item in records]
    if any(item["unit_id"] != unit_id for item in records):
        raise ValueError("context frontier overlay assignment digests span units")
    if (keys != sorted(keys)
            or len({item["role"] for item in records}) != len(records)
            or len({item["worker_id"] for item in records}) != len(records)):
        raise ValueError("context frontier overlay assignment digests are not canonical")
    return records

def _base_frontier(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("context frontier overlay base frontier is invalid")
    if set(value) == _BASE_FRONTIER_KEYS:
        source = value
    elif _BASE_FRONTIER_KEYS.issubset(value):
        source = {key: value[key] for key in _BASE_FRONTIER_KEYS}
    else:
        raise ValueError("context frontier overlay base frontier fields are invalid")
    return {
        "state_version": _nonnegative_int(
            source.get("state_version"), "base frontier state_version",
        ),
        "head_sha256": _sha256(source.get("head_sha256"), "base frontier head_sha256"),
        "catalog": _reference(source.get("catalog"), "base frontier catalog"),
    }


def _context_outputs(context: Mapping[str, Any]) -> dict[str, str]:
    retrieval = context.get("retrieval")
    if not isinstance(retrieval, Mapping):
        raise ValueError("context frontier overlay effective retrieval is invalid")
    return {
        field: _sha256(retrieval.get(field), f"effective context {field}")
        for field in _OUTPUT_SHA_FIELDS
    }


def _validate_frontier_binding(
    frontier: Mapping[str, Any], overlay: Mapping[str, Any],
) -> None:
    if _nonnegative_int(frontier.get("query_epoch"), "frontier query_epoch") != overlay["query_epoch"]:
        raise ValueError("context frontier overlay frontier epoch drifted")
    if _reference(frontier.get("catalog"), "frontier catalog") != overlay["effective_context"]["catalog"]:
        raise ValueError("context frontier overlay frontier catalog drifted")
    for field in _OUTPUT_SHA_FIELDS:
        if _sha256(frontier.get(field), f"frontier {field}") != overlay[field]:
            raise ValueError(f"context frontier overlay frontier {field} drifted")
    if "run_id" in frontier and frontier.get("run_id") != overlay["run_id"]:
        raise ValueError("context frontier overlay frontier run binding drifted")
    if "unit_id" in frontier and frontier.get("unit_id") != overlay["unit_id"]:
        raise ValueError("context frontier overlay frontier unit binding drifted")


def _reference(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REFERENCE_KEYS:
        raise ValueError(f"context frontier overlay {label} reference fields are invalid")
    path = checked_relative_path(value.get("path"))
    size = _nonnegative_int(value.get("size_bytes"), f"{label} size_bytes")
    return {"path": path, "sha256": _sha256(
        value.get("sha256"), f"{label} sha256"), "size_bytes": size}


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    try:
        result = json.loads(canonical_json_bytes(dict(value)).decode("utf-8"))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not canonical JSON data") from error
    if not isinstance(result, dict):
        raise ValueError(f"{label} must be an object")
    return result


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"context frontier overlay {label} is not a lowercase SHA-256")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"context frontier overlay {label} is invalid")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"context frontier overlay {label} must be non-negative")
    return value


def _valid_claim_boundary(value: Any) -> bool:
    return (
        isinstance(value, Mapping) and set(value) == set(_CLAIM_BOUNDARY)
        and value.get("semantic_gate") is False
        and type(value.get("translation_coverage_numerator")) is int
        and value.get("translation_coverage_numerator") == 0
    )


__all__ = ["build_context_frontier_overlay", "resolve_effective_context",
           "validate_context_frontier_overlay"]
