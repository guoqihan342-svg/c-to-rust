from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .build_ir import is_sha256
from .project_test_stdin import MAX_PROJECT_TEST_STDIN_BYTES
from .sandbox_contract import canonical_sha256


RAW_INVOCATION_KEYS = frozenset({
    "schema_version", "purpose", "executable_sha256", "input_sha256",
    "arguments", "working_directory", "environment", "stdin_sha256",
    "stdin_size_bytes", "timeout_seconds", "sandbox_contract_sha256",
    "sandbox_probe_receipt_sha256",
})
SHARED_RAW_INVOCATION_KEYS = RAW_INVOCATION_KEYS - {"executable_sha256"}
_COMMITMENT_KEYS = frozenset({
    "schema_version", "artifact_kind", "executable_sha256", "input_sha256",
    "argument_count", "arguments_sha256", "working_directory_sha256",
    "environment_count", "environment_sha256", "stdin_sha256",
    "stdin_size_bytes", "timeout_seconds", "sandbox_contract_sha256",
    "sandbox_probe_receipt_sha256", "commitment_sha256",
})
_SHARED_COMMITMENT_KEYS = _COMMITMENT_KEYS - {
    "executable_sha256", "commitment_sha256",
}


def validate_raw_project_test_invocation(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != RAW_INVOCATION_KEYS:
        raise ValueError("project_test_invocation_invalid")
    arguments, environment = value.get("arguments"), value.get("environment")
    if (
        value.get("schema_version") != 1
        or value.get("purpose") != "project-test-process"
        or any(not is_sha256(value.get(key)) for key in (
            "executable_sha256", "input_sha256", "stdin_sha256",
            "sandbox_contract_sha256", "sandbox_probe_receipt_sha256",
        ))
        or not isinstance(arguments, list) or len(arguments) > 128
        or any(not isinstance(item, str) for item in arguments)
        or not isinstance(environment, Mapping) or len(environment) > 128
        or any(not isinstance(key, str) or not isinstance(item, str)
               for key, item in environment.items())
        or not isinstance(value.get("working_directory"), str)
        or type(value.get("stdin_size_bytes")) is not int
        or not 0 <= value["stdin_size_bytes"] <= MAX_PROJECT_TEST_STDIN_BYTES
        or type(value.get("timeout_seconds")) is not int
        or not 1 <= value["timeout_seconds"] <= 3_600
    ):
        raise ValueError("project_test_invocation_invalid")
    return value


def build_project_test_invocation_commitment(value: Any) -> dict[str, Any]:
    invocation = validate_raw_project_test_invocation(value)
    arguments = invocation["arguments"]
    environment = {
        key: invocation["environment"][key]
        for key in sorted(invocation["environment"])
    }
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-test-invocation-commitment",
        "executable_sha256": invocation["executable_sha256"],
        "input_sha256": invocation["input_sha256"],
        "argument_count": len(arguments),
        "arguments_sha256": canonical_sha256(arguments),
        "working_directory_sha256": canonical_sha256(
            invocation["working_directory"],
        ),
        "environment_count": len(environment),
        "environment_sha256": canonical_sha256(environment),
        "stdin_sha256": invocation["stdin_sha256"],
        "stdin_size_bytes": invocation["stdin_size_bytes"],
        "timeout_seconds": invocation["timeout_seconds"],
        "sandbox_contract_sha256": invocation["sandbox_contract_sha256"],
        "sandbox_probe_receipt_sha256": invocation[
            "sandbox_probe_receipt_sha256"
        ],
    }
    return {**payload, "commitment_sha256": canonical_sha256(payload)}


def validate_project_test_invocation_commitment(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _COMMITMENT_KEYS:
        raise ValueError("project_test_invocation_commitment_invalid")
    payload = {
        key: item for key, item in value.items() if key != "commitment_sha256"
    }
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "project-test-invocation-commitment"
        or any(not is_sha256(value.get(key)) for key in (
            "executable_sha256", "input_sha256", "arguments_sha256",
            "working_directory_sha256", "environment_sha256", "stdin_sha256",
            "sandbox_contract_sha256", "sandbox_probe_receipt_sha256",
            "commitment_sha256",
        ))
        or type(value.get("argument_count")) is not int
        or not 0 <= value["argument_count"] <= 128
        or type(value.get("environment_count")) is not int
        or not 0 <= value["environment_count"] <= 128
        or type(value.get("stdin_size_bytes")) is not int
        or not 0 <= value["stdin_size_bytes"] <= MAX_PROJECT_TEST_STDIN_BYTES
        or type(value.get("timeout_seconds")) is not int
        or not 1 <= value["timeout_seconds"] <= 3_600
        or value.get("commitment_sha256") != canonical_sha256(payload)
    ):
        raise ValueError("project_test_invocation_commitment_invalid")
    return dict(value)


def shared_project_test_invocation_commitment(value: Any) -> dict[str, Any]:
    commitment = validate_project_test_invocation_commitment(value)
    return {key: commitment[key] for key in sorted(_SHARED_COMMITMENT_KEYS)}


__all__ = [
    "RAW_INVOCATION_KEYS", "SHARED_RAW_INVOCATION_KEYS",
    "build_project_test_invocation_commitment",
    "shared_project_test_invocation_commitment",
    "validate_project_test_invocation_commitment",
    "validate_raw_project_test_invocation",
]
