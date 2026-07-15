from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .migration_target_scope import (
    derive_build_ir_target_scopes, validate_scc_target_scope,
)
from .orchestration_facts import read_artifact_reference


def reopen_bound_target_scope_bindings(
    manifest: Mapping[str, Any], build_irs: Sequence[Mapping[str, Any]],
    artifact_root: Path,
) -> dict[str, Any] | None:
    scopes = reopen_bound_target_scope_map(manifest, build_irs, artifact_root)
    return None if scopes is None else _scope_facts(scopes)


def reopen_bound_target_scope_map(
    manifest: Mapping[str, Any], build_irs: Sequence[Mapping[str, Any]],
    artifact_root: Path,
) -> dict[str, dict[str, Any]] | None:
    reference = manifest.get("migration_graph")
    if manifest.get("target_scopes") is None and reference is None:
        return None
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("migration_target_scope_graph_reference_invalid")
    data = read_artifact_reference(artifact_root, reference)
    try:
        graph = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("migration_target_scope_graph_json_invalid") from error
    if (
        len(data) != reference.get("size_bytes") or not isinstance(graph, dict)
        or canonical_json_bytes(graph) != data
    ):
        raise ValueError("migration_target_scope_graph_content_invalid")
    return reopen_target_scope_map(manifest, build_irs, graph)


def reopen_target_scope_bindings(
    manifest: Mapping[str, Any], build_irs: Sequence[Mapping[str, Any]],
    migration_graph: Mapping[str, Any],
) -> dict[str, Any] | None:
    scopes = reopen_target_scope_map(manifest, build_irs, migration_graph)
    return None if scopes is None else _scope_facts(scopes)


def reopen_target_scope_map(
    manifest: Mapping[str, Any], build_irs: Sequence[Mapping[str, Any]],
    migration_graph: Mapping[str, Any],
) -> dict[str, dict[str, Any]] | None:
    bindings = manifest.get("target_scopes")
    graph_ref = manifest.get("migration_graph")
    if bindings is None and graph_ref is None:
        return None
    if not isinstance(bindings, Mapping) or not isinstance(graph_ref, Mapping):
        raise ValueError("migration_target_scope_binding_incomplete")
    dag, order = manifest.get("dag"), manifest.get("dag_order")
    if not isinstance(dag, Mapping) or not isinstance(order, list):
        raise ValueError("migration_target_scope_dag_invalid")
    group_ids = set(dag)
    if set(bindings) != group_ids:
        raise ValueError("migration_target_scope_group_set_drifted")
    graph_scopes = _graph_scopes(migration_graph, dag, order, cohort=(
        "parent_migration_dag" in manifest
    ))
    source_units: dict[str, list[str]] = {}
    manifest_scopes: dict[str, dict[str, Any]] = {}
    for group_id in sorted(group_ids):
        binding = bindings[group_id]
        if not isinstance(binding, Mapping) or set(binding) != {
            "group_content_sha256", "scope_sha256",
        }:
            raise ValueError("migration_target_scope_binding_invalid")
        scope = graph_scopes[group_id]
        if binding.get("scope_sha256") != scope["scope_sha256"]:
            raise ValueError("migration_target_scope_graph_binding_drifted")
        source_units[group_id] = scope["source_unit_ids"]
        manifest_scopes[group_id] = scope
    recomputed = derive_build_ir_target_scopes(build_irs, source_units)
    if recomputed != manifest_scopes:
        raise ValueError("migration_target_scope_build_ir_drifted")
    return recomputed


def _scope_facts(scopes: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "target-scopes-bound",
        "group_count": len(scopes),
        "source_unit_count": len({
            unit_id for scope in scopes.values()
            for unit_id in scope["source_unit_ids"]
        }),
        "scope_set_sha256": content_sha256(scopes),
    }


def _graph_scopes(
    graph: Mapping[str, Any], dag: Mapping[str, Any], order: list[Any], *,
    cohort: bool,
) -> dict[str, dict[str, Any]]:
    if (
        graph.get("schema_version") != 1
        or graph.get("status") not in {"ready", "ready_with_boundaries"}
    ):
        raise ValueError("migration_target_scope_graph_invalid")
    sccs, waves = graph.get("sccs"), graph.get("waves")
    if not isinstance(sccs, list) or not isinstance(waves, list):
        raise ValueError("migration_target_scope_graph_invalid")
    by_id: dict[str, Mapping[str, Any]] = {}
    for scc in sccs:
        scc_id = scc.get("scc_id") if isinstance(scc, Mapping) else None
        if not isinstance(scc_id, str) or not scc_id or scc_id in by_id:
            raise ValueError("migration_target_scope_graph_invalid")
        by_id[scc_id] = scc
    selected = set(dag)
    if not selected <= set(by_id) or (not cohort and selected != set(by_id)):
        raise ValueError("migration_target_scope_graph_group_set_drifted")
    graph_order = _graph_order(waves, set(by_id))
    if order != [group_id for group_id in graph_order if group_id in selected]:
        raise ValueError("migration_target_scope_graph_order_drifted")
    result = {}
    for group_id in sorted(selected):
        scc = by_id[group_id]
        dependencies = scc.get("dependency_scc_ids")
        if not isinstance(dependencies, list) or dag[group_id] != dependencies:
            raise ValueError("migration_target_scope_graph_dag_drifted")
        scope = validate_scc_target_scope(scc.get("target_scope"))
        if scc.get("source_unit_ids") != scope["source_unit_ids"]:
            raise ValueError("migration_target_scope_graph_source_units_drifted")
        result[group_id] = scope
    return result


def _graph_order(waves: list[Any], groups: set[str]) -> list[str]:
    result: list[str] = []
    indexes: list[int] = []
    for wave in waves:
        if not isinstance(wave, Mapping):
            raise ValueError("migration_target_scope_graph_waves_invalid")
        index, ids = wave.get("wave_index"), wave.get("scc_ids")
        if type(index) is not int or index < 0 or not isinstance(ids, list):
            raise ValueError("migration_target_scope_graph_waves_invalid")
        if any(not isinstance(item, str) or item not in groups for item in ids):
            raise ValueError("migration_target_scope_graph_waves_invalid")
        indexes.append(index)
        result.extend(ids)
    if indexes != list(range(len(indexes))) or len(result) != len(set(result)) or set(result) != groups:
        raise ValueError("migration_target_scope_graph_waves_invalid")
    return result


__all__ = [
    "reopen_bound_target_scope_bindings", "reopen_bound_target_scope_map",
    "reopen_target_scope_bindings", "reopen_target_scope_map",
]
