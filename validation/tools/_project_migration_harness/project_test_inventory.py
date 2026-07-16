from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256, write_json_artifact
from .build_facts import resolve_repository_path
from .project_test_inventory_adapter import select_project_test_adapter
from .project_test_inventory_ctest import collect_ctest_json
from .project_test_inventory_make_static import (
    MAKE_STATIC_ADAPTER, collect_static_make_test_recipes,
    inventory_from_static_make_observation,
)
from .project_test_inventory_meson import collect_meson_test_introspection
from .project_test_inventory_meson_binding import MESON_TEST_ADAPTER
from .project_test_inventory_meson_parse import inventory_from_meson_observation
from .project_test_inventory_paths import (
    build_output_index, normalize_argument, normalize_command_path,
    normalize_environment,
)
from .project_test_target_proposal import (
    ProjectTestTargetProposalSelection,
    load_project_test_target_proposal,
)


MAX_PROJECT_TESTS = 10_000
_IGNORED_PROPERTIES = frozenset({
    "ATTACHED_FILES", "ATTACHED_FILES_ON_FAIL", "BACKTRACE_TRIPLES", "COST",
    "LABELS", "MEASUREMENT", "PROCESSORS", "RUN_SERIAL", "_BACKTRACE_TRIPLES",
})
_SUPPORTED_PROPERTIES = frozenset({
    "DISABLED", "ENVIRONMENT", "TIMEOUT", "WORKING_DIRECTORY",
})


def collect_project_test_inventory(
    repo_root: Path, discovery: Mapping[str, Any], build_ir: Mapping[str, Any],
    *, output: Path,
    target_proposal: ProjectTestTargetProposalSelection | None = None,
) -> dict[str, Any]:
    selection = select_project_test_adapter(repo_root, discovery, build_ir)
    if selection.get("status") != "selected":
        blocker = selection.get("blocker")
        code = blocker.get("code") if isinstance(blocker, Mapping) else None
        return _blocked(str(code or "project_test_adapter_unavailable"))
    adapter = selection.get("adapter")
    if target_proposal is not None and adapter != "make-dry-run-v1":
        return _blocked("project_test_target_proposal_adapter_mismatch")
    database = discovery.get("compile_database")
    path = database.get("path") if isinstance(database, Mapping) else None
    if not isinstance(path, str) and adapter == "make-dry-run-v1":
        metadata = build_ir.get("build_metadata")
        if isinstance(metadata, list) and len(metadata) == 1:
            value = metadata[0]
            path = value.get("path") if isinstance(value, Mapping) else None
    if not isinstance(path, str):
        return _blocked("project_test_build_directory_unbound")
    try:
        input_path = resolve_repository_path(repo_root, path)
        build_directory = input_path.parent
    except (OSError, ValueError):
        return _blocked("project_test_build_directory_unbound")
    if adapter == "ctest-json-v1":
        collected = collect_ctest_json(repo_root, build_directory)
    elif adapter == "make-dry-run-v1":
        if target_proposal is None:
            return _blocked("project_test_make_ai_target_proposal_required")
        try:
            proposal = load_project_test_target_proposal(target_proposal)
        except ValueError:
            return _blocked("project_test_target_proposal_invalid")
        collected = collect_static_make_test_recipes(
            repo_root, build_directory, target_proposal=proposal,
        )
        adapter = MAKE_STATIC_ADAPTER
    elif adapter == MESON_TEST_ADAPTER:
        collected = collect_meson_test_introspection(
            repo_root, build_directory, input_path,
        )
    else:
        return _blocked("project_test_adapter_unavailable")
    observation = collected.get("observation")
    if collected.get("status") != "collected" or not isinstance(observation, dict):
        blocker = collected.get("blocker")
        code = blocker.get("code") if isinstance(blocker, Mapping) else None
        return _blocked(str(code or f"project_test_{adapter}_collection_failed"))
    observation_name = {
        "ctest-json-v1": "project-test-ctest-observation.json",
        MAKE_STATIC_ADAPTER: "project-test-make-static-observation.json",
        MESON_TEST_ADAPTER: "project-test-meson-observation.json",
    }[adapter]
    reference = write_json_artifact(
        output, f"plan/{observation_name}", observation,
    )
    derive = {
        "ctest-json-v1": inventory_from_ctest_observation,
        MAKE_STATIC_ADAPTER: inventory_from_static_make_observation,
        MESON_TEST_ADAPTER: inventory_from_meson_observation,
    }[adapter]
    return derive(repo_root, build_ir, observation, source_observation=reference)


def inventory_from_ctest_observation(
    repo_root: Path, build_ir: Mapping[str, Any], observation: Mapping[str, Any],
    *, source_observation: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    payload = observation.get("payload")
    version = payload.get("version") if isinstance(payload, Mapping) else None
    raw_tests = payload.get("tests") if isinstance(payload, Mapping) else None
    if (
        observation.get("artifact_kind") != "ctest-json-v1-observation"
        or observation.get("observation_sha256")
        != content_sha256({key: value for key, value in observation.items()
                           if key != "observation_sha256"})
        or not isinstance(payload, Mapping) or payload.get("kind") != "ctestInfo"
        or not isinstance(version, Mapping) or version.get("major") != 1
        or not isinstance(raw_tests, list) or len(raw_tests) > MAX_PROJECT_TESTS
    ):
        return _blocked("project_test_ctest_schema_invalid")
    try:
        build_directory = _relative_directory(
            str(observation["build_directory"]), repo_root, repo_root,
        )
        output_index = build_output_index(build_ir)
    except (KeyError, OSError, TypeError, ValueError):
        return _blocked("project_test_build_binding_invalid")
    for index, raw in enumerate(raw_tests):
        try:
            tests.append(_test_record(
                raw, index=index, repo_root=repo_root,
                build_directory=build_directory, output_index=output_index,
            ))
        except (OSError, TypeError, ValueError) as error:
            blockers.append({
                "code": str(error)[:96] or "project_test_record_invalid",
                "test_index": index,
            })
    if not raw_tests:
        blockers.append({"code": "project_test_inventory_empty"})
    payload_out = {
        "schema_version": 1,
        "artifact_kind": "project-test-inventory",
        "status": "blocked" if blockers else "ready",
        "adapter": "ctest-json-v1",
        "source_observation": dict(source_observation),
        "build_directory": build_directory.relative_to(repo_root.resolve()).as_posix(),
        "tests": sorted(tests, key=lambda item: item["test_id"]),
        "blockers": blockers,
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    payload_out["inventory_sha256"] = content_sha256(payload_out)
    return payload_out


def _test_record(
    raw: Any, *, index: int, repo_root: Path, build_directory: Path,
    output_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("project_test_record_invalid")
    name, command = raw.get("name"), raw.get("command")
    if (
        not isinstance(name, str) or not name or len(name.encode("utf-8")) > 1024
        or not isinstance(command, list) or not command or len(command) > 128
    ):
        raise ValueError("project_test_command_invalid")
    properties = _properties(raw.get("properties", []))
    if properties.get("DISABLED") is True:
        raise ValueError("project_test_disabled")
    working = _relative_directory(
        properties.get("WORKING_DIRECTORY", build_directory.as_posix()),
        repo_root, build_directory,
    )
    executable_path, executable = normalize_command_path(
        command[0], repo_root=repo_root, base=working,
    )
    target = output_index.get(executable_path)
    if target is None:
        raise ValueError("project_test_executable_target_unmapped")
    binding = target.get("binding")
    if not isinstance(binding, Mapping) or binding.get("materialized") is not True:
        raise ValueError("project_test_executable_unmaterialized")
    timeout = properties.get("TIMEOUT", 120)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 3600:
        raise ValueError("project_test_timeout_invalid")
    record = {
        "source_index": index,
        "name": name,
        "source_target_id": target["target_id"],
        "source_executable": dict(binding),
        "arguments": [
            normalize_argument(item, repo_root=repo_root, base=working)
            for item in command[1:]
        ],
        "working_directory": working.relative_to(repo_root.resolve()).as_posix(),
        "environment": normalize_environment(
            properties.get("ENVIRONMENT"), repo_root=repo_root, base=working,
        ),
        "timeout_seconds": int(timeout),
    }
    record["test_id"] = "test-" + content_sha256(record)[:24]
    return record


def _properties(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, list) or len(value) > 256:
        raise ValueError("project_test_properties_invalid")
    result = {}
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"name", "value"}:
            raise ValueError("project_test_property_invalid")
        name = item.get("name")
        if not isinstance(name, str) or not name or name in result:
            raise ValueError("project_test_property_invalid")
        if name in _IGNORED_PROPERTIES:
            continue
        if name not in _SUPPORTED_PROPERTIES:
            raise ValueError("project_test_property_unsupported")
        result[name] = item.get("value")
    return result


def _relative_directory(value: str, root: Path, base: Path) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("project_test_working_directory_invalid")
    path = resolve_repository_path(root, value, base=base)
    if not path.is_dir():
        raise ValueError("project_test_working_directory_invalid")
    return path


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


__all__ = [
    "collect_project_test_inventory", "inventory_from_ctest_observation",
    "inventory_from_meson_observation",
]
