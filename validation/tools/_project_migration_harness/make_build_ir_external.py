from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .build_ir import stable_build_id


_CONTROL_FLAGS = {
    "-E", "-S", "-export-dynamic", "-fPIC", "-fPIE", "-flto",
    "-fno-lto", "-fno-pie", "-fno-PIE", "-fpic", "-fpie", "-no-pie",
    "-nodefaultlibs", "-nostartfiles", "-nostdlib", "-pie", "-r",
    "-rdynamic", "-s", "-shared", "-static",
}
_CONTROL_PAIRS = {
    "--entry", "--soname", "--target", "-D", "-I", "-U", "-e",
    "-idirafter", "-imacros", "-include", "-iquote", "-isystem", "-m",
    "-soname", "-target", "-x",
}
_FORWARDED_CONTROL_FLAGS = {
    "--as-needed", "--build-id", "--eh-frame-hdr", "--end-group",
    "--gc-sections", "--no-as-needed", "--no-gc-sections",
    "--no-whole-archive", "--start-group", "--strip-all",
    "--whole-archive", "-Bdynamic", "-Bstatic", "-E", "-S", "-s",
}
_FORWARDED_CONTROL_PAIRS = {"--entry", "--soname", "-e", "-m", "-soname", "-z"}
_FORWARDED_SEARCH_PAIRS = {"--library-path", "--rpath", "--rpath-link", "-L", "-rpath", "-rpath-link"}


def project_make_external_dependencies(
    report: Mapping[str, Any], targets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    by_ordinal = {
        target["provenance"]["command_ordinal"]: target
        for target in targets if target["kind"] == "link"
    }
    result = []
    classification_errors = 0
    for command in report["commands"]:
        if command["kind"] != "link":
            continue
        target = by_ordinal[command["ordinal"]]
        classified, errors = _classify_link_args(command)
        classification_errors += errors
        for ordinal, arguments, kind in classified:
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
    return (
        sorted(result, key=lambda item: item["dependency_id"]),
        classification_errors,
    )


def _classify_link_args(
    command: Mapping[str, Any],
) -> tuple[list[tuple[int, list[str], str]], int]:
    arguments = command["argv"][1:]
    result: list[tuple[int, list[str], str]] = []
    errors = 0
    operands = 0
    outputs = 0
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in {"-o", "--output"}:
            if index + 1 >= len(arguments):
                errors += 1
            else:
                outputs += 1
                index += 2
                continue
        elif argument.startswith("--output=") or (
            argument.startswith("-o") and len(argument) > 2
        ):
            outputs += 1
        elif argument in {"-L", "--library-path"}:
            if index + 1 >= len(arguments):
                errors += 1
            else:
                result.append((
                    index, [argument, arguments[index + 1]],
                    "library-search-path",
                ))
                index += 2
                continue
        elif argument.startswith("--library-path=") or (
            argument.startswith("-L") and len(argument) > 2
        ):
            result.append((index, [argument], "library-search-path"))
        elif argument.startswith("-l") and len(argument) > 2:
            result.append((index, [argument], "library-name"))
        elif argument in {
            "-pthread", "-pthreads", "-static-libgcc", "-static-libstdc++",
        }:
            result.append((index, [argument], "library-name"))
        elif argument.startswith("-Wl,"):
            forwarded, forwarded_errors = _classify_forwarded(argument, index)
            result.extend(forwarded)
            errors += forwarded_errors
        elif argument in _CONTROL_PAIRS:
            if index + 1 >= len(arguments):
                errors += 1
            else:
                index += 2
                continue
        elif _known_control(argument):
            pass
        elif argument.startswith("-"):
            errors += 1
        else:
            operands += 1
        index += 1
    if operands != len(command["inputs"]):
        errors += 1
    if outputs != len(command["outputs"]):
        errors += 1
    return result, errors


def _classify_forwarded(
    argument: str, ordinal: int,
) -> tuple[list[tuple[int, list[str], str]], int]:
    values = argument[4:].split(",")
    result: list[tuple[int, list[str], str]] = []
    errors = 0
    index = 0
    while index < len(values):
        value = values[index]
        if value.startswith("-l") and len(value) > 2:
            result.append((ordinal, [f"-Wl,{value}"], "library-name"))
        elif value.startswith("-L") and len(value) > 2:
            result.append((ordinal, [f"-Wl,{value}"], "library-search-path"))
        elif value in _FORWARDED_SEARCH_PAIRS and index + 1 < len(values):
            pair = f"-Wl,{value},{values[index + 1]}"
            result.append((ordinal, [pair], "library-search-path"))
            index += 2
            continue
        elif value in _FORWARDED_CONTROL_PAIRS and index + 1 < len(values):
            index += 2
            continue
        elif value in _FORWARDED_CONTROL_FLAGS or value.startswith("--build-id="):
            pass
        else:
            errors += 1
        index += 1
    return result, errors


def _known_control(argument: str) -> bool:
    return (
        argument in _CONTROL_FLAGS
        or argument.startswith(("-O", "-g", "-std=", "-flto="))
        or argument.startswith("-W")
        or (argument.startswith(("-D", "-I", "-U")) and len(argument) > 2)
    )


__all__ = [
    "project_make_external_dependencies",
]
