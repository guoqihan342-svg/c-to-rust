#!/usr/bin/env python3
"""Validate project-agnostic full C-to-Rust conversion acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Full conversion acceptance report JSON.")
    parser.add_argument("--report", type=Path, help="Optional validator summary JSON path.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    validated = validate_acceptance_report(payload)
    text = json.dumps(validated, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def validate_acceptance_report(report: dict[str, Any]) -> dict[str, Any]:
    require(isinstance(report, dict), "acceptance report must be a JSON object")
    require(report.get("schema_version") == 1, "schema_version must be 1")
    require(report.get("status") == "passed", "full project acceptance status must be passed")
    require(
        report.get("claim_scope") == "project_agnostic_full_conversion",
        "claim_scope must be project_agnostic_full_conversion",
    )

    input_project = require_object(report, "input_project")
    source_files = require_list(report, "input_project.source_files")
    compile_commands = require_list(report, "input_project.compile_commands")
    require(source_files, "input_project.source_files must not be empty")
    require(compile_commands, "input_project.compile_commands must not be empty")
    require(
        input_project.get("generated_from_input_project") is True,
        "input_project.generated_from_input_project must be true",
    )

    discovery = require_object(report, "project_discovery")
    require(discovery.get("status") == "passed", "project_discovery.status must be passed")
    discovered_files = require_positive_int(report, "project_discovery.source_files_total")
    discovered_functions = require_positive_int(report, "project_discovery.functions_total")
    require(
        discovered_files == len(source_files),
        "project_discovery.source_files_total must match input_project.source_files length",
    )

    hardcoded = require_object(report, "hardcoded_target_references")
    require(hardcoded.get("status") == "passed", "hardcoded_target_references.status must be passed")
    occurrences = hardcoded.get("occurrences")
    require(occurrences == [], "hardcoded_target_references.occurrences must be empty")

    coverage = require_object(report, "translation_coverage")
    require(coverage.get("status") == "passed", "translation_coverage.status must be passed")
    source_functions = require_positive_int(report, "translation_coverage.source_functions_total")
    translated_functions = require_positive_int(report, "translation_coverage.translated_functions_total")
    accepted_functions = require_positive_int(report, "translation_coverage.accepted_functions_total")
    require(
        source_functions == discovered_functions,
        "translation_coverage.source_functions_total must match project_discovery.functions_total",
    )
    require(
        translated_functions == source_functions and accepted_functions == source_functions,
        "full function coverage requires translated_functions_total and accepted_functions_total to equal source_functions_total",
    )
    require(coverage.get("blocked") == [], "translation_coverage.blocked must be empty")
    require(coverage.get("untranslated") == [], "translation_coverage.untranslated must be empty")

    require_status(report, "rust_build")
    oracle = require_object(report, "oracle")
    require(oracle.get("status") == "passed", "oracle.status must be passed")
    require(
        oracle.get("producer_generated_from_input_project") is True,
        "oracle.producer_generated_from_input_project must be true",
    )
    require(oracle.get("project_specific_template") is False, "oracle.project_specific_template must be false")

    diff = require_object(report, "diff")
    require(diff.get("status") == "passed", "diff.status must be passed")
    require(diff.get("first_mismatch") is None, "diff.first_mismatch must be null")
    require(diff.get("accepted_differences") == [], "diff.accepted_differences must be empty")

    negative_diff = require_object(report, "negative_diff")
    require(negative_diff.get("status") == "passed", "negative_diff.status must be passed")
    require(negative_diff.get("detected") is True, "negative_diff.detected must be true")

    unsafe_ledger = require_object(report, "unsafe_ledger")
    require(unsafe_ledger.get("status") == "passed", "unsafe_ledger.status must be passed")
    unsafe_reduction = require_object(report, "unsafe_ledger.unsafe_reduction")
    require(unsafe_reduction.get("status") == "measured", "unsafe_ledger.unsafe_reduction.status must be measured")

    return {
        "schema_version": 1,
        "status": "passed",
        "claim_scope": "project_agnostic_full_conversion",
        "project_id": str(input_project.get("project_id", "")),
        "source_files_total": discovered_files,
        "source_functions_total": source_functions,
        "accepted_functions_total": accepted_functions,
    }


def require_status(report: dict[str, Any], section: str) -> None:
    payload = require_object(report, section)
    require(payload.get("status") == "passed", f"{section}.status must be passed")


def require_object(report: dict[str, Any], field: str) -> dict[str, Any]:
    value: Any = report
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SystemExit(f"{field} is required")
        value = value[part]
    require(isinstance(value, dict), f"{field} must be an object")
    return value


def require_list(report: dict[str, Any], field: str) -> list[Any]:
    value: Any = report
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SystemExit(f"{field} is required")
        value = value[part]
    require(isinstance(value, list), f"{field} must be a list")
    return value


def require_positive_int(report: dict[str, Any], field: str) -> int:
    value: Any = report
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            raise SystemExit(f"{field} is required")
        value = value[part]
    require(isinstance(value, int) and value > 0, f"{field} must be a positive integer")
    return int(value)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


if __name__ == "__main__":
    raise SystemExit(main())
