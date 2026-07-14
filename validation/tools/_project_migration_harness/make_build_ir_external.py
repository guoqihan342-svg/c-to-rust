from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .build_ir import stable_build_id


MAKE_BUILD_BOUNDARIES = [
    {"kind": "make_header_inputs_not_enumerated"},
    {"kind": "make_generated_outputs_not_materialized"},
    {"kind": "make_external_dependency_resolution_unverified"},
]


def project_make_external_dependencies(
    report: Mapping[str, Any], targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_ordinal = {
        target["provenance"]["command_ordinal"]: target
        for target in targets if target["kind"] == "link"
    }
    result = []
    for command in report["commands"]:
        if command["kind"] != "link":
            continue
        target = by_ordinal[command["ordinal"]]
        for ordinal, arguments, kind in _ordered_external_args(command["argv"][1:]):
            result.append({
                "dependency_id": stable_build_id("external", {
                    "target": target["target_id"], "ordinal": ordinal,
                    "arguments": arguments,
                }),
                "kind": kind,
                "name": " ".join(arguments),
                "consumer_target_ids": [target["target_id"]],
                "ordinal": ordinal,
                "arguments": arguments,
                "resolved": False,
                "provenance": {"raw_fact_role": "make-dry-run-report"},
            })
    return sorted(result, key=lambda item: item["dependency_id"])


def _ordered_external_args(
    arguments: list[str],
) -> list[tuple[int, list[str], str]]:
    result = []
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument == "-L" and index + 1 < len(arguments):
            result.append((index, [argument, arguments[index + 1]], "library-search-path"))
            index += 2
            continue
        if argument.startswith("-L") and len(argument) > 2:
            result.append((index, [argument], "library-search-path"))
        elif argument.startswith("-l") and len(argument) > 2:
            result.append((index, [argument], "library-name"))
        index += 1
    return result


__all__ = [
    "MAKE_BUILD_BOUNDARIES", "project_make_external_dependencies",
]
