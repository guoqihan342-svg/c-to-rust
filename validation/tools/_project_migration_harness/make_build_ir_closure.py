from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

from .build_ir_projection import target_closure
from .make_build_ir_closure_resolution import (
    RESOLUTION_KIND, assess_external_dependency_resolutions,
)


def project_make_closure(
    report: Mapping[str, Any], targets: list[dict[str, Any]],
    external_dependencies: list[dict[str, Any]], *,
    link_classification_error_count: int,
    report_inputs_verified: bool,
    external_dependency_resolution_records: list[dict[str, Any]] | None = None,
    toolchains: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated, graph_facts = _project_generated_graph(report, targets)
    snapshot_present = report.get("repository_snapshot_ref") is not None
    snapshot_verified = snapshot_present and report_inputs_verified
    repository_complete = (
        snapshot_verified and graph_facts["leaf_input_bindings_complete"]
    )
    external_complete = link_classification_error_count == 0
    generated_materialized = all(
        item["binding"]["materialized"] for item in generated
    )
    resolution = assess_external_dependency_resolutions(
        report, targets, external_dependencies,
        resolution_records=external_dependency_resolution_records,
        toolchains=toolchains,
    )
    claim = {
        "role": "canonical_build_projection_only",
        "closure_complete": all((
            graph_facts["command_graph_complete"],
            graph_facts["generated_output_graph_complete"],
            repository_complete,
            external_complete,
            resolution["complete"],
        )),
        "command_graph_complete": graph_facts["command_graph_complete"],
        "generated_output_graph_complete": graph_facts[
            "generated_output_graph_complete"
        ],
        "selected_translation_units_complete": True,
        "repository_snapshot_cas_bound": snapshot_verified,
        "repository_input_closure_complete": repository_complete,
        "generated_outputs_materialized": generated_materialized,
        "external_dependencies_complete": external_complete,
        "external_dependency_resolution_complete": resolution["complete"],
        "external_dependency_resolution_kind": RESOLUTION_KIND,
        "external_dependency_resolution_records": resolution[
            "accepted_records"
        ],
        "external_dependency_resolution_error_count": resolution[
            "invalid_record_count"
        ],
        "link_argument_classification_error_count": (
            link_classification_error_count
        ),
        "unresolved_external_dependency_count": len(
            resolution["unresolved_dependency_ids"]
        ),
        "parameters_guessed": False,
        "commands_executed": False,
        "fact_collection_executed": True,
    }
    boundaries = _boundaries(
        claim, snapshot_present=snapshot_present,
        report_inputs_verified=report_inputs_verified,
        resolution=resolution,
    )
    return {
        "generated_inputs": generated,
        "boundaries": boundaries,
        "claim_boundary": claim,
    }


def _project_generated_graph(
    report: Mapping[str, Any], targets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    owners: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    graph_complete = True
    for target in targets:
        for output in target["outputs"]:
            path = output["path"]
            if path in owners:
                graph_complete = False
            else:
                owners[path] = (target, output)
    consumers = {path: set() for path in owners}
    leaf_paths = {item["path"] for item in report["input_refs"]}
    observed_leaves: set[str] = set()
    for target in targets:
        dependencies = []
        for item in target["ordered_inputs"]:
            path = item["binding"]["path"]
            owned = owners.get(path)
            expected = owned[0]["target_id"] if owned is not None else None
            if item.get("dependency_target_id") != expected:
                graph_complete = False
            if owned is None:
                observed_leaves.add(path)
                if path not in leaf_paths or not item["binding"]["materialized"]:
                    graph_complete = False
            else:
                consumers[path].add(target["target_id"])
                if expected not in dependencies:
                    dependencies.append(expected)
        if target["dependency_target_ids"] != dependencies:
            graph_complete = False
    generated = [
        {
            "binding": copy.deepcopy(output),
            "role": "target-output",
            "producer_target_id": target["target_id"],
            "consumer_target_ids": sorted(consumers[path]),
            "provenance": {"raw_fact_role": "make-dry-run-report"},
        }
        for path, (target, output) in owners.items()
    ]
    generated.sort(key=lambda item: item["binding"]["path"])
    command_complete = _command_coverage_complete(report, targets)
    try:
        target_closure(targets)
    except ValueError:
        graph_complete = False
    return generated, {
        "command_graph_complete": command_complete and graph_complete,
        "generated_output_graph_complete": graph_complete,
        "leaf_input_bindings_complete": observed_leaves == leaf_paths,
    }


def _command_coverage_complete(
    report: Mapping[str, Any], targets: list[dict[str, Any]],
) -> bool:
    commands = {command["ordinal"]: command for command in report["commands"]}
    if len(commands) != len(report["commands"]):
        return False
    observed: list[int] = []
    for target in targets:
        ordinal = target["provenance"].get("command_ordinal")
        command = commands.get(ordinal)
        kind = _report_kind(target)
        if command is None or command["kind"] != kind:
            return False
        if (
            [item["binding"]["path"] for item in target["ordered_inputs"]]
            != command["inputs"]
            or [item["path"] for item in target["outputs"]]
            != command["outputs"]
        ):
            return False
        observed.append(ordinal)
        if kind == "link":
            if (
                target["compile_argument_sets"]
                or target["ordered_link_arguments"] != command["argv"][1:]
            ):
                return False
            continue
        if target["ordered_link_arguments"]:
            return False
        own_sets = [
            item for item in target["compile_argument_sets"]
            if item.get("command_ordinal") == ordinal
        ]
        if len(own_sets) != 1 or not _argument_set_bound(own_sets[0], command):
            return False
        ranlib_count = 0
        for item in target["compile_argument_sets"]:
            item_ordinal = item.get("command_ordinal")
            if item_ordinal == ordinal:
                continue
            auxiliary = commands.get(item_ordinal)
            if (
                kind != "archive" or auxiliary is None
                or auxiliary["kind"] != "ranlib"
                or auxiliary["inputs"] != command["outputs"]
                or auxiliary["outputs"] != command["outputs"]
                or not _argument_set_bound(item, auxiliary)
            ):
                return False
            ranlib_count += 1
            observed.append(item_ordinal)
        if kind == "archive" and target["archive_semantics"][
            "ranlib_passes"
        ] != ranlib_count:
            return False
    return sorted(observed) == sorted(commands)


def _argument_set_bound(
    value: Mapping[str, Any], command: Mapping[str, Any],
) -> bool:
    return dict(value) == {
        "kind": command["kind"],
        "command_ordinal": command["ordinal"],
        "arguments": command["argv"][1:],
        "argv_sha256": command["argv_sha256"],
    }


def _report_kind(target: Mapping[str, Any]) -> str:
    return "compile" if target["kind"] == "object" else str(target["kind"])


def _boundaries(
    claim: Mapping[str, Any], *, snapshot_present: bool,
    report_inputs_verified: bool, resolution: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result = [{"kind": "make_dry_run_nonsemantic_fact_collection"}]
    if not claim["command_graph_complete"]:
        result.append({"kind": "make_command_graph_incomplete"})
    if not claim["generated_output_graph_complete"]:
        result.append({"kind": "make_generated_output_graph_incomplete"})
    if not snapshot_present:
        result.append({"kind": "make_repository_input_snapshot_missing"})
    elif not report_inputs_verified:
        result.append({"kind": "make_repository_input_snapshot_unverified"})
    elif not claim["repository_input_closure_complete"]:
        result.append({"kind": "make_repository_input_closure_incomplete"})
    if not claim["external_dependencies_complete"]:
        result.append({
            "kind": "make_link_argument_classification_incomplete",
            "error_count": claim["link_argument_classification_error_count"],
        })
    if not claim["generated_outputs_materialized"]:
        result.append({"kind": "make_generated_outputs_not_materialized"})
    if not claim["external_dependency_resolution_complete"]:
        result.append({
            "kind": "make_external_dependency_resolution_unverified",
            "dependency_count": claim["unresolved_external_dependency_count"],
            "dependency_ids": list(resolution["unresolved_dependency_ids"]),
            "invalid_record_count": resolution["invalid_record_count"],
            "reason_codes": list(resolution["reason_codes"]),
            "required_resolution_kind": RESOLUTION_KIND,
        })
    return result


__all__ = ["project_make_closure"]
