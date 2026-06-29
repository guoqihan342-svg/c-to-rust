#!/usr/bin/env python3
"""Validate and summarize the translator capability coverage matrix."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = Path("validation/translator-coverage-matrix.json")
DEFAULT_EVIDENCE_ROOT = Path("validation/evidence")
GOVERNANCE_BINDING_KEYS = [
    "construct_id",
    "lowering_rule_id",
    "cfg_construct_id",
    "validation_false_positive_id",
    "competition_reproduction_blocker",
]
REQUIRED_DIMENSIONS = [
    "clang_fixture_replay",
    "handwritten_ir",
    "negative_case",
    "runtime_emitted_rust",
    "c_rust_diff",
    "legacy_fallback",
    "route_evidence",
]
DIMENSION_STATUSES = {"covered", "gap", "not_applicable"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--matrix", type=Path, default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    matrix_path = args.matrix
    if matrix_path is None:
        matrix_path = repo_root / DEFAULT_MATRIX
    elif not matrix_path.is_absolute():
        matrix_path = repo_root / matrix_path

    report = build_report(repo_root, matrix_path=matrix_path)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        output = args.output if args.output.is_absolute() else repo_root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["status"] == "passed" else 1


def build_report(repo_root: Path, *, matrix_path: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    matrix_path = matrix_path or repo_root / DEFAULT_MATRIX
    if not matrix_path.is_absolute():
        matrix_path = repo_root / matrix_path
    matrix = load_json(matrix_path)

    require(matrix.get("schema_version") == 1, "matrix schema_version must be 1")
    require(matrix.get("status") == "recorded", "matrix status must be recorded")
    claim_boundary = matrix.get("claim_boundary")
    require(isinstance(claim_boundary, str) and claim_boundary, "matrix claim_boundary is required")
    required_dimensions = matrix.get("required_dimensions")
    require(required_dimensions == REQUIRED_DIMENSIONS, "matrix required_dimensions drifted")
    capabilities = matrix.get("capabilities")
    require(isinstance(capabilities, list) and capabilities, "matrix capabilities are empty")

    dimension_summary = {
        dimension: {"covered": 0, "gap": 0, "not_applicable": 0}
        for dimension in REQUIRED_DIMENSIONS
    }
    capability_reports = []
    missing_links: list[str] = []

    for capability in capabilities:
        report = validate_capability(repo_root, capability)
        capability_reports.append(report)
        missing_links.extend(f"{report['id']}: {path}" for path in report["missing_links"])
        for dimension, item in report["dimension_status"].items():
            dimension_summary[dimension][item["status"]] += 1

    require(not missing_links, "missing matrix evidence links: " + ", ".join(missing_links))

    return {
        "schema_version": 1,
        "status": "passed",
        "matrix": {
            "path": rel(repo_root, matrix_path),
            "capability_count": len(capabilities),
        },
        "capability_count": len(capabilities),
        "dimensions": dimension_summary,
        "capabilities": capability_reports,
        "capability_delta_ledger": build_capability_delta_ledger(repo_root, evidence_root=DEFAULT_EVIDENCE_ROOT),
        "claim_boundary": claim_boundary,
    }


def build_capability_delta_ledger(repo_root: Path, *, evidence_root: Path) -> dict[str, Any]:
    evidence_dir = evidence_root if evidence_root.is_absolute() else repo_root / evidence_root
    ledger_files = sorted(evidence_dir.rglob("l3-*-capability-delta.json")) if evidence_dir.exists() else []
    generated_status = Counter()
    route_levels = Counter()
    route_statuses = Counter()
    by_construct: dict[str, Counter[str]] = {}
    ledger_summaries = []
    semantic_pass_count = 0
    delta_count = 0
    governance_delta_count = 0
    verification_command_count = 0
    blocked_callee_count = 0

    for path in ledger_files:
        payload = load_json(path)
        ledger_path = rel(repo_root, path)
        require(payload.get("schema_version") == 1, f"{rel(repo_root, path)} schema_version must be 1")
        require(payload.get("status") == "recorded", f"{rel(repo_root, path)} status must be recorded")
        target_id = require_string(payload, "target_id", f"{ledger_path} target_id is required")
        slice_id = require_string(payload, "slice_id", f"{ledger_path} slice_id is required")
        boundary = payload.get("boundary")
        require(isinstance(boundary, str) and boundary, f"{ledger_path} boundary is required")
        deltas = payload.get("capability_delta")
        require(isinstance(deltas, list) and deltas, f"{ledger_path} capability_delta is empty")
        governance = payload.get("governance_delta", [])
        require(isinstance(governance, list) and governance, f"{ledger_path} governance_delta is empty")
        for item in governance:
            require(isinstance(item, dict), f"{ledger_path} governance_delta item must be an object")
            require_string(item, "delta_id", f"{ledger_path} governance_delta delta_id is required")
            require_string(item, "kind", f"{ledger_path} governance_delta kind is required")
            refs = item.get("evidence_refs")
            require(isinstance(refs, list) and refs, f"{ledger_path} governance_delta evidence_refs are required")
            require(
                any(isinstance(item.get(key), str) and item.get(key) for key in GOVERNANCE_BINDING_KEYS),
                f"{ledger_path} governance_delta item must reference a construct, lowering rule, CFG construct, validation false positive, or competition reproduction blocker",
            )
        commands = payload.get("verification_commands", [])
        require(isinstance(commands, list) and commands, f"{ledger_path} verification_commands is empty")
        route_level = str(payload.get("route_level", "unknown"))
        route_status = str(payload.get("route_status", "unknown"))
        route_levels[route_level] += 1
        route_statuses[route_status] += 1
        governance_delta_count += len(governance)
        verification_command_count += len(commands)
        ledger_summaries.append(
            {
                "path": rel(repo_root, path),
                "target_id": target_id,
                "slice_id": slice_id,
                "route_level": route_level,
                "route_status": route_status,
                "delta_count": len(deltas),
            }
        )
        for delta in deltas:
            require(isinstance(delta, dict), f"{ledger_path} capability_delta item must be an object")
            require_string(delta, "delta_id", f"{ledger_path} delta_id is required")
            require_string(delta, "kind", f"{ledger_path} delta kind is required")
            construct_id = require_string(delta, "construct_id", f"{ledger_path} construct_id is required")
            require_string(delta, "real_c_slice", f"{ledger_path} real_c_slice is required")
            status = str(delta.get("generated_candidate_status", "unknown"))
            require(status != "unknown", f"{ledger_path} generated_candidate_status is required")
            semantic_pass = delta.get("semantic_pass")
            require(isinstance(semantic_pass, bool), f"{ledger_path} semantic_pass must be boolean")
            require(
                not (route_level == "L4" and route_status == "refused" and semantic_pass is True),
                f"{ledger_path} L4/refused capability delta cannot set semantic_pass=true",
            )
            evidence_refs = delta.get("evidence_refs")
            require(isinstance(evidence_refs, list) and evidence_refs, f"{ledger_path} evidence_refs are required")
            negative_coverage = delta.get("negative_coverage")
            require(
                isinstance(negative_coverage, list) and negative_coverage,
                f"{ledger_path} negative_coverage is required",
            )
            generated_status[status] += 1
            by_construct.setdefault(construct_id, Counter())[status] += 1
            delta_count += 1
            if semantic_pass is True:
                semantic_pass_count += 1
            blocked_callees = delta.get("blocked_callees", [])
            if isinstance(blocked_callees, list):
                blocked_callee_count += len(blocked_callees)

    return {
        "schema_version": 1,
        "status": "recorded",
        "ledger_count": len(ledger_files),
        "delta_count": delta_count,
        "governance_delta_count": governance_delta_count,
        "verification_command_count": verification_command_count,
        "semantic_pass_count": semantic_pass_count,
        "blocked_callee_count": blocked_callee_count,
        "generated_candidate_status": {
            status: generated_status[status] for status in sorted(generated_status)
        },
        "route_levels": {level: route_levels[level] for level in sorted(route_levels)},
        "route_statuses": {status: route_statuses[status] for status in sorted(route_statuses)},
        "by_construct": {
            construct: {status: counters[status] for status in sorted(counters)}
            for construct, counters in sorted(by_construct.items())
        },
        "ledgers": ledger_summaries,
        "claim_boundary": "Capability-delta ledger entries are not semantic acceptance evidence; use semantic_pass_count and validation gates for acceptance claims.",
    }


def validate_capability(repo_root: Path, capability: dict[str, Any]) -> dict[str, Any]:
    capability_id = require_string(capability, "id", "capability id is required")
    status = require_string(capability, "status", f"{capability_id} status is required")
    require(status in {"covered", "partial", "gap"}, f"{capability_id} status is invalid")
    ir_constructs = capability.get("ir_constructs")
    require(isinstance(ir_constructs, list) and ir_constructs, f"{capability_id} ir_constructs is empty")

    positive_cases = require_case_list(capability, "positive_cases", capability_id)
    negative_cases = require_case_list(capability, "negative_cases", capability_id)
    for case in negative_cases:
        reason = case.get("fail_closed_reason")
        require(
            isinstance(reason, str) and reason,
            f"{capability_id} negative case {case.get('name')} requires fail_closed_reason",
        )

    dimension_status = capability.get("dimension_status")
    require(isinstance(dimension_status, dict), f"{capability_id} dimension_status is required")
    require(set(dimension_status) == set(REQUIRED_DIMENSIONS), f"{capability_id} dimensions do not match required set")

    missing_links: list[str] = []
    for case in positive_cases + negative_cases:
        collect_missing_path(repo_root, missing_links, case)

    normalized_dimensions: dict[str, dict[str, Any]] = {}
    for dimension in REQUIRED_DIMENSIONS:
        item = dimension_status[dimension]
        require(isinstance(item, dict), f"{capability_id}.{dimension} must be an object")
        item_status = item.get("status")
        require(item_status in DIMENSION_STATUSES, f"{capability_id}.{dimension} status is invalid")
        if item_status == "covered":
            evidence = item.get("evidence")
            require(
                isinstance(evidence, list) and evidence,
                f"{capability_id}.{dimension} covered status requires evidence",
            )
            for evidence_item in evidence:
                require(isinstance(evidence_item, dict), f"{capability_id}.{dimension} evidence item is invalid")
                require_string(
                    evidence_item,
                    "path",
                    f"{capability_id}.{dimension} evidence item path is required",
                )
                collect_missing_path(repo_root, missing_links, evidence_item)
        else:
            reason = item.get("reason")
            require(
                isinstance(reason, str) and reason,
                f"{capability_id}.{dimension} {item_status} status requires reason",
            )
        normalized_dimensions[dimension] = {
            "status": item_status,
            "evidence_count": len(item.get("evidence", [])),
            "reason": item.get("reason"),
        }

    return {
        "id": capability_id,
        "status": status,
        "ir_construct_count": len(ir_constructs),
        "positive_cases": [case["name"] for case in positive_cases],
        "negative_cases": [case["name"] for case in negative_cases],
        "dimension_status": normalized_dimensions,
        "missing_links": missing_links,
    }


def require_case_list(capability: dict[str, Any], key: str, capability_id: str) -> list[dict[str, Any]]:
    cases = capability.get(key)
    require(isinstance(cases, list) and cases, f"{capability_id} {key} is empty")
    for case in cases:
        require(isinstance(case, dict), f"{capability_id} {key} item is invalid")
        require_string(case, "name", f"{capability_id} {key} item name is required")
        require_string(case, "path", f"{capability_id} {key} item path is required")
    return cases


def collect_missing_path(repo_root: Path, missing_links: list[str], item: dict[str, Any]) -> None:
    path_value = item.get("path")
    if not isinstance(path_value, str) or not path_value:
        return
    path = Path(path_value)
    candidate = path if path.is_absolute() else repo_root / path
    if not candidate.exists():
        missing_links.append(path_value)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require_string(payload: dict[str, Any], key: str, message: str) -> str:
    value = payload.get(key)
    require(isinstance(value, str) and value, message)
    return value


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def rel(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    sys.exit(main())
