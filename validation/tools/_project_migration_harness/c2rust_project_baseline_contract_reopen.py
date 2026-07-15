from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import PurePosixPath
import re
from typing import Any

from .c2rust_project_baseline_process_contract import (
    REQUIRED_ENVIRONMENT_KEYS, RUNTIME_OVERRIDE_KEYS,
    validated_portable_command,
)


_SCENARIO_FIELDS = {
    "id", "argv", "working_directory", "environment", "stdin_utf8",
    "expected_exit", "timeout_seconds",
}
_SCENARIO_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z", re.ASCII)
_ENVIRONMENT_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z", re.ASCII)


def validate_execution_contract_reopen(
    report: Mapping[str, Any], normalized: Mapping[str, Any],
) -> None:
    contract = report["inputs"]["execution_contract"]
    plan = report["generated"]["execution_plan"]
    if (
        not isinstance(contract, Mapping)
        or contract.get("status") != "validated"
        or not isinstance(plan, Mapping)
    ):
        raise ValueError("c2rust_scenario_reopen_contract_invalid")
    wrappers = _generated_wrappers(report["generated"]["wrappers"])
    expected = _normalized_scenarios(normalized, wrappers, report["policy"])
    expected_purposes = [item["purpose"] for item in expected]
    if (
        contract.get("wrapper_count") != len(wrappers)
        or contract.get("scenario_count") != len(expected)
        or plan.get("expected_run_purposes") != expected_purposes
    ):
        raise ValueError("c2rust_scenario_reopen_plan_mismatch")
    executions = [
        item for item in report["executions"]
        if str(item.get("purpose", "")).startswith("cargo-run-")
    ]
    observed_purposes = [item.get("purpose") for item in executions]
    if observed_purposes not in ([], expected_purposes):
        raise ValueError("c2rust_scenario_reopen_execution_set_mismatch")
    for execution, descriptor in zip(executions, expected):
        _validate_execution(execution, descriptor)


def _generated_wrappers(value: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("c2rust_scenario_reopen_wrappers_invalid")
    result: dict[str, Mapping[str, Any]] = {}
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("c2rust_scenario_reopen_wrapper_invalid")
        translated = _relative(item.get("translated_module_path"), allow_dot=False)
        manifest = _relative(item.get("manifest_path"), allow_dot=False)
        name = item.get("name")
        if (
            not isinstance(name, str) or not name or "/" in name or "\\" in name
            or translated in result
        ):
            raise ValueError("c2rust_scenario_reopen_wrapper_invalid")
        result[translated] = {
            "name": name, "manifest_path": manifest,
            "translated_module_path": translated,
        }
    return result


def _normalized_scenarios(
    value: Mapping[str, Any], wrappers: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"schema_version", "wrappers"}
        or value.get("schema_version") != 1
        or not isinstance(value.get("wrappers"), list)
    ):
        raise ValueError("c2rust_scenario_reopen_payload_invalid")
    entries = value["wrappers"]
    if any(
        not isinstance(item, Mapping)
        or not isinstance(item.get("translated_module_path"), str)
        for item in entries
    ):
        raise ValueError("c2rust_scenario_reopen_wrapper_invalid")
    paths = [item.get("translated_module_path") for item in entries]
    if paths != sorted(wrappers) or len(paths) != len(set(paths)):
        raise ValueError("c2rust_scenario_reopen_wrapper_set_mismatch")
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("c2rust_scenario_reopen_wrapper_invalid")
        path = entry.get("translated_module_path")
        mode = entry.get("execution_mode")
        expected_fields = (
            {"translated_module_path", "execution_mode", "scenarios"}
            if mode == "scenarios"
            else {"translated_module_path", "execution_mode"}
        )
        if set(entry) != expected_fields or mode not in {"compile_only", "scenarios"}:
            raise ValueError("c2rust_scenario_reopen_wrapper_invalid")
        if mode == "compile_only":
            continue
        scenarios = entry["scenarios"]
        if (
            not isinstance(scenarios, list) or not scenarios
            or any(not isinstance(item, Mapping) for item in scenarios)
        ):
            raise ValueError("c2rust_scenario_reopen_scenarios_invalid")
        identifiers = [item.get("id") for item in scenarios]
        if identifiers != sorted(identifiers):
            raise ValueError("c2rust_scenario_reopen_scenario_order_invalid")
        for scenario in scenarios:
            descriptor = _scenario_descriptor(
                scenario, wrappers[path], policy,
            )
            identifier = descriptor["id"]
            if identifier in seen_ids:
                raise ValueError("c2rust_scenario_reopen_id_duplicate")
            seen_ids.add(identifier)
            result.append(descriptor)
    return result


def _scenario_descriptor(
    value: Any, wrapper: Mapping[str, Any], policy: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SCENARIO_FIELDS:
        raise ValueError("c2rust_scenario_reopen_fields_invalid")
    identifier = value.get("id")
    argv = value.get("argv")
    environment = value.get("environment")
    stdin = value.get("stdin_utf8")
    expected_exit = value.get("expected_exit")
    timeout = value.get("timeout_seconds")
    if (
        not isinstance(identifier, str) or _SCENARIO_ID.fullmatch(identifier) is None
        or not isinstance(argv, list)
        or not isinstance(environment, Mapping)
        or not isinstance(stdin, str) or "\0" in stdin
        or type(expected_exit) is not int or not -255 <= expected_exit <= 255
        or type(timeout) is not int or not 1 <= timeout <= 3_600
    ):
        raise ValueError("c2rust_scenario_reopen_value_invalid")
    try:
        validated_portable_command(["scenario", *argv])
        stdin_bytes = stdin.encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as error:
        raise ValueError("c2rust_scenario_reopen_value_invalid") from error
    environment_keys = []
    for key, item in environment.items():
        if (
            not isinstance(key, str) or _ENVIRONMENT_KEY.fullmatch(key) is None
            or key in REQUIRED_ENVIRONMENT_KEYS | RUNTIME_OVERRIDE_KEYS
            or not isinstance(item, str) or "\0" in item
        ):
            raise ValueError("c2rust_scenario_reopen_environment_invalid")
        environment_keys.append(key)
    cargo_prefix = (
        [] if policy.get("cargo_toolchain") is None
        else [f"+{policy['cargo_toolchain']}"]
    )
    working = _relative(value.get("working_directory"), allow_dot=True)
    base_keys = set(REQUIRED_ENVIRONMENT_KEYS)
    base_keys.update(policy.get("environment_override_keys", []))
    base_keys.update(environment_keys)
    return {
        "id": identifier,
        "purpose": f"cargo-run-scenario-{identifier}",
        "argv": [
            "cargo", *cargo_prefix, "run", "--offline", "--manifest-path",
            wrapper["manifest_path"], "--bin", wrapper["name"], "--", *argv,
        ],
        "working_directory": (
            "repository-root" if working == "." else f"repository/{working}"
        ),
        "environment_keys": sorted(base_keys),
        "timeout_seconds": timeout,
        "expected_returncodes": [expected_exit],
        "stdin_sha256": hashlib.sha256(stdin_bytes).hexdigest(),
        "stdin_size_bytes": len(stdin_bytes),
    }


def _validate_execution(
    execution: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    for key in (
        "purpose", "argv", "working_directory", "environment_keys",
        "timeout_seconds", "expected_returncodes", "stdin_sha256",
    ):
        if execution.get(key) != expected[key]:
            raise ValueError("c2rust_scenario_reopen_execution_input_mismatch")
    stdin_ref = execution.get("stdin_ref")
    if (
        not isinstance(stdin_ref, Mapping)
        or stdin_ref.get("sha256") != expected["stdin_sha256"]
        or stdin_ref.get("size_bytes") != expected["stdin_size_bytes"]
    ):
        raise ValueError("c2rust_scenario_reopen_stdin_mismatch")


def _relative(value: Any, *, allow_dot: bool) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\0" in value:
        raise ValueError("c2rust_scenario_reopen_relative_path_invalid")
    if value == ".":
        if allow_dot:
            return value
        raise ValueError("c2rust_scenario_reopen_relative_path_invalid")
    path = PurePosixPath(value)
    if (
        path.is_absolute() or ".." in path.parts or path.as_posix() != value
        or path.parts[0].startswith("~") or ":" in path.parts[0]
    ):
        raise ValueError("c2rust_scenario_reopen_relative_path_invalid")
    return value


__all__ = ["validate_execution_contract_reopen"]
