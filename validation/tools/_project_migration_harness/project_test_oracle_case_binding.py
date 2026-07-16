from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .project_test_invocation_commitment import (
    shared_project_test_invocation_commitment,
    validate_project_test_invocation_commitment,
)
from .project_test_stdin import (
    MAX_PROJECT_TEST_STDIN_BYTES, stdin_repo_path,
)


_EVIDENCE_KEYS = {
    "schema_version", "artifact_kind", "inventory_sha256", "mapping_sha256",
    "case_count", "mismatch_count", "crash_count", "cases",
    "failure_details", "details_truncated", "semantic_gate", "evidence_sha256",
}
_CASE_V2_KEYS = {
    "test_id", "oracle_invocation_sha256", "replay_invocation_sha256",
    "matched", "crashed",
}
_CASE_V3_KEYS = _CASE_V2_KEYS | {
    "oracle_invocation", "replay_invocation",
    "stdin_sha256", "stdin_size_bytes",
}
_FILE_KEYS = {"path", "sha256", "size_bytes", "mode"}
_EMPTY_STDIN_SHA256 = hashlib.sha256(b"").hexdigest()


def validate_passed_project_oracle_evidence(
    evidence: Mapping[str, Any], inventory: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> None:
    schema_version = evidence.get("schema_version")
    cases = evidence.get("cases")
    tests = _tests_by_id(inventory)
    if (
        set(evidence) != _EVIDENCE_KEYS
        or schema_version not in {2, 3}
        or evidence.get("artifact_kind") != "project-test-oracle-evidence"
        or evidence.get("inventory_sha256") != inventory.get("inventory_sha256")
        or not is_sha256(evidence.get("mapping_sha256"))
        or not isinstance(cases, list) or len(cases) != len(tests)
        or evidence.get("case_count") != len(tests)
        or evidence.get("mismatch_count") != 0
        or evidence.get("crash_count") != 0
        or evidence.get("failure_details") != []
        or evidence.get("details_truncated") is not False
        or evidence.get("semantic_gate") is not False
        or evidence.get("evidence_sha256") != content_sha256({
            key: item for key, item in evidence.items()
            if key != "evidence_sha256"
        })
    ):
        raise ValueError("project_test_oracle_evidence_invalid")
    if schema_version == 2 and any(
        test.get("stdin") is not None for test in tests.values()
    ):
        raise ValueError("project_test_oracle_legacy_stdin_unbound")
    files, required = _snapshot_files(snapshot) if schema_version == 3 else ({}, set())
    normalized = []
    for case in cases:
        if not isinstance(case, Mapping):
            raise ValueError("project_test_oracle_case_invalid")
        test_id = case.get("test_id")
        expected_keys = _CASE_V2_KEYS if schema_version == 2 else _CASE_V3_KEYS
        if (
            set(case) != expected_keys or test_id not in tests
            or not is_sha256(case.get("oracle_invocation_sha256"))
            or not is_sha256(case.get("replay_invocation_sha256"))
            or case.get("matched") is not True or case.get("crashed") is not False
        ):
            raise ValueError("project_test_oracle_case_invalid")
        if schema_version == 3:
            expected_sha256, expected_size = _stdin_binding(
                tests[str(test_id)], files, required,
            )
            oracle_invocation = validate_project_test_invocation_commitment(
                case.get("oracle_invocation"),
            )
            replay_invocation = validate_project_test_invocation_commitment(
                case.get("replay_invocation"),
            )
            if (
                case.get("stdin_sha256") != expected_sha256
                or case.get("stdin_size_bytes") != expected_size
                or case.get("oracle_invocation_sha256")
                != oracle_invocation["commitment_sha256"]
                or case.get("replay_invocation_sha256")
                != replay_invocation["commitment_sha256"]
                or oracle_invocation["input_sha256"]
                != snapshot.get("snapshot_sha256")
                or replay_invocation["input_sha256"]
                != snapshot.get("snapshot_sha256")
                or oracle_invocation["stdin_sha256"] != expected_sha256
                or replay_invocation["stdin_sha256"] != expected_sha256
                or oracle_invocation["stdin_size_bytes"] != expected_size
                or replay_invocation["stdin_size_bytes"] != expected_size
                or shared_project_test_invocation_commitment(oracle_invocation)
                != shared_project_test_invocation_commitment(replay_invocation)
            ):
                raise ValueError("project_test_oracle_case_stdin_drifted")
        normalized.append(str(test_id))
    if normalized != sorted(tests) or len(set(normalized)) != len(normalized):
        raise ValueError("project_test_oracle_case_set_invalid")


def _tests_by_id(inventory: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    tests = inventory.get("tests")
    if not isinstance(tests, list) or not tests:
        raise ValueError("project_test_oracle_inventory_invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for test in tests:
        test_id = test.get("test_id") if isinstance(test, Mapping) else None
        if not isinstance(test_id, str) or not test_id or test_id in result:
            raise ValueError("project_test_oracle_inventory_invalid")
        result[test_id] = test
    return result


def _snapshot_files(
    snapshot: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    files, required = snapshot.get("files"), snapshot.get("required_inputs")
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("artifact_kind") != "project-test-input-snapshot"
        or not isinstance(files, list) or not isinstance(required, list)
        or required != sorted(set(required))
        or any(not _safe_relative(path) for path in required)
        or snapshot.get("snapshot_sha256") != content_sha256({
            key: item for key, item in snapshot.items()
            if key != "snapshot_sha256"
        })
    ):
        raise ValueError("project_test_oracle_snapshot_invalid")
    indexed: dict[str, Mapping[str, Any]] = {}
    total_size = 0
    for item in files:
        path = item.get("path") if isinstance(item, Mapping) else None
        if (
            not isinstance(item, Mapping) or set(item) != _FILE_KEYS
            or not _safe_relative(path) or path in indexed
            or not is_sha256(item.get("sha256"))
            or type(item.get("size_bytes")) is not int or item["size_bytes"] < 0
            or type(item.get("mode")) is not int or item["mode"] < 0
        ):
            raise ValueError("project_test_oracle_snapshot_invalid")
        indexed[str(path)] = item
        total_size += int(item["size_bytes"])
    if (
        snapshot.get("file_count") != len(indexed)
        or snapshot.get("size_bytes") != total_size
    ):
        raise ValueError("project_test_oracle_snapshot_invalid")
    return indexed, set(required)


def _stdin_binding(
    test: Mapping[str, Any], files: Mapping[str, Mapping[str, Any]],
    required: set[str],
) -> tuple[str, int]:
    path = stdin_repo_path(test.get("stdin"))
    if path is None:
        return _EMPTY_STDIN_SHA256, 0
    binding = files.get(path)
    if (
        not _safe_relative(path) or path not in required
        or not isinstance(binding, Mapping)
        or binding["size_bytes"] > MAX_PROJECT_TEST_STDIN_BYTES
    ):
        raise ValueError("project_test_oracle_stdin_snapshot_invalid")
    return str(binding["sha256"]), int(binding["size_bytes"])


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


__all__ = ["validate_passed_project_oracle_evidence"]
