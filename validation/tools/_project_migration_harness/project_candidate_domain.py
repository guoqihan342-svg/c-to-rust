from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .orchestration_facts import read_artifact_reference


_CONTRACT_KEYS = {
    "schema_version", "run_id", "dag_sha256", "integration_manifest",
    "dependency_edges", "dag_order", "context_sha256",
}
_CANDIDATE_SET_KEYS = {
    "schema_version", "scope", "run_context_sha256", "dag_sha256",
    "integration_manifest_sha256", "roots", "members",
}
_DOMAIN_CONTEXT_KEYS = (
    "run_id", "run_context_sha256", "dag_sha256", "integration_manifest",
    "candidate_set_sha256", "candidate_set_manifest_sha256",
    "rust_project_ir_sha256", "rust_project_interface_sha256",
    "rust_project_binding_sha256",
)


def validate_candidate_project_domain(
    *, run_id: str, migration_contract: Mapping[str, Any],
    rust_project_ir: Mapping[str, Any], rust_project_binding_sha256: str,
    candidate_set_sha256: str, candidate_set_manifest: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    """Bind a project-final candidate cohort to the live run DAG and IR."""
    _run_id(run_id)
    contract = _contract(migration_contract, run_id)
    ir_binding = rust_project_ir.get("bindings")
    if not isinstance(ir_binding, Mapping):
        raise ValueError("candidate_project_ir_bindings_invalid")
    dag_reference = ir_binding.get("migration_dag")
    if dag_reference != contract["integration_manifest"]:
        raise ValueError("candidate_project_contract_ir_dag_mismatch")
    dag = _reopen_dag(artifact_root, contract["integration_manifest"])
    _contract_dag(contract, dag)
    members = _ir_members(ir_binding.get("candidates"))
    manifest = _candidate_set(
        candidate_set_manifest, candidate_set_sha256, contract, members,
    )
    if not is_sha256(rust_project_binding_sha256):
        raise ValueError("candidate_project_ir_binding_invalid")
    projection = {
        "run_id": run_id,
        "run_context_sha256": contract["context_sha256"],
        "dag_sha256": contract["dag_sha256"],
        "integration_manifest": dict(contract["integration_manifest"]),
        "candidate_set_sha256": candidate_set_sha256,
        "candidate_set_manifest_sha256": content_sha256(manifest),
        "rust_project_ir_sha256": rust_project_ir.get("ir_sha256"),
        "rust_project_interface_sha256": rust_project_ir.get("interface_sha256"),
        "rust_project_binding_sha256": rust_project_binding_sha256,
    }
    if not all(is_sha256(projection[key]) for key in (
        "rust_project_ir_sha256", "rust_project_interface_sha256",
    )):
        raise ValueError("candidate_project_ir_identity_invalid")
    return {
        **projection,
        "candidate_domain_context_sha256": candidate_domain_context_sha256(
            projection
        ),
    }


def candidate_domain_context_sha256(value: Mapping[str, Any]) -> str:
    return content_sha256({key: value.get(key) for key in _DOMAIN_CONTEXT_KEYS})


def candidate_verification_context(
    domain: Mapping[str, Any], build_ir: Mapping[str, Any],
    materialization: Mapping[str, Any], execution: Mapping[str, Any],
    observations: Mapping[str, Any], native_settlement: Mapping[str, Any],
) -> str:
    generation = materialization.get("generation")
    return content_sha256({
        "candidate_domain_context_sha256": domain.get(
            "candidate_domain_context_sha256"
        ),
        "build_ir_verification": dict(build_ir),
        "generation_sha256": (
            generation.get("sha256") if isinstance(generation, Mapping) else None
        ),
        "project_input_sha256": execution.get("project_input_sha256"),
        "cargo_observations": dict(observations),
        "native_link_settlement_binding_sha256": native_settlement.get(
            "binding_sha256"
        ),
    })


def _contract(value: Any, run_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONTRACT_KEYS:
        raise ValueError("candidate_project_run_contract_invalid")
    contract = dict(value)
    reference = contract.get("integration_manifest")
    if (
        contract.get("schema_version") != 1
        or contract.get("run_id") != run_id
        or not is_sha256(contract.get("dag_sha256"))
        or not _reference(reference)
    ):
        raise ValueError("candidate_project_run_contract_invalid")
    context = contract.pop("context_sha256", None)
    if not is_sha256(context) or content_sha256(contract) != context:
        raise ValueError("candidate_project_run_context_drifted")
    return {**contract, "context_sha256": context}


def _reopen_dag(root: Path, reference: Mapping[str, Any]) -> dict[str, Any]:
    try:
        data = read_artifact_reference(Path(root), reference)
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("candidate_project_dag_unreadable") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ValueError("candidate_project_dag_noncanonical")
    return value


def _contract_dag(contract: Mapping[str, Any], dag: Mapping[str, Any]) -> None:
    graph, order = dag.get("dag"), dag.get("dag_order")
    if not isinstance(graph, Mapping) or not isinstance(order, list):
        raise ValueError("candidate_project_dag_invalid")
    edges = []
    for unit_id in sorted(graph):
        dependencies = graph[unit_id]
        if (
            not isinstance(unit_id, str) or not unit_id
            or not isinstance(dependencies, list)
            or dependencies != sorted(set(dependencies))
        ):
            raise ValueError("candidate_project_dag_invalid")
        edges.append({"unit_id": unit_id, "dependencies": dependencies})
    if contract.get("dependency_edges") != edges or contract.get("dag_order") != order:
        raise ValueError("candidate_project_contract_dag_drifted")


def _candidate_set(
    value: Any, digest: str, contract: Mapping[str, Any],
    members: list[dict[str, str]],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CANDIDATE_SET_KEYS:
        raise ValueError("candidate_project_set_manifest_invalid")
    manifest = json.loads(json.dumps(value, ensure_ascii=True))
    compact = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    units = [item["unit_id"] for item in members]
    if (
        not is_sha256(digest) or hashlib.sha256(compact).hexdigest() != digest
        or manifest.get("schema_version") != 2
        or manifest.get("scope") != "project-final"
        or manifest.get("run_context_sha256") != contract["context_sha256"]
        or manifest.get("dag_sha256") != contract["dag_sha256"]
        or manifest.get("integration_manifest_sha256")
        != contract["integration_manifest"]["sha256"]
        or manifest.get("roots") != units
        or manifest.get("members") != members
    ):
        raise ValueError("candidate_project_set_manifest_drifted")
    return manifest


def _ir_members(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError("candidate_project_ir_members_invalid")
    members = []
    for item in value:
        source = item.get("source") if isinstance(item, Mapping) else None
        if not isinstance(source, Mapping):
            raise ValueError("candidate_project_ir_members_invalid")
        members.append({
            "unit_id": str(item.get("unit_id")),
            "artifact_id": str(item.get("artifact_id")),
            "content_sha256": str(source.get("sha256")),
        })
    expected = sorted(members, key=lambda item: item["unit_id"])
    if members != expected or len({item["unit_id"] for item in members}) != len(members):
        raise ValueError("candidate_project_ir_members_noncanonical")
    return members


def _reference(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "sha256", "size_bytes"}
        and isinstance(value.get("path"), str) and bool(value["path"])
        and is_sha256(value.get("sha256"))
        and type(value.get("size_bytes")) is int and value["size_bytes"] > 0
    )


def _run_id(value: Any) -> None:
    if (
        not isinstance(value, str) or not value or len(value) > 128
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("candidate_project_run_id_invalid")


__all__ = [
    "candidate_domain_context_sha256", "candidate_verification_context",
    "validate_candidate_project_domain",
]
