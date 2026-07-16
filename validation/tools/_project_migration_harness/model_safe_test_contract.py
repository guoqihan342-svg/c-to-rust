from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256
from .runtime_security import assert_model_payload_safe


MAX_BOUND_TESTS = 128
MAX_INPUT_PATHS = 128
SUPPORTED_TEST_ADAPTERS = frozenset({
    "ctest-json-v1", "make-dry-run-v1", "make-static-direct-v1",
})
LEGACY_WITHHELD_FIELDS = [
    "argument_literals", "environment_values", "expected", "actual",
    "oracle_values", "raw_output",
]
WITHHELD_FIELDS = [*LEGACY_WITHHELD_FIELDS, "stdin_contents"]
_REFERENCE_KEYS = {"path", "sha256", "size_bytes"}
_CONTRACT_KEYS = {
    "schema_version", "artifact_kind", "group_id", "target_scope_sha256",
    "inventory_sha256", "adapter", "test_count", "included_test_count",
    "omitted_test_count", "tests", "withheld_fields", "claim_boundary",
    "contract_sha256",
}
_TEST_KEYS_V1 = {
    "test_id", "source_target_id", "argument_count", "argument_shape",
    "environment_keys", "input_paths", "omitted_input_path_count",
    "working_directory", "timeout_class",
}
_TEST_KEYS_V2 = _TEST_KEYS_V1 | {"stdin_shape"}


def build_model_safe_test_contract(
    inventory: Mapping[str, Any], *, group_id: str,
    target_scope: Mapping[str, Any],
) -> dict[str, Any]:
    validate_test_inventory_binding(inventory)
    if inventory.get("status") != "ready":
        raise ValueError("model-safe test contract requires a ready inventory")
    scope_sha256 = target_scope.get("scope_sha256")
    reachable = target_scope.get("reachable_target_ids")
    terminal = target_scope.get("terminal_target_ids")
    if (
        not isinstance(group_id, str) or not group_id
        or not is_sha256(scope_sha256)
        or not _canonical_strings(reachable, allow_empty=True)
        or not _canonical_strings(terminal, allow_empty=True)
    ):
        raise ValueError("model-safe test contract target scope is invalid")
    target_ids = set(reachable) | set(terminal)
    tests = inventory.get("tests")
    if not isinstance(tests, list):
        raise ValueError("model-safe test contract inventory tests are invalid")
    relevant = sorted(
        (_project_test(item) for item in tests
         if isinstance(item, Mapping) and item.get("source_target_id") in target_ids),
        key=lambda item: item["test_id"],
    )
    included = relevant[:MAX_BOUND_TESTS]
    payload = {
        "schema_version": 2,
        "artifact_kind": "model-safe-project-test-contract",
        "group_id": group_id,
        "target_scope_sha256": scope_sha256,
        "inventory_sha256": inventory["inventory_sha256"],
        "adapter": inventory["adapter"],
        "test_count": len(relevant),
        "included_test_count": len(included),
        "omitted_test_count": len(relevant) - len(included),
        "tests": included,
        "withheld_fields": list(WITHHELD_FIELDS),
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    result = {**payload, "contract_sha256": content_sha256(payload)}
    return validate_model_safe_test_contract(result, group_id=group_id)


def validate_model_safe_test_contract(
    value: Any, *, group_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONTRACT_KEYS:
        raise ValueError("model-safe test contract fields are invalid")
    payload = {key: item for key, item in value.items() if key != "contract_sha256"}
    tests = value.get("tests")
    schema_version = value.get("schema_version")
    withheld_fields = (
        LEGACY_WITHHELD_FIELDS if schema_version == 1 else WITHHELD_FIELDS
    )
    if (
        schema_version not in {1, 2}
        or value.get("artifact_kind") != "model-safe-project-test-contract"
        or not isinstance(value.get("group_id"), str) or not value["group_id"]
        or group_id is not None and value.get("group_id") != group_id
        or not is_sha256(value.get("target_scope_sha256"))
        or not is_sha256(value.get("inventory_sha256"))
        or value.get("adapter") not in SUPPORTED_TEST_ADAPTERS
        or not isinstance(tests, list) or len(tests) > MAX_BOUND_TESTS
        or value.get("included_test_count") != len(tests)
        or not _nonnegative_int(value.get("test_count"))
        or not _nonnegative_int(value.get("omitted_test_count"))
        or value["test_count"] != len(tests) + value["omitted_test_count"]
        or value.get("withheld_fields") != withheld_fields
        or value.get("claim_boundary") != {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        }
        or value.get("contract_sha256") != content_sha256(payload)
    ):
        raise ValueError("model-safe test contract binding is invalid")
    normalized = [
        _validate_projected_test(item, schema_version=schema_version)
        for item in tests
    ]
    if normalized != tests or tests != sorted(tests, key=lambda item: item["test_id"]):
        raise ValueError("model-safe test contract tests are not canonical")
    result = dict(value)
    assert_model_payload_safe(result, "model_safe_test_contract")
    return result


def validate_test_contract_reference(value: Any) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping) or set(value) != _REFERENCE_KEYS
        or not isinstance(value.get("path"), str) or not value["path"]
        or value["path"].startswith(("/", "~")) or "\\" in value["path"]
        or ".." in value["path"].split("/")
        or not is_sha256(value.get("sha256"))
        or not _nonnegative_int(value.get("size_bytes"))
        or value["size_bytes"] == 0
    ):
        raise ValueError("model-safe test contract reference is invalid")
    return dict(value)


def _project_test(value: Mapping[str, Any]) -> dict[str, Any]:
    arguments, environment = value.get("arguments"), value.get("environment")
    if not isinstance(arguments, list) or not isinstance(environment, Mapping):
        raise ValueError("project test input contract is invalid")
    paths: set[str] = set()
    shape = [_input_shape(item, paths) for item in arguments]
    environment_keys = sorted(environment)
    if any(not isinstance(key, str) or not key for key in environment_keys):
        raise ValueError("project test environment contract is invalid")
    for item in environment.values():
        _input_shape(item, paths)
    stdin = value.get("stdin")
    stdin_shape = "none" if stdin is None else _input_shape(stdin, paths)
    if stdin_shape not in {"none", "repo-path"}:
        raise ValueError("project test stdin contract is invalid")
    selected_paths = sorted(paths)[:MAX_INPUT_PATHS]
    timeout = value.get("timeout_seconds")
    if not _nonnegative_int(timeout) or timeout < 1:
        raise ValueError("project test timeout contract is invalid")
    return _validate_projected_test({
        "test_id": value.get("test_id"),
        "source_target_id": value.get("source_target_id"),
        "argument_count": len(arguments),
        "argument_shape": shape,
        "environment_keys": environment_keys,
        "input_paths": selected_paths,
        "omitted_input_path_count": len(paths) - len(selected_paths),
        "stdin_shape": stdin_shape,
        "working_directory": value.get("working_directory"),
        "timeout_class": "short" if timeout <= 30 else "normal" if timeout <= 120 else "long",
    }, schema_version=2)


def _input_shape(value: Any, paths: set[str]) -> str:
    if not isinstance(value, Mapping):
        raise ValueError("project test argument contract is invalid")
    kind = value.get("kind")
    if kind == "literal" and set(value) == {"kind", "value"}:
        literal = value.get("value")
        if not isinstance(literal, str):
            raise ValueError("project test literal contract is invalid")
        return "literal-option" if literal.startswith("-") else "literal-positional"
    if kind in {"repo-path", "repo-path-template"}:
        path = value.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("project test path contract is invalid")
        paths.add(path)
        return str(kind)
    raise ValueError("project test argument contract is invalid")


def _validate_projected_test(
    value: Any, *, schema_version: int,
) -> dict[str, Any]:
    expected_keys = _TEST_KEYS_V1 if schema_version == 1 else _TEST_KEYS_V2
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise ValueError("projected test contract fields are invalid")
    shape = value.get("argument_shape")
    environment = value.get("environment_keys")
    paths = value.get("input_paths")
    working = value.get("working_directory")
    if (
        not isinstance(value.get("test_id"), str) or not value["test_id"]
        or not isinstance(value.get("source_target_id"), str)
        or not value["source_target_id"]
        or not _nonnegative_int(value.get("argument_count"))
        or not isinstance(shape, list) or len(shape) != value["argument_count"]
        or any(item not in {
            "literal-option", "literal-positional", "repo-path",
            "repo-path-template",
        } for item in shape)
        or not _canonical_strings(environment, allow_empty=True)
        or not _canonical_strings(paths, allow_empty=True)
        or len(paths) > MAX_INPUT_PATHS
        or not _nonnegative_int(value.get("omitted_input_path_count"))
        or schema_version == 2
        and value.get("stdin_shape") not in {"none", "repo-path"}
        or not isinstance(working, str) or "\\" in working
        or working.startswith(("/", "~")) or ".." in working.split("/")
        or value.get("timeout_class") not in {"short", "normal", "long"}
    ):
        raise ValueError("projected test contract is invalid")
    return dict(value)


def validate_test_inventory_binding(value: Mapping[str, Any]) -> None:
    claimed = value.get("inventory_sha256")
    payload = {key: item for key, item in value.items() if key != "inventory_sha256"}
    if (
        value.get("artifact_kind") != "project-test-inventory"
        or value.get("status") not in {"ready", "blocked"}
        or not is_sha256(claimed) or claimed != content_sha256(payload)
    ):
        raise ValueError("project test inventory binding is invalid")


def _canonical_strings(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list) and (allow_empty or bool(value))
        and all(isinstance(item, str) and item for item in value)
        and value == sorted(set(value))
    )


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


__all__ = [
    "SUPPORTED_TEST_ADAPTERS", "WITHHELD_FIELDS", "build_model_safe_test_contract",
    "validate_model_safe_test_contract", "validate_test_contract_reference",
    "validate_test_inventory_binding",
]
