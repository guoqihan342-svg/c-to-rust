from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .build_facts import resolve_repository_path
from .project_test_inventory_meson_binding import (
    MESON_TEST_ADAPTER,
)
from .project_test_inventory_meson_schema import valid_meson_test_observation
from .project_test_inventory_paths import (
    build_output_index, normalize_argument, normalize_command_path,
    normalize_environment,
)


_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_RESERVED_ENVIRONMENT = {
    "HOME", "LANG", "LC_ALL", "PATH", "TEMP", "TMP", "TMPDIR",
}
_TEST_KEYS = {
    "cmd", "env", "name", "workdir", "timeout", "suite", "is_parallel",
    "priority", "protocol", "depends", "extra_paths",
}


def inventory_from_meson_observation(
    repo_root: Path, build_ir: Mapping[str, Any], observation: Mapping[str, Any],
    *, source_observation: Mapping[str, Any],
) -> dict[str, Any]:
    if not valid_meson_test_observation(observation):
        return _blocked("project_test_meson_schema_invalid")
    raw_tests = observation["payload"]
    tests: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    try:
        root = Path(repo_root).resolve(strict=True)
        build = _working_directory(
            root, str(observation["build_directory"]), root,
        )
        output_index = build_output_index(build_ir)
        targets, meson_targets = _meson_target_indexes(build_ir)
    except (KeyError, OSError, TypeError, ValueError):
        return _blocked("project_test_build_binding_invalid")
    for index, raw in enumerate(raw_tests):
        try:
            tests.append(_test_record(
                raw, index=index, root=root, build=build,
                output_index=output_index, targets=targets,
                meson_targets=meson_targets,
            ))
        except (KeyError, OSError, TypeError, ValueError) as error:
            blockers.append({
                "code": str(error)[:96] or "project_test_meson_record_invalid",
                "test_index": index,
            })
    if not raw_tests:
        blockers.append({"code": "project_test_inventory_empty"})
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-test-inventory",
        "status": "blocked" if blockers else "ready",
        "adapter": MESON_TEST_ADAPTER,
        "source_observation": dict(source_observation),
        "build_directory": build.relative_to(root).as_posix() or ".",
        "tests": sorted(tests, key=lambda item: item["test_id"]),
        "blockers": blockers,
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    payload["inventory_sha256"] = content_sha256(payload)
    return payload


def _test_record(
    raw: Any, *, index: int, root: Path, build: Path,
    output_index: Mapping[str, Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, Any]],
    meson_targets: Mapping[str, list[Mapping[str, Any]]],
) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _TEST_KEYS:
        raise ValueError("project_test_meson_record_schema_invalid")
    name, command = raw.get("name"), raw.get("cmd")
    if (
        not isinstance(name, str) or not name
        or len(name.encode("utf-8")) > 1024
        or not isinstance(command, list) or not command or len(command) > 128
        or any(
            not isinstance(item, str) or not item or "\x00" in item
            or len(item.encode("utf-8")) > 4096 for item in command
        )
    ):
        raise ValueError("project_test_meson_command_invalid")
    if raw.get("protocol") != "exitcode":
        raise ValueError("project_test_meson_protocol_unsupported")
    extra_paths = raw.get("extra_paths")
    if not isinstance(extra_paths, list) or extra_paths:
        raise ValueError("project_test_meson_environment_unsupported")
    suite = _string_list(raw.get("suite"), "project_test_meson_suite_invalid")
    parallel, priority = raw.get("is_parallel"), raw.get("priority")
    if (
        not isinstance(parallel, bool)
        or isinstance(priority, bool) or not isinstance(priority, int)
        or not -1_000_000 <= priority <= 1_000_000
    ):
        raise ValueError("project_test_meson_scheduling_invalid")
    timeout = raw.get("timeout")
    if (
        isinstance(timeout, bool) or not isinstance(timeout, int)
        or not 1 <= timeout <= 3600
    ):
        raise ValueError("project_test_meson_timeout_invalid")
    working = _working_directory(root, raw.get("workdir"), build)
    try:
        executable_path, _ = normalize_command_path(
            command[0], repo_root=root, base=working,
        )
    except (OSError, ValueError) as error:
        raise ValueError(
            "project_test_meson_runner_or_wrapper_unsupported"
        ) from error
    output = output_index.get(executable_path)
    if output is None:
        raise ValueError("project_test_executable_target_unmapped")
    target = targets.get(str(output.get("target_id")))
    binding = output.get("binding")
    if (
        target is None or target.get("kind") != "link"
        or not isinstance(binding, Mapping)
        or binding.get("materialized") is not True
    ):
        raise ValueError("project_test_executable_unmaterialized")
    provenance = target.get("provenance")
    meson_id = provenance.get("meson_target_id") if isinstance(
        provenance, Mapping,
    ) else None
    matches = meson_targets.get(str(meson_id), []) if isinstance(meson_id, str) else []
    if len(matches) != 1 or matches[0] is not target:
        raise ValueError("project_test_meson_target_mapping_ambiguous")
    depends = _string_list(
        raw.get("depends"), "project_test_meson_dependency_invalid",
    )
    if depends != [meson_id]:
        raise ValueError("project_test_meson_fixture_or_dependency_unsupported")
    environment = _environment(raw.get("env"), root=root, working=working)
    record = {
        "source_index": index,
        "name": name,
        "source_target_id": target["target_id"],
        "source_executable": dict(binding),
        "arguments": [
            normalize_argument(item, repo_root=root, base=working)
            for item in command[1:]
        ],
        "working_directory": working.relative_to(root).as_posix() or ".",
        "environment": environment,
        "timeout_seconds": timeout,
        "adapter_metadata": {
            "meson_target_id": meson_id, "suite": suite,
            "is_parallel": parallel, "priority": priority,
        },
    }
    record["test_id"] = "test-" + content_sha256(record)[:24]
    return record


def _meson_target_indexes(
    build_ir: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, list[Mapping[str, Any]]]]:
    raw = build_ir.get("targets")
    if not isinstance(raw, list):
        raise ValueError("project_test_build_ir_targets_invalid")
    targets: dict[str, Mapping[str, Any]] = {}
    meson: dict[str, list[Mapping[str, Any]]] = {}
    for target in raw:
        identity = target.get("target_id") if isinstance(target, Mapping) else None
        if not isinstance(identity, str) or not identity or identity in targets:
            raise ValueError("project_test_build_ir_target_invalid")
        targets[identity] = target
        provenance = target.get("provenance")
        meson_id = provenance.get("meson_target_id") if isinstance(
            provenance, Mapping,
        ) else None
        if isinstance(meson_id, str) and meson_id:
            meson.setdefault(meson_id, []).append(target)
    return targets, meson


def _environment(
    value: Any, *, root: Path, working: Path,
) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping) or len(value) > 128:
        raise ValueError("project_test_meson_environment_invalid")
    assignments = []
    for name in sorted(value):
        assigned = value[name]
        if (
            not isinstance(name, str) or _ENVIRONMENT_NAME.fullmatch(name) is None
            or name in _RESERVED_ENVIRONMENT or not isinstance(assigned, str)
        ):
            raise ValueError("project_test_meson_environment_invalid")
        assignments.append(f"{name}={assigned}")
    return normalize_environment(assignments, repo_root=root, base=working)


def _working_directory(root: Path, value: Any, default: Path) -> Path:
    if value is None:
        path = default
    elif isinstance(value, str) and value:
        path = resolve_repository_path(root, value, base=default)
    else:
        raise ValueError("project_test_working_directory_invalid")
    if not path.is_dir():
        raise ValueError("project_test_working_directory_invalid")
    return path


def _string_list(value: Any, code: str) -> list[str]:
    if (
        not isinstance(value, list) or len(value) > 256
        or any(
            not isinstance(item, str) or not item or "\x00" in item
            or len(item.encode("utf-8")) > 4096 for item in value
        )
        or len(value) != len(set(value))
    ):
        raise ValueError(code)
    return list(value)


def _blocked(code: str) -> dict[str, Any]:
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "blocked", "adapter": None, "source_observation": None,
        "build_directory": None, "tests": [], "blockers": [{"code": code}],
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


__all__ = ["inventory_from_meson_observation"]
