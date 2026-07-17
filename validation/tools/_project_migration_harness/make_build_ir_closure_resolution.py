from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256, stable_build_id, validate_artifact_reference
from .build_ir_host_toolchains import validate_host_bound_toolchains
from .build_ir_toolchains import tool_basename


RESOLUTION_KIND = "toolchain-provided-link-argument"
WITNESS_KIND = "c-toolchain-link-argument-resolution"
_RECORD_FIELDS = {
    "resolution_id", "schema_version", "resolution_kind", "dependency_id",
    "consumer_target_id", "command_ordinal", "command_argv_sha256",
    "argument_ordinal", "arguments", "toolchain_id", "toolchain_driver",
    "toolchain_evidence_sha256", "driver_binary_sha256", "sysroot_probe",
    "witness",
}
_WITNESS_FIELDS = {
    "artifact_kind", "status", "path", "sha256", "size_bytes",
}


def assess_external_dependency_resolutions(
    report: Mapping[str, Any], targets: list[dict[str, Any]],
    dependencies: list[dict[str, Any]], *,
    resolution_records: list[dict[str, Any]] | None = None,
    toolchains: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    records = resolution_records if isinstance(resolution_records, list) else []
    target_by_id = _unique_map(targets, "target_id")
    command_by_ordinal = _unique_map(report.get("commands", []), "ordinal")
    toolchain_by_id, toolchain_error = _toolchain_map(toolchains)
    record_by_dependency, record_errors = _resolution_map(records)
    unresolved: list[str] = []
    accepted: list[dict[str, Any]] = []
    reasons = set(record_errors)
    dependency_ids = set()
    for index, dependency in enumerate(dependencies):
        identifier = dependency.get("dependency_id")
        if not isinstance(identifier, str) or not identifier:
            identifier = f"invalid-external-dependency-{index}"
            reasons.add("external_dependency_identity_invalid")
        elif identifier in dependency_ids:
            reasons.add("external_dependency_identity_duplicate")
        dependency_ids.add(identifier)
        record = record_by_dependency.get(identifier)
        failure = _resolution_failure(
            report, dependency, record, target_by_id, command_by_ordinal,
            toolchain_by_id, toolchain_error,
        )
        if failure:
            unresolved.append(identifier)
            reasons.update(failure)
        else:
            accepted.append(copy.deepcopy(dict(record)))
    unknown_records = sorted(set(record_by_dependency) - dependency_ids)
    if unknown_records:
        reasons.add("resolution_record_dependency_unknown")
    invalid_record_count = max(0, len(records) - len(accepted))
    complete = not unresolved and not reasons
    return {
        "complete": complete,
        "accepted_records": sorted(
            accepted, key=lambda item: item["resolution_id"],
        ),
        "unresolved_dependency_ids": sorted(unresolved),
        "invalid_record_count": invalid_record_count,
        "reason_codes": sorted(reasons),
    }


def create_toolchain_argument_resolution_record(
    report_command: Mapping[str, Any], target: Mapping[str, Any],
    dependency: Mapping[str, Any], toolchain: Mapping[str, Any],
    witness: Mapping[str, Any],
) -> dict[str, Any]:
    driver = _driver_tool(toolchain)
    core = {
        "schema_version": 1,
        "resolution_kind": RESOLUTION_KIND,
        "dependency_id": dependency["dependency_id"],
        "consumer_target_id": dependency["consumer_target_ids"][0],
        "command_ordinal": report_command["ordinal"],
        "command_argv_sha256": report_command["argv_sha256"],
        "argument_ordinal": dependency["ordinal"],
        "arguments": list(dependency["arguments"]),
        "toolchain_id": target["toolchain_id"],
        "toolchain_driver": toolchain["driver"],
        "toolchain_evidence_sha256": toolchain["evidence_sha256"],
        "driver_binary_sha256": driver["binary"]["sha256"],
        "sysroot_probe": copy.deepcopy(driver["sysroot"]),
        "witness": copy.deepcopy(dict(witness)),
    }
    return {
        "resolution_id": stable_build_id("make-external-resolution", core),
        **core,
    }


def _resolution_failure(
    report: Mapping[str, Any], dependency: Mapping[str, Any],
    record: Mapping[str, Any] | None,
    targets: Mapping[Any, Mapping[str, Any]],
    commands: Mapping[Any, Mapping[str, Any]],
    toolchains: Mapping[Any, Mapping[str, Any]],
    toolchain_error: str | None,
) -> set[str]:
    reasons: set[str] = set()
    if dependency.get("resolved") is not True:
        reasons.add("external_dependency_not_marked_resolved")
    target, command = _bound_target_command(dependency, targets, commands, reasons)
    if record is None:
        reasons.add("external_dependency_resolution_record_missing")
        if toolchain_error:
            reasons.add(toolchain_error)
        return reasons
    if target is None or command is None:
        return reasons
    toolchain = toolchains.get(target.get("toolchain_id"))
    if toolchain_error:
        reasons.add(toolchain_error)
    elif toolchain is None:
        reasons.add("external_dependency_toolchain_unbound")
    elif not _record_matches(record, dependency, target, command, toolchain):
        reasons.add("external_dependency_resolution_record_invalid")
    return reasons


def _bound_target_command(
    dependency: Mapping[str, Any],
    targets: Mapping[Any, Mapping[str, Any]],
    commands: Mapping[Any, Mapping[str, Any]], reasons: set[str],
) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
    consumers = dependency.get("consumer_target_ids")
    if not isinstance(consumers, list) or len(consumers) != 1:
        reasons.add("external_dependency_consumer_invalid")
        return None, None
    target = targets.get(consumers[0])
    if target is None or target.get("kind") != "link":
        reasons.add("external_dependency_link_target_invalid")
        return None, None
    provenance = target.get("provenance")
    ordinal = provenance.get("command_ordinal") if isinstance(provenance, Mapping) else None
    command = commands.get(ordinal)
    if command is None or command.get("kind") != "link":
        reasons.add("external_dependency_report_command_missing")
        return target, None
    argv = command.get("argv")
    link_arguments = argv[1:] if isinstance(argv, list) and argv else []
    if (
        not isinstance(argv, list) or not argv
        or command.get("argv_sha256") != content_sha256(argv)
    ):
        reasons.add("external_dependency_report_command_drift")
    argument_ordinal = dependency.get("ordinal")
    arguments = dependency.get("arguments")
    if (
        isinstance(argument_ordinal, bool) or not isinstance(argument_ordinal, int)
        or argument_ordinal < 0 or not isinstance(arguments, list) or not arguments
        or link_arguments[
            argument_ordinal:argument_ordinal + len(arguments)
        ] != arguments
    ):
        reasons.add("external_dependency_argument_binding_invalid")
    return target, command


def _record_matches(
    record: Mapping[str, Any], dependency: Mapping[str, Any],
    target: Mapping[str, Any], command: Mapping[str, Any],
    toolchain: Mapping[str, Any],
) -> bool:
    if set(record) != _RECORD_FIELDS or record.get("schema_version") != 1:
        return False
    driver = _driver_tool(toolchain)
    witness = record.get("witness")
    if (
        record.get("resolution_kind") != RESOLUTION_KIND
        or toolchain.get("role") not in {"linker", "linker-driver"}
        or driver is None or not _valid_witness(witness)
    ):
        return False
    core = {key: record[key] for key in _RECORD_FIELDS - {"resolution_id"}}
    consumers = dependency["consumer_target_ids"]
    return (
        record.get("resolution_id")
        == stable_build_id("make-external-resolution", core)
        and record.get("dependency_id") == dependency.get("dependency_id")
        and record.get("consumer_target_id") == consumers[0]
        and record.get("command_ordinal") == command.get("ordinal")
        and record.get("command_argv_sha256") == command.get("argv_sha256")
        and record.get("argument_ordinal") == dependency.get("ordinal")
        and record.get("arguments") == dependency.get("arguments")
        and record.get("toolchain_id") == target.get("toolchain_id")
        and record.get("toolchain_driver") == toolchain.get("driver")
        and tool_basename(command["tool"]) == tool_basename(toolchain["driver"])
        and record.get("toolchain_evidence_sha256")
        == toolchain.get("evidence_sha256")
        and record.get("driver_binary_sha256") == driver["binary"]["sha256"]
        and record.get("sysroot_probe") == driver["sysroot"]
    )


def _valid_witness(value: Any) -> bool:
    try:
        validate_artifact_reference(value, "resolution_witness_invalid")
    except ValueError:
        return False
    return (
        set(value) == _WITNESS_FIELDS
        and value.get("artifact_kind") == WITNESS_KIND
        and value.get("status") == "verified"
    )


def _driver_tool(toolchain: Mapping[str, Any]) -> Mapping[str, Any] | None:
    tools = toolchain.get("tools")
    if not isinstance(tools, list):
        return None
    drivers = [item for item in tools if item.get("relation") == "driver"]
    return drivers[0] if len(drivers) == 1 else None


def _toolchain_map(
    toolchains: list[dict[str, Any]] | None,
) -> tuple[dict[Any, Mapping[str, Any]], str | None]:
    if toolchains is None:
        return {}, "external_dependency_toolchain_evidence_missing"
    try:
        validate_host_bound_toolchains(toolchains)
    except ValueError:
        return {}, "external_dependency_toolchain_evidence_invalid"
    return _unique_map(toolchains, "toolchain_id"), None


def _resolution_map(
    records: list[dict[str, Any]],
) -> tuple[dict[Any, Mapping[str, Any]], list[str]]:
    result: dict[Any, Mapping[str, Any]] = {}
    errors = []
    for record in records:
        identifier = record.get("dependency_id") if isinstance(record, Mapping) else None
        if not isinstance(identifier, str) or identifier in result:
            errors.append("external_dependency_resolution_record_set_invalid")
        else:
            result[identifier] = record
    return result, sorted(set(errors))


def _unique_map(values: Any, key: str) -> dict[Any, Mapping[str, Any]]:
    if not isinstance(values, list):
        return {}
    result = {}
    for value in values:
        if not isinstance(value, Mapping) or value.get(key) in result:
            continue
        result[value.get(key)] = value
    return result


__all__ = [
    "RESOLUTION_KIND", "WITNESS_KIND",
    "assess_external_dependency_resolutions",
    "create_toolchain_argument_resolution_record",
]
