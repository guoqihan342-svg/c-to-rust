from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .migration_target_scope_reopen import reopen_bound_target_scope_map
from .rust_project_ir_binding_domain import (
    validate_bound_build_ir, validate_bound_migration_dag,
    validate_embedded_build_ir,
)
from .rust_project_ir_binding_io import (
    artifact_identity, fail, read_reference, strict_json,
)
from .rust_project_ir_compilation_facts import reopen_manifest_compilation_facts
from .rust_project_ir_native import validate_bound_native_link_requirements
from .rust_project_ir_v3_topology import derive_rust_project_ir_v3_topology
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


_TOPOLOGY_KEYS = (
    "workspace", "packages", "targets", "modules",
    "topology_status", "topology_blockers",
)


def reopen_rust_project_ir_v3_bindings(
    value: Mapping[str, Any], artifact_root: Path,
) -> dict[str, Any]:
    validate_rust_project_ir_v3(value)
    bindings = value["bindings"]
    dag = strict_json(
        read_reference(artifact_root, bindings["migration_dag"]), "migration DAG",
    )
    dag_units = validate_bound_migration_dag(dag, artifact_root)
    _validate_graph_identity(dag, bindings["migration_graph"])
    build_payloads: dict[str, dict[str, Any]] = {}
    build_unit_count = 0
    for reference in bindings["build_ir"]:
        data = read_reference(artifact_root, reference)
        payload = strict_json(data, "BuildIR")
        validate_bound_build_ir(payload, data)
        digest = str(reference["sha256"])
        if digest in build_payloads:
            fail("RustProjectIR v3 binds a duplicate BuildIR entity")
        build_payloads[digest] = payload
        build_unit_count += len(payload["translation_units"])
    if not build_unit_count:
        fail("RustProjectIR v3 BuildIR closure has no translation units")
    try:
        scopes = reopen_bound_target_scope_map(
            dag, list(build_payloads.values()), artifact_root,
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(f"bound migration target scope validation failed: {error}") from error
    if scopes is None or set(scopes) != dag_units:
        fail("RustProjectIR v3 requires complete target scope bindings")
    compilation_facts = _compilation_facts(
        artifact_root, dag, bindings["c_compilation_facts"],
        list(build_payloads.values()),
    )
    candidate_units = {str(item["unit_id"]) for item in bindings["candidates"]}
    if candidate_units != dag_units:
        fail("RustProjectIR v3 candidates do not exactly cover the migration DAG")
    for candidate in bindings["candidates"]:
        read_reference(artifact_root, candidate["source"])
    _validate_recomputed_topology(value, scopes, build_payloads)
    _validate_module_scopes(
        value, scopes, dag_units, require_complete=(
            value["topology_status"] == "ready"
        ),
    )
    if value["topology_status"] == "ready":
        _validate_product_coverage(value, list(build_payloads.values()))
    validate_embedded_build_ir(dag, bindings["build_ir"])
    try:
        validate_bound_native_link_requirements(value, list(build_payloads.values()))
    except ValueError as error:
        fail(str(error))
    return {
        "schema_version": 1,
        "status": "v3-domain-bound",
        "reference_count": (
            2 + len(build_payloads) + len(bindings["candidates"])
            + int(compilation_facts is not None)
        ),
        "bindings_sha256": content_sha256(bindings),
        "dag_unit_count": len(dag_units),
        "build_ir_count": len(build_payloads),
        "build_ir_translation_unit_count": build_unit_count,
        "candidate_count": len(bindings["candidates"]),
        "package_count": len(value["packages"]),
        "target_count": len(value["targets"]),
        "module_count": len(value["modules"]),
        "target_scope_set_sha256": content_sha256(scopes),
        "c_compilation_facts": compilation_facts,
        "semantic_gate": False,
        "semantic_pass": False,
    }


def _validate_graph_identity(
    dag: Mapping[str, Any], reference: Mapping[str, Any],
) -> None:
    embedded = dag.get("migration_graph")
    if not isinstance(embedded, Mapping):
        fail("RustProjectIR v3 migration graph binding is unavailable")
    if artifact_identity(embedded) != artifact_identity(reference):
        fail("RustProjectIR v3 and migration DAG bind different migration graphs")


def _compilation_facts(
    artifact_root: Path, dag: Mapping[str, Any], reference: Mapping[str, Any] | None,
    build_irs: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    try:
        return reopen_manifest_compilation_facts(
            artifact_root, dag, reference, build_irs,
        )
    except (OSError, TypeError, ValueError) as error:
        raise ValueError(f"bound C compilation facts validation failed: {error}") from error


def _validate_module_scopes(
    value: Mapping[str, Any], scopes: Mapping[str, Mapping[str, Any]],
    dag_units: set[str], *, require_complete: bool,
) -> None:
    covered = set()
    for module in value["modules"]:
        unit_id = str(module["unit_id"])
        scope = scopes.get(unit_id)
        if scope is None or module["source_unit_ids"] != scope["source_unit_ids"]:
            fail("RustProjectIR v3 module source scope drifted from BuildIR")
        covered.add(unit_id)
    if require_complete and covered != dag_units:
        fail("RustProjectIR v3 modules do not cover every migration group")


def _validate_recomputed_topology(
    value: Mapping[str, Any], scopes: Mapping[str, Mapping[str, Any]],
    build_payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    bindings: dict[str, str] = {}
    for artifact_sha, payload in build_payloads.items():
        semantic_sha = str(payload["semantic_sha256"])
        if semantic_sha in bindings:
            fail("RustProjectIR v3 BuildIR semantic identity is ambiguous")
        bindings[semantic_sha] = artifact_sha
    expected = derive_rust_project_ir_v3_topology(
        list(build_payloads.values()), scopes, value["bindings"]["candidates"],
        build_ir_binding_sha256s=bindings,
    )
    if any(value[key] != expected[key] for key in _TOPOLOGY_KEYS):
        fail("RustProjectIR v3 topology drifted from BuildIR target scopes")


def _validate_product_coverage(
    value: Mapping[str, Any], build_irs: list[Mapping[str, Any]],
) -> None:
    targets: dict[str, Mapping[str, Any]] = {}
    for build_ir in build_irs:
        for target in build_ir["targets"]:
            target_id = str(target["target_id"])
            if target_id in targets:
                fail("RustProjectIR v3 BuildIR target identity is ambiguous")
            targets[target_id] = target
    products = {
        target_id for target_id, target in targets.items()
        if target.get("kind") in {"archive", "link"}
    }
    package_products = [str(item["build_ir_target_id"]) for item in value["packages"]]
    rust_target_products = [str(item["build_ir_target_id"]) for item in value["targets"]]
    if (
        not products
        or len(package_products) != len(set(package_products))
        or len(rust_target_products) != len(set(rust_target_products))
        or set(package_products) != products
        or set(rust_target_products) != products
    ):
        fail("RustProjectIR v3 product target coverage drifted from BuildIR")
    package_by_id = {str(item["package_id"]): item for item in value["packages"]}
    rust_targets = {str(item["target_id"]): item for item in value["targets"]}
    for package_id, package in package_by_id.items():
        for target_id in package["target_ids"]:
            target = rust_targets[str(target_id)]
            if target["build_ir_target_id"] != package["build_ir_target_id"]:
                fail("RustProjectIR v3 package product and target disagree")


__all__ = ["reopen_rust_project_ir_v3_bindings"]
