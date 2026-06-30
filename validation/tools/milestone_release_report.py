#!/usr/bin/env python3
"""Build milestone-facing release metrics without expanding semantic claims."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import translator_coverage_matrix
from validation.tools import validate_competition_run_summary


REFUSED_STATUSES = {"refused"}
BLOCKED_STATUSES = {"blocked"}
GENERATED_CANDIDATE_STATUSES = {"candidate", "generated", "generated_candidate", "compiled"}
SEMANTIC_PASS_STATUSES = {"accepted", "passed", "semantic_pass"}
SEMANTIC_ROUTE_STATUSES = {"accepted", "passed", "semantic_pass"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--coverage-report", type=Path)
    parser.add_argument("--competition-summary", type=Path, action="append", default=[])
    parser.add_argument("--batch-profile-report", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    report = build_report(
        repo_root,
        coverage_report_path=args.coverage_report,
        competition_summary_paths=args.competition_summary,
        batch_profile_report_paths=args.batch_profile_report,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def build_report(
    repo_root: Path,
    *,
    coverage_report_path: Path | None = None,
    competition_summary_paths: list[Path] | None = None,
    batch_profile_report_paths: list[Path] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    coverage_report = load_coverage_report(repo_root, coverage_report_path=coverage_report_path)
    workflow_metrics_inputs = load_competition_workflow_metrics(
        repo_root,
        competition_summary_paths=competition_summary_paths or [],
    )
    s2_workflow_metrics = summarize_s2_workflow_metrics(workflow_metrics_inputs)
    before_after_exhibit_inputs = load_bound_before_after_exhibits(
        repo_root,
        batch_profile_report_paths=batch_profile_report_paths or [],
    )
    before_after_exhibits = summarize_before_after_exhibits(before_after_exhibit_inputs)

    require(coverage_report.get("schema_version") == 1, "coverage report schema_version must be 1")
    require(coverage_report.get("status") == "passed", "coverage report status must be passed")
    ledger = coverage_report.get("capability_delta_ledger")
    require(isinstance(ledger, dict), "coverage report capability_delta_ledger is required")
    require(ledger.get("schema_version") == 1, "capability_delta_ledger schema_version must be 1")
    require(ledger.get("status") == "recorded", "capability_delta_ledger status must be recorded")

    legacy_semantic_pass_count = require_int(ledger, "semantic_pass_count")
    translator_generated_semantic_pass_count = optional_int(
        ledger,
        "translator_generated_semantic_pass_count",
        legacy_semantic_pass_count,
    )
    accepted_evidence_semantic_pass_count = optional_int(ledger, "accepted_evidence_semantic_pass_count", 0)
    ledger_count = require_int(ledger, "ledger_count")
    delta_count = require_int(ledger, "delta_count")
    generated_status = require_dict(ledger, "generated_candidate_status")
    route_levels = require_dict(ledger, "route_levels")
    route_statuses = require_dict(ledger, "route_statuses")
    ledgers = ledger.get("ledgers", [])
    require(isinstance(ledgers, list), "capability_delta_ledger ledgers must be a list")
    if translator_generated_semantic_pass_count > 0 and ledgers and all(is_l4_refused(item) for item in ledgers):
        raise SystemExit("L4/refused ledger entries cannot be the translation coverage numerator")
    candidate_classification = classify_candidate_statuses(
        generated_status,
        route_levels=route_levels,
        route_statuses=route_statuses,
        semantic_pass_count=translator_generated_semantic_pass_count,
    )

    blockers = []
    if translator_generated_semantic_pass_count == 0:
        blockers.append("no_translator_generated_semantic_pass")
    if translator_generated_semantic_pass_count < 3:
        blockers.append("translator_generated_semantic_pass_below_p0_minimum")
    blockers.append("external_review_not_recorded")

    report_status = "release_candidate" if not blockers else "internal_preview"
    return {
        "schema_version": 1,
        "status": report_status,
        "report_kind": "milestone-release-metrics",
        "inputs": {
            "translator_coverage_matrix": {
                "path": coverage_report.get("matrix", {}).get("path", "unknown"),
                "status": coverage_report.get("status"),
                "capability_count": coverage_report.get("capability_count"),
                "claim_boundary": coverage_report.get("claim_boundary"),
            }
        },
        "metrics": {
            "translation_coverage_numerator": translator_generated_semantic_pass_count,
            "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
            "s2_workflow_metrics": s2_workflow_metrics,
            "before_after_exhibits": before_after_exhibits,
            "tracked_capability_delta_ledgers": ledger_count,
            "tracked_capability_delta_count": delta_count,
            "native_build_catalogue_included_in_translation_coverage": False,
            "handwritten_reference_included_in_translation_coverage": False,
            "candidate_classification": candidate_classification,
            "capability_delta_ledger": {
                "ledger_count": ledger_count,
                "delta_count": delta_count,
                "translator_generated_semantic_pass_count": translator_generated_semantic_pass_count,
                "semantic_pass_count": legacy_semantic_pass_count,
                "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
                "generated_candidate_status": generated_status,
                "route_levels": route_levels,
                "route_statuses": route_statuses,
                "by_construct": ledger.get("by_construct", {}),
                "blocked_callee_count": ledger.get("blocked_callee_count", 0),
            },
        },
        "readiness": {
            "status": report_status,
            "blockers": blockers,
            "minimum_p0_translator_generated_semantic_pass_count": 3,
        },
        "release_note_inputs": {
            "capability_delta_ledger": ledger,
            "s2_workflow_metrics": s2_workflow_metrics,
            "before_after_exhibits": before_after_exhibits,
            "coverage_claim_boundary": coverage_report.get("claim_boundary"),
            "must_not_claim": [
                "native build catalogue as translated Rust coverage",
                "handwritten flashDB_rust as translator-generated output",
                "L4/refused capability evidence as semantic acceptance",
            ],
            "known_non_goals": [
                "full C99/C11 support",
                "project-level FlashDB semantic equivalence",
                "competition-exact clang lane without exact-host evidence",
            ],
        },
        "claim_boundary": "Milestone release metrics are not semantic acceptance evidence; capability_delta_ledger entries and S2 workflow metrics are not semantic acceptance evidence unless the shared validation gates prove semantic_pass for translator-generated Rust drafts.",
    }


def classify_candidate_statuses(
    generated_status: dict[str, Any],
    *,
    route_levels: dict[str, Any],
    route_statuses: dict[str, Any],
    semantic_pass_count: int,
) -> dict[str, Any]:
    normalized = {
        str(key): require_nonnegative_int(value, f"generated_candidate_status.{key}")
        for key, value in generated_status.items()
    }
    refused_count = sum(normalized.get(status, 0) for status in REFUSED_STATUSES)
    blocked_count = sum(normalized.get(status, 0) for status in BLOCKED_STATUSES)
    generated_count = sum(normalized.get(status, 0) for status in GENERATED_CANDIDATE_STATUSES)
    semantic_status_count = sum(normalized.get(status, 0) for status in SEMANTIC_PASS_STATUSES)
    require(
        semantic_pass_count <= semantic_status_count,
        "semantic_pass_count must be backed by semantic-pass generated_candidate_status entries",
    )
    if semantic_pass_count > 0:
        route_level_l3 = require_nonnegative_int(route_levels.get("L3", 0), "route_levels.L3")
        semantic_route_count = sum(
            require_nonnegative_int(route_statuses.get(status, 0), f"route_statuses.{status}")
            for status in SEMANTIC_ROUTE_STATUSES
        )
        require(route_level_l3 >= semantic_pass_count, "semantic_pass_count must be backed by L3 route evidence")
        require(
            semantic_route_count >= semantic_pass_count,
            "semantic_pass_count must be backed by accepted/passed route status",
        )
    return {
        "refused_delta_count": refused_count,
        "blocked_delta_count": blocked_count,
        "generated_candidate_delta_count": generated_count,
        "semantic_pass_delta_count": semantic_pass_count,
        "semantic_pass_status_count": semantic_status_count,
        "unclassified_delta_count": sum(normalized.values())
        - refused_count
        - blocked_count
        - generated_count
        - semantic_status_count,
        "status_counts": normalized,
    }


def load_coverage_report(repo_root: Path, *, coverage_report_path: Path | None) -> dict[str, Any]:
    if coverage_report_path is None:
        return translator_coverage_matrix.build_report(repo_root)
    path = coverage_report_path if coverage_report_path.is_absolute() else repo_root / coverage_report_path
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_competition_workflow_metrics(
    repo_root: Path,
    *,
    competition_summary_paths: list[Path],
) -> list[dict[str, Any]]:
    metrics = []
    for summary_path in competition_summary_paths:
        summary_abs = summary_path if summary_path.is_absolute() else repo_root / summary_path
        summary_abs = summary_abs.resolve()
        require(summary_abs.exists(), f"competition summary does not exist: {summary_path}")
        validate_competition_run_summary.validate_summary(summary_abs, repo_root=repo_root)
        summary = json.loads(summary_abs.read_text(encoding="utf-8-sig"))
        require(isinstance(summary, dict), f"competition summary must be an object: {summary_path}")
        binding = summary.get("workflow_metrics")
        require(isinstance(binding, dict), f"competition summary workflow_metrics binding is required: {summary_path}")
        metrics_ref = binding.get("path")
        expected_sha = binding.get("sha256")
        require(
            isinstance(metrics_ref, str) and isinstance(expected_sha, str),
            f"competition summary workflow_metrics.path and workflow_metrics.sha256 are required: {summary_path}",
        )
        metrics_path = resolve_bound_summary_artifact(metrics_ref, summary_path=summary_abs, repo_root=repo_root)
        require(metrics_path is not None, f"competition summary workflow_metrics.path does not exist: {metrics_ref}")
        require(
            sha256_file(metrics_path) == expected_sha,
            f"competition summary workflow_metrics.sha256 does not match artifact: {summary_path}",
        )
        payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        require(isinstance(payload, dict), f"workflow metrics artifact must be an object: {metrics_ref}")
        if isinstance(summary.get("run_id"), str):
            require(
                payload.get("run_id") == summary["run_id"],
                f"workflow metrics run_id must match competition summary: {summary_path}",
            )
        if isinstance(summary.get("proof_class"), str):
            require(
                payload.get("proof_class") == summary["proof_class"],
                f"workflow metrics proof_class must match competition summary: {summary_path}",
            )
        metrics.append(
            {
                "summary_path": rel(repo_root, summary_abs),
                "metrics_path": rel(repo_root, metrics_path),
                "metrics_sha256": expected_sha,
                "metrics": payload,
            }
        )
    return metrics


def load_bound_before_after_exhibits(
    repo_root: Path,
    *,
    batch_profile_report_paths: list[Path],
) -> list[dict[str, Any]]:
    exhibits = []
    for report_path in batch_profile_report_paths:
        report_abs = report_path if report_path.is_absolute() else repo_root / report_path
        report_abs = report_abs.resolve()
        require(report_abs.exists(), f"batch profile report does not exist: {report_path}")
        batch_report = json.loads(report_abs.read_text(encoding="utf-8-sig"))
        require(isinstance(batch_report, dict), f"batch profile report must be an object: {report_path}")
        binding = batch_report.get("before_after_exhibit_report")
        require(
            isinstance(binding, dict),
            f"batch profile report before_after_exhibit_report binding is required: {report_path}",
        )
        exhibit_ref = binding.get("path")
        expected_sha = binding.get("sha256")
        require(
            isinstance(exhibit_ref, str) and isinstance(expected_sha, str),
            f"before_after_exhibit_report.path and before_after_exhibit_report.sha256 are required: {report_path}",
        )
        exhibit_path = resolve_bound_summary_artifact(exhibit_ref, summary_path=report_abs, repo_root=repo_root)
        require(exhibit_path is not None, f"before_after_exhibit_report.path does not exist: {exhibit_ref}")
        require(
            sha256_file(exhibit_path) == expected_sha,
            f"before_after_exhibit_report.sha256 does not match artifact: {report_path}",
        )
        exhibit = json.loads(exhibit_path.read_text(encoding="utf-8-sig"))
        require(isinstance(exhibit, dict), f"before-after exhibit artifact must be an object: {exhibit_ref}")
        require(exhibit.get("report_kind") == "before-after-exhibit", f"unexpected before-after report_kind: {exhibit_ref}")
        require(isinstance(exhibit.get("status"), str), f"before-after exhibit status is required: {exhibit_ref}")
        if isinstance(batch_report.get("run_id"), str) and isinstance(exhibit.get("run_id"), str):
            require(
                batch_report["run_id"] == exhibit["run_id"],
                f"before-after exhibit run_id must match batch profile report: {report_path}",
            )
        validate_before_after_exhibit_inputs(repo_root, exhibit=exhibit, exhibit_path=exhibit_path)
        exhibits.append(
            {
                "batch_profile_report_path": rel(repo_root, report_abs),
                "before_after_exhibit_path": rel(repo_root, exhibit_path),
                "before_after_exhibit_sha256": expected_sha,
                "binding": binding,
                "exhibit": exhibit,
            }
        )
    return exhibits


def validate_before_after_exhibit_inputs(repo_root: Path, *, exhibit: dict[str, Any], exhibit_path: Path) -> None:
    inputs = require_dict(exhibit, "inputs")
    for field in ("competition_summary", "workflow_metrics"):
        binding = require_dict(inputs, field)
        artifact_ref = binding.get("path")
        expected_sha = binding.get("sha256")
        require(
            isinstance(artifact_ref, str) and isinstance(expected_sha, str),
            f"before-after exhibit inputs.{field}.path and sha256 are required: {exhibit_path}",
        )
        artifact_path = resolve_bound_summary_artifact(artifact_ref, summary_path=exhibit_path, repo_root=repo_root)
        require(artifact_path is not None, f"before-after exhibit inputs.{field}.path does not exist: {artifact_ref}")
        require(
            sha256_file(artifact_path) == expected_sha,
            f"before-after exhibit inputs.{field}.sha256 does not match artifact: {exhibit_path}",
        )
        if field == "competition_summary":
            validate_competition_run_summary.validate_summary(artifact_path, repo_root=repo_root)


def summarize_s2_workflow_metrics(workflow_metrics_inputs: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = [item["metrics"] for item in workflow_metrics_inputs if isinstance(item.get("metrics"), dict)]
    units_total = sum(nonnegative_int(metric.get("units_total")) for metric in metrics)
    units_converged = sum(nonnegative_int(metric.get("units_converged")) for metric in metrics)
    units_baseline_only = sum(nonnegative_int(metric.get("units_baseline_only")) for metric in metrics)
    fail_closed_count = sum(nonnegative_int(metric.get("fail_closed_count")) for metric in metrics)
    human_interventions = sum(nonnegative_int(metric.get("human_interventions")) for metric in metrics)
    llm_calls = sum(nonnegative_int(metric.get("llm_calls")) for metric in metrics)
    wall_clock_seconds = sum(nonnegative_int(metric.get("wall_clock_seconds")) for metric in metrics)
    avg_repair_rounds = weighted_metric(metrics, "avg_repair_rounds", units_total)
    auto_recovery_rate = weighted_metric(metrics, "auto_recovery_rate", units_total)
    per_unit_statuses = [
        unit
        for metric in metrics
        for unit in list_or_empty(metric.get("per_unit_statuses"))
        if isinstance(unit, dict)
    ]
    root_cause_counts: dict[str, int] = {}
    for metric in metrics:
        for key, value in require_count_mapping(metric.get("root_cause_counts")).items():
            root_cause_counts[key] = root_cause_counts.get(key, 0) + value
    repair_history_unit_count = sum(1 for unit in per_unit_statuses if isinstance(unit.get("repair_history"), dict))
    auto_recovered_units = sum(1 for unit in per_unit_statuses if unit.get("auto_recovered") is True)
    measured_unsafe_run_count = sum(
        1
        for metric in metrics
        if isinstance(metric.get("unsafe_reduction"), dict)
        and metric["unsafe_reduction"].get("status") == "measured"
    )
    return {
        "run_count": len(metrics),
        "input_summaries": [
            {
                "summary_path": item["summary_path"],
                "workflow_metrics_path": item["metrics_path"],
                "workflow_metrics_sha256": item["metrics_sha256"],
            }
            for item in workflow_metrics_inputs
        ],
        "units_total": units_total,
        "units_converged": units_converged,
        "units_baseline_only": units_baseline_only,
        "unsafe_reduction": summarize_unsafe_reduction(metrics),
        "translation_before_after": summarize_translation_before_after(metrics),
        "measured_unsafe_reduction_run_count": measured_unsafe_run_count,
        "avg_repair_rounds": avg_repair_rounds,
        "auto_recovery_rate": auto_recovery_rate,
        "human_interventions": human_interventions,
        "fail_closed_count": fail_closed_count,
        "root_cause_counts": root_cause_counts,
        "wall_clock_seconds": wall_clock_seconds,
        "llm_calls": llm_calls,
        "repair_history_unit_count": repair_history_unit_count,
        "auto_recovered_units": auto_recovered_units,
        "claim_boundary": (
            "S2 workflow metrics summarize bound competition-run workflow metrics only; they do not prove "
            "semantic acceptance or unsafe reduction unless the underlying metrics already mark unsafe_reduction "
            "as measured with baseline/current counts; before/after bindings are artifact references, not semantic "
            "acceptance by themselves."
        ),
    }


def summarize_before_after_exhibits(exhibit_inputs: list[dict[str, Any]]) -> dict[str, Any]:
    unit_count = 0
    measured_unsafe_unit_count = 0
    accepted_patch_unit_count = 0
    passed_report_count = 0
    input_reports = []
    for item in exhibit_inputs:
        exhibit = item["exhibit"]
        translation_before_after = (
            exhibit.get("translation_before_after")
            if isinstance(exhibit.get("translation_before_after"), dict)
            else {}
        )
        unit_count += nonnegative_int(translation_before_after.get("unit_count"))
        measured_unsafe_unit_count += nonnegative_int(translation_before_after.get("measured_unsafe_unit_count"))
        accepted_patch_unit_count += nonnegative_int(translation_before_after.get("accepted_patch_unit_count"))
        status = str(exhibit.get("status", "unknown"))
        if status == "passed":
            passed_report_count += 1
        stage_contracts = exhibit.get("stage_contracts") if isinstance(exhibit.get("stage_contracts"), dict) else {}
        input_reports.append(
            {
                "batch_profile_report_path": item["batch_profile_report_path"],
                "before_after_exhibit_path": item["before_after_exhibit_path"],
                "before_after_exhibit_sha256": item["before_after_exhibit_sha256"],
                "status": status,
                "unit_count": nonnegative_int(translation_before_after.get("unit_count")),
                "measured_unsafe_unit_count": nonnegative_int(
                    translation_before_after.get("measured_unsafe_unit_count")
                ),
                "accepted_patch_unit_count": nonnegative_int(
                    translation_before_after.get("accepted_patch_unit_count")
                ),
                "stage_contract_statuses": {
                    str(stage): str(contract.get("status", "unknown"))
                    for stage, contract in stage_contracts.items()
                    if isinstance(contract, dict)
                },
            }
        )
    return {
        "status": "bound" if unit_count > 0 else "not_provided",
        "report_count": len(exhibit_inputs),
        "passed_report_count": passed_report_count,
        "unit_count": unit_count,
        "measured_unsafe_unit_count": measured_unsafe_unit_count,
        "accepted_patch_unit_count": accepted_patch_unit_count,
        "input_reports": input_reports,
        "claim_boundary": (
            "Before/after exhibits are judge-facing harness artifacts. They bind baseline/final/patch/oracle "
            "references and unsafe deltas, but do not expand the translation coverage numerator."
        ),
    }


def summarize_translation_before_after(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    unit_count = 0
    measured_unsafe_unit_count = 0
    accepted_patch_unit_count = 0
    input_run_count = 0
    for metric in metrics:
        before_after = metric.get("translation_before_after")
        if not isinstance(before_after, dict):
            continue
        count = nonnegative_int(before_after.get("unit_count"))
        unit_count += count
        measured_unsafe_unit_count += nonnegative_int(before_after.get("measured_unsafe_unit_count"))
        accepted_patch_unit_count += nonnegative_int(before_after.get("accepted_patch_unit_count"))
        if count > 0:
            input_run_count += 1
    return {
        "status": "bound" if unit_count > 0 else "not_provided",
        "input_run_count": input_run_count,
        "unit_count": unit_count,
        "measured_unsafe_unit_count": measured_unsafe_unit_count,
        "accepted_patch_unit_count": accepted_patch_unit_count,
    }


def summarize_unsafe_reduction(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics:
        return {
            "status": "not_measured",
            "baseline_total_unsafe": None,
            "current_total_unsafe": None,
            "reduced_by": None,
            "ratio": None,
        }
    baseline_total = 0
    current_total = 0
    for metric in metrics:
        unsafe_reduction = metric.get("unsafe_reduction")
        if not isinstance(unsafe_reduction, dict) or unsafe_reduction.get("status") != "measured":
            return {
                "status": "not_measured",
                "baseline_total_unsafe": None,
                "current_total_unsafe": None,
                "reduced_by": None,
                "ratio": None,
            }
        baseline = nonnegative_count(unsafe_reduction.get("baseline_total_unsafe"))
        current = nonnegative_count(unsafe_reduction.get("current_total_unsafe"))
        reduced_by = nonnegative_count(unsafe_reduction.get("reduced_by"))
        if baseline is None or current is None or reduced_by is None or baseline - current != reduced_by:
            raise SystemExit("measured unsafe_reduction requires consistent baseline/current/reduced_by counts")
        baseline_total += baseline
        current_total += current
    return {
        "status": "measured",
        "baseline_total_unsafe": baseline_total,
        "current_total_unsafe": current_total,
        "reduced_by": baseline_total - current_total,
        "ratio": 0.0 if baseline_total == 0 else current_total / baseline_total,
    }


def resolve_bound_summary_artifact(value: str, *, summary_path: Path, repo_root: Path) -> Path | None:
    checked_relative_artifact_path(value)
    candidates = [
        repo_root / value,
        summary_path.parent / value,
        summary_path.parent.parent / value,
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            continue
        if resolved.exists():
            return resolved
    return None


def checked_relative_artifact_path(value: str) -> None:
    candidate = Path(value)
    require(not candidate.is_absolute(), f"artifact path must be relative: {value}")
    require(candidate.drive == "", f"artifact path must not include a drive: {value}")
    require("\\" not in value, f"artifact path must use POSIX separators: {value}")
    require("~" not in candidate.parts, f"artifact path must not include ~: {value}")
    require(".." not in candidate.parts, f"artifact path must not include ..: {value}")


def weighted_metric(metrics: list[dict[str, Any]], key: str, units_total: int) -> float:
    if units_total <= 0:
        return 0.0
    numerator = 0.0
    for metric in metrics:
        value = metric.get(key)
        if isinstance(value, (int, float)) and value >= 0:
            numerator += float(value) * nonnegative_int(metric.get("units_total"))
    return numerator / units_total


def require_count_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, count in value.items():
        if isinstance(key, str) and isinstance(count, int) and count >= 0:
            result[key] = count
    return result


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def nonnegative_int(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def nonnegative_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) and value >= 0 else None


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    require(isinstance(value, int), f"{key} must be an integer")
    return value


def optional_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    require(isinstance(value, int), f"{key} must be an integer")
    return value


def require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    require(isinstance(value, dict), f"{key} must be an object")
    return value


def require_nonnegative_int(value: Any, message: str) -> int:
    require(isinstance(value, int) and value >= 0, f"{message} must be a non-negative integer")
    return value


def is_l4_refused(item: Any) -> bool:
    return isinstance(item, dict) and item.get("route_level") == "L4" and item.get("route_status") == "refused"


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SystemExit(message)


if __name__ == "__main__":
    raise SystemExit(main())
