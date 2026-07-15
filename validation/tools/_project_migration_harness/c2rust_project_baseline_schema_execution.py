from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
import re
from typing import Any


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def validate_execution_contract(value: Any) -> None:
    if value is None:
        return
    fields = {
        "status", "path", "source_ref", "normalized_ref",
        "semantic_sha256", "wrapper_count", "scenario_count",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_execution_contract_invalid")
    _relative(value.get("path"))
    _validate_reference(value.get("source_ref"))
    if value.get("status") == "source-bound":
        if any(value.get(key) is not None for key in (
            "normalized_ref", "semantic_sha256", "wrapper_count",
            "scenario_count",
        )):
            raise ValueError("c2rust_baseline_execution_contract_invalid")
        return
    normalized = value.get("normalized_ref")
    wrapper_count = value.get("wrapper_count")
    scenario_count = value.get("scenario_count")
    if value.get("status") != "validated":
        raise ValueError("c2rust_baseline_execution_contract_invalid")
    _validate_reference(normalized)
    if (
        value.get("semantic_sha256") != normalized.get("sha256")
        or type(wrapper_count) is not int or wrapper_count <= 0
        or type(scenario_count) is not int or scenario_count < 0
    ):
        raise ValueError("c2rust_baseline_execution_contract_invalid")


def validate_execution_plan(
    value: Any, wrappers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if value is None:
        if wrappers:
            raise ValueError("c2rust_baseline_execution_plan_missing")
        return None
    fields = {
        "mode", "contract_sha256", "wrapper_count", "scenario_count",
        "compile_only_wrapper_count", "expected_run_purposes",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_execution_plan_invalid")
    mode = value.get("mode")
    wrapper_count = value.get("wrapper_count")
    scenario_count = value.get("scenario_count")
    compile_only = value.get("compile_only_wrapper_count")
    purposes = value.get("expected_run_purposes")
    if (
        mode not in {"legacy-all-wrappers", "declared-scenarios"}
        or type(wrapper_count) is not int or wrapper_count != len(wrappers)
        or type(scenario_count) is not int or scenario_count < 0
        or type(compile_only) is not int or not 0 <= compile_only <= wrapper_count
        or not isinstance(purposes, list)
        or purposes != list(dict.fromkeys(purposes))
        or any(
            not isinstance(item, str)
            or not item.startswith("cargo-run-")
            for item in purposes
        )
    ):
        raise ValueError("c2rust_baseline_execution_plan_invalid")
    if mode == "legacy-all-wrappers":
        if (
            value.get("contract_sha256") is not None
            or scenario_count != 0 or compile_only != 0
            or len(purposes) != wrapper_count
        ):
            raise ValueError("c2rust_baseline_execution_plan_invalid")
    elif (
        _SHA256.fullmatch(str(value.get("contract_sha256"))) is None
        or len(purposes) != scenario_count
    ):
        raise ValueError("c2rust_baseline_execution_plan_invalid")
    return dict(value)


def validate_execution_mode_binding(
    execution_contract: Any, policy: Any, execution_plan: Any,
) -> None:
    if not isinstance(policy, Mapping):
        raise ValueError("c2rust_baseline_execution_mode_binding_invalid")
    mode = policy.get("wrapper_execution_policy")
    if mode == "legacy-all-wrappers":
        if execution_contract is not None or (
            execution_plan is not None
            and execution_plan.get("mode") != "legacy-all-wrappers"
        ):
            raise ValueError("c2rust_baseline_execution_mode_binding_invalid")
        return
    if mode != "declared-scenarios" or not isinstance(
        execution_contract, Mapping,
    ):
        raise ValueError("c2rust_baseline_execution_mode_binding_invalid")
    if execution_plan is None:
        return
    if (
        execution_contract.get("status") != "validated"
        or execution_plan.get("mode") != "declared-scenarios"
        or execution_plan.get("contract_sha256")
        != execution_contract.get("semantic_sha256")
        or execution_plan.get("wrapper_count")
        != execution_contract.get("wrapper_count")
        or execution_plan.get("scenario_count")
        != execution_contract.get("scenario_count")
    ):
        raise ValueError("c2rust_baseline_execution_mode_binding_invalid")


def _validate_reference(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256", "size_bytes"}
        or _relative(value.get("path")) is None
        or _SHA256.fullmatch(str(value.get("sha256"))) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] < 0
    ):
        raise ValueError("c2rust_baseline_artifact_reference_invalid")


def _relative(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("c2rust_baseline_relative_path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError("c2rust_baseline_relative_path_invalid")
    return value


__all__ = [
    "validate_execution_contract", "validate_execution_mode_binding",
    "validate_execution_plan",
]
