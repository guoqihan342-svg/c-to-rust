from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .build_facts import resolve_repository_path
from .project_test_inventory_automake import (
    AUTOMAKE_CHECK_COMMAND, MAKE_TEST_COMMAND, command_for_target_binding,
    verify_make_target_binding,
)
from .project_test_inventory_make_records import (
    blocked_inventory, derive_make_command_inventory,
)

MAX_STDOUT_BYTES, MAX_STDERR_BYTES = 4 * 1024 * 1024, 1024 * 1024
MAKE_COMMAND = list(MAKE_TEST_COMMAND)
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
    if not _valid_observation(observation):
        return blocked_inventory("project_test_make_schema_invalid")
    try:
        root = Path(repo_root).resolve(strict=True)
        build = resolve_repository_path(root, str(observation["build_directory"]))
        if not root.is_dir() or not build.is_dir():
            raise ValueError("project test build directory is invalid")
        if not verify_make_target_binding(
            root, observation.get("target_binding"),
        ):
            return blocked_inventory("project_test_make_schema_invalid")
    except (KeyError, OSError, TypeError, ValueError):
        return blocked_inventory("project_test_build_binding_invalid")
    return derive_make_command_inventory(
        root, build, build_ir, str(observation["stdout"]).splitlines(),
        source_observation=source_observation,
        adapter="make-dry-run-v1",
    )


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
