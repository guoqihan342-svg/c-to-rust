from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .build_facts import compiler_name, json_sha256
from .closure_paths import bind_repository_artifact, path_error_blocker
from .link_ordered_occurrences import append_ordered_link_occurrence


_ARCHIVER = re.compile(
    r"^(?:(?:[a-z0-9_+.]+-){0,4}(?:ar|gcc-ar|llvm-ar)|lib)$",
    re.IGNORECASE,
)
_RANLIB = re.compile(
    r"^(?:(?:[a-z0-9_+.]+-){0,4}(?:ranlib|gcc-ranlib|llvm-ranlib))$",
    re.IGNORECASE,
)
_GNU_OPERATION = re.compile(r"^-?[A-Za-z]{1,16}$")
_GNU_CREATE_FLAGS = frozenset("rqcsDSv")
_MSVC_DISPLAY_OPTIONS = frozenset({"/NOLOGO"})


def is_archiver_command(argv: list[str]) -> bool:
    return bool(argv and _ARCHIVER.fullmatch(compiler_name(argv[0])))


def is_ranlib_command(argv: list[str]) -> bool:
    return bool(argv and _RANLIB.fullmatch(compiler_name(argv[0])))


def parse_archive_command(
    root: Path, base: Path, fact: dict[str, Any], argv: list[str],
    *, response_files: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    fact_path = str(fact.get("path", ""))
    if not is_archiver_command(argv):
        return None, [{"kind": "archive_driver_unsupported", "path": fact_path}]
    driver = compiler_name(argv[0]).lower()
    try:
        operation, output_value, input_values = _arguments(driver, argv[1:])
    except ValueError as error:
        return None, [{"kind": str(error), "path": fact_path}]
    blockers: list[dict[str, Any]] = []
    output = _bind(root, base, output_value, "archive_target", blockers)
    inputs: list[dict[str, Any]] = []
    occurrences: list[dict[str, int | str]] = []
    for argument_index, value in input_values:
        bound = _bind(root, base, value, "archive_input", blockers)
        if bound is not None:
            append_ordered_link_occurrence(
                occurrences, inputs, bound, kind="input",
                argument_index=argument_index,
            )
    if not inputs:
        blockers.append({"kind": "archive_inputs_missing", "fact": fact_path})
    return {
        "fact_file": fact,
        "driver": driver,
        "argv_sha256": json_sha256(argv),
        "output": output,
        "inputs": inputs,
        "search_roots": [],
        "response_files": response_files or [],
        "ordered_system_link_args": [],
        "ordered_link_occurrences": occurrences,
        "archive_operation": operation,
    }, blockers


def ranlib_output(argv: list[str]) -> str | None:
    if not is_ranlib_command(argv) or len(argv) != 2:
        return None
    return argv[1]


def _arguments(
    driver: str, arguments: list[str],
) -> tuple[str, str, list[tuple[int, str]]]:
    if driver in {"lib", "lib.exe"}:
        outputs: list[str] = []
        inputs: list[tuple[int, str]] = []
        semantic_index = 0
        for item in arguments:
            upper = item.upper()
            if upper.startswith("/OUT:"):
                outputs.append(item[5:])
                continue
            if upper in _MSVC_DISPLAY_OPTIONS:
                semantic_index += 1
                continue
            if item.startswith(("/", "-")):
                raise ValueError("archive_option_unsupported")
            inputs.append((semantic_index, item))
            semantic_index += 1
        if not outputs or (len(outputs) == 1 and not outputs[0]):
            raise ValueError("archive_target_output_missing")
        if len(outputs) != 1:
            raise ValueError("archive_target_output_duplicate")
        return "msvc-lib", outputs[0], inputs
    if len(arguments) < 3:
        raise ValueError("archive_arguments_invalid")
    if _GNU_OPERATION.fullmatch(arguments[0]) is None:
        raise ValueError("archive_operation_unsupported")
    operation = arguments[0].lstrip("-")
    flags = set(operation)
    if (
        not operation or len(flags) != len(operation)
        or len(flags & {"r", "q"}) != 1
        or not flags <= _GNU_CREATE_FLAGS
        or {"s", "S"} <= flags
    ):
        raise ValueError("archive_operation_unsupported")
    output = arguments[1]
    if not output or output.startswith("-"):
        raise ValueError("archive_target_argument_unsupported")
    # The operation remains at index 0; the archive output token is elided.
    inputs = list(enumerate(arguments[2:], start=1))
    if any(value.startswith("-") for _index, value in inputs):
        raise ValueError("archive_input_argument_unsupported")
    return operation, output, inputs


def _bind(
    root: Path, base: Path, value: str, role: str,
    blockers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        return bind_repository_artifact(root, value, base=base, kind="file")
    except (OSError, ValueError) as error:
        blockers.append(path_error_blocker(error, role=role, path=value))
        return None
__all__ = [
    "is_archiver_command", "is_ranlib_command", "parse_archive_command",
    "ranlib_output",
]
