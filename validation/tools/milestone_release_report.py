#!/usr/bin/env python3
"""Build milestone-facing release metrics without expanding semantic claims."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import translator_coverage_matrix


REFUSED_STATUSES = {"refused"}
BLOCKED_STATUSES = {"blocked"}
GENERATED_CANDIDATE_STATUSES = {"candidate", "generated", "generated_candidate", "compiled"}
SEMANTIC_PASS_STATUSES = {"accepted", "passed", "semantic_pass"}
SEMANTIC_ROUTE_STATUSES = {"accepted", "passed", "semantic_pass"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--coverage-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    report = build_report(repo_root, coverage_report_path=args.coverage_report)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def build_report(repo_root: Path, *, coverage_report_path: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    coverage_report = load_coverage_report(repo_root, coverage_report_path=coverage_report_path)

    require(coverage_report.get("schema_version") == 1, "coverage report schema_version must be 1")
    require(coverage_report.get("status") == "passed", "coverage report status must be passed")
    ledger = coverage_report.get("capability_delta_ledger")
    require(isinstance(ledger, dict), "coverage report capability_delta_ledger is required")
    require(ledger.get("schema_version") == 1, "capability_delta_ledger schema_version must be 1")
    require(ledger.get("status") == "recorded", "capability_delta_ledger status must be recorded")

    semantic_pass_count = require_int(ledger, "semantic_pass_count")
    ledger_count = require_int(ledger, "ledger_count")
    delta_count = require_int(ledger, "delta_count")
    generated_status = require_dict(ledger, "generated_candidate_status")
    route_levels = require_dict(ledger, "route_levels")
    route_statuses = require_dict(ledger, "route_statuses")
    ledgers = ledger.get("ledgers", [])
    require(isinstance(ledgers, list), "capability_delta_ledger ledgers must be a list")
    if semantic_pass_count > 0 and ledgers and all(is_l4_refused(item) for item in ledgers):
        raise SystemExit("L4/refused ledger entries cannot be the translation coverage numerator")
    candidate_classification = classify_candidate_statuses(
        generated_status,
        route_levels=route_levels,
        route_statuses=route_statuses,
        semantic_pass_count=semantic_pass_count,
    )

    blockers = []
    if semantic_pass_count == 0:
        blockers.append("no_translator_generated_semantic_pass")
    if semantic_pass_count < 3:
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
            "translation_coverage_numerator": semantic_pass_count,
            "tracked_capability_delta_ledgers": ledger_count,
            "tracked_capability_delta_count": delta_count,
            "native_build_catalogue_included_in_translation_coverage": False,
            "handwritten_reference_included_in_translation_coverage": False,
            "candidate_classification": candidate_classification,
            "capability_delta_ledger": {
                "ledger_count": ledger_count,
                "delta_count": delta_count,
                "semantic_pass_count": semantic_pass_count,
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
        "claim_boundary": "Milestone release metrics are not semantic acceptance evidence; capability_delta_ledger entries are not semantic acceptance evidence unless the shared validation gates prove semantic_pass for translator-generated Rust drafts.",
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


def require_int(payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
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
