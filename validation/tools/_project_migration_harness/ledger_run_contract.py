from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .ledger_security import LedgerError
from .orchestration_facts import read_artifact_reference
from .build_ir import is_sha256


CONTRACT_KEYS = {
    "schema_version", "run_id", "dag_sha256", "integration_manifest",
    "dependency_edges", "dag_order", "context_sha256",
}


def derive_migration_contract(
    database_path: Path, artifacts: Mapping[str, Any], *, run_id: str,
    dag_sha256: str, units: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    reference = artifacts.get("integration_manifest")
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("integration manifest reference is invalid")
    try:
        raw = read_artifact_reference(database_path.parent.parent, reference)
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("integration manifest cannot bind the run") from error
    if (
        not isinstance(manifest, dict)
        or canonical_json_bytes(manifest) != raw
        or reference.get("size_bytes") != len(raw)
    ):
        raise ValueError("integration manifest is not canonical or size-bound")
    edges, order = _validated_dag(manifest, units)
    _validated_target_scopes(manifest, units, artifacts.get("migration_graph"))
    binding = {
        "path": str(reference["path"]),
        "sha256": str(reference["sha256"]),
        "size_bytes": int(reference["size_bytes"]),
    }
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "dag_sha256": dag_sha256,
        "integration_manifest": binding,
        "dependency_edges": edges,
        "dag_order": order,
    }
    return {**payload, "context_sha256": content_sha256(payload)}, manifest


def load_migration_contract(
    database_path: Path, connection: Any, run_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    run = connection.execute(
        "select dag_sha256,metadata_json from project_runs where run_id=?", (run_id,),
    ).fetchone()
    if run is None:
        raise LedgerError("project run does not exist")
    try:
        metadata = json.loads(str(run["metadata_json"]))
    except json.JSONDecodeError as error:
        raise LedgerError("project run metadata is invalid") from error
    stored = metadata.get("migration_contract") if isinstance(metadata, dict) else None
    artifacts = metadata.get("artifacts") if isinstance(metadata, dict) else None
    if not isinstance(stored, dict) or set(stored) != CONTRACT_KEYS:
        raise LedgerError("project run migration contract is missing")
    units = [dict(row) for row in connection.execute(
        """select unit_id,group_id,wave_index,content_sha256 from migration_units
           where run_id=? order by unit_id""",
        (run_id,),
    ).fetchall()]
    try:
        expected, manifest = derive_migration_contract(
            database_path, artifacts if isinstance(artifacts, Mapping) else {},
            run_id=run_id, dag_sha256=str(run["dag_sha256"]), units=units,
        )
    except (OSError, TypeError, ValueError) as error:
        raise LedgerError("project run migration contract revalidation failed") from error
    if stored != expected:
        raise LedgerError("project run migration contract drifted")
    return expected, manifest


def _validated_dag(
    manifest: Mapping[str, Any], units: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    if manifest.get("schema_version") != 1:
        raise ValueError("integration manifest schema is invalid")
    profile = manifest.get("profile")
    if profile is not None and profile not in {"competition", "development"}:
        raise ValueError("integration manifest profile is invalid")
    dag = manifest.get("dag")
    order = manifest.get("dag_order")
    if not isinstance(dag, Mapping) or not isinstance(order, list):
        raise ValueError("integration manifest DAG is invalid")
    unit_map: dict[str, int] = {}
    for unit in units:
        unit_id = unit.get("unit_id")
        if (
            not isinstance(unit_id, str) or not unit_id
            or unit.get("group_id") != unit_id
            or isinstance(unit.get("wave_index"), bool)
            or not isinstance(unit.get("wave_index"), int)
        ):
            raise ValueError("ledger unit cannot bind the migration DAG")
        unit_map[unit_id] = int(unit["wave_index"])
    if set(dag) != set(unit_map) or len(order) != len(unit_map) or set(order) != set(unit_map):
        raise ValueError("integration manifest DAG does not match ledger units")
    positions = {unit_id: index for index, unit_id in enumerate(order)}
    if len(positions) != len(order):
        raise ValueError("integration manifest DAG order contains duplicates")
    edges = []
    for unit_id in sorted(unit_map):
        dependencies = dag.get(unit_id)
        if (
            not isinstance(dependencies, list)
            or not all(isinstance(item, str) for item in dependencies)
            or len(dependencies) != len(set(dependencies))
            or any(item not in unit_map or item == unit_id for item in dependencies)
            or any(unit_map[item] >= unit_map[unit_id] for item in dependencies)
            or any(positions[item] >= positions[unit_id] for item in dependencies)
        ):
            raise ValueError("integration manifest dependency closure is invalid")
        edges.append({"unit_id": unit_id, "dependencies": sorted(dependencies)})
    if any(unit_map[order[index]] > unit_map[order[index + 1]] for index in range(len(order) - 1)):
        raise ValueError("integration manifest DAG order crosses wave order")
    return edges, list(order)


def _validated_target_scopes(
    manifest: Mapping[str, Any], units: Sequence[Mapping[str, Any]],
    expected_graph: Any = None,
) -> None:
    scopes = manifest.get("target_scopes")
    graph = manifest.get("migration_graph")
    if scopes is None and graph is None:
        return
    if not isinstance(scopes, Mapping) or set(scopes) != {
        str(item.get("unit_id")) for item in units
    }:
        raise ValueError("integration manifest target scopes are invalid")
    if not isinstance(graph, Mapping) or set(graph) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("integration manifest migration graph is invalid")
    if expected_graph is not None and graph != expected_graph:
        raise ValueError("integration manifest migration graph binding drifted")
    content_by_group = {
        str(item.get("unit_id")): item.get("content_sha256") for item in units
    }
    for group_id in sorted(scopes):
        binding = scopes[group_id]
        if not isinstance(binding, Mapping) or set(binding) != {
            "group_content_sha256", "scope_sha256",
        }:
            raise ValueError("integration manifest target scope binding is invalid")
        if binding.get("group_content_sha256") != content_by_group[group_id]:
            raise ValueError("integration manifest target scope group binding drifted")
        if not is_sha256(binding.get("scope_sha256")):
            raise ValueError("integration manifest target scope hash is invalid")


__all__ = ["derive_migration_contract", "load_migration_contract"]
