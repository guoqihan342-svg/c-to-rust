from __future__ import annotations

from pathlib import Path
import re
import shlex
from typing import Any

from validation.tools._ai_candidate_harness_parts.context_response_files import (
    expand_response_files,
)

from .build_facts import (
    compiler_name,
    file_binding,
    json_sha256,
    normalize_response_files,
    rejection,
    repository_path,
    resolve_repository_path,
    summarize_path,
)
from .compile_arguments import extract_arguments
from .compile_security import (
    default_output,
    validate_command_text,
    validate_compile_contract,
    validate_compiler,
)


COMPILER_WRAPPERS = {"ccache", "distcc", "icecc", "sccache"}
MAX_SOURCE_BYTES = 16 * 1024 * 1024


def parse_compile_entry(
    entry: Any,
    entry_index: int,
    repo_root: Path,
    database_directory: Path | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    entry_sha256 = json_sha256(entry)
    if not isinstance(entry, dict):
        return None, rejection(entry_index, entry_sha256, "entry_not_object", True)
    directory = entry.get("directory", ".")
    source_value = entry.get("file")
    if not isinstance(directory, str) or not isinstance(source_value, str) or not source_value:
        return None, rejection(entry_index, entry_sha256, "entry_path_invalid", True)
    try:
        working_directory = resolve_repository_path(repo_root, directory)
    except (OSError, ValueError):
        return None, rejection(
            entry_index, entry_sha256, "working_directory_outside_repository", True
        )
    try:
        source_path = resolve_repository_path(
            repo_root, source_value, base=working_directory
        )
    except (OSError, ValueError):
        return None, rejection(
            entry_index, entry_sha256, "source_path_outside_repository", True
        )
    if not working_directory.is_dir():
        return None, rejection(
            entry_index, entry_sha256, "working_directory_invalid", True
        )
    try:
        source_binding = file_binding(
            repo_root, source_path, max_bytes=MAX_SOURCE_BYTES
        )
    except ValueError as error:
        reason = (
            "source_file_too_large"
            if str(error) == "file_size_limit_exceeded"
            else "source_not_regular"
        )
        return None, rejection(entry_index, entry_sha256, reason, True)
    except OSError:
        return None, rejection(entry_index, entry_sha256, "source_not_regular", True)
    try:
        argv = command_arguments(entry)
    except ValueError as error:
        return None, rejection(entry_index, entry_sha256, str(error), True)
    compiler_at = compiler_position(argv)
    if compiler_at is None:
        return None, rejection(entry_index, entry_sha256, "compiler_missing", True)
    try:
        compiler, dialect = validate_compiler(argv, compiler_at)
    except ValueError as error:
        return None, rejection(entry_index, entry_sha256, str(error), True)
    if dialect == "msvc" and any(item.startswith("@") for item in argv):
        return None, rejection(
            entry_index, entry_sha256, "response_file_compiler_unsupported", True
        )
    response_compiler = re.sub(r"-(?:\d+(?:\.\d+)*)$", "", compiler)
    expanded, response_report = expand_response_files(
        argv,
        source_root=repo_root,
        working_directory=working_directory,
        compiler=response_compiler,
    )
    if expanded is None:
        reason = (
            response_report.get("reason", "response_file_invalid")
            if isinstance(response_report, dict)
            else "response_file_invalid"
        )
        return None, rejection(entry_index, entry_sha256, reason, True)
    compiler_at = compiler_position(expanded)
    if compiler_at is None:
        return None, rejection(entry_index, entry_sha256, "compiler_missing", True)
    try:
        compiler, dialect = validate_compiler(expanded, compiler_at)
        validate_compile_contract(
            expanded,
            compiler_at,
            repo_root,
            working_directory,
            source_path,
            dialect,
        )
    except ValueError as error:
        return None, rejection(entry_index, entry_sha256, str(error), True)
    language = source_language(expanded, source_path, compiler)
    if language not in {"c", "c-cpp-output"}:
        return None, rejection(
            entry_index,
            entry_sha256,
            "non_c_translation_unit",
            False,
            source=source_binding["path"],
            language=language,
        )
    details = extract_arguments(
        expanded, compiler_at, repo_root, working_directory, source_path
    )
    declared_output = entry.get("output")
    if "output" in entry and (
        not isinstance(declared_output, str) or not declared_output
    ):
        return None, rejection(entry_index, entry_sha256, "output_invalid", True)
    command_output = details["output"] or default_output(
        compiler, source_path, repo_root, working_directory
    )
    if command_output["scope"] != "repository":
        return None, rejection(
            entry_index, entry_sha256, "compile_output_outside_repository", True
        )
    if isinstance(declared_output, str):
        declared_candidates = [
            summarize_path(declared_output, repo_root, working_directory)
        ]
        if database_directory is not None and database_directory != working_directory:
            declared_candidates.append(
                summarize_path(declared_output, repo_root, database_directory)
            )
        repository_outputs = {
            item["path"]
            for item in declared_candidates
            if item["scope"] == "repository"
        }
        if not repository_outputs:
            return None, rejection(
                entry_index, entry_sha256, "compile_output_outside_repository", True
            )
        if command_output["path"] not in repository_outputs:
            return None, rejection(
                entry_index, entry_sha256, "compile_output_binding_mismatch", True
            )
    response_files = normalize_response_files(response_report)
    unit = {
        "entry": {"index": entry_index, "sha256": entry_sha256},
        "entry_sha256": entry_sha256,
        "source": source_binding,
        "working_directory": repository_path(repo_root, working_directory),
        "compiler": compiler,
        "compiler_wrappers": [
            compiler_name(item)
            for item in expanded[:compiler_at]
            if compiler_name(item).lower() in COMPILER_WRAPPERS
        ],
        "language": language,
        "includes": details["includes"],
        "defines": details["defines"],
        "redacted_define_count": details["redacted_define_count"],
        "semantic_flags": details["semantic_flags"],
        "output": command_output["path"],
        "expanded_argv_sha256": json_sha256(expanded),
        "response_files": response_files,
    }
    return unit, None


def command_arguments(entry: dict[str, Any]) -> list[str]:
    if "arguments" in entry:
        arguments = entry.get("arguments")
        if (
            not isinstance(arguments, list)
            or not arguments
            or not all(isinstance(item, str) and item for item in arguments)
        ):
            raise ValueError("arguments_invalid")
        return list(arguments)
    command = entry.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command_missing")
    validate_command_text(command)
    try:
        parsed = shlex.split(command, posix=True)
    except ValueError as error:
        raise ValueError("command_parse_invalid") from error
    normalized = [item.strip('"') for item in parsed]
    if not normalized:
        raise ValueError("command_parse_invalid")
    return normalized


def compiler_position(argv: list[str]) -> int | None:
    index = 0
    if argv and compiler_name(argv[0]).lower() == "env":
        index = 1
        while index < len(argv) and (
            "=" in argv[index] or argv[index] in {"-i", "--ignore-environment"}
        ):
            index += 1
    while index < len(argv) and "=" in argv[index] and not argv[index].startswith(("-", "/")):
        index += 1
    while index < len(argv) and compiler_name(argv[index]).lower() in COMPILER_WRAPPERS:
        index += 1
    return index if index < len(argv) else None


def source_language(argv: list[str], source: Path, compiler: str) -> str:
    explicit: str | None = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "-x" and index + 1 < len(argv):
            explicit = argv[index + 1].lower()
            index += 1
        elif argument.startswith("-x") and len(argument) > 2:
            explicit = argument[2:].lower()
        elif argument.lower() == "/tc" or argument.lower().startswith("/tc"):
            explicit = "c"
        elif argument.lower() == "/tp" or argument.lower().startswith("/tp"):
            explicit = "c++"
        index += 1
    if explicit and explicit != "none":
        return explicit
    lowered_compiler = compiler.lower()
    if re.search(
        r"(?:^|-)(?:c\+\+|g\+\+|clang\+\+)(?:-\d+(?:\.\d+)*)?$",
        lowered_compiler,
    ):
        return "c++"
    if source.suffix == ".c":
        return "c"
    if source.suffix == ".i":
        return "c-cpp-output"
    return "unknown"


__all__ = ["json_sha256", "parse_compile_entry"]
