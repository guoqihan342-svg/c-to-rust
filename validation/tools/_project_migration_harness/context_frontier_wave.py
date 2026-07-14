from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .gate_authority import candidate_kind, validate_candidate_verdict
from .portfolio_integrity import (
    canonical_dag, canonical_group, dependencies_by_group, groups_by_id,
    wave_layout,
)


WAVE_INPUT_POLICY = "host-context-frontier-wave-v1"
EXPANSION_QUERY_POLICY = "host-context-expansion-v1"
CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_QUERY_KEYS = {
    "schema_version", "artifact_kind", "policy", "run_id", "unit_id",
    "query_epoch", "requests", "claim_boundary", "sha256",
}
_MAX_ITEMS = 4096
_MAX_REQUESTS = 64
def build_context_expansion_query(
    *, run_id: str, unit_id: str, query_epoch: int,
    requests: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    run_id = _text(run_id, "expansion query run_id")
    unit_id = _text(unit_id, "expansion query unit_id")
    query_epoch = _count(query_epoch, "expansion query epoch")
    entries = _array(requests, "expansion query requests", _MAX_REQUESTS)
    if not entries:
        raise ValueError("expansion query requires at least one request")
    normalized = [_request(item) for item in entries]
    ordered = sorted(normalized, key=lambda item: (item["family"], content_sha256(item)))
    if len({content_sha256(item) for item in ordered}) != len(ordered):
        raise ValueError("expansion query requests are duplicated")
    payload = {
        "schema_version": 1,
        "artifact_kind": "context-frontier-expansion-query",
        "policy": EXPANSION_QUERY_POLICY,
        "run_id": run_id,
        "unit_id": unit_id,
        "query_epoch": query_epoch,
        "requests": ordered,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    return {**payload, "sha256": content_sha256(payload)}
def validate_context_expansion_query(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _QUERY_KEYS:
        raise ValueError("context expansion query shape is invalid")
    rebuilt = build_context_expansion_query(
        run_id=value.get("run_id"), unit_id=value.get("unit_id"),
        query_epoch=value.get("query_epoch"), requests=value.get("requests"),
    )
    if dict(value) != rebuilt:
        raise ValueError("context expansion query binding drifted")
    return rebuilt
def derive_context_frontier_wave_input(
    latest_dag: Mapping[str, Any], *, completed_wave_index: int,
    failure_evidence: Sequence[Mapping[str, Any]],
    expansion_queries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    completed = _count(completed_wave_index, "completed wave index")
    dag = _dag(latest_dag)
    next_wave = completed + 1
    if completed >= len(dag["layout"]) or next_wave >= len(dag["layout"]):
        raise ValueError("latest DAG has no next wave after the completed wave")
    failures = _latest_failures(
        failure_evidence, run_id=dag["run_id"], membership=dag["membership"],
        completed_wave_index=completed,
    )
    targets = dag["layout"][next_wave]
    queries = _latest_queries(
        expansion_queries, run_id=dag["run_id"], target_ids=set(targets),
    )
    failure_items = sorted(failures.values(), key=lambda item: (
        item["unit_id"], item["gate_family"], item["sequence"],
    ))
    query_items = [
        {"unit_id": unit_id, "query_epoch": query["query_epoch"],
         "sha256": query["sha256"]}
        for unit_id, query in sorted(queries.items())
    ]
    units = [
        _unit_input(unit_id, next_wave, dag, failure_items, queries.get(unit_id))
        for unit_id in targets
    ]
    payload = {
        "schema_version": 1,
        "artifact_kind": "context-frontier-wave-input",
        "policy": WAVE_INPUT_POLICY,
        "run_id": dag["run_id"],
        "project_key": dag["project_key"],
        "completed_wave_index": completed,
        "next_wave_index": next_wave,
        "dag_sha256": dag["dag_sha256"],
        "next_unit_ids": list(targets),
        "failure_evidence": failure_items,
        "failure_evidence_set_sha256": content_sha256(failure_items),
        "expansion_queries": query_items,
        "expansion_query_set_sha256": content_sha256(query_items),
        "units": units,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    return {**payload, "sha256": content_sha256(payload)}
def _unit_input(
    unit_id: str, wave: int, dag: Mapping[str, Any],
    failures: Sequence[Mapping[str, Any]], query: Mapping[str, Any] | None,
) -> dict[str, Any]:
    closure = _closure(unit_id, dag["dependencies"])
    relevant = [item for item in failures if item["unit_id"] in closure]
    failure_hashes = sorted(item["sha256"] for item in relevant)
    if query is not None:
        _query_scope(
            query, direct_dependencies=set(dag["dependencies"][unit_id]),
            failure_hashes=set(failure_hashes),
        )
    query_hashes = [] if query is None else [query["sha256"]]
    seed = {
        "policy": WAVE_INPUT_POLICY,
        "run_id": dag["run_id"],
        "unit_id": unit_id,
        "wave_index": wave,
        "dag_sha256": dag["dag_sha256"],
        "group_sha256": dag["groups"][unit_id]["content_sha256"],
        "dependency_closure_sha256": content_sha256(sorted(closure)),
        "failure_fact_set_sha256": content_sha256(failure_hashes),
        "expansion_query_set_sha256": content_sha256(query_hashes),
    }
    return {
        **seed,
        "failure_evidence_sha256s": failure_hashes,
        "expansion_query_sha256s": query_hashes,
        "selection_seed_sha256": content_sha256(seed),
    }
def _dag(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("latest DAG must be an object")
    if value.get("schema_version") != 1 or value.get("claim_boundary") != CLAIM_BOUNDARY:
        raise ValueError("latest DAG header or claim boundary is invalid")
    run_id = _text(value.get("run_id"), "latest DAG run_id")
    project_key = _text(value.get("project_key"), "latest DAG project_key")
    groups = groups_by_id(value)
    if list(groups) != sorted(groups):
        raise ValueError("latest DAG groups are not canonical")
    layout, membership = wave_layout(value, groups)
    for index, (raw, ids) in enumerate(zip(value["waves"], layout, strict=True)):
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"wave_index", "group_ids"}
            or raw.get("wave_index") != index
            or not ids or ids != sorted(ids)
        ):
            raise ValueError("latest DAG waves are not canonical")
    dependencies = dependencies_by_group(groups, membership)
    canonical_groups = []
    for raw in value["groups"]:
        group_id = raw["group_id"]
        deps = dependencies[group_id]
        if deps != sorted(deps) or any(membership[item] >= membership[group_id] for item in deps):
            raise ValueError("latest DAG dependencies are not canonical earlier-wave edges")
        context = raw.get("context_pack")
        if context is not None and not isinstance(context, Mapping):
            raise ValueError("latest DAG group context is invalid")
        payload, digest = canonical_group(raw, deps, context)
        if raw.get("content_sha256") != digest:
            raise ValueError("latest DAG group binding drifted")
        canonical_groups.append({**payload, "content_sha256": digest})
    digest = value.get("dag_sha256")
    if not _sha(digest) or digest != canonical_dag(value, canonical_groups):
        raise ValueError("latest DAG SHA-256 drifted")
    return {
        "run_id": run_id, "project_key": project_key, "dag_sha256": digest,
        "groups": groups, "layout": layout, "membership": membership,
        "dependencies": dependencies,
    }
def _latest_failures(
    values: Any, *, run_id: str, membership: Mapping[str, int],
    completed_wave_index: int,
) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    sequences: set[int] = set()
    for entry in _array(values, "failure evidence", _MAX_ITEMS):
        if not isinstance(entry, Mapping) or set(entry) != {"sequence", "sha256", "evidence"}:
            raise ValueError("failure evidence wrapper shape is invalid")
        sequence = _count(entry.get("sequence"), "failure evidence sequence")
        if sequence in sequences:
            raise ValueError("failure evidence sequence is duplicated")
        sequences.add(sequence)
        evidence = entry.get("evidence")
        if not isinstance(evidence, Mapping) or evidence.get("status") != "failed":
            raise ValueError("failure evidence must be a failed host verdict")
        if not _sha(entry.get("sha256")) or entry["sha256"] != content_sha256(evidence):
            raise ValueError("failure evidence SHA-256 drifted")
        unit_id = _text(evidence.get("unit_id"), "failure evidence unit_id")
        family = _text(evidence.get("gate_family"), "failure evidence gate_family")
        if evidence.get("run_id") != run_id or membership.get(unit_id, 10**9) > completed_wave_index:
            raise ValueError("failure evidence is outside the completed DAG frontier")
        validate_candidate_verdict(
            evidence, run_id=run_id, unit_id=unit_id,
            candidate_artifact_id=evidence.get("candidate_artifact_id"),
            candidate_sha256=evidence.get("candidate_sha256"), gate_family=family,
            candidate_set_sha256=evidence.get("candidate_set_sha256"),
            status="failed", verifier_id=evidence.get("authority_id"),
            kind=candidate_kind(family),
        )
        descriptor = {
            "sequence": sequence, "unit_id": unit_id, "gate_family": family,
            "sha256": entry["sha256"],
        }
        key = (unit_id, family)
        if key not in latest or sequence > latest[key]["sequence"]:
            latest[key] = descriptor
    return latest
def _latest_queries(values: Any, *, run_id: str, target_ids: set[str]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, int]] = set()
    for entry in _array(values, "expansion queries", _MAX_ITEMS):
        query = validate_context_expansion_query(entry)
        unit_id = query["unit_id"]
        key = (unit_id, query["query_epoch"])
        if query["run_id"] != run_id or unit_id not in target_ids:
            raise ValueError("expansion query is outside the next DAG wave")
        if key in seen:
            raise ValueError("expansion query epoch is duplicated for a unit")
        seen.add(key)
        if unit_id not in latest or query["query_epoch"] > latest[unit_id]["query_epoch"]:
            latest[unit_id] = query
    return latest
def _query_scope(
    query: Mapping[str, Any], *, direct_dependencies: set[str],
    failure_hashes: set[str],
) -> None:
    for request in query["requests"]:
        if request["family"] == "dependency-scc-interface" \
                and request["dependency_scc_id"] not in direct_dependencies:
            raise ValueError("expansion query requests a non-direct dependency interface")
        if request["family"] == "verified-failure-fact" \
                and request["failure_evidence_sha256"] not in failure_hashes:
            raise ValueError("expansion query references unrelated failure evidence")
def _request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expansion request must be an object")
    family = value.get("family")
    fields = {
        "include-adjacency": "anchor_fact_sha256",
        "dependency-scc-interface": "dependency_scc_id",
        "verified-failure-fact": "failure_evidence_sha256",
    }
    field = fields.get(family)
    if field is None or set(value) != {"family", field}:
        raise ValueError("expansion request shape or family is invalid")
    item = value.get(field)
    if family == "dependency-scc-interface":
        item = _text(item, "expansion dependency SCC")
    elif not _sha(item):
        raise ValueError("expansion request SHA-256 is invalid")
    return {"family": family, field: item}
def _closure(unit_id: str, dependencies: Mapping[str, list[str]]) -> set[str]:
    result: set[str] = set()
    pending = list(dependencies[unit_id])
    while pending:
        current = pending.pop()
        if current not in result:
            result.add(current)
            pending.extend(dependencies[current])
    return result
def _array(value: Any, label: str, limit: int) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    if len(value) > limit:
        raise ValueError(f"{label} exceeds its bounded count")
    return list(value)
def _count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value
def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{label} must be a bounded non-empty string")
    return value
def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None
__all__ = [
    "EXPANSION_QUERY_POLICY", "WAVE_INPUT_POLICY",
    "build_context_expansion_query", "derive_context_frontier_wave_input",
    "validate_context_expansion_query",
]
