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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    report = build_report(
        repo_root,
        coverage_report_path=args.coverage_report,
        evidence_root=args.evidence_root,
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
            "candidate_generation_inventory": candidate_inventory,
        },
        "denominators": {
            "capability_delta_ledger": "capability delta ledger artifacts under validation/evidence/**/l3-*-capability-delta.json",
            "candidate_generation_inventory": "route decision artifacts under validation/evidence/**/*-route-decision.json",
            "translation_coverage_numerator": "translator-generated Rust drafts with semantic-pass status backed by L3 accepted/passed route evidence",
            "accepted_evidence_semantic_pass_count": "accepted external evidence contexts reported separately and excluded from translation_coverage_numerator",
        },
        "claim_boundary": (
            "Route governance metrics are not semantic acceptance evidence; capability_delta_ledger entries "
            "and L4/accepted-evidence contexts are not counted as translator-generated semantic passes unless "
            "the shared validation gates prove semantic_pass for translator-generated Rust drafts."
        ),
    }


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
