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
REQUIRED_REVIEW_CHECKLIST_ITEMS = [
    "harness_architecture",
    "unsafe_ledger",
    "test_coverage_matrix",
    "real_slice_evidence",
    "public_claim_boundary",
    "known_refusals",
]
LF_STABLE_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hh",
    ".hpp",
    ".json",
    ".jsonl",
    ".md",
    ".rs",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--coverage-report", type=Path)
    parser.add_argument("--competition-summary", type=Path, action="append", default=[])
    parser.add_argument("--batch-profile-report", type=Path, action="append", default=[])
    parser.add_argument("--review-checklist", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    report = build_report(
        repo_root,
        coverage_report_path=args.coverage_report,
        competition_summary_paths=args.competition_summary,
        batch_profile_report_paths=args.batch_profile_report,
        review_checklist_paths=args.review_checklist,
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
    review_checklist_paths: list[Path] | None = None,
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
    review_checklist_inputs = load_review_checklists(repo_root, review_checklist_paths=review_checklist_paths or [])
    review_gate = summarize_review_gate(review_checklist_inputs)

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
    if review_gate["status"] == "missing":
        blockers.append("external_review_not_recorded")
    elif review_gate["status"] != "passed":
        blockers.append("external_review_not_passed")

    report_status = "release_candidate" if not blockers else "internal_preview"
    harness_architecture = {
        "entrypoint": "milestone-release-report",
        "pipeline": [
            "translator-coverage-matrix",
            "competition-summary",
            "workflow-metrics",
            "before-after-exhibit",
            "release-report",
        ],
        "workflow_run_count": int(s2_workflow_metrics.get("run_count", 0)),
        "before_after_report_count": int(before_after_exhibits.get("report_count", 0)),
        "input_summaries": s2_workflow_metrics.get("input_summaries", []),
        "before_after_inputs": before_after_exhibits.get("input_reports", []),
    }
    core_translation_quality = {
        "translation_coverage_numerator": translator_generated_semantic_pass_count,
        "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
        "unsafe_reduction": s2_workflow_metrics.get("unsafe_reduction", {"status": "not_measured"}),
        "translation_before_after": s2_workflow_metrics.get(
            "translation_before_after",
            {"status": "not_provided", "unit_count": 0},
        ),
        "before_after_exhibits": before_after_exhibits,
        "readiness_status": report_status,
        "readiness_blockers": blockers,
    }
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
        "harness_architecture": harness_architecture,
        "core_translation_quality": core_translation_quality,
        "review_gate": review_gate,
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
            "review_gate": review_gate,
        },
        "release_note_inputs": {
            "capability_delta_ledger": ledger,
            "s2_workflow_metrics": s2_workflow_metrics,
            "before_after_exhibits": before_after_exhibits,
            "review_gate": review_gate,
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


def load_review_checklists(
    repo_root: Path,
    *,
    review_checklist_paths: list[Path],
) -> list[dict[str, Any]]:
    reviews = []
    for review_path in review_checklist_paths:
        review_abs = review_path if review_path.is_absolute() else repo_root / review_path
        review_abs = review_abs.resolve()
        try:
            review_abs.relative_to(repo_root.resolve())
        except ValueError as error:
            raise SystemExit(f"review checklist must stay under repo root: {review_path}") from error
        require(review_abs.exists(), f"review checklist does not exist: {review_path}")
        payload = json.loads(review_abs.read_text(encoding="utf-8-sig"))
        require(isinstance(payload, dict), f"review checklist must be an object: {review_path}")
        review = validate_review_checklist_payload(payload, review_path=review_abs)
        review["path"] = rel(repo_root, review_abs)
        review["sha256"] = sha256_file(review_abs)
        reviews.append(review)
    return reviews


def validate_review_checklist_payload(payload: dict[str, Any], *, review_path: Path) -> dict[str, Any]:
    require(payload.get("schema_version") == 1, f"review checklist schema_version must be 1: {review_path}")
    require(
        payload.get("report_kind") == "milestone-review-checklist",
        f"review checklist report_kind must be milestone-review-checklist: {review_path}",
    )
    status = payload.get("status")
    require(status in {"passed", "needs_changes", "failed"}, f"review checklist status is invalid: {review_path}")
    reviewer = require_dict(payload, "reviewer")
    reviewer_kind = reviewer.get("kind")
    reviewer_id = reviewer.get("id")
    require(reviewer_kind in {"internal", "external", "independent"}, f"reviewer.kind is invalid: {review_path}")
    require(isinstance(reviewer_id, str) and reviewer_id, f"reviewer.id is required: {review_path}")

    claim_boundary = require_dict(payload, "claim_boundary")
    require(
        claim_boundary.get("semantic_gate") is False,
        f"review checklist claim_boundary.semantic_gate must be false: {review_path}",
    )
    require(
        claim_boundary.get("review_is_semantic_acceptance") is False,
        f"review checklist claim_boundary.review_is_semantic_acceptance must be false: {review_path}",
    )

    checklist = require_dict(payload, "checklist")
    item_statuses: dict[str, str] = {}
    item_evidence: dict[str, list[str]] = {}
    for item in REQUIRED_REVIEW_CHECKLIST_ITEMS:
        entry = require_dict(checklist, item)
        item_status = entry.get("status")
        require(item_status in {"passed", "needs_changes", "failed"}, f"{item}.status is invalid: {review_path}")
        evidence = entry.get("evidence")
        require(
            isinstance(evidence, list) and evidence and all(isinstance(path, str) for path in evidence),
            f"{item}.evidence must be a non-empty string list: {review_path}",
        )
        for evidence_path in evidence:
            checked_relative_artifact_path(evidence_path)
        item_statuses[item] = str(item_status)
        item_evidence[item] = [str(path) for path in evidence]

    if status == "passed":
        not_passed = [item for item, item_status in item_statuses.items() if item_status != "passed"]
        require(not not_passed, f"passed review checklist has non-passed items: {not_passed}")

    return {
        "review_id": str(payload.get("review_id", review_path.stem)),
        "status": str(status),
        "reviewer": {"kind": str(reviewer_kind), "id": str(reviewer_id)},
        "required_items": list(REQUIRED_REVIEW_CHECKLIST_ITEMS),
        "item_statuses": item_statuses,
        "item_evidence": item_evidence,
        "claim_boundary": claim_boundary,
    }


def summarize_review_gate(review_inputs: list[dict[str, Any]]) -> dict[str, Any]:
    if not review_inputs:
        return {
            "status": "missing",
            "review_count": 0,
            "required_items": list(REQUIRED_REVIEW_CHECKLIST_ITEMS),
            "reviews": [],
            "claim_boundary": (
                "Milestone review checklists are human or external review evidence only. "
                "They do not create semantic acceptance."
            ),
        }
    status = "passed" if all(review.get("status") == "passed" for review in review_inputs) else "needs_changes"
    return {
        "status": status,
        "review_count": len(review_inputs),
        "required_items": list(REQUIRED_REVIEW_CHECKLIST_ITEMS),
        "reviews": review_inputs,
        "claim_boundary": (
            "Milestone review checklists cover release readiness, public claim boundaries, and known refusals. "
            "They are not semantic gates and do not expand translation coverage."
        ),
    }


def validate_before_after_exhibit_inputs(repo_root: Path, *, exhibit: dict[str, Any], exhibit_path: Path) -> None:
    inputs = require_dict(exhibit, "inputs")
    workflow_metrics = {}
    for field in ("profile", "competition_summary", "workflow_metrics"):
        binding = require_dict(inputs, field)
        artifact_path = validate_path_sha_binding(
            repo_root,
            binding=binding,
            field=f"before-after exhibit inputs.{field}",
            anchor_path=exhibit_path,
        )
        if field == "competition_summary":
            validate_competition_run_summary.validate_summary(artifact_path, repo_root=repo_root)
        if field == "workflow_metrics":
            workflow_metrics = json.loads(artifact_path.read_text(encoding="utf-8-sig"))
    units = exhibit.get("units")
    require(isinstance(units, list), f"before-after exhibit units must be an array: {exhibit_path}")
    for index, unit in enumerate(units):
        require(isinstance(unit, dict), f"before-after exhibit units[{index}] must be an object: {exhibit_path}")
        for field in ("baseline", "final", "oracle_evidence", "accepted_patch", "patch_log"):
            binding = require_dict(unit, field)
            validate_path_sha_binding(
                repo_root,
                binding=binding,
                field=f"before-after exhibit units[{index}].{field}",
                anchor_path=exhibit_path,
            )
        repair_history = unit.get("repair_history")
        if isinstance(repair_history, dict):
            validate_repair_history_binding(
                repo_root,
                repair_history=repair_history,
                field=f"before-after exhibit units[{index}].repair_history",
                anchor_path=exhibit_path,
            )
        validate_before_after_unit_matches_workflow(
            unit,
            workflow_metrics=workflow_metrics,
            field=f"before-after exhibit units[{index}]",
            exhibit_path=exhibit_path,
        )
        validate_before_after_unit_provenance(
            unit,
            field=f"before-after exhibit units[{index}]",
            exhibit_path=exhibit_path,
        )
    stage_contracts = exhibit.get("stage_contracts")
    repairer = stage_contracts.get("repairer") if isinstance(stage_contracts, dict) else None
    if isinstance(repairer, dict) and repairer.get("status") == "verified":
        histories = repairer.get("histories")
        verified_histories = [
            history
            for history in histories
            if isinstance(history, dict) and history.get("verified") is True
        ] if isinstance(histories, list) else []
        require(
            verified_histories,
            f"before-after exhibit repairer.status=verified requires verified history: {exhibit_path}",
        )
        for index, history in enumerate(verified_histories):
            repair_history = history.get("repair_history")
            require(
                isinstance(repair_history, dict),
                f"before-after exhibit stage_contracts.repairer.histories[{index}].repair_history is required: {exhibit_path}",
            )
            validate_repair_history_binding(
                repo_root,
                repair_history=repair_history,
                field=f"before-after exhibit stage_contracts.repairer.histories[{index}].repair_history",
                anchor_path=exhibit_path,
            )


def validate_before_after_unit_matches_workflow(
    unit: dict[str, Any],
    *,
    workflow_metrics: dict[str, Any],
    field: str,
    exhibit_path: Path,
) -> None:
    unit_id = unit.get("unit_id")
    require(isinstance(unit_id, str) and unit_id, f"{field}.unit_id is required: {exhibit_path}")
    per_unit_statuses = workflow_metrics.get("per_unit_statuses")
    require(isinstance(per_unit_statuses, list), f"{field} requires workflow metrics per_unit_statuses: {exhibit_path}")
    workflow_unit = next(
        (
            item
            for item in per_unit_statuses
            if isinstance(item, dict) and item.get("unit_id") == unit_id
        ),
        None,
    )
    require(workflow_unit is not None, f"{field}.unit_id is not present in workflow metrics: {unit_id}")
    before_after = workflow_unit.get("translation_before_after")
    require(
        isinstance(before_after, dict) and before_after.get("status") == "bound",
        f"{field} requires bound workflow translation_before_after: {unit_id}",
    )
    for binding_field in ("baseline", "final", "oracle_evidence", "accepted_patch", "patch_log"):
        require(
            unit.get(binding_field) == before_after.get(binding_field),
            f"{field}.{binding_field} must match workflow metrics translation_before_after: {exhibit_path}",
        )
    require(
        unit.get("unsafe_reduction") == before_after.get("unsafe_reduction"),
        f"{field}.unsafe_reduction must match workflow metrics translation_before_after: {exhibit_path}",
    )


def validate_before_after_unit_provenance(
    unit: dict[str, Any],
    *,
    field: str,
    exhibit_path: Path,
) -> None:
    accepted_patch = unit.get("accepted_patch")
    accepted_patch_bound = isinstance(accepted_patch, dict) and isinstance(accepted_patch.get("path"), str)
    repair_history_bound = isinstance(unit.get("repair_history"), dict)
    patch_origin = unit.get("patch_origin")
    if patch_origin is not None:
        require(isinstance(patch_origin, dict), f"{field}.patch_origin must be an object: {exhibit_path}")
        require(
            patch_origin.get("source") in {"accepted_safe_evidence", "unbound"},
            f"{field}.patch_origin.source must stay inside accepted evidence boundary: {exhibit_path}",
        )
        require(
            patch_origin.get("accepted_patch_bound") is accepted_patch_bound,
            f"{field}.patch_origin.accepted_patch_bound must match accepted_patch binding: {exhibit_path}",
        )
        require(
            patch_origin.get("repair_history_bound") is repair_history_bound,
            f"{field}.patch_origin.repair_history_bound must match repair_history binding: {exhibit_path}",
        )
        if "opencode_session_bound" in patch_origin:
            require(
                isinstance(patch_origin.get("opencode_session_bound"), bool),
                f"{field}.patch_origin.opencode_session_bound must be boolean: {exhibit_path}",
            )
        if "semantic_claim_source" in patch_origin:
            require(
                isinstance(patch_origin.get("semantic_claim_source"), str)
                and bool(patch_origin.get("semantic_claim_source")),
                f"{field}.patch_origin.semantic_claim_source must be non-empty: {exhibit_path}",
            )
        if "generated_draft_semantic_pass" in patch_origin:
            require(
                patch_origin.get("generated_draft_semantic_pass") is False,
                f"{field}.patch_origin.generated_draft_semantic_pass must be false: {exhibit_path}",
            )
        require(
            patch_origin.get("semantic_gate") is False,
            f"{field}.patch_origin.semantic_gate must be false: {exhibit_path}",
        )
        require(
            patch_origin.get("translation_coverage_numerator") == 0,
            f"{field}.patch_origin.translation_coverage_numerator must be 0: {exhibit_path}",
        )
    provenance = unit.get("safety_loop_provenance")
    if provenance is not None:
        require(isinstance(provenance, dict), f"{field}.safety_loop_provenance must be an object: {exhibit_path}")
        if isinstance(patch_origin, dict):
            require(
                provenance.get("patch_source") == patch_origin.get("source"),
                f"{field}.safety_loop_provenance.patch_source must match patch_origin.source: {exhibit_path}",
            )
        require(
            provenance.get("unsafe_delta") == unit.get("unsafe_reduction"),
            f"{field}.safety_loop_provenance.unsafe_delta must match unsafe_reduction: {exhibit_path}",
        )
        require(
            provenance.get("repair_history_bound") is repair_history_bound,
            f"{field}.safety_loop_provenance.repair_history_bound must match repair_history binding: {exhibit_path}",
        )
        if "opencode_session_bound" in provenance:
            require(
                isinstance(provenance.get("opencode_session_bound"), bool),
                f"{field}.safety_loop_provenance.opencode_session_bound must be boolean: {exhibit_path}",
            )
        if "repair_rounds" in unit:
            require(
                provenance.get("repair_rounds") == unit.get("repair_rounds"),
                f"{field}.safety_loop_provenance.repair_rounds must match unit repair_rounds: {exhibit_path}",
            )
        if isinstance(unit.get("auto_recovered"), bool):
            require(
                provenance.get("auto_recovered") is unit.get("auto_recovered"),
                f"{field}.safety_loop_provenance.auto_recovered must match unit auto_recovered: {exhibit_path}",
            )
        require(
            provenance.get("semantic_gate") is False,
            f"{field}.safety_loop_provenance.semantic_gate must be false: {exhibit_path}",
        )
        require(
            provenance.get("translation_coverage_numerator") == 0,
            f"{field}.safety_loop_provenance.translation_coverage_numerator must be 0: {exhibit_path}",
        )


def validate_path_sha_binding(
    repo_root: Path,
    *,
    binding: dict[str, Any],
    field: str,
    anchor_path: Path,
) -> Path:
    artifact_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    require(
        isinstance(artifact_ref, str) and isinstance(expected_sha, str),
        f"{field}.path and sha256 are required: {anchor_path}",
    )
    artifact_path = resolve_bound_summary_artifact(artifact_ref, summary_path=anchor_path, repo_root=repo_root)
    require(artifact_path is not None, f"{field}.path does not exist: {artifact_ref}")
    require(
        sha256_file(artifact_path) == expected_sha,
        f"{field}.sha256 does not match artifact: {anchor_path}",
    )
    return artifact_path


def validate_repair_history_binding(
    repo_root: Path,
    *,
    repair_history: dict[str, Any],
    field: str,
    anchor_path: Path,
) -> None:
    patch_events_path = repair_history.get("patch_events_path")
    patch_events_sha256 = repair_history.get("patch_events_sha256")
    require(
        isinstance(patch_events_path, str) and isinstance(patch_events_sha256, str),
        f"{field}.patch_events_path and patch_events_sha256 are required: {anchor_path}",
    )
    artifact_path = resolve_bound_summary_artifact(patch_events_path, summary_path=anchor_path, repo_root=repo_root)
    require(artifact_path is not None, f"{field}.patch_events_path does not exist: {patch_events_path}")
    require(
        sha256_file(artifact_path) == patch_events_sha256,
        f"{field}.patch_events_sha256 does not match artifact: {anchor_path}",
    )


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
        units = compact_before_after_units(exhibit)
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
                "units": units,
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


def compact_before_after_units(exhibit: dict[str, Any]) -> list[dict[str, Any]]:
    units = exhibit.get("units")
    if not isinstance(units, list):
        return []
    compacted = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        detail = {}
        for key in [
            "unit_id",
            "status",
            "baseline",
            "final",
            "oracle_evidence",
            "accepted_patch",
            "patch_log",
            "unsafe_reduction",
            "patch_origin",
            "safety_loop_provenance",
            "repair_history",
        ]:
            if key in unit:
                detail[key] = unit[key]
        compacted.append(detail)
    return compacted


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
    data = path.read_bytes()
    if path.suffix.lower() in LF_STABLE_TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


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
