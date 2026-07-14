from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .context_frontier_cas import read_bound_frontier_cas_json
from .context_frontier_state import (
    ContextFrontierProjection,
    FRONTIER_PENDING,
    FRONTIER_READY,
    validate_context_frontier_head,
)
from .context_frontier_wave import WAVE_INPUT_POLICY
_WAVE_KIND = "context-frontier-wave-input"
_PERMIT_KIND = "context-frontier-wave-invalidation-permit"
_PERMIT_POLICY = "host-context-frontier-wave-invalidation-v1"
_CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ISSUER = object()
_WAVE_KEYS = {
    "schema_version", "artifact_kind", "policy", "run_id", "project_key", "completed_wave_index",
    "next_wave_index", "dag_sha256", "next_unit_ids", "failure_evidence",
    "failure_evidence_set_sha256", "expansion_queries", "expansion_query_set_sha256",
    "units", "claim_boundary", "sha256",
}
_UNIT_KEYS = {
    "policy", "run_id", "unit_id", "wave_index", "dag_sha256", "group_sha256", "dependency_closure_sha256",
    "failure_fact_set_sha256", "expansion_query_set_sha256", "selection_seed_sha256",
    "failure_evidence_sha256s", "expansion_query_sha256s",
}
_SEED_KEYS = (
    "policy", "run_id", "unit_id", "wave_index", "dag_sha256", "group_sha256", "dependency_closure_sha256",
    "failure_fact_set_sha256", "expansion_query_set_sha256",
)
_PERMIT_KEYS = {
    "schema_version", "artifact_kind", "policy", "run_id", "unit_id", "expected_status", "expected_version",
    "expected_head_sha256", "next_wave_index", "next_query_epoch", "dag_sha256", "group_sha256",
    "dependency_closure_sha256", "failure_fact_set_sha256", "expansion_query_set_sha256",
    "selection_seed_sha256", "limits", "selection_input_sha256", "wave_input", "wave_input_sha256",
    "claim_boundary", "permit_sha256",
}
class _HostContextFrontierWavePermit:
    __slots__ = ("_authority", "_binding")

    def __init__(self, authority: object, binding: Mapping[str, Any]) -> None:
        if authority is not _ISSUER:
            raise TypeError("context frontier wave permits are host-issued")
        self._authority = authority
        self._binding = dict(binding)
def _issue_host_context_frontier_wave_permit(
    wave_input: Mapping[str, Any],
    wave_input_reference: Mapping[str, Any],
    current_projection: ContextFrontierProjection,
) -> _HostContextFrontierWavePermit:
    wave = _validate_wave_input(wave_input)
    reference = _payload_reference(wave_input_reference, wave)
    payload = _permit_payload(wave, reference, current_projection)
    return _HostContextFrontierWavePermit(
        _ISSUER, {**payload, "permit_sha256": content_sha256(payload)},
    )
def _reopen_host_context_frontier_wave_permit(
    permit: _HostContextFrontierWavePermit, *, harness_root: Path,
    current_projection: ContextFrontierProjection,
) -> dict[str, Any]:
    binding = _host_context_frontier_wave_binding(permit)
    wave = _validate_wave_input(read_bound_frontier_cas_json(
        Path(harness_root), binding["wave_input"], _WAVE_KIND,
    ))
    expected = _permit_payload(wave, binding["wave_input"], current_projection)
    actual = {key: value for key, value in binding.items() if key != "permit_sha256"}
    if actual != expected:
        raise ValueError("context frontier wave permit is stale or identity-drifted")
    target = _pending_target(current_projection, expected)
    return {**binding, "wave_input_payload": wave, "target_head": target}
def _host_context_frontier_wave_binding(
    permit: _HostContextFrontierWavePermit,
) -> dict[str, Any]:
    if type(permit) is not _HostContextFrontierWavePermit or permit._authority is not _ISSUER:
        raise TypeError("context frontier wave permit is not host-issued")
    binding = dict(permit._binding)
    if set(binding) != _PERMIT_KEYS:
        raise ValueError("context frontier wave permit shape drifted")
    payload = {key: value for key, value in binding.items() if key != "permit_sha256"}
    if content_sha256(payload) != binding.get("permit_sha256"):
        raise ValueError("context frontier wave permit binding drifted")
    return binding
def _permit_payload(
    wave: Mapping[str, Any], reference: Mapping[str, Any],
    current: ContextFrontierProjection,
) -> dict[str, Any]:
    projection = _ready_projection(current)
    head = projection.head
    unit_id = head["unit_id"]
    if wave["run_id"] != head["run_id"]:
        raise ValueError("context frontier wave run identity drifted")
    units = {item["unit_id"]: item for item in wave["units"]}
    if unit_id not in units:
        raise ValueError("context frontier unit is outside the next wave")
    unit = units[unit_id]
    limits = dict(head["input_binding"]["limits"])
    input_binding = {
        "dag_sha256": unit["dag_sha256"],
        "group_sha256": unit["group_sha256"],
        "failure_fact_set_sha256": unit["failure_fact_set_sha256"],
        "selection_seed_sha256": unit["selection_seed_sha256"],
        "limits": limits,
    }
    return {
        "schema_version": 1,
        "artifact_kind": _PERMIT_KIND,
        "policy": _PERMIT_POLICY,
        "run_id": head["run_id"],
        "unit_id": unit_id,
        "expected_status": FRONTIER_READY,
        "expected_version": projection.version,
        "expected_head_sha256": projection.head_sha256,
        "next_wave_index": wave["next_wave_index"],
        "next_query_epoch": head["query_epoch"] + 1,
        "dag_sha256": unit["dag_sha256"],
        "group_sha256": unit["group_sha256"],
        "dependency_closure_sha256": unit["dependency_closure_sha256"],
        "failure_fact_set_sha256": unit["failure_fact_set_sha256"],
        "expansion_query_set_sha256": unit["expansion_query_set_sha256"],
        "selection_seed_sha256": unit["selection_seed_sha256"],
        "limits": limits,
        "selection_input_sha256": content_sha256(input_binding),
        "wave_input": dict(reference),
        "wave_input_sha256": wave["sha256"],
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
def _pending_target(
    current: ContextFrontierProjection, binding: Mapping[str, Any],
) -> dict[str, Any]:
    input_binding = {
        "dag_sha256": binding["dag_sha256"],
        "group_sha256": binding["group_sha256"],
        "failure_fact_set_sha256": binding["failure_fact_set_sha256"],
        "selection_seed_sha256": binding["selection_seed_sha256"],
        "limits": dict(binding["limits"]),
    }
    target = {
        **current.head,
        "schema_version": 2,
        "status": FRONTIER_PENDING,
        "mode": "host_retrieval",
        "query_epoch": binding["next_query_epoch"],
        "input_binding": input_binding,
        "selection_input_sha256": binding["selection_input_sha256"],
        "context_overlay": None,
        "selection_receipt_sha256": None,
        "materialized_page_set_sha256": None,
        "selection_materialization_sha256": None,
    }
    return validate_context_frontier_head(target)
def _ready_projection(value: Any) -> ContextFrontierProjection:
    if type(value) is not ContextFrontierProjection:
        raise TypeError("context frontier wave requires an exact projection")
    head = validate_context_frontier_head(value.head)
    if (
        value.status != FRONTIER_READY or head["status"] != FRONTIER_READY
        or head["mode"] != "host_retrieval"
        or isinstance(value.version, bool) or not isinstance(value.version, int)
        or value.version < 0 or value.head_sha256 != content_sha256(head)
    ):
        raise ValueError("context frontier wave requires a bound ready host projection")
    return ContextFrontierProjection(value.status, value.version, head, value.head_sha256)
def _validate_wave_input(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _WAVE_KEYS:
        raise ValueError("context frontier wave input shape is invalid")
    wave = dict(value)
    if (
        wave.get("schema_version") != 1 or wave.get("artifact_kind") != _WAVE_KIND
        or wave.get("policy") != WAVE_INPUT_POLICY
        or wave.get("claim_boundary") != _CLAIM_BOUNDARY
        or not _text(wave.get("run_id")) or not _text(wave.get("project_key"))
        or not _sha(wave.get("dag_sha256")) or not _sha(wave.get("sha256"))
    ):
        raise ValueError("context frontier wave input header is invalid")
    completed = _count(wave.get("completed_wave_index"))
    next_wave = _count(wave.get("next_wave_index"))
    if next_wave != completed + 1:
        raise ValueError("context frontier wave indexes are invalid")
    failures = _descriptors(wave.get("failure_evidence"), failure=True)
    queries = _descriptors(wave.get("expansion_queries"), failure=False)
    if len({item["sequence"] for item in failures}) != len(failures) or len({item["unit_id"] for item in queries}) != len(queries):
        raise ValueError("context frontier wave descriptor identity is duplicated")
    if (
        wave.get("failure_evidence_set_sha256") != content_sha256(failures)
        or wave.get("expansion_query_set_sha256") != content_sha256(queries)
    ):
        raise ValueError("context frontier wave descriptor set drifted")
    ids = _string_list(wave.get("next_unit_ids"), "next unit ids", allow_empty=False)
    if ids != sorted(ids) or any(item["unit_id"] not in ids for item in queries):
        raise ValueError("context frontier next unit ids are not canonical")
    units_raw = wave.get("units")
    if not isinstance(units_raw, list) or len(units_raw) != len(ids):
        raise ValueError("context frontier wave units shape is invalid")
    failure_hashes = {item["sha256"] for item in failures}
    query_by_unit = {item["unit_id"]: item["sha256"] for item in queries}
    units = [
        _validate_unit(item, wave, unit_id, failure_hashes, query_by_unit)
        for item, unit_id in zip(units_raw, ids, strict=True)
    ]
    if [item["unit_id"] for item in units] != ids:
        raise ValueError("context frontier wave unit order drifted")
    payload = {key: item for key, item in wave.items() if key != "sha256"}
    if content_sha256(payload) != wave["sha256"]:
        raise ValueError("context frontier wave input SHA-256 drifted")
    return wave
def _validate_unit(
    value: Any, wave: Mapping[str, Any], unit_id: str,
    failure_hashes: set[str], query_by_unit: Mapping[str, str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _UNIT_KEYS:
        raise ValueError("context frontier wave unit shape is invalid")
    unit = dict(value)
    if (
        unit.get("policy") != WAVE_INPUT_POLICY or unit.get("run_id") != wave["run_id"]
        or unit.get("unit_id") != unit_id or unit.get("wave_index") != wave["next_wave_index"]
        or unit.get("dag_sha256") != wave["dag_sha256"]
        or not all(_sha(unit.get(key)) for key in _UNIT_KEYS if key.endswith("_sha256"))
    ):
        raise ValueError("context frontier wave unit binding is invalid")
    failures = _sha_list(unit.get("failure_evidence_sha256s"), "unit failures")
    queries = _sha_list(unit.get("expansion_query_sha256s"), "unit queries")
    if not set(failures).issubset(failure_hashes) or len(queries) > 1:
        raise ValueError("context frontier wave unit evidence scope is invalid")
    expected_query = query_by_unit.get(unit_id)
    if queries != ([] if expected_query is None else [expected_query]):
        raise ValueError("context frontier wave unit query scope drifted")
    if (
        unit["failure_fact_set_sha256"] != content_sha256(failures)
        or unit["expansion_query_set_sha256"] != content_sha256(queries)
        or unit["selection_seed_sha256"]
        != content_sha256({key: unit[key] for key in _SEED_KEYS})
    ):
        raise ValueError("context frontier wave unit selection seed drifted")
    return unit
def _descriptors(value: Any, *, failure: bool) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 4096:
        raise ValueError("context frontier wave descriptors are invalid")
    keys = {"sequence", "unit_id", "gate_family", "sha256"} if failure else {
        "unit_id", "query_epoch", "sha256",
    }
    result = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != keys or not _text(item.get("unit_id")) or not _sha(item.get("sha256")):
            raise ValueError("context frontier wave descriptor shape is invalid")
        if failure:
            if not _text(item.get("gate_family")):
                raise ValueError("context frontier failure descriptor is invalid")
            _count(item.get("sequence"))
        else:
            _count(item.get("query_epoch"))
        result.append(dict(item))
    key = (lambda item: (item["unit_id"], item["gate_family"], item["sequence"])) if failure else (lambda item: item["unit_id"])
    if result != sorted(result, key=key) or len({content_sha256(item) for item in result}) != len(result):
        raise ValueError("context frontier wave descriptors are not canonical")
    return result
def _payload_reference(value: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size_bytes"}:
        raise ValueError("context frontier wave input reference shape is invalid")
    path = checked_relative_path(str(value.get("path", "")))
    encoded = canonical_json_bytes(payload)
    digest = hashlib.sha256(encoded).hexdigest()
    reference = {"path": path, "sha256": value.get("sha256"), "size_bytes": value.get("size_bytes")}
    expected_tail = ("context", "frontier-cas", _WAVE_KIND, "sha256", digest[:2], f"{digest}.json")
    parts = PurePosixPath(path).parts
    matches = [index for index in range(len(parts) - 5) if parts[index:index + 6] == expected_tail]
    if reference["sha256"] != digest or reference["size_bytes"] != len(encoded) or len(matches) != 1:
        raise ValueError("context frontier wave input reference binding drifted")
    return reference
def _sha_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 4096 or any(not _sha(item) for item in value):
        raise ValueError(f"context frontier {label} are invalid")
    if value != sorted(value) or len(set(value)) != len(value):
        raise ValueError(f"context frontier {label} are not canonical")
    return list(value)
def _string_list(value: Any, label: str, *, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or len(value) > 4096 or (not allow_empty and not value) or any(not _text(item) for item in value):
        raise ValueError(f"context frontier {label} are invalid")
    if len(set(value)) != len(value):
        raise ValueError(f"context frontier {label} are duplicated")
    return list(value)
def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("context frontier wave count is invalid")
    return value
def _text(value: Any) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 256

def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None

__all__: list[str] = []
