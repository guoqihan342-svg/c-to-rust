from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from .build_ir import (
    BUILD_IR_EXTRACTOR, BUILD_IR_KIND, BUILD_IR_SCHEMA_VERSION,
    canonical_build_ir_bytes, is_sha256,
    validate_artifact_reference, validate_materialized_binding,
)
from .build_ir_validation_io import (
    MAX_BUILD_IR_ARTIFACT_BYTES, attachments, read_bound,
    repository_bindings, strict_object,
)
from .build_ir_reopen import (
    accepted_provenance_role, accepted_raw_roles, reproject_bound_build_ir,
)
from .build_ir_host_toolchains import validate_host_bound_toolchains
from .build_ir_toolchain_validation import validate_toolchain_references
from .build_ir_target_extensions import validate_target_extensions
from .build_ir_projection import target_closure
from .c_toolchain_schema import C_TOOLCHAIN_RAW_ROLE
from .closure_paths import verify_repository_artifact
TOP_LEVEL_KEYS = {
    "abi_facts", "artifact_kind", "boundaries", "build_metadata", "claim_boundary",
    "external_dependencies", "extractor", "generated_inputs", "raw_fact_refs",
    "schema_version", "semantic_sha256", "source_inputs", "status",
    "target_closure", "targets", "toolchains", "translation_units",
}


class BuildIRValidationError(ValueError):
    pass
def verify_build_ir_artifact(
    repo_root: str | Path,
    artifact_root: str | Path,
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    payload: dict[str, Any] | None = None
    verified_bindings = 0
    try:
        artifact_base = Path(artifact_root).resolve(strict=True)
        data = read_bound(artifact_base, reference, "build_ir")
        payload = strict_object(data, "build_ir")
        if canonical_build_ir_bytes(payload) != data:
            raise BuildIRValidationError("build_ir_not_canonical")
        validate_build_ir(payload)
        bound = attachments(artifact_base, payload["raw_fact_refs"])
        recomputed = reproject_bound_build_ir(repo_root, payload, bound)
        if recomputed != payload:
            raise BuildIRValidationError("build_ir_projection_drift")
        seen: dict[tuple[str, str], dict[str, Any]] = {}
        for binding in repository_bindings(payload):
            if not binding["materialized"]:
                continue
            identity = (binding["path"], binding["kind"])
            previous = seen.get(identity)
            if previous is not None and previous != binding:
                raise BuildIRValidationError("build_ir_binding_conflict")
            seen[identity] = binding
        for binding in seen.values():
            blocker = verify_repository_artifact(Path(repo_root).resolve(), binding)
            if blocker is not None:
                blockers.append(blocker)
        verified_bindings = len(seen)
    except (BuildIRValidationError, OSError, UnicodeError, json.JSONDecodeError,
            TypeError, ValueError) as error:
        blockers.append({"kind": str(error) or "build_ir_validation_failed"})
    blockers = _unique_blockers(blockers)
    return {
        "schema_version": 1,
        "status": "verified" if not blockers else "blocked",
        "build_ir_sha256": reference.get("sha256"),
        "semantic_sha256": payload.get("semantic_sha256") if payload else None,
        "toolchain_profile": payload.get("claim_boundary", {}).get(
            "toolchain_profile",
        ) if payload else None,
        "verified_binding_count": verified_bindings,
        "blockers": blockers,
    }
def validate_build_ir(value: Mapping[str, Any]) -> None:
    if set(value) != TOP_LEVEL_KEYS:
        raise BuildIRValidationError("build_ir_top_level_schema_invalid")
    if value.get("schema_version") != BUILD_IR_SCHEMA_VERSION:
        raise BuildIRValidationError("build_ir_schema_version_invalid")
    if value.get("artifact_kind") != BUILD_IR_KIND:
        raise BuildIRValidationError("build_ir_artifact_kind_invalid")
    if value.get("extractor") != BUILD_IR_EXTRACTOR:
        raise BuildIRValidationError("build_ir_extractor_invalid")
    if value.get("status") not in {"ready", "ready_with_boundaries"}:
        raise BuildIRValidationError("build_ir_status_invalid")
    claim_boundary = _object(
        value.get("claim_boundary"), "build_ir_claim_boundary_invalid",
    )
    numerator = claim_boundary.get("translation_coverage_numerator")
    if (
        claim_boundary.get("semantic_gate") is not False
        or isinstance(numerator, bool)
        or numerator != 0
    ):
        raise BuildIRValidationError("build_ir_claim_boundary_invalid")
    raw_roles = _validate_raw_refs(value.get("raw_fact_refs"))
    host_bound = C_TOOLCHAIN_RAW_ROLE in raw_roles
    if claim_boundary.get("host_toolchain_bound", False) is not host_bound:
        raise BuildIRValidationError("build_ir_claim_boundary_invalid")
    toolchain_profile = claim_boundary.get("toolchain_profile")
    if host_bound:
        if toolchain_profile not in {"competition", "development"}:
            raise BuildIRValidationError("build_ir_claim_boundary_invalid")
    elif toolchain_profile is not None:
        raise BuildIRValidationError("build_ir_claim_boundary_invalid")
    arrays = {
        key: _objects(value.get(key), f"build_ir_{key}_invalid")
        for key in (
            "build_metadata", "translation_units", "source_inputs",
            "generated_inputs", "targets", "toolchains",
            "external_dependencies", "abi_facts",
        )
    }
    metadata = arrays["build_metadata"]
    if len(metadata) != 1:
        raise BuildIRValidationError("build_ir_build_metadata_invalid")
    validate_materialized_binding(metadata[0], materialized=True)
    units = arrays["translation_units"]
    unit_ids = _ordered_ids(units, "unit_id", "build_ir_translation_unit")
    for unit in units:
        _validate_unit(unit)
    sources = arrays["source_inputs"]
    _validate_binding_order(sources, "build_ir_source_inputs")
    generated = arrays["generated_inputs"]
    generated_paths = []
    for item in generated:
        _require_provenance(item)
        binding = _object(item.get("binding"), "build_ir_generated_binding_invalid")
        validate_materialized_binding(binding, binding.get("materialized"))
        generated_paths.append(binding["path"])
    _require_sorted_unique(generated_paths, "build_ir_generated_inputs")
    targets = arrays["targets"]
    target_ids = _ordered_ids(targets, "target_id", "build_ir_target")
    _validate_targets(targets, set(target_ids))
    if value.get("target_closure") != target_closure(targets):
        raise BuildIRValidationError("build_ir_target_closure_invalid")
    toolchain_ids = _ordered_ids(
        arrays["toolchains"], "toolchain_id", "build_ir_toolchain",
    )
    if host_bound:
        try:
            validate_host_bound_toolchains(arrays["toolchains"])
        except ValueError as error:
            raise BuildIRValidationError(str(error)) from error
        if {item.get("profile") for item in arrays["toolchains"]} != {
            toolchain_profile,
        }:
            raise BuildIRValidationError("build_ir_host_toolchain_profile_invalid")
    _ordered_ids(
        arrays["external_dependencies"], "dependency_id",
        "build_ir_external_dependency",
    )
    abi = arrays["abi_facts"]
    if [item.get("unit_id") for item in abi] != unit_ids:
        raise BuildIRValidationError("build_ir_abi_unit_order_invalid")
    try:
        validate_toolchain_references(
            units, targets, abi, toolchain_ids, require_target_refs=host_bound,
        )
    except ValueError as error:
        raise BuildIRValidationError(str(error)) from error
    for item in [*value["toolchains"], *value["external_dependencies"], *abi]:
        _require_provenance(item)
    if not isinstance(value.get("boundaries"), list):
        raise BuildIRValidationError("build_ir_boundaries_invalid")
    canonical_build_ir_bytes(value)


def _validate_unit(unit: Mapping[str, Any]) -> None:
    for key in ("unit_id", "working_directory", "compiler", "language", "toolchain_id"):
        if not isinstance(unit.get(key), str) or not unit[key]:
            raise BuildIRValidationError("build_ir_translation_unit_invalid")
    for key in ("variant_index", "variant_count", "redacted_define_count"):
        value = unit.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BuildIRValidationError("build_ir_translation_unit_invalid")
    validate_materialized_binding(_object(unit.get("source"), "build_ir_source_invalid"), True)
    validate_materialized_binding(_object(unit.get("output"), "build_ir_output_invalid"),
                                  unit["output"].get("materialized"))
    arguments = _object(
        unit.get("compile_arguments"), "build_ir_compile_arguments_invalid"
    )
    if not _strings(arguments.get("semantic_flags")):
        raise BuildIRValidationError("build_ir_compile_arguments_invalid")
    if not is_sha256(arguments.get("expanded_argv_sha256")):
        raise BuildIRValidationError("build_ir_compile_arguments_invalid")
    for response in _objects(
        arguments.get("response_files"), "build_ir_response_files_invalid"
    ):
        validate_materialized_binding(response, True)
    for key in ("compiler_wrappers", "includes", "defines"):
        if not isinstance(unit.get(key), list):
            raise BuildIRValidationError("build_ir_translation_unit_invalid")
    _require_provenance(unit)

def _validate_targets(targets: list[Mapping[str, Any]], identifiers: set[str]) -> None:
    output_owners: dict[str, str] = {}
    for target in targets:
        _require_provenance(target)
        target_id = str(target["target_id"])
        try:
            validate_target_extensions(target)
        except ValueError as error:
            raise BuildIRValidationError(str(error)) from error
        dependencies = target.get("dependency_target_ids")
        if not _strings(dependencies) or len(dependencies) != len(set(dependencies)):
            raise BuildIRValidationError("build_ir_target_dependencies_invalid")
        if target_id in dependencies or any(item not in identifiers for item in dependencies):
            raise BuildIRValidationError("build_ir_target_dependencies_invalid")
        for output in _objects(target.get("outputs"), "build_ir_target_outputs_invalid"):
            validate_materialized_binding(output, output.get("materialized"))
            path = output["path"]
            if path in output_owners and output_owners[path] != target_id:
                raise BuildIRValidationError("build_ir_target_output_duplicate")
            output_owners[path] = target_id
        inputs = _objects(target.get("ordered_inputs"), "build_ir_target_inputs_invalid")
        if [item.get("ordinal") for item in inputs] != list(range(len(inputs))):
            raise BuildIRValidationError("build_ir_target_input_order_invalid")
        for item in inputs:
            validate_materialized_binding(
                _object(item.get("binding"), "build_ir_target_input_invalid"),
                item["binding"].get("materialized"),
            )
        if not _strings(target.get("ordered_link_arguments")):
            raise BuildIRValidationError("build_ir_link_arguments_invalid")

def _validate_raw_refs(value: Any) -> list[Any]:
    refs = _objects(value, "build_ir_raw_fact_refs_invalid")
    roles = [item.get("role") for item in refs]
    if not accepted_raw_roles(roles):
        raise BuildIRValidationError("build_ir_raw_fact_refs_invalid")
    for item in refs:
        validate_artifact_reference(item, "build_ir_raw_fact_ref_invalid")
    return roles

def _validate_binding_order(values: list[Mapping[str, Any]], code: str) -> None:
    for value in values:
        validate_materialized_binding(value, True)
    _require_sorted_unique([item["path"] for item in values], code)

def _ordered_ids(values: list[Mapping[str, Any]], key: str, code: str) -> list[str]:
    result = [item.get(key) for item in values]
    if not all(isinstance(item, str) and item for item in result):
        raise BuildIRValidationError(f"{code}_id_invalid")
    _require_sorted_unique(result, f"{code}_order_invalid")
    return result

def _require_sorted_unique(values: list[Any], code: str) -> None:
    if values != sorted(set(values)):
        raise BuildIRValidationError(code)

def _object(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BuildIRValidationError(code)
    return value

def _objects(value: Any, code: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise BuildIRValidationError(code)
    return value

def _require_provenance(value: Mapping[str, Any]) -> None:
    provenance = value.get("provenance")
    if not isinstance(provenance, Mapping) or not accepted_provenance_role(
        provenance.get("raw_fact_role")
    ):
        raise BuildIRValidationError("build_ir_provenance_invalid")

def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)

def _unique_blockers(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {json.dumps(item, sort_keys=True): item for item in values}
    return [keyed[key] for key in sorted(keyed)]

__all__ = ["BuildIRValidationError", "MAX_BUILD_IR_ARTIFACT_BYTES",
           "validate_build_ir", "verify_build_ir_artifact"]
