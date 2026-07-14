from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .build_facts import compiler_name, json_sha256
from .closure_paths import bind_repository_artifact, path_error_blocker


_ARCHIVER = re.compile(
    r"^(?:(?:[a-z0-9_+.]+-){0,4}(?:ar|gcc-ar|llvm-ar)|lib)$",
    re.IGNORECASE,
)
_RANLIB = re.compile(
    r"^(?:(?:[a-z0-9_+.]+-){0,4}(?:ranlib|gcc-ranlib|llvm-ranlib))$",
    re.IGNORECASE,
)
_GNU_OPERATION = re.compile(r"^-?[A-Za-z]{1,16}$")


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
    inputs = []
    for value in input_values:
        bound = _bind(root, base, value, "archive_input", blockers)
        if bound is not None:
            inputs.append(bound)
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
        "archive_operation": operation,
    }, blockers


def ranlib_output(argv: list[str]) -> str | None:
    if not is_ranlib_command(argv) or len(argv) != 2:
        return None
    return argv[1]


def _arguments(
    driver: str, arguments: list[str],
) -> tuple[str, str, list[str]]:
    if driver in {"lib", "lib.exe"}:
        output = next(
            (item[5:] for item in arguments if item.upper().startswith("/OUT:")),
            None,
        )
        inputs = [
            item for item in arguments
            if not item.startswith("/") and not item.startswith("-")
        ]
        if output is None:
            raise ValueError("archive_target_output_missing")
        return "msvc-lib", output, inputs
    if len(arguments) < 3 or _GNU_OPERATION.fullmatch(arguments[0]) is None:
        raise ValueError("archive_arguments_invalid")
    operation = arguments[0].lstrip("-")
    if not ({"r", "q"} & set(operation)) or any(
        char not in "abcDdfilmNPoqrSTsuvVx" for char in operation
    ):
        raise ValueError("archive_operation_unsupported")
    output = arguments[1]
    inputs = arguments[2:]
    if any(value.startswith("-") for value in inputs):
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
