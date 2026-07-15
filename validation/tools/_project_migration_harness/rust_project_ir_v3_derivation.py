from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import cargo_project
from .integration_validation import load_candidates, normalize_manifest
from .migration_target_scope_reopen import reopen_bound_target_scope_map
from .native_link_context import native_link_requirements
from .rust_candidate_facts import derive_rust_metadata
from .rust_project_cargo import MAX_UNSAFE_OBLIGATIONS
from .rust_project_ir_compilation_facts import (
    manifest_compilation_facts_reference, reopen_compilation_facts,
)
from .rust_project_ir_inputs import (
    build_reference_digests, candidate_descriptor_map, reopen_build_payloads,
)
from .rust_project_ir_native import derived_interface_completeness
from .rust_project_ir_records import ffi_records, public_records, unsafe_records
from .rust_project_ir_source_facts import derive_bound_candidate_source_facts
from .rust_project_ir_v3 import build_rust_project_ir_v3
from .rust_project_ir_v3_topology import derive_rust_project_ir_v3_topology


def derive_rust_project_ir_v3_from_candidates(
    *, migration_manifest: Mapping[str, Any],
    migration_dag_ref: Mapping[str, Any],
    build_ir_refs: Sequence[Mapping[str, Any]],
    candidate_descriptors: Sequence[Mapping[str, Any]],
    artifact_root: Path,
) -> dict[str, Any]:
    """Derive target-scoped v3 IR; blocked topology remains non-semantic."""
    manifest = normalize_manifest(migration_manifest)
    dependencies, order = cargo_project._migration_dag(manifest)
    candidates = load_candidates(
        candidate_descriptors, artifact_root, cargo_project.MAX_SOURCE_BYTES,
    )
    by_group = {item.group_id: item for item in candidates}
    if set(by_group) != set(dependencies) or len(by_group) != len(candidates):
        _fail("rust_project_ir_candidate_coverage_invalid")
    descriptors = candidate_descriptor_map(candidate_descriptors)
    build_digests = build_reference_digests(build_ir_refs)
    build_payloads = reopen_build_payloads(build_ir_refs, artifact_root)
    build_bindings = _build_bindings(build_payloads, build_ir_refs)
    try:
        scopes = reopen_bound_target_scope_map(manifest, build_payloads, artifact_root)
    except (OSError, TypeError, ValueError) as error:
        raise cargo_project.ProjectInputError(
            "rust_project_ir_v3_target_scope_binding_invalid", "rust_project_ir",
        ) from error
    if scopes is None or set(scopes) != set(dependencies):
        _fail("rust_project_ir_v3_target_scope_binding_invalid")
    graph_ref = manifest.get("migration_graph")
    if not isinstance(graph_ref, Mapping):
        _fail("rust_project_ir_v3_migration_graph_binding_invalid")
    compilation_ref, compilation_complete = _compilation_state(
        manifest, build_payloads, artifact_root,
    )
    candidate_refs, facts = _candidate_facts(
        order, by_group, descriptors, build_digests,
    )
    topology = derive_rust_project_ir_v3_topology(
        build_payloads, scopes, candidate_refs,
        build_ir_binding_sha256s=build_bindings,
    )
    public_api: list[dict[str, Any]] = []
    ffi_boundaries: list[dict[str, Any]] = []
    unsafe_obligations: list[dict[str, Any]] = []
    for module in topology["modules"]:
        unit_id = str(module["unit_id"])
        fact = facts[unit_id]
        public_api.extend(public_records(
            str(module["module_id"]), unit_id, str(module["candidate_sha256"]),
            build_digests, fact["metadata"]["public_symbols"], fact["source_facts"],
        ))
        ffi_boundaries.extend(ffi_records(
            str(module["module_id"]), unit_id, str(module["candidate_sha256"]),
            build_digests, fact["source"],
        ))
        try:
            unsafe_obligations.extend(unsafe_records(
                str(module["module_id"]), unit_id,
                str(module["candidate_sha256"]), build_digests,
                int(fact["metadata"]["unsafe_count"]),
                max_count=MAX_UNSAFE_OBLIGATIONS, target_scoped_identity=True,
            ))
        except ValueError:
            _fail("candidate_unsafe_obligations_unbounded", "candidate", unit_id)
    native_requirements = native_link_requirements(build_payloads)
    unresolved = {
        section for fact in facts.values()
        for section in fact["source_facts"]["unresolved_sections"]
    }
    if topology["topology_status"] != "ready" or not compilation_complete:
        unresolved.add("target-matrix")
    if {item["unit_id"] for item in topology["modules"]} != set(dependencies):
        unresolved.add("candidate-module-binding")
    return build_rust_project_ir_v3(
        migration_dag_ref=migration_dag_ref,
        migration_graph_ref=graph_ref,
        build_ir_refs=build_ir_refs,
        c_compilation_facts_ref=compilation_ref,
        candidate_refs=candidate_refs,
        workspace=topology["workspace"], packages=topology["packages"],
        targets=topology["targets"], modules=topology["modules"],
        public_api=public_api, shared_types=[], global_ownership=[],
        initialization=[], ffi_boundaries=ffi_boundaries, cfgs=[], features=[],
        unsafe_obligations=unsafe_obligations,
        native_link_requirements=native_requirements,
        interface_completeness=derived_interface_completeness(
            sorted(unresolved), native_requirements,
        ),
        topology_blockers=topology["topology_blockers"],
    )


def _candidate_facts(
    order: Sequence[str], candidates: Mapping[str, Any],
    descriptors: Mapping[str, Mapping[str, Any]], build_digests: list[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    refs, facts = [], {}
    for unit_id in order:
        candidate = candidates[unit_id]
        descriptor = descriptors.get(unit_id)
        if descriptor is None:
            _fail("rust_project_ir_unit_group_mismatch", "candidate", unit_id)
        if hashlib.sha256(candidate.source).hexdigest() != candidate.sha256:
            _fail("candidate_source_hash_drift", "candidate", unit_id)
        source = candidate.source.decode("utf-8")
        metadata = derive_rust_metadata(source)
        if (
            tuple(metadata["public_symbols"]) != candidate.public_symbols
            or tuple(metadata["required_symbols"]) != candidate.required_symbols
            or int(metadata["unsafe_count"]) != candidate.unsafe_count
        ):
            _fail("candidate_interface_metadata_drift", "candidate", unit_id)
        refs.append({
            "unit_id": unit_id, "artifact_id": str(descriptor["artifact_id"]),
            "source": {
                "path": candidate.source_path, "sha256": candidate.sha256,
                "size_bytes": len(candidate.source),
            },
        })
        facts[unit_id] = {
            "source": source, "metadata": metadata,
            "source_facts": derive_bound_candidate_source_facts(
                source, metadata["public_symbols"],
            ),
            "build_digests": build_digests,
        }
    return refs, facts


def _build_bindings(
    payloads: Sequence[Mapping[str, Any]], refs: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    if len(payloads) != len(refs):
        _fail("rust_project_ir_v3_build_binding_invalid")
    result = {}
    for payload, reference in zip(payloads, refs, strict=True):
        semantic = str(payload["semantic_sha256"])
        digest = reference.get("sha256")
        if semantic in result or not isinstance(digest, str):
            _fail("rust_project_ir_v3_build_binding_invalid")
        result[semantic] = digest
    return result


def _compilation_state(
    manifest: Mapping[str, Any], build_payloads: list[dict[str, Any]],
    artifact_root: Path,
) -> tuple[Mapping[str, Any] | None, bool]:
    try:
        reference = manifest_compilation_facts_reference(manifest)
        facts = reopen_compilation_facts(artifact_root, reference, build_payloads)
    except (OSError, TypeError, ValueError) as error:
        raise cargo_project.ProjectInputError(
            "rust_project_ir_compilation_facts_binding_invalid", "rust_project_ir",
        ) from error
    complete = bool(reference is not None and facts and facts["coverage_complete"])
    return reference, complete


def _fail(code: str, stage: str = "rust_project_ir", group_id: str | None = None) -> None:
    raise cargo_project.ProjectInputError(code, stage, group_id)


__all__ = ["derive_rust_project_ir_v3_from_candidates"]
