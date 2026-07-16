from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import re
from typing import Any

from .artifacts import content_sha256
from .project_test_inventory_make_command import parse_direct_make_test_command
from .project_test_inventory_paths import (
    build_output_index, normalize_argument, normalize_command_path,
    normalize_environment,
)
from .project_test_stdin import normalize_stdin_file


MAX_LINE_BYTES, MAX_COMMANDS = 64 * 1024, 4_096
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_PRESENTATION_COMMANDS = frozenset({
    "echo", "printf", "/bin/echo", "/bin/printf",
    "/usr/bin/echo", "/usr/bin/printf",
})


def derive_make_command_inventory(
    root: Path, build: Path, build_ir: Mapping[str, Any],
    commands: Sequence[str], *, source_observation: Mapping[str, Any],
    adapter: str,
) -> dict[str, Any]:
    try:
        outputs = build_output_index(build_ir)
    except (KeyError, OSError, TypeError, ValueError):
        return blocked_inventory("project_test_build_binding_invalid")
    tests: list[dict[str, Any]] = []
    signatures: dict[str, int] = {}
    command_count = 0
    for source_index, raw_line in enumerate(commands):
        if not isinstance(raw_line, str):
            return _inventory(
                root, build, source_observation, adapter, [],
                [{"code": "project_test_make_output_invalid"}],
            )
        line = raw_line.strip()
        if not line:
            continue
        command_count += 1
        if command_count > MAX_COMMANDS or len(line.encode("utf-8")) > MAX_LINE_BYTES:
            return _inventory(
                root, build, source_observation, adapter, [],
                [{"code": "project_test_make_output_invalid"}],
            )
        try:
            argv, stdin_path = parse_direct_make_test_command(line)
            record = _test_record(
                argv, stdin_path=stdin_path, index=source_index,
                root=root, build=build, outputs=outputs,
            )
        except (OSError, TypeError, ValueError) as error:
            return _inventory(root, build, source_observation, adapter, [], [{
                "code": str(error)[:96] or "project_test_make_command_invalid",
                "source_index": source_index,
            }])
        if record is None:
            continue
        signature = content_sha256({
            key: value for key, value in record.items()
            if key not in {"source_index", "name", "test_id"}
        })
        if signature in signatures:
            return _inventory(root, build, source_observation, adapter, [], [{
                "code": "project_test_make_command_duplicate",
                "source_index": source_index,
                "first_source_index": signatures[signature],
            }])
        signatures[signature] = source_index
        tests.append(record)
    if not tests:
        return _inventory(
            root, build, source_observation, adapter, [],
            [{"code": "project_test_inventory_empty"}],
        )
    return _inventory(root, build, source_observation, adapter, tests, [])


def _test_record(
    argv: list[str], *, stdin_path: str | None, index: int,
    root: Path, build: Path,
    outputs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    environment, command = _split_environment(argv)
    if not command:
        raise ValueError("project_test_make_command_invalid")
    try:
        executable_path, _ = normalize_command_path(
            _host_path(command[0], root), repo_root=root, base=build,
        )
    except (OSError, ValueError):
        return _unmapped_command(command[0])
    target = outputs.get(executable_path)
    if target is None:
        return _unmapped_command(command[0])
    binding = target.get("binding")
    if not isinstance(binding, Mapping) or binding.get("materialized") is not True:
        raise ValueError("project_test_executable_unmaterialized")
    record = {
        "source_index": index, "name": f"make-test-{index + 1}",
        "source_target_id": target["target_id"], "source_executable": dict(binding),
        "arguments": [
            normalize_argument(_host_path(item, root), repo_root=root, base=build)
            for item in command[1:]
        ],
        "working_directory": build.relative_to(root).as_posix() or ".",
        "environment": normalize_environment(
            [_host_assignment(item, root) for item in environment],
            repo_root=root, base=build,
        ),
        "timeout_seconds": 120,
    }
    if stdin_path is not None:
        record["stdin"] = normalize_stdin_file(
            _host_stdin_path(stdin_path, root), repo_root=root, base=build,
        )
    record["test_id"] = "test-" + content_sha256(record)[:24]
    return record


def _split_environment(argv: list[str]) -> tuple[list[str], list[str]]:
    offset = 0
    for item in argv:
        name, separator, _ = item.partition("=")
        if not separator or _ENVIRONMENT_NAME.fullmatch(name) is None:
            break
        offset += 1
    return argv[:offset], argv[offset:]


def _unmapped_command(executable: str) -> None:
    if executable in _PRESENTATION_COMMANDS:
        return None
    raise ValueError("project_test_make_command_unmapped")


def _host_assignment(value: str, root: Path) -> str:
    name, separator, assigned = value.partition("=")
    return name + separator + _host_path(assigned, root)


def _host_path(value: str, root: Path) -> str:
    guest, host = "/workspace", root.as_posix().rstrip("/")
    if value == guest or value.startswith(guest + "/"):
        return host + value.removeprefix(guest)
    marker = "=" + guest
    if value.count(marker) == 1:
        prefix, suffix = value.split(marker, 1)
        if not suffix or suffix.startswith("/"):
            return prefix + "=" + host + suffix
    return value


def _host_stdin_path(value: str, root: Path) -> str:
    if value == "/workspace" or value.startswith("/workspace/"):
        return root.as_posix().rstrip("/") + value.removeprefix("/workspace")
    return value


def _inventory(
    root: Path, build: Path, source: Mapping[str, Any], adapter: str,
    tests: list[dict[str, Any]], blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "blocked" if blockers else "ready", "adapter": adapter,
        "source_observation": dict(source),
        "build_directory": build.relative_to(root).as_posix() or ".",
        "tests": sorted(tests, key=lambda item: item["test_id"]),
        "blockers": blockers,
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


def blocked_inventory(code: str) -> dict[str, Any]:
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "blocked", "adapter": None, "source_observation": None,
        "build_directory": None, "tests": [], "blockers": [{"code": code}],
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


__all__ = [
    "MAX_COMMANDS", "MAX_LINE_BYTES", "blocked_inventory",
    "derive_make_command_inventory",
]
