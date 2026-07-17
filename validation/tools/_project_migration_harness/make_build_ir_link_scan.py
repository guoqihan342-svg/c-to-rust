from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from pathlib import Path
import re
from typing import Any

from .ledger_security import assert_no_secrets
from .link_system_arguments import normalize_system_link_argument
from .make_dry_run_binding import normalize_repository_path
from .make_dry_run_parser import validate_make_archive_argv


_PAIR_OPTIONS = {
    "--entry", "--soname", "--target", "-D", "-U", "-e", "-m",
    "-soname", "-target", "-x",
}
_RESOLUTION_FLAGS = {
    "-pthread", "-pthreads", "-static-libgcc", "-static-libstdc++",
}
_SAFE_PAIR_VALUE = re.compile(r"^[A-Za-z0-9_+.,:=@%-]{1,512}$")


def scan_make_archive(
    command: Mapping[str, Any], target: Mapping[str, Any],
    report: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    argv = _argv(command)
    inputs = _target_bindings(target)
    workdir = str(report.get("working_directory", "."))
    line = command.get("line_number", 1)
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        line = 1
    try:
        _kind, parsed_inputs, parsed_outputs = validate_make_archive_argv(
            argv, line, workdir,
        )
    except ValueError as error:
        raise ValueError("make_build_ir_archive_argv_invalid") from error
    if parsed_outputs != command.get("outputs"):
        raise ValueError("make_build_ir_archive_output_drift")
    if (
        parsed_inputs != command.get("inputs")
        or parsed_inputs != [binding.get("path") for binding in inputs]
    ):
        raise ValueError("make_build_ir_archive_input_drift")
    occurrences = [
        _occurrence(index, index + 1, 1, "input", index)
        for index in range(len(inputs))
    ]
    return _raw_authority(inputs, [], [], occurrences), []


def scan_make_link(
    repo_root: Path, command: Mapping[str, Any], target: Mapping[str, Any],
    report: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    arguments = _argv(command)[1:]
    workdir = str(report.get("working_directory", "."))
    base = repo_root / ("" if workdir == "." else workdir)
    inputs = _target_bindings(target)
    search_roots: list[dict[str, Any]] = []
    system: list[str] = []
    occurrences: list[dict[str, Any]] = []
    resolution: list[dict[str, Any]] = []
    input_index = output_count = semantic_index = index = 0
    while index < len(arguments):
        argument = arguments[index]
        output = _output_argument(arguments, index, workdir)
        if output is not None:
            path, consumed = output
            if path != command["outputs"][0]:
                raise ValueError("make_build_ir_link_output_drift")
            output_count += 1
            index += consumed
            continue
        root = _search_root_argument(arguments, index, workdir)
        if root is not None:
            binding, consumed = root
            reference = len(search_roots)
            search_roots.append(binding)
            occurrences.append(_occurrence(
                len(occurrences), semantic_index, consumed,
                "search-root", reference,
            ))
            resolution.append({
                "ordinal": index,
                "arguments": arguments[index:index + consumed],
                "kind": "library-search-path",
            })
            index += consumed
            semantic_index += consumed
            continue
        if not argument.startswith(("-", "/")):
            if input_index >= len(inputs):
                raise ValueError("make_build_ir_link_input_count_invalid")
            path = _repository_path(argument, workdir)
            if (
                path != command["inputs"][input_index]
                or path != inputs[input_index]["path"]
            ):
                raise ValueError("make_build_ir_link_input_drift")
            occurrences.append(_occurrence(
                len(occurrences), semantic_index, 1, "input", input_index,
            ))
            input_index += 1
            index += 1
            semantic_index += 1
            continue
        if argument in _PAIR_OPTIONS:
            if index + 1 >= len(arguments):
                raise ValueError("make_build_ir_link_option_value_missing")
            pair = arguments[index:index + 2]
            if not all(_safe_pair_token(value) for value in pair):
                raise ValueError("make_build_ir_link_argument_unrepresentable")
            for value in pair:
                _append_system(system, occurrences, value, semantic_index)
                semantic_index += 1
            index += 2
            continue
        normalized = normalize_system_link_argument(repo_root, base, argument)
        if normalized is None:
            raise ValueError("make_build_ir_link_argument_unrepresentable")
        _append_system(system, occurrences, normalized, semantic_index)
        kind = _resolution_kind(argument)
        if kind is not None:
            resolution.append({
                "ordinal": index, "arguments": [argument], "kind": kind,
            })
        index += 1
        semantic_index += 1
    if input_index != len(inputs) or output_count != 1:
        raise ValueError("make_build_ir_link_command_closure_invalid")
    return _raw_authority(inputs, search_roots, system, occurrences), resolution


def _output_argument(
    arguments: Sequence[str], index: int, workdir: str,
) -> tuple[str, int] | None:
    value = arguments[index]
    if value in {"-o", "--output"}:
        if index + 1 >= len(arguments):
            raise ValueError("make_build_ir_link_output_missing")
        return _repository_path(arguments[index + 1], workdir), 2
    if value.startswith("--output="):
        return _repository_path(value.split("=", 1)[1], workdir), 1
    if value.startswith("-o") and len(value) > 2:
        return _repository_path(value[2:], workdir), 1
    return None


def _search_root_argument(
    arguments: Sequence[str], index: int, workdir: str,
) -> tuple[dict[str, Any], int] | None:
    value = arguments[index]
    consumed = 1
    if value in {"-L", "--library-path"}:
        if index + 1 >= len(arguments):
            raise ValueError("make_build_ir_link_search_root_missing")
        path, consumed = arguments[index + 1], 2
    elif value.startswith("--library-path="):
        path = value.split("=", 1)[1]
    elif value.startswith("-L") and len(value) > 2:
        path = value[2:]
    else:
        path = _forwarded_search_root(value)
        if path is None:
            return None
    normalized = _repository_path(path, workdir)
    return {"path": normalized, "kind": "directory", "materialized": False}, consumed


def _forwarded_search_root(value: str) -> str | None:
    if not value.startswith("-Wl,"):
        return None
    parts = value[4:].split(",")
    if len(parts) == 1 and parts[0].startswith("-L") and len(parts[0]) > 2:
        return parts[0][2:]
    if len(parts) == 2 and parts[0] in {"-L", "--library-path"}:
        return parts[1]
    if len(parts) == 1 and parts[0].startswith("--library-path="):
        return parts[0].split("=", 1)[1]
    return None


def _resolution_kind(value: str) -> str | None:
    if value in _RESOLUTION_FLAGS:
        return "library-name"
    if value.startswith("-l") and len(value) > 2:
        return "library-name"
    if value.upper().startswith("/DEFAULTLIB:"):
        return "library-name"
    if value.startswith("-Wl,"):
        parts = value[4:].split(",")
        if len(parts) == 1 and parts[0].startswith("-l") and len(parts[0]) > 2:
            return "library-name"
    return None


def _raw_authority(
    inputs: list[dict[str, Any]], search_roots: list[dict[str, Any]],
    system: list[str], occurrences: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "inputs": inputs,
        "search_roots": search_roots,
        "ordered_system_link_args": system,
        "external_native_libraries": [],
        "response_files": [],
        "ordered_link_occurrences": occurrences,
    }


def _target_bindings(target: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = target.get("ordered_inputs")
    if not isinstance(values, list):
        raise ValueError("make_build_ir_link_inputs_invalid")
    return [copy.deepcopy(item["binding"]) for item in values]


def _append_system(
    system: list[str], occurrences: list[dict[str, Any]],
    value: str, argument_index: int,
) -> None:
    reference = len(system)
    system.append(value)
    occurrences.append(_occurrence(
        len(occurrences), argument_index, 1, "system-argument", reference,
    ))


def _occurrence(
    ordinal: int, argument_index: int, argument_count: int,
    kind: str, reference_ordinal: int,
) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "argument_index": argument_index,
        "argument_count": argument_count,
        "kind": kind,
        "reference_ordinal": reference_ordinal,
    }


def _safe_pair_token(value: str) -> bool:
    if _SAFE_PAIR_VALUE.fullmatch(value) is None:
        return False
    try:
        assert_no_secrets(value, "make_link_pair_argument")
    except ValueError:
        return False
    return True


def _repository_path(value: str, workdir: str) -> str:
    try:
        return normalize_repository_path(value, workdir)
    except ValueError as error:
        raise ValueError("make_build_ir_link_path_unrepresentable") from error


def _argv(command: Mapping[str, Any]) -> list[str]:
    value = command.get("argv")
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError("make_build_ir_link_argv_invalid")
    return list(value)


__all__ = ["scan_make_archive", "scan_make_link"]
