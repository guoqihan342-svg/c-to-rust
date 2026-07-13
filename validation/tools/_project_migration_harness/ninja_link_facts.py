from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from .build_facts import compiler_name, resolve_repository_path
from .archive_closure import is_archiver_command
from .closure_paths import bind_repository_artifact, path_error_blocker
from .compile_security import SUPPORTED_COMPILER
from .ninja_syntax import (
    expand_ninja,
    logical_lines,
    parse_assignment,
    split_ninja_words,
    unescaped_colon,
)
from .ninja_scope import NinjaScope


MAX_NINJA_FILES = 64
MAX_NINJA_BYTES = 4 * 1024 * 1024
MAX_NINJA_LINES = 100_000
MAX_NINJA_EDGES = 50_000
MAX_NINJA_COMMANDS = 4_096
MAX_EXPANDED_COMMAND = 256 * 1024
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def discover_ninja_link_commands(
    repo_root: Path, fact: dict[str, Any]
) -> dict[str, Any]:
    root = repo_root.resolve()
    state: dict[str, Any] = {
        "edges": [], "support_files": [], "seen": set(),
        "bytes": 0, "lines": 0, "blockers": [],
    }
    path_text = str(fact.get("path", ""))
    try:
        path = resolve_repository_path(root, path_text)
        current = bind_repository_artifact(root, path, kind="file")
    except (OSError, ValueError) as error:
        return _report([], [], [path_error_blocker(
            error, role="ninja_fact", path=path_text
        )])
    if current.get("sha256") != fact.get("sha256"):
        return _report([], [], [{"kind": "ninja_fact_sha256_drift", "path": path_text}])
    _parse_file(root, path, state, scope=NinjaScope(), depth=0)
    commands = _commands(state)
    if not commands and not state["blockers"]:
        state["blockers"].append({"kind": "ninja_link_command_not_found", "path": path_text})
    return _report(commands, state["support_files"], state["blockers"])


def _parse_file(
    root: Path, path: Path, state: dict[str, Any], *,
    scope: NinjaScope, depth: int,
) -> None:
    relative = path.relative_to(root).as_posix()
    if relative in state["seen"]:
        state["blockers"].append({
            "kind": "ninja_repeated_file_unsupported", "path": relative,
        })
        return
    if depth > 8 or len(state["seen"]) >= MAX_NINJA_FILES:
        state["blockers"].append({"kind": "ninja_include_limit_exceeded"})
        return
    try:
        binding = bind_repository_artifact(root, path, kind="file")
        size = int(binding["size_bytes"])
        if state["bytes"] + size > MAX_NINJA_BYTES:
            raise ValueError("ninja_byte_limit_exceeded")
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError) as error:
        state["blockers"].append(path_error_blocker(
            error, role="ninja_include", path=relative
        ))
        return
    state["seen"].add(relative)
    state["bytes"] += size
    state["support_files"].append(binding)
    try:
        lines = logical_lines(text)
    except ValueError as error:
        state["blockers"].append({"kind": str(error), "path": relative})
        return
    state["lines"] += len(lines)
    if state["lines"] > MAX_NINJA_LINES:
        state["blockers"].append({"kind": "ninja_line_limit_exceeded"})
        return
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            index += 1
            continue
        if raw[:1].isspace():
            state["blockers"].append({"kind": "ninja_orphan_binding", "path": relative})
            index += 1
            continue
        if stripped.startswith(("include ", "subninja ")):
            directive, source = stripped.split(None, 1)
            try:
                value = expand_ninja(source, scope.values())
                included = resolve_repository_path(root, value, base=path.parent)
            except (OSError, ValueError) as error:
                state["blockers"].append(path_error_blocker(
                    error, role="ninja_include", path="<invalid-include>"
                ))
            else:
                _parse_file(
                    root, included, state,
                    scope=scope if directive == "include" else scope.child(),
                    depth=depth + 1,
                )
            index += 1
            continue
        if stripped.startswith("rule "):
            name = stripped[5:].strip()
            bindings, index = _indented_bindings(lines, index + 1, relative, state)
            if _NAME.fullmatch(name) is None or "command" not in bindings:
                state["blockers"].append({"kind": "ninja_rule_invalid", "path": relative})
            elif not scope.define_rule(name, bindings):
                state["blockers"].append({
                    "kind": "ninja_rule_redefined", "path": relative,
                })
            continue
        if stripped.startswith("build "):
            bindings, next_index = _indented_bindings(lines, index + 1, relative, state)
            try:
                header = expand_ninja(stripped[6:], scope.values())
            except ValueError:
                edge = None
            else:
                edge = _edge(header, bindings, path, relative, scope)
            if edge is None:
                state["blockers"].append({"kind": "ninja_edge_invalid", "path": relative})
            elif len(state["edges"]) >= MAX_NINJA_EDGES:
                state["blockers"].append({"kind": "ninja_edge_limit_exceeded"})
                return
            else:
                state["edges"].append(edge)
            index = next_index
            continue
        if stripped.startswith("pool "):
            _, index = _indented_bindings(lines, index + 1, relative, state)
            continue
        assignment = parse_assignment(stripped)
        if assignment is not None:
            scope.variables[assignment[0]] = assignment[1]
        elif not stripped.startswith(("default ", "pool ")):
            state["blockers"].append({"kind": "ninja_statement_unsupported", "path": relative})
        index += 1


def _indented_bindings(
    lines: list[str], index: int, relative: str, state: dict[str, Any]
) -> tuple[dict[str, str], int]:
    values: dict[str, str] = {}
    while index < len(lines) and lines[index][:1].isspace():
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#"):
            assignment = parse_assignment(stripped)
            if assignment is None:
                state["blockers"].append({"kind": "ninja_binding_invalid", "path": relative})
            else:
                values[assignment[0]] = assignment[1]
        index += 1
    return values, index


def _edge(
    header: str, bindings: dict[str, str], path: Path, relative: str,
    scope: NinjaScope,
) -> dict[str, Any] | None:
    separator = unescaped_colon(header)
    if separator < 1:
        return None
    outputs = split_ninja_words(header[:separator])
    remainder = split_ninja_words(header[separator + 1:])
    if not outputs or not remainder or _NAME.fullmatch(remainder[0]) is None:
        return None
    inputs: list[str] = []
    for value in remainder[1:]:
        if value == "||":
            break
        if value != "|":
            inputs.append(value)
    return {
        "outputs": [value for value in outputs if value != "|"],
        "rule": remainder[0],
        "rule_bindings": scope.rule(remainder[0]),
        "scope": scope,
        "inputs": inputs,
        "bindings": bindings,
        "base": path.parent,
        "fact_path": relative,
    }


def _commands(state: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for edge in state["edges"]:
        rule = edge["rule_bindings"]
        if edge["rule"] == "phony":
            continue
        if not isinstance(rule, dict):
            state["blockers"].append({
                "kind": "ninja_rule_missing", "path": edge["fact_path"],
            })
            continue
        values = edge["scope"].values(
            {"in": " ".join(edge["inputs"]), "out": " ".join(edge["outputs"])},
            edge["bindings"],
            rule,
        )
        try:
            command = expand_ninja(str(rule["command"]), values)
            if len(command.encode("utf-8")) > MAX_EXPANDED_COMMAND:
                raise ValueError("ninja_command_size_limit_exceeded")
            argv = _link_segment(shlex.split(command, posix=True))
        except (UnicodeError, ValueError):
            state["blockers"].append({
                "kind": "ninja_command_parse_invalid", "path": edge["fact_path"],
            })
            continue
        if argv is None:
            continue
        if len(result) >= MAX_NINJA_COMMANDS:
            state["blockers"].append({"kind": "ninja_command_limit_exceeded"})
            break
        result.append({
            "argv": argv,
            "base": edge["base"],
            "fact_path": edge["fact_path"],
        })
    return result


def _link_segment(argv: list[str]) -> list[str] | None:
    segments: list[list[str]] = [[]]
    for value in argv:
        if value == "&&":
            segments.append([])
        elif value in {";", "|", "||", ">", "<"}:
            raise ValueError("ninja_shell_operator_unsupported")
        else:
            segments[-1].append(value)
    matches = [
        part for part in segments
        if part
        and (
            is_archiver_command(part)
            or (
                SUPPORTED_COMPILER.fullmatch(compiler_name(part[0])) is not None
                and "-c" not in part
                and any(
                    item == "-o" or item.startswith(("-o", "/OUT:"))
                    for item in part[1:]
                )
            )
        )
    ]
    if len(matches) > 1:
        raise ValueError("ninja_link_command_ambiguous")
    return matches[0] if matches else None


def _report(
    commands: list[dict[str, Any]], support_files: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    keyed = {(item["path"], item["sha256"]): item for item in support_files}
    return {
        "status": "ready" if commands and not blockers else "blocked",
        "commands": commands,
        "support_files": [keyed[key] for key in sorted(keyed)],
        "blockers": blockers,
        "commands_executed": False,
    }


__all__ = ["discover_ninja_link_commands"]
