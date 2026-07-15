from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import cargo_project
from .integration_validation import load_candidates, normalize_manifest
from .rust_candidate_facts import derive_rust_metadata
from .rust_project_cargo import MAX_UNSAFE_OBLIGATIONS, VIRTUAL_CRATE_ROOT
from .rust_project_ir import build_rust_project_ir
from .rust_project_ir_compilation_facts import (
    manifest_compilation_facts_reference, reopen_compilation_facts,
)
from .rust_project_ir_source_facts import derive_bound_candidate_source_facts
from .rust_project_ir_inputs import (
    build_reference_digests, candidate_descriptor_map, reopen_build_payloads,
)
from .rust_project_ir_records import (
    ffi_records, project_evidence, public_records, unsafe_records,
)
from .rust_project_ir_topology import derive_project_interface_plan
from .rust_project_ir_validation import module_id_for_candidate
from .native_link_context import native_link_requirements


def derive_rust_project_ir_from_candidates(
    *, migration_manifest: Mapping[str, Any],
    migration_dag_ref: Mapping[str, Any],
    build_ir_refs: Sequence[Mapping[str, Any]],
    candidate_descriptors: Sequence[Mapping[str, Any]],
    artifact_root: Path,
) -> dict[str, Any]:
    """Derive a conservative host-fact IR; unresolved interfaces stay explicit."""
    manifest = normalize_manifest(migration_manifest)
    dependencies, order = cargo_project._migration_dag(manifest)
    candidates = load_candidates(
        candidate_descriptors, artifact_root, cargo_project.MAX_SOURCE_BYTES,
    )
    by_group = {item.group_id: item for item in candidates}
    if set(by_group) != set(dependencies) or len(by_group) != len(candidates):
        _fail("rust_project_ir_candidate_coverage_invalid", "rust_project_ir")
    descriptors = candidate_descriptor_map(candidate_descriptors)
    build_digests = build_reference_digests(build_ir_refs)
    build_payloads = reopen_build_payloads(build_ir_refs, artifact_root)
    try:
        compilation_facts_ref = manifest_compilation_facts_reference(manifest)
        compilation_facts = reopen_compilation_facts(
            artifact_root, compilation_facts_ref, build_payloads,
        )
    except (OSError, TypeError, ValueError) as error:
        raise cargo_project.ProjectInputError(
            "rust_project_ir_compilation_facts_binding_invalid",
            "rust_project_ir",
        ) from error
    native_requirements = native_link_requirements(build_payloads)
    candidate_refs = []
    modules = []
    public_api = []
    ffi_boundaries = []
    unsafe_obligations = []
    source_fact_bindings = []
    for unit_id in order:
        candidate = by_group[unit_id]
        descriptor = descriptors.get(unit_id)
        if descriptor is None or descriptor.get("unit_id") != unit_id:
            _fail("rust_project_ir_unit_group_mismatch", "rust_project_ir", unit_id)
        if hashlib.sha256(candidate.source).hexdigest() != candidate.sha256:
            _fail("candidate_source_hash_drift", "candidate", unit_id)
        source_text = candidate.source.decode("utf-8")
        metadata = derive_rust_metadata(source_text)
        if (
            tuple(metadata["public_symbols"]) != candidate.public_symbols
            or tuple(metadata["required_symbols"]) != candidate.required_symbols
            or int(metadata["unsafe_count"]) != candidate.unsafe_count
        ):
            _fail("candidate_interface_metadata_drift", "candidate", unit_id)
        evidence = project_evidence(build_digests, unit_id, candidate.sha256)
        source = {
            "path": candidate.source_path, "sha256": candidate.sha256,
            "size_bytes": len(candidate.source),
        }
        candidate_refs.append({
            "unit_id": unit_id, "artifact_id": str(descriptor["artifact_id"]),
            "source": source,
        })
        module_id = module_id_for_candidate(candidate.sha256)
        source_facts = derive_bound_candidate_source_facts(
            source_text, metadata["public_symbols"],
        )
        source_fact_bindings.append({
            "unit_id": unit_id, "candidate_sha256": candidate.sha256,
            "module_id": module_id, "source_facts": source_facts,
        })
        modules.append({
            "module_id": module_id, "parent_module_id": None,
            "rust_path": f"src/{candidate.module_name}.rs", "unit_id": unit_id,
            "candidate_sha256": candidate.sha256, "visibility": "crate",
            "evidence": evidence,
        })
        public_api.extend(public_records(
            module_id, unit_id, candidate.sha256, build_digests,
            metadata["public_symbols"], source_facts,
        ))
        ffi_boundaries.extend(ffi_records(
            module_id, unit_id, candidate.sha256, build_digests,
            source_text,
        ))
        try:
            unsafe_obligations.extend(unsafe_records(
                module_id, unit_id, candidate.sha256, build_digests,
                int(metadata["unsafe_count"]), max_count=MAX_UNSAFE_OBLIGATIONS,
            ))
        except ValueError:
            _fail("candidate_unsafe_obligations_unbounded", "candidate", unit_id)
    all_candidates = sorted(item.sha256 for item in candidates)
    crate_evidence = {
        "build_ir_sha256s": build_digests,
        "dag_unit_ids": sorted(dependencies),
        "candidate_sha256s": all_candidates,
    }
    interface_plan = derive_project_interface_plan(
        build_irs=build_payloads, candidates=source_fact_bindings,
        dependencies=dependencies,
        native_link_requirements=native_requirements,
        compilation_facts_complete=bool(
            compilation_facts_ref is not None
            and compilation_facts is not None
            and compilation_facts["coverage_complete"]
        ),
    )
    return build_rust_project_ir(
        migration_dag_ref=migration_dag_ref,
        build_ir_refs=build_ir_refs,
        c_compilation_facts_ref=compilation_facts_ref,
        candidate_refs=candidate_refs,
        crate={
            "crate_id": interface_plan["crate_id"], "edition": "2021",
            "crate_types": interface_plan["crate_types"],
            "root_module_id": VIRTUAL_CRATE_ROOT,
            "targets": interface_plan["targets"], "evidence": crate_evidence,
        },
        modules=modules, public_api=public_api,
        shared_types=[], global_ownership=[], initialization=[],
        ffi_boundaries=ffi_boundaries, cfgs=[], features=[],
        unsafe_obligations=unsafe_obligations,
        native_link_requirements=native_requirements,
        interface_completeness=interface_plan["interface_completeness"],
    )


def _fail(code: str, stage: str, group_id: str | None = None) -> None:
    raise cargo_project.ProjectInputError(code, stage, group_id)


__all__ = ["derive_rust_project_ir_from_candidates"]
