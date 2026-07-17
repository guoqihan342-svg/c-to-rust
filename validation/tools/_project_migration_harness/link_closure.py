from __future__ import annotations

import shlex
from pathlib import Path, PurePosixPath
from typing import Any

from .archive_closure import (
    is_archiver_command, is_ranlib_command, parse_archive_command,
)
from .build_facts import compiler_name, json_sha256
from .closure_paths import bind_repository_artifact, path_error_blocker
from .compile_security import SUPPORTED_COMPILER
from .ninja_link_facts import discover_ninja_link_commands
from .link_response import expand_link_response_files, take_link_output
from .link_fact_paths import link_fact_working_directory
from .link_ranlib import bind_ranlib_commands
from .link_ordered_occurrences import split_ordered_link_arguments
from .link_closure_schema import LINK_CLOSURE_SCHEMA_VERSION


MAX_LINK_ARGUMENTS = 16_384
def discover_link_closure(
    repo_root: Path,
    compile_database_path: Path,
    generated_facts: dict[str, Any],
) -> dict[str, Any]:
    fact_files = generated_facts.get("link_command_files", [])
    ninja_files = [
        item for item in generated_facts.get("metadata_files", [])
        if isinstance(item, dict)
        and PurePosixPath(str(item.get("path", ""))).name == "build.ninja"
    ]
    targets: list[dict[str, Any]] = []
    support_files: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    if not fact_files and not ninja_files:
        blockers.append({"kind": "link_facts_not_found"})
    for fact in fact_files:
        target, current = _parse_link_fact(
            repo_root, compile_database_path.parent, fact
        )
        blockers.extend(current)
        if target is not None:
            targets.append(target)
    for fact in ninja_files:
        report = discover_ninja_link_commands(repo_root, fact)
        blockers.extend(report["blockers"])
        support_files.extend(report["support_files"])
        for command in report["commands"]:
            try:
                argv, response_files = expand_link_response_files(
                    repo_root, command["base"], command["argv"]
                )
            except (OSError, ValueError) as error:
                blockers.append({
                    "kind": str(error), "path": str(fact.get("path", "")),
                })
                continue
            target, current = _parse_command_argv(
                repo_root,
                command["base"],
                fact,
                argv,
                response_files=response_files,
            )
            blockers.extend(current)
            if target is not None:
                blockers.extend(bind_ranlib_commands(
                    repo_root,
                    command["base"],
                    target,
                    command.get("ranlib_argvs", []),
                    fact_path=str(fact.get("path", "")),
                ))
                targets.append(target)
    targets.sort(key=lambda item: item["fact_file"]["path"])
    outputs: dict[str, list[str]] = {}
    for target in targets:
        output = target.get("output")
        if isinstance(output, dict) and isinstance(output.get("path"), str):
            outputs.setdefault(output["path"], []).append(target["fact_file"]["path"])
    for output, facts in outputs.items():
        if len(facts) > 1:
            blockers.append({
                "kind": "ambiguous_link_target_output",
                "path": output,
                "fact_count": len(facts),
            })
    blockers = _unique_blockers(blockers)
    return {
        "schema_version": LINK_CLOSURE_SCHEMA_VERSION,
        "status": "ready" if targets and not blockers else "blocked",
        "fact_files": fact_files,
        "support_files": _canonical_binding_set(support_files),
        "targets": targets,
        "blockers": blockers,
        "parameters_guessed": False,
    }


def _parse_link_fact(
    root: Path, base: Path, fact: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    fact_path = str(fact.get("path", ""))
    blockers: list[dict[str, Any]] = []
    try:
        current_fact = bind_repository_artifact(root, fact_path, kind="file")
    except (OSError, ValueError) as error:
        return None, [path_error_blocker(error, role="link_fact", path=fact_path)]
    if current_fact["sha256"] != fact.get("sha256"):
        return None, [{"kind": "link_fact_sha256_drift", "path": fact_path}]
    base = link_fact_working_directory(root, fact_path, base)
    try:
        lines = [line.strip() for line in (root / fact_path).read_text(
            encoding="utf-8-sig"
        ).splitlines() if line.strip()]
        if not 1 <= len(lines) <= 4:
            raise ValueError("link_fact_command_count_invalid")
        commands = [shlex.split(line, posix=True) for line in lines]
    except (OSError, UnicodeError, ValueError) as error:
        return None, [{"kind": str(error) or "link_fact_parse_invalid", "path": fact_path}]
    primary = [
        argv for argv in commands
        if is_archiver_command(argv)
        or (
            argv
            and SUPPORTED_COMPILER.fullmatch(compiler_name(argv[0])) is not None
        )
    ]
    auxiliaries = [argv for argv in commands if argv not in primary]
    if len(primary) != 1 or any(not is_ranlib_command(argv) for argv in auxiliaries):
        return None, [{"kind": "link_fact_command_set_invalid", "path": fact_path}]
    try:
        argv, response_files = expand_link_response_files(root, base, primary[0])
    except (OSError, ValueError) as error:
        return None, [{"kind": str(error), "path": fact_path}]
    target, blockers = _parse_command_argv(
        root, base, current_fact, argv, response_files=response_files
    )
    if target is not None:
        blockers.extend(bind_ranlib_commands(
            root, base, target, auxiliaries, fact_path=fact_path,
        ))
    return target, blockers


def _parse_command_argv(
    root: Path, base: Path, fact: dict[str, Any], argv: list[str],
    *, response_files: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if is_archiver_command(argv):
        return parse_archive_command(
            root, base, fact, argv, response_files=response_files
        )
    return _parse_link_argv(
        root, base, fact, argv, response_files=response_files
    )


def _parse_link_argv(
    root: Path, base: Path, fact: dict[str, Any], argv: list[str],
    *, response_files: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    fact_path = str(fact.get("path", ""))
    blockers: list[dict[str, Any]] = []
    if not argv or SUPPORTED_COMPILER.fullmatch(compiler_name(argv[0])) is None:
        return None, [{"kind": "link_driver_unsupported", "path": fact_path}]
    if len(argv) > MAX_LINK_ARGUMENTS:
        return None, [{"kind": "link_argument_limit_exceeded", "path": fact_path}]
    output_value, arguments = take_link_output(argv[1:])
    if output_value is None:
        blockers.append({"kind": "link_target_output_missing", "fact": fact_path})
    output = _bind(root, base, output_value, "link_target", blockers)
    split = split_ordered_link_arguments(
        root, base, fact_path, arguments, blockers,
    )
    target = {
        "fact_file": fact,
        "driver": compiler_name(argv[0]).lower(),
        "argv_sha256": json_sha256(argv),
        "output": output,
        "inputs": split["inputs"],
        "search_roots": split["search_roots"],
        "response_files": response_files or [],
        "ordered_system_link_args": split["ordered_system_link_args"],
        "ordered_link_occurrences": split["ordered_link_occurrences"],
    }
    external_libraries = split["external_native_libraries"]
    if external_libraries:
        target["external_native_libraries"] = external_libraries
    return target, blockers


def _bind(
    root: Path,
    base: Path,
    value: str | None,
    role: str,
    blockers: list[dict[str, Any]],
    *,
    kind: str = "file",
) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        return bind_repository_artifact(root, value, base=base, kind=kind)
    except (OSError, ValueError) as error:
        blockers.append(path_error_blocker(error, role=role, path=value))
        return None


def _canonical_binding_set(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_path = {item["path"]: item for item in items}
    return [by_path[path] for path in sorted(by_path)]


def _unique_blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {json_sha256(item): item for item in items}
    return [keyed[key] for key in sorted(keyed)]


__all__ = ["discover_link_closure"]
