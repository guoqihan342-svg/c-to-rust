#!/usr/bin/env python3
"""Build route governance and capability metrics without expanding semantic claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import evidence_governance
from validation.tools import milestone_release_report


DEFAULT_EVIDENCE_ROOT = Path("validation/evidence")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--coverage-report", type=Path)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--competition-summary", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    report = build_report(
        repo_root,
        coverage_report_path=args.coverage_report,
        evidence_root=args.evidence_root,
        competition_summary_paths=args.competition_summary,
    )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "passed" else 1


def build_report(
    repo_root: Path,
    *,
    coverage_report_path: Path | None = None,
    evidence_root: Path = DEFAULT_EVIDENCE_ROOT,
    competition_summary_paths: list[Path] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    coverage_report = milestone_release_report.load_coverage_report(
        repo_root,
        coverage_report_path=coverage_report_path,
    )
    coverage_metrics = coverage_metrics_from(coverage_report)
    evidence_report = evidence_governance.build_report(repo_root, evidence_root=evidence_root)
    require(evidence_report.get("schema_version") == 1, "evidence governance report schema_version must be 1")
    require(evidence_report.get("status") == "passed", "evidence governance report status must be passed")
    inventory = require_dict(evidence_report, "inventory")
    candidate_inventory = require_dict(inventory, "candidate_generation")
    evidence_dir = evidence_root if evidence_root.is_absolute() else repo_root / evidence_root
    slice_gate_contexts = build_slice_gate_contexts(repo_root, evidence_dir)
    s2_workflow_metrics = milestone_release_report.summarize_s2_workflow_metrics(
        milestone_release_report.load_competition_workflow_metrics(
            repo_root,
            competition_summary_paths=competition_summary_paths or [],
        )
    )

    return {
        "schema_version": 1,
        "status": "passed",
        "report_kind": "route-governance-metrics",
        "inputs": {
            "translator_coverage_matrix": {
                "path": coverage_report.get("matrix", {}).get("path", "unknown"),
                "status": coverage_report.get("status"),
                "capability_count": coverage_report.get("capability_count"),
                "claim_boundary": coverage_report.get("claim_boundary"),
            },
            "evidence_governance": {
                "evidence_root": evidence_report.get("evidence_root"),
                "status": evidence_report.get("status"),
                "file_count": inventory.get("file_count"),
                "claim_anchor_issue_count": evidence_report.get("portability", {}).get("claim_anchor_issue_count"),
                "profile_hash_issue_count": evidence_report.get("portability", {}).get("profile_hash_issue_count"),
            },
        },
        "metrics": {
            **coverage_metrics,
            "tracked_route_decision_artifacts": require_nonnegative_int(
                candidate_inventory.get("route_decision_artifact_count", 0),
                "candidate_generation.route_decision_artifact_count",
            ),
            "s2_workflow_metrics": s2_workflow_metrics,
            "candidate_generation_inventory": candidate_inventory,
            "tracked_slice_gate_contexts": len(slice_gate_contexts),
            "slice_gate_contexts": slice_gate_contexts,
        },
        "denominators": {
            "capability_delta_ledger": "capability delta ledger artifacts under validation/evidence/**/l3-*-capability-delta.json",
            "candidate_generation_inventory": "route decision artifacts under validation/evidence/**/*-route-decision.json",
            "slice_gate_contexts": "one row per validation/evidence/<target>/auto-translation/<slice> directory with route/profile/final gate evidence",
            "translation_coverage_numerator": "translator-generated Rust drafts with semantic-pass status backed by L3 accepted/passed route evidence",
            "accepted_evidence_semantic_pass_count": "accepted external evidence contexts reported separately and excluded from translation_coverage_numerator",
            "s2_workflow_metrics": "S2 repair, retry, unsafe-reduction, and before/after artifact-binding workflow metrics loaded from hash-bound competition-run summaries when provided",
        },
        "claim_boundary": (
            "Route governance metrics are not semantic acceptance evidence; capability_delta_ledger entries "
            "and L4/accepted-evidence contexts are not counted as translator-generated semantic passes unless "
            "the shared validation gates prove semantic_pass for translator-generated Rust drafts."
        ),
        "retention_policy": build_retention_policy(),
    }


def build_slice_gate_contexts(repo_root: Path, evidence_dir: Path) -> list[dict[str, Any]]:
    if not evidence_dir.exists():
        return []
    contexts = []
    for target_dir in sorted(path for path in evidence_dir.iterdir() if path.is_dir()):
        auto_dir = target_dir / "auto-translation"
        if not auto_dir.is_dir():
            continue
        for slice_dir in sorted(path for path in auto_dir.iterdir() if path.is_dir()):
            contexts.append(build_slice_gate_context(repo_root, target_dir.name, slice_dir))
    return contexts


def build_slice_gate_context(repo_root: Path, fallback_target_id: str, slice_dir: Path) -> dict[str, Any]:
    manifest = load_optional_json(find_artifact(slice_dir, "-evidence-manifest.json"))
    route = load_optional_json(find_artifact(slice_dir, "-route-decision.json"))
    final = load_optional_json(find_artifact(slice_dir, "-final-verification.json"))
    repairs = load_optional_json(find_artifact(slice_dir, "-self-healing-blocked-repairs.json"))
    unsafe_scan = load_optional_json(find_artifact(slice_dir, "-unsafe-scan.json"))
    negative_diff = load_optional_json(find_artifact(slice_dir, "-negative-diff.json"))
    performance_smoke = load_optional_json(find_artifact(slice_dir, "-performance-smoke.json"))

    target_id = first_string(
        manifest.get("target_id"),
        final.get("target_id"),
        route.get("target_id"),
        fallback_target_id,
    )
    slice_id = first_string(
        manifest.get("slice_id"),
        final.get("slice_id"),
        route.get("slice_id"),
        slice_dir.name,
    )
    route_summary = route_governance_summary(route)
    return {
        "target_id": target_id,
        "slice_id": slice_id,
        "pipeline_id": rel(repo_root, slice_dir),
        "route": {
            "level": route_summary.get("route_level") or route.get("level") or route.get("route_level"),
            "status": route_summary.get("route_status") or route.get("route_status") or route.get("status"),
            "artifact_status": route.get("status"),
        },
        "final_verification": {
            "status": final.get("status"),
            "semantic_pass": final.get("semantic_pass"),
            "c_oracle_status": final.get("c_oracle_status"),
            "validation_profile_status": final.get("validation_profile_status"),
            "skipped_gates": list_or_empty(final.get("skipped_gates")),
        },
        "failure_reasons": failure_reasons(final, negative_diff),
        "human_intervention_points": human_intervention_points(repairs),
        "blocked_callees": blocked_callees(repairs),
        "fixture": {
            "case_count": fixture_case_count(manifest),
        },
        "unsafe": {
            "status": unsafe_scan.get("status"),
            "first_party_non_test_unsafe_count": unsafe_scan.get("first_party_non_test_unsafe_count"),
            "first_party_non_test_unsafe_ratio": unsafe_scan.get("first_party_non_test_unsafe_ratio"),
        },
        "negative_diff": {
            "status": negative_diff.get("status"),
            "expected_failure": negative_diff.get("expected_failure"),
            "mutation_detected": negative_diff.get("mutation_detected"),
            "reason_code": negative_diff.get("reason_code"),
            "blocked_by": list_or_empty(negative_diff.get("blocked_by")),
            "root_blocked_by": list_or_empty(negative_diff.get("root_blocked_by")),
        },
        "performance_smoke": {
            "status": performance_smoke.get("status"),
            "secondary_only": performance_smoke.get("secondary_only"),
            "semantic_pass": performance_smoke.get("semantic_pass"),
        },
        "claim_boundary": (
            "Slice gate context summarizes existing route/profile/final evidence; it is not a semantic pass claim."
        ),
    }


def route_governance_summary(route: dict[str, Any]) -> dict[str, Any]:
    generation = route.get("candidate_generation")
    if not isinstance(generation, dict):
        return {}
    summary = generation.get("governance_summary")
    return summary if isinstance(summary, dict) else {}


def find_artifact(slice_dir: Path, suffix: str) -> Path | None:
    matches = sorted(slice_dir.glob(f"*{suffix}"))
    return matches[0] if matches else None


def load_optional_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, dict) else {}


def first_string(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return "unknown"


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def failure_reasons(final: dict[str, Any], negative_diff: dict[str, Any]) -> list[str]:
    reasons = []
    for gate in list_or_empty(final.get("skipped_gates")):
        if isinstance(gate, dict):
            append_unique(reasons, gate.get("reason"))
    append_unique(reasons, negative_diff.get("reason_code"))
    append_unique(reasons, negative_diff.get("reason"))
    return reasons


def human_intervention_points(repairs: dict[str, Any]) -> list[str]:
    points = []
    for repair in list_or_empty(repairs.get("blocked_repairs")):
        if isinstance(repair, dict):
            append_unique(points, repair.get("human_intervention_point"))
    return points


def blocked_callees(repairs: dict[str, Any]) -> list[str]:
    callees = []
    for repair in list_or_empty(repairs.get("blocked_repairs")):
        if not isinstance(repair, dict):
            continue
        gap = repair.get("ir_feature_gap")
        if not isinstance(gap, dict):
            continue
        for callee in list_or_empty(gap.get("blocked_callees")):
            append_unique(callees, callee)
    return callees


def fixture_case_count(manifest: dict[str, Any]) -> int | None:
    fixture = manifest.get("fixture")
    if isinstance(fixture, dict) and isinstance(fixture.get("operation_count"), int):
        return fixture["operation_count"]
    oracle = manifest.get("oracle")
    if isinstance(oracle, dict) and isinstance(oracle.get("case_count"), int):
        return oracle["case_count"]
    binding = oracle.get("fixture_binding") if isinstance(oracle, dict) else None
    if isinstance(binding, dict) and isinstance(binding.get("case_count"), int):
        return binding["case_count"]
    return None


def append_unique(items: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in items:
        items.append(value)


def rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def coverage_metrics_from(coverage_report: dict[str, Any]) -> dict[str, Any]:
    require(coverage_report.get("schema_version") == 1, "coverage report schema_version must be 1")
    require(coverage_report.get("status") == "passed", "coverage report status must be passed")
    ledger = require_dict(coverage_report, "capability_delta_ledger")
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
    if translator_generated_semantic_pass_count > 0 and ledgers and all(
        milestone_release_report.is_l4_refused(item) for item in ledgers
    ):
        raise SystemExit("L4/refused ledger entries cannot be the translation coverage numerator")

    candidate_classification = milestone_release_report.classify_candidate_statuses(
        generated_status,
        route_levels=route_levels,
        route_statuses=route_statuses,
        semantic_pass_count=translator_generated_semantic_pass_count,
    )
    return {
        "translation_coverage_numerator": translator_generated_semantic_pass_count,
        "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
        "tracked_capability_delta_ledgers": ledger_count,
        "tracked_capability_delta_count": delta_count,
        "candidate_classification": candidate_classification,
        "capability_delta_ledger": {
            "ledger_count": ledger_count,
            "delta_count": delta_count,
            "governance_delta_count": optional_int(ledger, "governance_delta_count", 0),
            "verification_command_count": optional_int(ledger, "verification_command_count", 0),
            "translator_generated_semantic_pass_count": translator_generated_semantic_pass_count,
            "semantic_pass_count": legacy_semantic_pass_count,
            "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
            "generated_candidate_status": generated_status,
            "route_levels": route_levels,
            "route_statuses": route_statuses,
            "by_construct": ledger.get("by_construct", {}),
            "blocked_callee_count": optional_int(ledger, "blocked_callee_count", 0),
        },
    }


def build_retention_policy() -> dict[str, Any]:
    return {
        "report_kind": "route-governance-metrics-retention-policy",
        "report_role": "p0-route-governance-and-capability-metrics",
        "target_artifacts": {
            "retention_class": "reproducible-local-output",
            "committed": False,
            "policy": "Regenerate from validation evidence, translator coverage matrix, and competition summaries; bind published runs by repo-relative path and sha256.",
        },
        "committed_anchors": {
            "retention_class": "release-evidence",
            "policy": "Use validation/evidence manifests, validation/translator-coverage-matrix.json, and config/competition-env profiles as committed anchors.",
        },
        "claim_boundary": "Retention policy does not expand semantic acceptance, generated-draft pass counts, or translation coverage.",
    }


def require_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    require(isinstance(value, dict), f"{key} must be an object")
    return value


def require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    require(isinstance(value, int), f"{key} must be an integer")
    return value


def optional_int(payload: dict[str, Any], key: str, default: int) -> int:
    value = payload.get(key, default)
    require(isinstance(value, int), f"{key} must be an integer")
    return value


def require_nonnegative_int(value: Any, message: str) -> int:
    require(isinstance(value, int) and value >= 0, f"{message} must be a non-negative integer")
    return value


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SystemExit(message)


if __name__ == "__main__":
    raise SystemExit(main())
