from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .rust_project_ir_native import DERIVED_INTERFACE_PRODUCER, validate_bound_native_link_requirements
from .rust_project_ir_compilation_facts import (
    reopen_manifest_compilation_facts,
)
from .rust_project_ir_reopen_facts import recompute_bound_interface_plan
from .migration_target_scope_reopen import reopen_bound_target_scope_bindings
from .rust_project_ir_validation import RustProjectIRError, validate_rust_project_ir
from .rust_project_ir_binding_domain import (
    validate_bound_build_ir, validate_bound_migration_dag,
    validate_embedded_build_ir,
)
from .rust_project_ir_binding_io import (
    MAX_BOUND_ARTIFACT_BYTES, fail as _fail, read_reference as _read_reference,
    strict_json as _strict_json,
)
_EVIDENCE_SECTIONS = (
    "modules", "public_api", "shared_types", "global_ownership",
    "initialization", "ffi_boundaries", "cfgs", "features",
    "unsafe_obligations",
)


def reopen_rust_project_ir_bindings(
    value: Mapping[str, Any], artifact_root: Path,
) -> dict[str, Any]:
    if value.get("schema_version") == 3:
        from .rust_project_ir_v3_bindings import reopen_rust_project_ir_v3_bindings
        return reopen_rust_project_ir_v3_bindings(value, artifact_root)
    validate_rust_project_ir(value)
    bindings = value["bindings"]
    dag_data = _read_reference(artifact_root, bindings["migration_dag"])
    dag = _strict_json(dag_data, "migration DAG")
    dag_units = validate_bound_migration_dag(dag, artifact_root)
    build_payloads: dict[str, dict[str, Any]] = {}
    build_unit_count = 0
    for reference in bindings["build_ir"]:
        data = _read_reference(artifact_root, reference)
        payload = _strict_json(data, "BuildIR")
        validate_bound_build_ir(payload, data)
        digest = str(reference["sha256"])
        if digest in build_payloads:
            _fail("RustProjectIR binds a duplicate BuildIR entity")
        build_payloads[digest] = payload
        build_unit_count += len(payload["translation_units"])
    if build_unit_count == 0:
        _fail("RustProjectIR BuildIR closure has no translation units")
    try:
        target_scope_facts = reopen_bound_target_scope_bindings(
            dag, list(build_payloads.values()), artifact_root,
        )
    except (OSError, TypeError, ValueError) as error:
        raise RustProjectIRError(
            f"bound migration target scope validation failed: {error}"
        ) from error
    try:
        compilation_facts = reopen_manifest_compilation_facts(
            artifact_root, dag, bindings["c_compilation_facts"],
            list(build_payloads.values()),
        )
    except (OSError, TypeError, ValueError) as error:
        raise RustProjectIRError(
            f"bound C compilation facts validation failed: {error}"
        ) from error
    candidate_sources = {
        str(candidate["unit_id"]): _read_reference(
            artifact_root, candidate["source"],
        )
        for candidate in bindings["candidates"]
    }
    _validate_domain_coverage(value, dag, dag_units, build_payloads)
    result = {
        "schema_version": 1,
        "status": "domain-bound",
        "reference_count": (
            1 + len(build_payloads) + len(bindings["candidates"])
            + int(compilation_facts is not None)
        ),
        "bindings_sha256": content_sha256(bindings),
        "dag_unit_count": len(dag_units),
        "build_ir_count": len(build_payloads),
        "build_ir_translation_unit_count": build_unit_count,
        "candidate_count": len(bindings["candidates"]),
        "c_compilation_facts": compilation_facts,
        "target_scopes": target_scope_facts,
        "semantic_gate": False,
        "semantic_pass": False,
    }
    if value["interface_completeness"]["producer"] == DERIVED_INTERFACE_PRODUCER:
        plan = recompute_bound_interface_plan(
            value, dag, list(build_payloads.values()), candidate_sources,
            compilation_facts_complete=bool(
                bindings["c_compilation_facts"] is not None
                and compilation_facts is not None
                and compilation_facts["coverage_complete"]
            ),
        )
        result.update({
            "target_topology": plan["target_topology"],
            "target_topology_sha256": plan["target_topology_sha256"],
            "topology_verified": plan["topology_verified"],
            "topology_blockers": plan["topology_blockers"],
        })
    return result


def _validate_domain_coverage(
    value: Mapping[str, Any], dag: Mapping[str, Any], dag_units: set[str],
    build_payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    bindings = value["bindings"]
    candidate_units = {str(item["unit_id"]) for item in bindings["candidates"]}
    candidate_shas = {str(item["source"]["sha256"]) for item in bindings["candidates"]}
    if len(candidate_shas) != len(bindings["candidates"]):
        _fail("RustProjectIR candidate entities are not unique")
    if candidate_units != dag_units:
        _fail("RustProjectIR candidate units do not exactly cover the migration DAG")
    module_units = [str(item["unit_id"]) for item in value["modules"]]
    if len(module_units) != len(set(module_units)) or set(module_units) != dag_units:
        _fail("RustProjectIR module units do not exactly cover the migration DAG")
    build_digests = set(build_payloads)
    try:
        validate_bound_native_link_requirements(value, list(build_payloads.values()))
    except ValueError as error:
        _fail(str(error))
    validate_embedded_build_ir(dag, bindings["build_ir"])
    records = [value["crate"]]
    records.extend(record for section in _EVIDENCE_SECTIONS for record in value[section])
    covered_builds: set[str] = set()
    covered_units: set[str] = set()
    covered_candidates: set[str] = set()
    for record in records:
        evidence = record["evidence"]
        evidence_builds = set(evidence["build_ir_sha256s"])
        evidence_units = set(evidence["dag_unit_ids"])
        evidence_candidates = set(evidence["candidate_sha256s"])
        if (
            not evidence_builds <= build_digests
            or not evidence_units <= dag_units
            or not evidence_candidates <= candidate_shas
        ):
            _fail("RustProjectIR evidence references an unknown domain entity")
        covered_builds.update(evidence_builds)
        covered_units.update(evidence_units)
        covered_candidates.update(evidence_candidates)
    if (
        covered_builds != build_digests
        or covered_units != dag_units
        or covered_candidates != candidate_shas
    ):
        _fail("RustProjectIR evidence does not cover every bound domain entity")
    crate_evidence = value["crate"]["evidence"]
    if (
        set(crate_evidence["build_ir_sha256s"]) != build_digests
        or set(crate_evidence["dag_unit_ids"]) != dag_units
        or set(crate_evidence["candidate_sha256s"]) != candidate_shas
    ):
        _fail("RustProjectIR crate evidence does not bind the complete project")


__all__ = ["MAX_BOUND_ARTIFACT_BYTES", "reopen_rust_project_ir_bindings"]
