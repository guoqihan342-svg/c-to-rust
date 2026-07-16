from __future__ import annotations

import hashlib
import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .build_facts import resolve_repository_path
from .project_test_inventory_automake import (
    AUTOMAKE_CHECK_COMMAND, MAKE_TEST_COMMAND, command_for_target_binding,
    verify_make_target_binding,
)
from .project_test_inventory_paths import (
    build_output_index, normalize_argument, normalize_command_path,
    normalize_environment,
)

MAX_STDOUT_BYTES, MAX_STDERR_BYTES = 4 * 1024 * 1024, 1024 * 1024
MAX_LINE_BYTES, MAX_COMMANDS = 64 * 1024, 4_096
MAKE_COMMAND = list(MAKE_TEST_COMMAND)
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_PRESENTATION_COMMANDS = frozenset({
    "echo", "printf", "/bin/echo", "/bin/printf",
    "/usr/bin/echo", "/usr/bin/printf",
})
_OBSERVATION_KEYS = frozenset({
    "schema_version", "artifact_kind", "command", "target_binding",
    "build_directory", "tool", "sandbox_launcher", "timeout_seconds",
    "returncode", "stdout",
    "stdout_sha256", "stdout_size_bytes", "stderr_sha256", "stderr_size_bytes",
    "semantic_gate", "observation_sha256",
})


def derive_make_inventory(
    repo_root: Path, build_ir: Mapping[str, Any], observation: Mapping[str, Any],
    *, source_observation: Mapping[str, Any],
) -> dict[str, Any]:
    if (
        not _valid_observation(observation)
        or not verify_make_target_binding(
            repo_root, observation.get("target_binding"),
        )
    ):
        return _blocked_inventory("project_test_make_schema_invalid")
    try:
        root = Path(repo_root).resolve(strict=True)
        build = resolve_repository_path(root, str(observation["build_directory"]))
        if not root.is_dir() or not build.is_dir():
            raise ValueError("project test build directory is invalid")
        outputs = build_output_index(build_ir)
    except (KeyError, OSError, TypeError, ValueError):
        return _blocked_inventory("project_test_build_binding_invalid")
    tests: list[dict[str, Any]] = []
    signatures: dict[str, int] = {}
    command_count = 0
    for line_number, raw_line in enumerate(str(observation["stdout"]).splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        command_count += 1
        if command_count > MAX_COMMANDS or len(line.encode("utf-8")) > MAX_LINE_BYTES:
            return _inventory(
                root, build, source_observation, [],
                [{"code": "project_test_make_output_invalid"}],
            )
        try:
            record = _test_record(
                _direct_argv(line), index=line_number - 1,
                root=root, build=build, outputs=outputs,
            )
        except (OSError, TypeError, ValueError) as error:
            blocker = {
                "code": str(error)[:96] or "project_test_make_command_invalid",
                "source_index": line_number - 1,
            }
            return _inventory(root, build, source_observation, [], [blocker])
        if record is None:
            continue
        signature = content_sha256({
            key: value for key, value in record.items()
            if key not in {"source_index", "name", "test_id"}
        })
        if signature in signatures:
            blocker = {
                "code": "project_test_make_command_duplicate",
                "source_index": line_number - 1,
                "first_source_index": signatures[signature],
            }
            return _inventory(root, build, source_observation, [], [blocker])
        signatures[signature] = line_number - 1
        tests.append(record)
    if not tests:
        return _inventory(
            root, build, source_observation, [],
            [{"code": "project_test_inventory_empty"}],
        )
    return _inventory(root, build, source_observation, tests, [])


def _test_record(
    argv: list[str], *, index: int, root: Path, build: Path,
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
    record["test_id"] = "test-" + content_sha256(record)[:24]
    return record


def _direct_argv(line: str) -> list[str]:
    quote: str | None = None
    for index, character in enumerate(line):
        if quote == "'":
            quote = None if character == "'" else quote
        elif quote == '"':
            if character == '"':
                quote = None
            elif character in "$`\\":
                raise ValueError("project_test_make_shell_control_rejected")
        elif character in "'\"":
            quote = character
        elif character in ";|&<>()`$\\*?[]{}":
            raise ValueError("project_test_make_shell_control_rejected")
        elif character == "#" and (index == 0 or line[index - 1].isspace()):
            raise ValueError("project_test_make_shell_control_rejected")
    if quote is not None or "\x00" in line:
        raise ValueError("project_test_make_command_invalid")
    try:
        argv = shlex.split(line, posix=True)
    except ValueError as error:
        raise ValueError("project_test_make_command_invalid") from error
    if (
        not argv or not argv[0] or len(argv) > 128
        or any(len(item.encode("utf-8")) > 4096 for item in argv)
    ):
        raise ValueError("project_test_make_command_invalid")
    return argv


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
    marker, host = "/workspace/", root.as_posix().rstrip("/") + "/"
    return value.replace(marker, host) if marker in value else value


def _valid_observation(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != _OBSERVATION_KEYS:
        return False
    stdout = value.get("stdout")
    if not isinstance(stdout, str):
        return False
    try:
        raw = stdout.encode("utf-8")
    except UnicodeError:
        return False
    timeout, stderr_size = value.get("timeout_seconds"), value.get("stderr_size_bytes")
    expected_command = command_for_target_binding(value.get("target_binding"))
    return (
        value.get("schema_version") == 1
        and value.get("artifact_kind") == "make-dry-run-v1-observation"
        and expected_command is not None
        and value.get("command") == expected_command
        and isinstance(timeout, int) and not isinstance(timeout, bool)
        and 5 <= timeout <= 120 and value.get("returncode") == 0
        and value.get("semantic_gate") is False and len(raw) <= MAX_STDOUT_BYTES
        and value.get("stdout_size_bytes") == len(raw)
        and value.get("stdout_sha256") == hashlib.sha256(raw).hexdigest()
        and _identity_valid(value.get("tool"))
        and _identity_valid(value.get("sandbox_launcher"))
        and _sha_valid(value.get("stderr_sha256"))
        and isinstance(stderr_size, int) and not isinstance(stderr_size, bool)
        and 0 <= stderr_size <= MAX_STDERR_BYTES
        and value.get("observation_sha256") == content_sha256({
            key: item for key, item in value.items() if key != "observation_sha256"
        })
    )


def _inventory(
    root: Path, build: Path, source: Mapping[str, Any],
    tests: list[dict[str, Any]], blockers: list[dict[str, Any]],
) -> dict[str, Any]:
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "blocked" if blockers else "ready",
        "adapter": "make-dry-run-v1", "source_observation": dict(source),
        "build_directory": build.relative_to(root).as_posix() or ".",
        "tests": sorted(tests, key=lambda item: item["test_id"]),
        "blockers": blockers,
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


def _blocked_inventory(code: str) -> dict[str, Any]:
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "blocked", "adapter": None, "source_observation": None,
        "build_directory": None, "tests": [], "blockers": [{"code": code}],
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


def _identity_valid(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"basename", "sha256", "size_bytes"}
        and isinstance(value.get("basename"), str) and bool(value["basename"])
        and _sha_valid(value.get("sha256"))
        and isinstance(value.get("size_bytes"), int)
        and not isinstance(value.get("size_bytes"), bool) and value["size_bytes"] >= 0
    )


def _sha_valid(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


__all__ = [
    "AUTOMAKE_CHECK_COMMAND", "MAKE_COMMAND", "MAX_STDERR_BYTES",
    "MAX_STDOUT_BYTES", "derive_make_inventory",
]
