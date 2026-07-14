from __future__ import annotations

from collections.abc import Mapping
import copy
from pathlib import Path
from typing import Any

from .build_ir import (
    BUILD_IR_EXTRACTOR, BUILD_IR_KIND, BUILD_IR_SCHEMA_VERSION,
    finalize_build_ir, normalize_binding, stable_build_id, target_record,
)
from .build_ir_host_toolchains import HostToolchainProjection
from .build_ir_projection import target_closure
from .build_ir_toolchains import make_command_tool_role
from .compile_database import parse_compile_entry
from .discovery_variants import finalize_variants
from .make_build_ir_external import (
    MAKE_BUILD_BOUNDARIES, project_make_external_dependencies,
)
from .make_build_ir_toolchains import (
    abi_facts, legacy_toolchain_id, legacy_toolchains,
)


MAKE_RAW_ROLE = "make-dry-run-report"


def normalize_make_translation_units(
    repo_root: Path, report: Mapping[str, Any], max_units: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    parsed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    blockers: list[str] = []
    for command in report.get("commands", []):
        if not isinstance(command, Mapping) or command.get("kind") != "compile":
            continue
        entry = {
            "directory": ".",
            "file": command["inputs"][0],
            "arguments": list(command["argv"]),
            "output": command["outputs"][0],
        }
        unit, rejection = parse_compile_entry(
            entry, int(command["ordinal"]), repo_root, repo_root,
        )
        if unit is not None:
            parsed.append(unit)
        if rejection is not None:
            rejected.append(rejection)
            blockers.append("make_compile_command_unrepresentable")
    units, variant_rejections, variant_blockers = finalize_variants(parsed, max_units)
    rejected.extend(variant_rejections)
    blockers.extend(variant_blockers)
    if variant_rejections:
        blockers.append("make_compile_command_not_lossless")
    compile_count = sum(
        command.get("kind") == "compile"
        for command in report.get("commands", [])
        if isinstance(command, Mapping)
    )
    if not units or len(units) != compile_count:
        blockers.append("make_translation_units_incomplete")
    return units, rejected, sorted(set(blockers))


def project_make_build_ir(
    repo_root: Path, report: Mapping[str, Any],
    report_reference: Mapping[str, Any], *, max_units: int,
    toolchain_evidence: Mapping[str, Any] | None = None,
    toolchain_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    units, _rejected, blockers = normalize_make_translation_units(
        repo_root, report, max_units,
    )
    if blockers:
        raise ValueError(blockers[0])
    projector = (
        HostToolchainProjection(toolchain_evidence)
        if toolchain_evidence is not None else None
    )
    if (projector is None) != (toolchain_reference is None):
        raise ValueError("make_build_ir_toolchain_binding_invalid")
    projected_units = _project_units(units, report, projector)
    targets = _project_targets(report, projected_units, projector)
    external = project_make_external_dependencies(report, targets)
    sources = _unique_bindings([unit["source"] for unit in projected_units])
    generated = [
        {
            "binding": copy.deepcopy(output),
            "role": "target-output",
            "producer_target_id": target["target_id"],
            "consumer_target_ids": [],
            "provenance": {"raw_fact_role": MAKE_RAW_ROLE},
        }
        for target in targets for output in target["outputs"]
    ]
    generated.sort(key=lambda item: item["binding"]["path"])
    raw_refs = [{"role": MAKE_RAW_ROLE, **dict(report_reference)}]
    if toolchain_reference is not None:
        raw_refs.append({
            "role": "c-toolchain-evidence", **dict(toolchain_reference),
        })
    payload = {
        "schema_version": BUILD_IR_SCHEMA_VERSION,
        "artifact_kind": BUILD_IR_KIND,
        "status": "ready_with_boundaries",
        "extractor": dict(BUILD_IR_EXTRACTOR),
        "raw_fact_refs": sorted(raw_refs, key=lambda item: item["role"]),
        "build_metadata": [normalize_binding(report["makefile_ref"], materialized=True)],
        "translation_units": projected_units,
        "source_inputs": sources,
        "generated_inputs": generated,
        "targets": targets,
        "target_closure": target_closure(targets),
        "toolchains": projector.records() if projector else legacy_toolchains(report),
        "external_dependencies": external,
        "abi_facts": abi_facts(projected_units),
        "boundaries": [
            {"kind": "make_dry_run_nonsemantic_fact_collection"},
            *copy.deepcopy(MAKE_BUILD_BOUNDARIES),
        ],
        "claim_boundary": {
            "role": "canonical_build_projection_only",
            "closure_complete": False,
            "command_graph_complete": True,
            "selected_translation_units_complete": True,
            "repository_input_closure_complete": False,
            "generated_outputs_materialized": False,
            "external_dependencies_complete": False,
            "parameters_guessed": False,
            "commands_executed": False,
            "fact_collection_executed": True,
            "host_toolchain_bound": projector is not None,
            "toolchain_profile": projector.profile if projector else None,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    return finalize_build_ir(payload)


def _project_units(
    units: list[dict[str, Any]], report: Mapping[str, Any],
    projector: HostToolchainProjection | None,
) -> list[dict[str, Any]]:
    commands = {command["ordinal"]: command for command in report["commands"]}
    result = []
    for raw in units:
        command = commands[raw["entry"]["index"]]
        toolchain_id = (
            projector.compile(command["tool"], [], raw["language"])
            if projector else legacy_toolchain_id(command["tool"], report)
        )
        result.append({
            "unit_id": raw["unit_id"],
            "variant_index": raw["variant_index"],
            "variant_count": raw["variant_count"],
            "source": normalize_binding(raw["source"], materialized=True),
            "working_directory": raw["working_directory"],
            "compiler": raw["compiler"],
            "compiler_wrappers": list(raw["compiler_wrappers"]),
            "language": raw["language"],
            "toolchain_id": toolchain_id,
            "includes": copy.deepcopy(raw["includes"]),
            "defines": copy.deepcopy(raw["defines"]),
            "redacted_define_count": raw["redacted_define_count"],
            "compile_arguments": {
                "semantic_flags": list(raw["semantic_flags"]),
                "expanded_argv_sha256": raw["expanded_argv_sha256"],
                "response_files": [],
                "direct_argv": list(command["argv"]),
                "direct_argv_sha256": command["argv_sha256"],
            },
            "output": {
                "path": raw["output"], "kind": "file", "materialized": False,
            },
            "provenance": {
                "raw_fact_role": MAKE_RAW_ROLE,
                "entry_index": raw["entry"]["index"],
                "entry_sha256": raw["entry"]["sha256"],
                "extractor": dict(BUILD_IR_EXTRACTOR),
            },
        })
    return sorted(result, key=lambda item: item["unit_id"])


def _project_targets(
    report: Mapping[str, Any], units: list[dict[str, Any]],
    projector: HostToolchainProjection | None,
) -> list[dict[str, Any]]:
    unit_by_ordinal = {unit["provenance"]["entry_index"]: unit for unit in units}
    leaves = {
        item["path"]: normalize_binding(item, materialized=True)
        for item in report["input_refs"]
    }
    owners: dict[str, dict[str, Any]] = {}
    targets: list[dict[str, Any]] = []
    for command in report["commands"]:
        kind = command["kind"]
        if kind == "ranlib":
            _merge_ranlib(command, owners, projector)
            continue
        output_path = command["outputs"][0]
        if output_path in owners:
            raise ValueError("make_build_ir_output_duplicate")
        output = {"path": output_path, "kind": "file", "materialized": False}
        canonical_kind = "object" if kind == "compile" else kind
        target_id = stable_build_id(
            "target", {"kind": canonical_kind, "output": output_path}
        )
        inputs, dependencies = _target_inputs(command, owners, leaves)
        if kind == "compile":
            unit = unit_by_ordinal.get(command["ordinal"])
            if unit is None or unit["output"]["path"] != output_path:
                raise ValueError("make_build_ir_compile_unit_missing")
            inputs = [{
                "ordinal": 0, "role": "source", "binding": unit["source"],
                "dependency_target_id": None,
            }]
        argument_sets = [] if kind == "link" else [_command_arguments(command)]
        link_arguments = list(command["argv"][1:]) if kind == "link" else []
        target = target_record(
            target_id, output_path, "object" if kind == "compile" else kind,
            [output], inputs, dependencies, argument_sets, link_arguments,
            {"raw_fact_role": MAKE_RAW_ROLE, "command_ordinal": command["ordinal"]},
        )
        if kind == "archive":
            target["archive_semantics"] = {
                "operation": command["argv"][1].lstrip("-"),
                "ranlib_passes": 0,
            }
        if projector and kind == "compile":
            target["toolchain_id"] = unit["toolchain_id"]
        elif projector:
            target["toolchain_id"] = projector.command(
                command["tool"], make_command_tool_role(command),
            )
        else:
            target["toolchain_id"] = legacy_toolchain_id(command["tool"], report)
        owners[output_path] = target
        targets.append(target)
    return sorted(targets, key=lambda item: item["target_id"])


def _target_inputs(
    command: Mapping[str, Any], owners: Mapping[str, dict[str, Any]],
    leaves: Mapping[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    inputs = []
    dependencies = []
    for ordinal, path in enumerate(command["inputs"]):
        owner = owners.get(path)
        binding = owner["outputs"][0] if owner is not None else leaves.get(path)
        if binding is None:
            raise ValueError("make_build_ir_unbound_command_input")
        dependency = owner["target_id"] if owner is not None else None
        if dependency is not None and dependency not in dependencies:
            dependencies.append(dependency)
        inputs.append({
            "ordinal": ordinal, "role": "link-input", "binding": copy.deepcopy(binding),
            "dependency_target_id": dependency,
        })
    return inputs, dependencies


def _merge_ranlib(
    command: Mapping[str, Any], owners: Mapping[str, dict[str, Any]],
    projector: HostToolchainProjection | None,
) -> None:
    target = owners.get(command["inputs"][0])
    if target is None or target["kind"] != "archive":
        raise ValueError("make_build_ir_ranlib_without_archive")
    target["compile_argument_sets"].append(_command_arguments(command))
    target["archive_semantics"]["ranlib_passes"] += 1
    if projector:
        identifiers = target.setdefault("auxiliary_toolchain_ids", [])
        identifiers.append(projector.command(command["tool"], "ranlib"))
        target["auxiliary_toolchain_ids"] = sorted(set(identifiers))


def _command_arguments(command: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": command["kind"], "command_ordinal": command["ordinal"],
        "arguments": list(command["argv"][1:]),
        "argv_sha256": command["argv_sha256"],
    }


def _unique_bindings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {item["path"]: copy.deepcopy(item) for item in values}
    if len(keyed) != len(values):
        raise ValueError("make_build_ir_source_binding_duplicate")
    return [keyed[path] for path in sorted(keyed)]


__all__ = [
    "MAKE_RAW_ROLE", "normalize_make_translation_units", "project_make_build_ir",
]
