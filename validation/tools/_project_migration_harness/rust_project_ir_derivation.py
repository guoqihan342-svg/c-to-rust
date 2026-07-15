from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import cargo_project
from .artifacts import canonical_json_bytes, content_sha256
from .build_ir_validation import validate_build_ir
from .integration_validation import load_candidates, normalize_manifest
from .rust_candidate_facts import derive_rust_metadata
from .rust_ffi_facts import NoFfiBoundaryError, derive_ffi_boundary_facts
from .rust_project_cargo import MAX_UNSAFE_OBLIGATIONS, VIRTUAL_CRATE_ROOT
from .rust_project_ir import build_rust_project_ir
from .rust_project_ir_compilation_facts import (
    manifest_compilation_facts_reference, reopen_compilation_facts,
)
from .rust_project_ir_source_facts import (
    derive_bound_candidate_source_facts, project_bound_public_items,
)
from .rust_project_ir_topology import derive_project_interface_plan
from .rust_project_ir_validation import module_id_for_candidate
from .native_link_context import native_link_requirements
from .orchestration_facts import read_artifact_reference


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
    descriptors = _descriptor_map(candidate_descriptors)
    build_digests = _build_digests(build_ir_refs)
    build_payloads = _build_payloads(build_ir_refs, artifact_root)
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
        source_text = candidate.source.decode("utf-8")
        metadata = derive_rust_metadata(source_text)
        if (
            tuple(metadata["public_symbols"]) != candidate.public_symbols
            or tuple(metadata["required_symbols"]) != candidate.required_symbols
            or int(metadata["unsafe_count"]) != candidate.unsafe_count
        ):
            _fail("candidate_interface_metadata_drift", "candidate", unit_id)
        evidence = _evidence(build_digests, unit_id, candidate.sha256)
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
        public_api.extend(_public_records(
            module_id, unit_id, candidate.sha256, build_digests,
            metadata["public_symbols"], source_facts,
        ))
        ffi_boundaries.extend(_ffi_records(
            module_id, unit_id, candidate.sha256, build_digests,
            source_text,
        ))
        unsafe_obligations.extend(_unsafe_records(
            module_id, unit_id, candidate.sha256, build_digests,
            int(metadata["unsafe_count"]),
        ))
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


def _descriptor_map(values: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result = {}
    for value in values:
        unit_id = value.get("unit_id") if isinstance(value, Mapping) else None
        artifact_id = value.get("artifact_id") if isinstance(value, Mapping) else None
        group_id = value.get("group_id") if isinstance(value, Mapping) else None
        if (
            not isinstance(unit_id, str) or not unit_id
            or not isinstance(artifact_id, str) or not artifact_id
            or group_id != unit_id or unit_id in result
        ):
            _fail("rust_project_ir_candidate_identity_invalid", "rust_project_ir")
        result[unit_id] = value
    return result


def _build_digests(values: Sequence[Mapping[str, Any]]) -> list[str]:
    digests = []
    for value in values:
        digest = value.get("sha256") if isinstance(value, Mapping) else None
        if not isinstance(digest, str):
            _fail("rust_project_ir_build_binding_invalid", "rust_project_ir")
        digests.append(digest)
    if not digests or len(digests) != len(set(digests)):
        _fail("rust_project_ir_build_binding_invalid", "rust_project_ir")
    return sorted(digests)


def _build_payloads(
    references: Sequence[Mapping[str, Any]], artifact_root: Path,
) -> list[dict[str, Any]]:
    payloads = []
    for reference in references:
        raw = read_artifact_reference(artifact_root, reference)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise cargo_project.ProjectInputError(
                "rust_project_ir_build_binding_invalid", "rust_project_ir",
            ) from error
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != raw:
            _fail("rust_project_ir_build_binding_invalid", "rust_project_ir")
        try:
            validate_build_ir(payload)
        except ValueError as error:
            raise cargo_project.ProjectInputError(
                "rust_project_ir_build_binding_invalid", "rust_project_ir",
            ) from error
        payloads.append(payload)
    return payloads


def _evidence(builds: list[str], unit_id: str, candidate_sha: str) -> dict[str, Any]:
    return {
        "build_ir_sha256s": list(builds), "dag_unit_ids": [unit_id],
        "candidate_sha256s": [candidate_sha],
    }


def _public_records(
    module_id: str, unit_id: str, candidate_sha: str,
    build_digests: list[str], symbols: Sequence[str],
    source_facts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    evidence = _evidence(build_digests, unit_id, candidate_sha)
    projected = {
        item["symbol"]: item
        for item in project_bound_public_items(symbols, source_facts)
    }
    return [{
        "declaration_id": "api-" + content_sha256({
            "module_id": module_id, "symbol": symbol,
        })[:24],
        "module_id": module_id, "symbol": symbol,
        "kind": projected[symbol]["kind"],
        "signature": projected[symbol]["signature"],
        "visibility": "public",
        "evidence": evidence,
    } for symbol in symbols]


def _ffi_records(
    module_id: str, unit_id: str, candidate_sha: str,
    build_digests: list[str], source: str,
) -> list[dict[str, Any]]:
    evidence = _evidence(build_digests, unit_id, candidate_sha)
    result = []
    try:
        facts = derive_ffi_boundary_facts(source, candidate_sha)
    except NoFfiBoundaryError:
        return []
    for fact in facts:
        result.append({
            "declaration_id": "ffi-" + content_sha256({
                "module_id": module_id, **fact,
            })[:24],
            "module_id": module_id, **fact, "evidence": evidence,
        })
    return result


def _unsafe_records(
    module_id: str, unit_id: str, candidate_sha: str,
    build_digests: list[str], count: int,
) -> list[dict[str, Any]]:
    if count > MAX_UNSAFE_OBLIGATIONS:
        _fail("candidate_unsafe_obligations_unbounded", "candidate", unit_id)
    evidence = _evidence(build_digests, unit_id, candidate_sha)
    return [{
        "obligation_id": f"unsafe-{candidate_sha[:16]}-{index:04d}",
        "module_id": module_id, "kind": "host-derived-unsafe-token",
        "reason_code": "requires-project-safety-verification",
        "source_span": None, "evidence": evidence,
    } for index in range(count)]


def _fail(code: str, stage: str, group_id: str | None = None) -> None:
    raise cargo_project.ProjectInputError(code, stage, group_id)


__all__ = ["derive_rust_project_ir_from_candidates"]
