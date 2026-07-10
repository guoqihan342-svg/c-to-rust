from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .contract import (
    ReporterError,
    behavior_fields,
    mutated_outputs,
    reference_outputs,
    replay_outputs,
)
from .runtime_binding import load_runtime_provenance
from .negative_execution import run_negative_execution
from .field_add_contract import KIND as FIELD_ADD_KIND
from .field_add_reports import (
    build_negative_report as build_field_add_negative_report,
    build_report_claim as build_field_add_report_claim,
)
from .record_contract import KIND as RECORD_KIND
from .sequence_contract import KIND as SEQUENCE_KIND
from .sequence_model import mutated_observable_outputs, mutation_partition
from .source_binding import StaticContext, load_static_context


def emit_reports(
    *,
    slice_spec: Path,
    auto_evidence_dir: Path,
    output_dir: Path,
    repo_root: Path,
) -> dict[str, Path]:
    context = load_static_context(slice_spec, repo_root)
    runtime = load_runtime_provenance(context, auto_evidence_dir, output_dir)
    generated_paths = runtime["generated_rust_paths"]
    negative_execution = run_negative_execution(
        context,
        generated_paths["draft"],
        generated_paths["replay_test"],
        output_dir,
    )
    negative_artifacts = negative_execution.pop("artifacts")
    reports = build_reports(context, runtime, negative_execution)
    prefix = f"l3-{context.spec['slice_id']}"
    paths = {
        "c_oracle": output_dir / f"{prefix}-c-oracle.json",
        "rust_report": output_dir / f"{prefix}-rust-report.json",
        "diff": output_dir / f"{prefix}-diff.json",
        "negative_diff": output_dir / f"{prefix}-negative-diff.json",
    }
    write_reports_atomically(paths, reports, negative_artifacts)
    return paths


def build_reports(
    context: StaticContext,
    runtime: dict[str, Any],
    negative_execution: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fields = behavior_fields(context.contract)
    c_cases: list[dict[str, Any]] = []
    rust_cases: list[dict[str, Any]] = []
    for case in context.cases:
        expected = case["expected_outputs"]
        reference = reference_outputs(case, context.contract)
        if reference != expected:
            raise ReporterError(f"fixture case {case['id']} disagrees with the declared reference model")
        replay = replay_outputs(case, context.contract)
        if replay != expected:
            raise ReporterError(f"fixture case {case['id']} disagrees with the declared replay model")
        c_cases.append({"id": case["id"], **expected, "status": "passed"})
        rust_cases.append({"id": case["id"], **replay, "status": "passed"})

    claim = report_claim(context)
    common = {
        "schema_version": 1,
        "level": context.fixture.get("level", context.spec.get("level")),
        "target_id": context.spec["target_id"],
        "slice_id": context.spec["slice_id"],
        "source_commit": context.spec["source_commit"],
        "case_count": len(context.cases),
        "compared_fields": fields,
        "claim_boundary": claim,
    }
    negative = build_negative_report(context, common, negative_execution)
    c_oracle = {
        **common,
        "status": "passed",
        "semantic_pass": True,
        "toolchain_status": "C_ORACLE_GENERATED",
        "source_boundary": context.fixture.get("source_boundary"),
        "provenance": {
            "binding_mode": runtime["binding_mode"],
            "evidence_refs": runtime["refs"],
            "compile_execution": runtime.get("compile_execution"),
        },
        "cases": c_cases,
    }
    rust_report = {
        **common,
        "status": "passed",
        "replay_contract_kind": context.contract["kind"],
        "replay_engine": "exact_generated_rust_replay_plus_declarative_field_check",
        "generated_draft_replay_pass": True,
        "generated_draft_semantic_pass": False,
        "provenance": runtime["generated_rust_replay"],
        "cases": rust_cases,
    }
    diff = {
        **common,
        "status": "passed",
        "semantic_pass": True,
        "first_mismatch": None,
    }
    return {
        "c_oracle": c_oracle,
        "rust_report": rust_report,
        "diff": diff,
        "negative_diff": negative,
    }


def build_negative_report(
    context: StaticContext,
    common: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    if context.contract.get("kind") == FIELD_ADD_KIND:
        return build_field_add_negative_report(context, common, execution)
    if context.contract.get("kind") == SEQUENCE_KIND:
        return build_sequence_negative_report(context, common, execution)
    return_field = behavior_fields(context.contract)[0]
    detected_true = execution["partition_replay"]["comparison_true_case_ids"]
    detected_false = execution["partition_replay"]["comparison_false_case_ids"]
    declarative_true: list[str] = []
    declarative_false: list[str] = []
    mismatches: list[dict[str, Any]] = []
    for case in context.cases:
        expected = case["expected_outputs"]
        mutated = mutated_outputs(case, context.contract)
        if mutated[return_field] == expected[return_field]:
            continue
        bucket = declarative_true if expected[return_field] else declarative_false
        bucket.append(str(case["id"]))
        mismatches.append(
            {
                "case_id": case["id"],
                "field": return_field,
                "accepted_value": expected[return_field],
                "mutated_value": mutated[return_field],
            }
        )
    if detected_true != declarative_true or detected_false != declarative_false:
        raise ReporterError(
            "actual negative replay partitions do not match declarative mismatch case ids"
        )
    if not declarative_true or not declarative_false:
        raise ReporterError("negative mutation must be detected by true and false comparison partitions")
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation": "comparison operator == changed to !=",
        "detected_case_ids": [*detected_true, *detected_false],
        "partition_detection": {
            "comparison_true_case_ids": detected_true,
            "comparison_false_case_ids": detected_false,
        },
        "actual_mutation_execution": execution,
        "first_mismatch": mismatches[0],
        "mismatches": mismatches,
    }


def build_sequence_negative_report(
    context: StaticContext,
    common: dict[str, Any],
    execution: dict[str, Any],
) -> dict[str, Any]:
    actual_runs = execution["partition_replay"]["case_runs"]
    detected_ids = [str(item["case_id"]) for item in actual_runs]
    expected_ids = [str(case["id"]) for case in context.cases]
    if detected_ids != expected_ids:
        raise ReporterError("actual sequence negative replay case ids drifted")
    mismatches: list[dict[str, Any]] = []
    for case in context.cases:
        partition = mutation_partition(case, context.contract)
        if partition == "sequence_exhaustion":
            mismatches.append(
                {
                    "case_id": case["id"],
                    "field": "scripted_return_sequence",
                    "accepted_value": "sentinel_reached",
                    "mutated_value": "sequence_exhausted",
                }
            )
            continue
        mutated = mutated_observable_outputs(case, context.contract)
        if mutated is None:
            raise ReporterError("sequence mutation model unexpectedly exhausted")
        for field in behavior_fields(context.contract):
            if mutated[field] != case["expected_outputs"][field]:
                mismatches.append(
                    {
                        "case_id": case["id"],
                        "field": field,
                        "accepted_value": case["expected_outputs"][field],
                        "mutated_value": mutated[field],
                    }
                )
    if not mismatches:
        raise ReporterError("sequence comparison mutation produced no declared mismatch")
    observable_fields = set(behavior_fields(context.contract))
    first_observable_mismatch = next(
        (item for item in mismatches if item.get("field") in observable_fields),
        mismatches[0],
    )
    partition = execution["partition_replay"]
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation": "loop comparison operator != changed to ==",
        "detected_case_ids": detected_ids,
        "partition_detection": {
            "sequence_exhaustion_case_ids": partition["sequence_exhaustion_case_ids"],
            "observable_mismatch_case_ids": partition["observable_mismatch_case_ids"],
        },
        "actual_mutation_execution": execution,
        "first_mismatch": first_observable_mismatch,
        "mismatches": mismatches,
    }


def report_claim(context: StaticContext) -> dict[str, Any]:
    if context.contract.get("kind") == FIELD_ADD_KIND:
        return build_field_add_report_claim(context)
    external_name = context.contract["external_callee"]["name"]
    if context.contract.get("kind") == SEQUENCE_KIND:
        verified_behavior = (
            "Fixture-created records cross the declared entry boundary; a finite u32 sequence drives "
            "a do-while tail, mixed record-reference and scalar-field arguments are traced per call, "
            "and the declared mutable state stops at the explicit sentinel within the call bound."
        )
    elif context.contract.get("kind") == RECORD_KIND:
        verified_behavior = (
            "Fixture-created records are passed through the declared entry boundary; selected "
            "u32 fields observed by one scripted external call are recorded, its u32 return is "
            "assigned to the declared nested state field, and that field is compared with UINT32_MAX."
        )
    else:
        verified_behavior = (
            "A fixture-scripted u32 external return is assigned to the declared output and compared "
            "with UINT32_MAX; one call and its declared arguments are observed."
        )
    return {
        "scope": "source_fragment_only",
        "whole_function_semantics_verified": False,
        "external_callee_semantics_verified": False,
        "verified_behavior": verified_behavior,
        "external_callee": external_name,
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }


def write_reports_atomically(
    paths: dict[str, Path],
    reports: dict[str, dict[str, Any]],
    artifacts: dict[Path, bytes],
) -> None:
    if set(paths) != set(reports):
        raise ReporterError("report path set does not match generated report set")
    output_dir = next(iter(paths.values())).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    temporary: list[tuple[Path, Path]] = []
    try:
        for path, content in artifacts.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temp.write_bytes(content)
            temporary.append((temp, path))
        for name, path in paths.items():
            temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            temp.write_bytes((json.dumps(reports[name], indent=2) + "\n").encode("utf-8"))
            temporary.append((temp, path))
        for temp, path in temporary:
            os.replace(temp, path)
    finally:
        for temp, _ in temporary:
            temp.unlink(missing_ok=True)
