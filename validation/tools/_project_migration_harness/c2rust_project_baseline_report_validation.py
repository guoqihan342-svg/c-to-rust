from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .c2rust_project_baseline_schema import validate_c2rust_baseline_report
from .c2rust_project_baseline_schema_v3 import validate_c2rust_baseline_report_v3


def validate_baseline_report(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("c2rust_baseline_report_invalid")
    if value.get("schema_version") == 2:
        return validate_c2rust_baseline_report(value)
    if value.get("schema_version") == 3:
        return validate_c2rust_baseline_report_v3(value)
    raise ValueError("c2rust_baseline_report_version_invalid")


def required_report_references(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    inputs = report["inputs"]
    result = [inputs["original_compile_database_ref"]]
    if report.get("schema_version") == 2:
        result.append(inputs["normalized_compile_database_ref"])
        contract = inputs.get("execution_contract")
        if isinstance(contract, Mapping):
            result.append(contract["source_ref"])
            if contract.get("normalized_ref") is not None:
                result.append(contract["normalized_ref"])
    else:
        result.extend((inputs["build_ir_ref"], report["target_plan"]["ref"]))
        target_exports = report["target_exports"]
        if target_exports["ref"] is not None:
            result.append(target_exports["ref"])
        for unit in report["unit_transpiles"]:
            result.append(unit["compile_database_ref"])
    for execution in report.get("executions", []):
        result.extend((
            execution["stdout_ref"], execution["stderr_ref"],
            execution["stdin_ref"],
        ))
    result.extend(generated_snapshot_references(report))
    return result


def generated_snapshot_references(
    report: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    if report.get("schema_version") == 2:
        snapshot = report.get("generated", {}).get("snapshot_ref")
        return [] if snapshot is None else [snapshot]
    return [
        unit["generated_snapshot_ref"]
        for unit in report.get("unit_transpiles", [])
        if unit.get("generated_snapshot_ref") is not None
    ]


__all__ = [
    "generated_snapshot_references", "required_report_references",
    "validate_baseline_report",
]
