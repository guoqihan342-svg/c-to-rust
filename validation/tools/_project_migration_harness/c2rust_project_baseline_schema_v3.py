from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from .artifacts import content_sha256
from .c2rust_project_baseline_schema import (
    _reject_absolute_paths,
    _relative,
    _validate_artifact_refs,
    _validate_executions,
    _validate_tools,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_OPAQUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z", re.ASCII)
_REPORT_FIELDS = {
    "schema_version", "artifact_kind", "status", "blockers", "run_id",
    "inputs", "tools", "policy", "executions", "unit_transpiles",
    "target_plan", "target_exports", "artifact_refs", "claims", "semantic_gate",
    "translation_coverage_numerator",
}


def validate_c2rust_baseline_report_v3(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _REPORT_FIELDS:
        raise ValueError("c2rust_baseline_v3_report_fields_invalid")
    report = dict(value)
    blockers = report.get("blockers")
    if (
        report.get("schema_version") != 3
        or report.get("artifact_kind") != "c2rust-project-baseline-report"
        or report.get("status") != "blocked"
        or not _unique_strings(blockers)
        or "c2rust_target_cargo_assembly_pending" not in blockers
        or _SHA256.fullmatch(str(report.get("run_id"))) is None
        or report.get("semantic_gate") is not False
        or report.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("c2rust_baseline_v3_policy_invalid")
    _validate_inputs(report.get("inputs"))
    _validate_tools(report.get("tools"))
    _validate_policy(report.get("policy"))
    executions = _validate_executions(report.get("executions"))
    units = _validate_units(report.get("unit_transpiles"), executions)
    _validate_target_plan(report.get("target_plan"), units)
    _validate_target_exports(report.get("target_exports"), units)
    _validate_artifact_refs(report.get("artifact_refs"))
    _validate_claims(report.get("claims"), executions)
    _reject_absolute_paths(report)
    return report


def _validate_inputs(value: Any) -> None:
    fields = {
        "repository_identity_sha256", "compile_commands_path",
        "original_compile_database_ref", "build_ir_ref",
        "build_ir_semantic_sha256", "source_bindings",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_v3_inputs_invalid")
    compile_path = _relative(value.get("compile_commands_path"))
    sources = value.get("source_bindings")
    if not isinstance(sources, list) or not sources:
        raise ValueError("c2rust_baseline_v3_sources_invalid")
    paths = []
    for source in sources:
        _binding(source, "c2rust_baseline_v3_source_binding_invalid")
        paths.append(source["path"])
    if paths != sorted(set(paths)):
        raise ValueError("c2rust_baseline_v3_sources_invalid")
    _reference(value.get("original_compile_database_ref"))
    _reference(value.get("build_ir_ref"))
    semantic = value.get("build_ir_semantic_sha256")
    expected = content_sha256({
        "compile_commands_path": compile_path,
        "source_bindings": sources,
        "build_ir_semantic_sha256": semantic,
    })
    if _SHA256.fullmatch(str(semantic)) is None or value.get(
        "repository_identity_sha256"
    ) != expected:
        raise ValueError("c2rust_baseline_v3_repository_identity_invalid")


def _validate_policy(value: Any) -> None:
    fields = {
        "mode", "timeout_seconds", "minimal_environment",
        "per_unit_isolation", "fresh_unit_output",
        "overwrite_existing_scope", "cargo_executed",
        "environment_override_keys", "environment_overrides_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_v3_policy_contract_invalid")
    keys = value.get("environment_override_keys")
    if (
        value.get("mode") != "build-ir-unit-transpile"
        or type(value.get("timeout_seconds")) is not int
        or not 1 <= value["timeout_seconds"] <= 3600
        or any(value.get(key) is not True for key in (
            "minimal_environment", "per_unit_isolation", "fresh_unit_output",
        ))
        or value.get("overwrite_existing_scope") != "fresh-unit-workspace-only"
        or value.get("cargo_executed") is not False
        or not isinstance(keys, list) or keys != sorted(set(keys))
        or set(keys) - {"CARGO_HOME", "RUSTUP_HOME", "RUSTC_BOOTSTRAP"}
        or _SHA256.fullmatch(str(value.get("environment_overrides_sha256"))) is None
    ):
        raise ValueError("c2rust_baseline_v3_policy_contract_invalid")


def _validate_units(
    value: Any, executions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    fields = {
        "unit_id", "unit_key", "variant", "source", "object_target_id",
        "compile_database_ref", "generated_snapshot_ref",
        "execution_purpose", "status", "blockers",
    }
    if not isinstance(value, list) or not value:
        raise ValueError("c2rust_baseline_v3_units_invalid")
    by_purpose = {item["purpose"]: item for item in executions}
    if len(by_purpose) != len(executions):
        raise ValueError("c2rust_baseline_v3_execution_purpose_duplicate")
    keys = []
    for unit in value:
        if not isinstance(unit, Mapping) or set(unit) != fields:
            raise ValueError("c2rust_baseline_v3_unit_invalid")
        key = str(unit.get("unit_key"))
        purpose = unit.get("execution_purpose")
        variant = unit.get("variant")
        blockers = unit.get("blockers")
        execution = by_purpose.get(purpose)
        snapshot = unit.get("generated_snapshot_ref")
        if (
            _OPAQUE_ID.fullmatch(str(unit.get("unit_id"))) is None
            or _SHA256.fullmatch(key) is None
            or purpose != f"c2rust-transpile-unit-{key}"
            or not isinstance(variant, Mapping)
            or set(variant) != {"index", "count"}
            or type(variant.get("index")) is not int
            or type(variant.get("count")) is not int
            or variant["count"] < 1 or not 0 <= variant["index"] < variant["count"]
            or _OPAQUE_ID.fullmatch(str(unit.get("object_target_id"))) is None
            or not _unique_strings(blockers, allow_empty=True)
            or execution is None
        ):
            raise ValueError("c2rust_baseline_v3_unit_invalid")
        _binding(unit.get("source"), "c2rust_baseline_v3_unit_source_invalid")
        _reference(unit.get("compile_database_ref"))
        if snapshot is not None:
            _reference(snapshot)
        passed = execution["status"] == "passed" and snapshot is not None and not blockers
        if unit.get("status") != ("passed" if passed else "failed"):
            raise ValueError("c2rust_baseline_v3_unit_status_invalid")
        keys.append(key)
    if keys != sorted(set(keys)) or set(by_purpose) != {
        item["execution_purpose"] for item in value
    }:
        raise ValueError("c2rust_baseline_v3_units_invalid")
    return [dict(item) for item in value]


def _validate_target_plan(value: Any, units: list[dict[str, Any]]) -> None:
    fields = {
        "ref", "semantic_sha256", "build_ir_status",
        "build_ir_boundary_count", "terminal_target_count",
        "unit_occurrence_count", "target_owned_boundary_count",
        "covered_unit_keys",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_v3_target_plan_invalid")
    _reference(value.get("ref"))
    covered = value.get("covered_unit_keys")
    if (
        _SHA256.fullmatch(str(value.get("semantic_sha256"))) is None
        or value.get("build_ir_status") not in {"ready", "ready_with_boundaries"}
        or type(value.get("build_ir_boundary_count")) is not int
        or value["build_ir_boundary_count"] < 0
        or (
            value["build_ir_status"] == "ready"
            and value["build_ir_boundary_count"] != 0
        )
        or (
            value["build_ir_status"] == "ready_with_boundaries"
            and value["build_ir_boundary_count"] == 0
        )
        or type(value.get("terminal_target_count")) is not int
        or value["terminal_target_count"] < 1
        or type(value.get("unit_occurrence_count")) is not int
        or value["unit_occurrence_count"] < len(units)
        or type(value.get("target_owned_boundary_count")) is not int
        or value["target_owned_boundary_count"] < 0
        or not isinstance(covered, list)
        or covered != sorted({item["unit_key"] for item in units})
    ):
        raise ValueError("c2rust_baseline_v3_target_plan_invalid")


def _validate_claims(value: Any, executions: list[dict[str, Any]]) -> None:
    expected = {
        "classification": "candidate-generation-evidence-only",
        "publication_scope": "portable-summary-only",
        "referenced_artifact_visibility": "private-local",
        "host_absolute_paths_in_report": False,
        "real_process_exit_zero": all(item.get("returncode") == 0 for item in executions),
        "ai_translation": False,
        "cargo_executed": False,
        "final_semantic_gate": False,
    }
    if value != expected:
        raise ValueError("c2rust_baseline_v3_claims_invalid")


def _validate_target_exports(
    value: Any, units: list[dict[str, Any]],
) -> None:
    fields = {"status", "ref", "report_sha256", "refusal_count", "blockers"}
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ValueError("c2rust_baseline_v3_target_exports_invalid")
    status = value.get("status")
    reference = value.get("ref")
    digest = value.get("report_sha256")
    count = value.get("refusal_count")
    blockers = value.get("blockers")
    if type(count) is not int or count < 0 or not isinstance(blockers, list):
        raise ValueError("c2rust_baseline_v3_target_exports_invalid")
    if status == "unavailable":
        valid = (
            reference is None and digest is None and count == 0
            and blockers == ["c2rust_target_export_inventory_unavailable"]
            and any(
                unit["status"] != "passed"
                or unit["generated_snapshot_ref"] is None
                for unit in units
            )
        )
    else:
        _reference(reference)
        valid = (
            _SHA256.fullmatch(str(digest)) is not None
            and (
                status == "passed" and count == 0 and blockers == []
                or status == "refused" and count > 0
                and blockers == ["c2rust_target_export_conflict"]
            )
        )
    if not valid:
        raise ValueError("c2rust_baseline_v3_target_exports_invalid")


def _reference(value: Any) -> None:
    if (
        not isinstance(value, Mapping)
        or set(value) != {"path", "sha256", "size_bytes"}
        or _relative(value.get("path")) is None
        or _SHA256.fullmatch(str(value.get("sha256"))) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] < 0
    ):
        raise ValueError("c2rust_baseline_v3_reference_invalid")


def _binding(value: Any, code: str) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError(code)
    try:
        _relative(value.get("path"))
    except ValueError as error:
        raise ValueError(code) from error
    if (
        _SHA256.fullmatch(str(value.get("sha256"))) is None
        or type(value.get("size_bytes")) is not int or value["size_bytes"] < 0
    ):
        raise ValueError(code)


def _unique_strings(value: Any, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(value, list) and (allow_empty or bool(value))
        and value == list(dict.fromkeys(value))
        and all(isinstance(item, str) and item for item in value)
    )


__all__ = ["validate_c2rust_baseline_report_v3"]
