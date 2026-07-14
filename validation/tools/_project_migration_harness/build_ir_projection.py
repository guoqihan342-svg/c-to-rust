from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

from .artifacts import content_sha256
from .build_ir import (
    BUILD_IR_EXTRACTOR, BUILD_IR_KIND, BUILD_IR_SCHEMA_VERSION,
    finalize_build_ir, list_value, normalize_binding, stable_build_id,
    string_list, target_record,
)
from .build_ir_meson import merge_meson_targets
from .build_ir_host_toolchains import HostToolchainProjection
from .build_ir_projection_inputs import generated_inputs, source_inputs
from .build_ir_projection_legacy import (
    ABI_PREFIXES, abi_facts, legacy_toolchains,
)
from .c_toolchain_schema import C_TOOLCHAIN_RAW_ROLE


RAW_ROLES = {
    "discovery",
    "generated-build-closure",
    "generated-build-closure-verification",
}
HOST_BOUND_RAW_ROLES = {*RAW_ROLES, C_TOOLCHAIN_RAW_ROLE}


def project_build_ir(
    discovery: Mapping[str, Any],
    closure: Mapping[str, Any],
    closure_verification: Mapping[str, Any],
    raw_fact_refs: list[Mapping[str, Any]],
    toolchain_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if discovery.get("status") != "ready":
        raise ValueError("build_ir_discovery_not_ready")
    if discovery.get("generated_build_closure") != closure:
        raise ValueError("build_ir_generated_closure_mismatch")
    refs = _raw_refs(raw_fact_refs, host_bound=toolchain_evidence is not None)
    projector = (
        HostToolchainProjection(toolchain_evidence)
        if toolchain_evidence is not None else None
    )
    units = _translation_units(discovery.get("translation_units"), projector)
    metadata = normalize_binding(discovery.get("compile_database"), materialized=True)
    targets, external, boundaries = _targets(units, closure, projector)
    sources = source_inputs(units, targets)
    generated = generated_inputs(closure, targets)
    boundaries.extend(_boundaries(closure, closure_verification))
    closure_complete = (
        closure.get("status") == "ready"
        and closure_verification.get("status") == "verified"
    )
    payload = {
        "schema_version": BUILD_IR_SCHEMA_VERSION,
        "artifact_kind": BUILD_IR_KIND,
        "status": "ready" if closure_complete else "ready_with_boundaries",
        "extractor": dict(BUILD_IR_EXTRACTOR),
        "raw_fact_refs": refs,
        "build_metadata": [metadata],
        "translation_units": units,
        "source_inputs": sources,
        "generated_inputs": generated,
        "targets": targets,
        "target_closure": target_closure(targets),
        "toolchains": projector.records() if projector else legacy_toolchains(units),
        "external_dependencies": external,
        "abi_facts": abi_facts(units),
        "boundaries": _unique(boundaries),
        "claim_boundary": {
            "role": "canonical_build_projection_only",
            "closure_complete": closure_complete,
            "parameters_guessed": False,
            "commands_executed": False,
            "host_toolchain_bound": projector is not None,
            "toolchain_profile": projector.profile if projector else None,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    return finalize_build_ir(payload)


def _translation_units(
    value: Any, projector: HostToolchainProjection | None,
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("build_ir_translation_units_missing")
    result = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise ValueError("build_ir_translation_unit_invalid")
        entry = raw.get("entry")
        if not isinstance(entry, Mapping):
            raise ValueError("build_ir_translation_unit_provenance_missing")
        output = {"path": raw.get("output"), "kind": "file", "materialized": False}
        toolchain_id = (
            projector.compile(
                raw.get("compiler"), raw.get("compiler_wrappers"),
                raw.get("language"),
            )
            if projector else stable_build_id("toolchain", {
                "driver": raw.get("compiler"),
                "wrappers": raw.get("compiler_wrappers"),
            })
        )
        item = {
            "unit_id": raw.get("unit_id"),
            "variant_index": raw.get("variant_index"),
            "variant_count": raw.get("variant_count"),
            "source": normalize_binding(raw.get("source"), materialized=True),
            "working_directory": raw.get("working_directory"),
            "compiler": raw.get("compiler"),
            "compiler_wrappers": copy.deepcopy(raw.get("compiler_wrappers")),
            "language": raw.get("language"),
            "toolchain_id": toolchain_id,
            "includes": copy.deepcopy(raw.get("includes")),
            "defines": copy.deepcopy(raw.get("defines")),
            "redacted_define_count": raw.get("redacted_define_count"),
            "compile_arguments": {
                "semantic_flags": copy.deepcopy(raw.get("semantic_flags")),
                "expanded_argv_sha256": raw.get("expanded_argv_sha256"),
                "response_files": [
                    normalize_binding(item, materialized=True)
                    for item in list_value(raw.get("response_files"))
                ],
            },
            "output": output,
            "provenance": {
                "raw_fact_role": "discovery",
                "entry_index": entry.get("index"),
                "entry_sha256": entry.get("sha256"),
                "extractor": dict(BUILD_IR_EXTRACTOR),
            },
        }
        result.append(item)
    result.sort(key=lambda item: str(item["unit_id"]))
    return result


def _targets(
    units: list[dict[str, Any]], closure: Mapping[str, Any],
    projector: HostToolchainProjection | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    materialized = binding_map(closure.get("compile_outputs"))
    targets: list[dict[str, Any]] = []
    owners: dict[str, str] = {}
    for unit in units:
        path = str(unit["output"]["path"])
        output = copy.deepcopy(materialized.get(path, unit["output"]))
        output.setdefault("materialized", "sha256" in output)
        unit["output"] = copy.deepcopy(output)
        target_id = stable_build_id("target", {"kind": "object", "output": path})
        owners[path] = target_id
        target = target_record(
            target_id, path, "object", [output],
            [{"ordinal": 0, "role": "source", "binding": unit["source"],
              "dependency_target_id": None}],
            [], [{"kind": "compile", "arguments": unit["compile_arguments"]["semantic_flags"]}],
            [], {"raw_fact_role": "discovery", "unit_id": unit["unit_id"]},
        )
        if projector:
            target["toolchain_id"] = unit["toolchain_id"]
        targets.append(target)
    link = closure.get("target_link_closure")
    raw_targets = link.get("targets", []) if isinstance(link, Mapping) else []
    skeletons: list[tuple[Mapping[str, Any], str]] = []
    for raw in raw_targets if isinstance(raw_targets, list) else []:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("output"), Mapping):
            continue
        output = normalize_binding(raw["output"], materialized=True)
        kind = "archive" if "archive_operation" in raw else "link"
        target_id = stable_build_id("target", {"kind": kind, "output": output["path"]})
        if output["path"] in owners:
            raise ValueError("build_ir_target_output_duplicate")
        owners[output["path"]] = target_id
        skeletons.append((raw, target_id))
    external: list[dict[str, Any]] = []
    for raw, target_id in skeletons:
        output = normalize_binding(raw["output"], materialized=True)
        inputs = []
        dependencies = []
        for ordinal, value in enumerate(list_value(raw.get("inputs"))):
            binding = normalize_binding(value, materialized=True)
            dependency = owners.get(binding["path"])
            if dependency and dependency not in dependencies:
                dependencies.append(dependency)
            inputs.append({"ordinal": ordinal, "role": "link-input",
                           "binding": binding, "dependency_target_id": dependency})
        arguments = string_list(raw.get("ordered_system_link_args"))
        for ordinal, argument in enumerate(arguments):
            external.append({
                "dependency_id": stable_build_id("external", {
                    "target": target_id, "ordinal": ordinal, "argument": argument,
                }),
                "kind": "ordered-link-argument",
                "name": argument,
                "consumer_target_ids": [target_id],
                "ordinal": ordinal,
                "provenance": {"raw_fact_role": "generated-build-closure"},
            })
        fact = raw.get("fact_file") if isinstance(raw.get("fact_file"), Mapping) else {}
        kind = "archive" if "archive_operation" in raw else "link"
        target = target_record(
            target_id, output["path"], kind,
            [output], inputs, dependencies, [], arguments,
            {"raw_fact_role": "generated-build-closure", "fact_path": fact.get("path")},
        )
        if kind == "archive":
            target["archive_semantics"] = {
                "operation": raw.get("archive_operation"),
                "ranlib_passes": len(string_list(raw.get("ranlib_drivers"))),
            }
        if projector:
            target["toolchain_id"] = projector.command(
                raw.get("driver"),
                "archiver" if kind == "archive" else "linker-driver",
            )
            if kind == "archive":
                target["auxiliary_toolchain_ids"] = sorted({
                    projector.command(token, "ranlib")
                    for token in raw.get("ranlib_drivers", [])
                })
        targets.append(target)
    merge_meson_targets(closure, targets, owners, external)
    targets.sort(key=lambda item: item["target_id"])
    external.sort(key=lambda item: item["dependency_id"])
    return targets, external, []


def _raw_refs(
    values: list[Mapping[str, Any]], *, host_bound: bool,
) -> list[dict[str, Any]]:
    expected = HOST_BOUND_RAW_ROLES if host_bound else RAW_ROLES
    result = []
    for value in values:
        role = value.get("role")
        if role not in expected:
            raise ValueError("build_ir_raw_fact_role_invalid")
        result.append({"role": role, "path": value.get("path"),
                       "sha256": value.get("sha256"), "size_bytes": value.get("size_bytes")})
    if {item["role"] for item in result} != expected or len(result) != len(expected):
        raise ValueError("build_ir_raw_fact_refs_incomplete")
    return sorted(result, key=lambda item: item["role"])


def _boundaries(closure: Mapping[str, Any], verification: Mapping[str, Any]) -> list[dict[str, Any]]:
    result = []
    for source, values in (("closure", closure.get("blockers")),
                           ("verification", verification.get("blockers"))):
        for value in list_value(values):
            item = copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {"kind": str(value)}
            item["source"] = source
            result.append(item)
    return result


def _unique(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {content_sha256(item): item for item in values}
    return [keyed[key] for key in sorted(keyed)]


def binding_map(value: Any) -> dict[str, dict[str, Any]]:
    return {str(item.get("path")): normalize_binding(item, materialized=True)
            for item in list_value(value) if isinstance(item, Mapping)}


def target_closure(targets: list[dict[str, Any]]) -> list[str]:
    pending = {item["target_id"]: set(item["dependency_target_ids"]) for item in targets}
    order = []
    while pending:
        ready = sorted(key for key, dependencies in pending.items() if not dependencies)
        if not ready:
            raise ValueError("build_ir_target_dependency_cycle")
        order.extend(ready)
        for key in ready:
            del pending[key]
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return order


__all__ = [
    "HOST_BOUND_RAW_ROLES", "RAW_ROLES", "project_build_ir", "target_closure",
]
