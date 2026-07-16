from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256, write_json_artifact
from .ledger import LedgerError
from .rust_project_ir_derivation import derive_rust_project_ir_from_candidates
from .rust_project_ir_cohort import PARENT_DAG_KEY
from .rust_project_ir_v3_derivation import derive_rust_project_ir_v3_from_candidates


def derive_bound_project_ir(
    *, migration_contract: Mapping[str, Any],
    migration_manifest: Mapping[str, Any],
    candidate_descriptors: Sequence[Mapping[str, Any]],
    artifact_root: Path,
) -> dict[str, Any]:
    dag_ref = migration_contract.get("integration_manifest")
    build = migration_manifest.get("build_ir")
    if (
        not isinstance(dag_ref, Mapping)
        or not isinstance(build, Mapping)
        or build.get("status") != "bound"
        or not isinstance(build.get("artifact"), Mapping)
    ):
        raise LedgerError("project RustProjectIR domain bindings are unavailable")
    try:
        cohort_manifest, cohort_ref = _cohort_domain(
            migration_manifest, dag_ref, candidate_descriptors, artifact_root,
        )
        derive = (
            derive_rust_project_ir_v3_from_candidates
            if _full_target_scoped_domain(cohort_manifest)
            else derive_rust_project_ir_from_candidates
        )
        return derive(
            migration_manifest=cohort_manifest,
            migration_dag_ref=cohort_ref,
            build_ir_refs=[build["artifact"]],
            candidate_descriptors=candidate_descriptors,
            artifact_root=artifact_root,
        )
    except (OSError, TypeError, ValueError) as error:
        raise LedgerError("project RustProjectIR derivation failed") from error


def _full_target_scoped_domain(manifest: Mapping[str, Any]) -> bool:
    dag = manifest.get("dag")
    scopes = manifest.get("target_scopes")
    return (
        PARENT_DAG_KEY not in manifest
        and manifest.get("profile") == "competition"
        and isinstance(dag, Mapping) and bool(dag)
        and isinstance(scopes, Mapping) and set(scopes) == set(dag)
        and isinstance(manifest.get("migration_graph"), Mapping)
    )


def _cohort_domain(
    manifest: Mapping[str, Any], parent_ref: Mapping[str, Any],
    descriptors: Sequence[Mapping[str, Any]], artifact_root: Path,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    dag, order = manifest.get("dag"), manifest.get("dag_order")
    if not isinstance(dag, Mapping) or not isinstance(order, list):
        raise LedgerError("project migration DAG is unavailable")
    selected = sorted(str(item.get("unit_id")) for item in descriptors)
    if len(selected) != len(set(selected)) or any(unit not in dag for unit in selected):
        raise LedgerError("project candidate cohort does not bind the migration DAG")
    if set(selected) == set(dag):
        return manifest, parent_ref
    selected_set = set(selected)
    cohort_dag = {}
    for unit_id in selected:
        dependencies = dag.get(unit_id)
        if not isinstance(dependencies, list) or any(item not in selected_set for item in dependencies):
            raise LedgerError("project candidate cohort is not dependency closed")
        cohort_dag[unit_id] = list(dependencies)
    cohort = {
        key: value for key, value in manifest.items()
        if key not in {"dag", "dag_order", PARENT_DAG_KEY}
    }
    cohort.update({
        "dag": cohort_dag,
        "dag_order": [unit for unit in order if unit in selected_set],
        PARENT_DAG_KEY: {
            "scope": "verification-dependency-closure",
            "artifact": dict(parent_ref), "selected_unit_ids": selected,
        },
    })
    scopes = manifest.get("target_scopes")
    if isinstance(scopes, Mapping):
        cohort["target_scopes"] = {
            unit_id: scopes[unit_id] for unit_id in selected
        }
    digest = content_sha256(cohort)
    reference = write_json_artifact(
        artifact_root, f"project-ir-domain/cohort-dag-{digest[:24]}.json", cohort,
    )
    return cohort, reference


def persist_project_ir(
    artifact_root: Path, scope: str, rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    digest = str(rust_project_ir.get("ir_sha256", ""))
    if content_sha256({key: item for key, item in rust_project_ir.items() if key != "ir_sha256"}) != digest:
        raise LedgerError("project RustProjectIR content hash is invalid")
    relative = f"{scope}/rust-project-ir-{digest[:24]}.json"
    reference = write_json_artifact(artifact_root, relative, rust_project_ir)
    if reference["sha256"] != _bytes_sha(rust_project_ir):
        raise LedgerError("persisted RustProjectIR encoding drifted")
    return reference


def _bytes_sha(value: Mapping[str, Any]) -> str:
    import hashlib
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = ["derive_bound_project_ir", "persist_project_ir"]
