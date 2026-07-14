from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import shlex
from typing import Any

from .archive_closure import is_archiver_command, is_ranlib_command
from .build_facts import compiler_name, json_sha256
from .build_ir_toolchains import standard_tool_requests
from .closure_paths import bind_repository_artifact
from .compile_database import (
    COMPILER_WRAPPERS, command_arguments, compiler_position,
)
from .compile_security import SUPPORTED_COMPILER
from .discovery_database import load_compile_database
from .link_fact_paths import link_fact_working_directory
from .link_response import expand_link_response_files
from .ninja_link_facts import discover_ninja_link_commands


def bound_standard_tool_requests(
    repo_root: str | Path,
    discovery: Mapping[str, Any],
    closure: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Reopen raw build facts and retain selected tools only in host evidence."""
    normalized = standard_tool_requests(discovery, closure)
    root = Path(repo_root).resolve(strict=True)
    database, database_path = _compile_database(root, discovery)
    result = _compile_requests(database, discovery)
    result.extend(_link_requests(root, database_path, closure))
    if _normalized_requests(result) != _normalized_requests(normalized):
        raise ValueError("build_ir_tool_selection_mapping_invalid")
    return result


def _compile_database(
    root: Path, discovery: Mapping[str, Any],
) -> tuple[list[Any], Path]:
    binding = discovery.get("compile_database")
    if not isinstance(binding, Mapping):
        raise ValueError("build_ir_tool_compile_database_invalid")
    relative = binding.get("path")
    digest = binding.get("sha256")
    if not isinstance(relative, str) or not isinstance(digest, str):
        raise ValueError("build_ir_tool_compile_database_invalid")
    path = root.joinpath(*PurePosixPath(relative).parts).resolve(strict=True)
    path.relative_to(root)
    database, blocker = load_compile_database(path, digest)
    if blocker is not None or database is None:
        raise ValueError(blocker or "build_ir_tool_compile_database_invalid")
    return database, path


def _compile_requests(
    database: list[Any], discovery: Mapping[str, Any],
) -> list[dict[str, str]]:
    units = discovery.get("translation_units")
    if not isinstance(units, list) or not units:
        raise ValueError("build_ir_tool_translation_units_invalid")
    result = []
    for unit in units:
        if not isinstance(unit, Mapping) or not isinstance(unit.get("entry"), Mapping):
            raise ValueError("build_ir_tool_translation_unit_invalid")
        index = unit["entry"].get("index")
        digest = unit["entry"].get("sha256")
        if type(index) is not int or not 0 <= index < len(database):
            raise ValueError("build_ir_tool_compile_entry_invalid")
        entry = database[index]
        if not isinstance(entry, dict) or json_sha256(entry) != digest:
            raise ValueError("build_ir_tool_compile_entry_drift")
        argv = command_arguments(entry)
        position = compiler_position(argv)
        if position is None:
            raise ValueError("build_ir_tool_compiler_missing")
        prefix = argv[:position]
        wrappers = [
            item for item in prefix
            if compiler_name(item).lower() in COMPILER_WRAPPERS
        ]
        if len(wrappers) != len(prefix):
            raise ValueError("build_ir_tool_command_environment_unsupported")
        _require_normalized(argv[position], unit.get("compiler"))
        expected_wrappers = unit.get("compiler_wrappers")
        if (
            not isinstance(expected_wrappers, list)
            or [compiler_name(item).lower() for item in wrappers]
            != [str(item).lower() for item in expected_wrappers]
        ):
            raise ValueError("build_ir_tool_wrapper_selection_invalid")
        result.append({"token": argv[position], "role": "compiler-driver"})
        result.extend(
            {"token": token, "role": "compiler-wrapper"}
            for token in wrappers
        )
    return result


def _link_requests(
    root: Path, database_path: Path, closure: Mapping[str, Any],
) -> list[dict[str, str]]:
    link = closure.get("target_link_closure")
    targets = link.get("targets") if isinstance(link, Mapping) else None
    if not isinstance(targets, list):
        raise ValueError("build_ir_tool_link_targets_invalid")
    result = []
    for target in targets:
        if not isinstance(target, Mapping):
            raise ValueError("build_ir_tool_link_target_invalid")
        primary, ranlib = _target_commands(root, database_path, target)
        role = "archiver" if "archive_operation" in target else "linker-driver"
        _require_normalized(primary[0], target.get("driver"))
        result.append({"token": primary[0], "role": role})
        expected_ranlib = target.get("ranlib_drivers", [])
        actual_ranlib = sorted({compiler_name(item[0]).lower() for item in ranlib})
        if actual_ranlib != expected_ranlib:
            raise ValueError("build_ir_tool_ranlib_selection_invalid")
        result.extend(
            {"token": token, "role": "ranlib"}
            for token in sorted({item[0] for item in ranlib})
        )
    return result


def _target_commands(
    root: Path, database_path: Path, target: Mapping[str, Any],
) -> tuple[list[str], list[list[str]]]:
    fact = target.get("fact_file")
    if not isinstance(fact, Mapping) or not isinstance(fact.get("path"), str):
        raise ValueError("build_ir_tool_link_fact_invalid")
    if PurePosixPath(fact["path"]).name == "build.ninja":
        candidates = _ninja_commands(root, fact)
    else:
        candidates = _link_file_commands(root, database_path, fact)
    matches = [
        item for item in candidates
        if json_sha256(item[0]) == target.get("argv_sha256")
    ]
    if len(matches) != 1:
        raise ValueError("build_ir_tool_link_command_binding_invalid")
    return matches[0]


def _ninja_commands(
    root: Path, fact: Mapping[str, Any],
) -> list[tuple[list[str], list[list[str]]]]:
    report = discover_ninja_link_commands(root, dict(fact))
    if report.get("blockers"):
        raise ValueError("build_ir_tool_ninja_reopen_blocked")
    result = []
    for command in report.get("commands", []):
        argv, _responses = expand_link_response_files(
            root, command["base"], command["argv"],
        )
        result.append((argv, command.get("ranlib_argvs", [])))
    return result


def _link_file_commands(
    root: Path, database_path: Path, fact: Mapping[str, Any],
) -> list[tuple[list[str], list[list[str]]]]:
    current = bind_repository_artifact(root, str(fact["path"]), kind="file")
    if current.get("sha256") != fact.get("sha256"):
        raise ValueError("build_ir_tool_link_fact_drift")
    path = root.joinpath(*PurePosixPath(str(fact["path"])).parts)
    base = link_fact_working_directory(root, str(fact["path"]), database_path.parent)
    lines = [
        line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not 1 <= len(lines) <= 4:
        raise ValueError("build_ir_tool_link_fact_command_count_invalid")
    commands = [shlex.split(line, posix=True) for line in lines]
    ranlib = [item for item in commands if is_ranlib_command(item)]
    result = []
    for command in commands:
        if not _primary(command):
            continue
        argv, _responses = expand_link_response_files(root, base, command)
        result.append((argv, ranlib))
    return result


def _primary(argv: list[str]) -> bool:
    return bool(
        is_archiver_command(argv)
        or (
            argv
            and SUPPORTED_COMPILER.fullmatch(compiler_name(argv[0])) is not None
        )
    )


def _require_normalized(selected: str, normalized: Any) -> None:
    if not isinstance(normalized, str) or compiler_name(selected).lower() != normalized.lower():
        raise ValueError("build_ir_tool_selection_mapping_invalid")


def _normalized_requests(values: list[dict[str, str]]) -> list[tuple[str, str]]:
    return sorted(
        (compiler_name(item["token"]).lower(), item["role"])
        for item in values
    )


__all__ = ["bound_standard_tool_requests"]
