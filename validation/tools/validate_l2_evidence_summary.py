#!/usr/bin/env python3
"""Validate L2 slice evidence completeness for full regression."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=REPO_ROOT / "validation" / "evidence")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = validate_l2_evidence(args.evidence_root)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def validate_l2_evidence(evidence_root: Path) -> dict[str, Any]:
    l2_root = evidence_root / "l2-slices"
    summary_path = l2_root / "l2-l3-summary.json"
    summary = load_json(summary_path)
    require(summary.get("status") == "passed", f"L2 summary status must be passed: {summary_path}")
    require(
        summary.get("safety_check", {}).get("status") == "passed",
        "L2 unsafe scan status must be passed",
    )
    require(
        summary.get("unsafe_ledger_check", {}).get("audit_status") == "passed",
        "L2 unsafe ledger audit_status must be passed",
    )
    unsafe_scan_path = l2_root / "unsafe-scan.json"
    unsafe_ledger_path = l2_root / "unsafe-ledger.json"
    require(unsafe_scan_path.exists(), "L2 unsafe-scan.json is missing")
    require(unsafe_ledger_path.exists(), "L2 unsafe-ledger.json is missing")
    unsafe_scan = load_json(unsafe_scan_path)
    unsafe_ledger = load_json(unsafe_ledger_path)
    require(unsafe_scan.get("status") == "passed", "L2 unsafe scan report status must be passed")
    require(
        unsafe_ledger.get("audit_status") == "passed",
        "L2 unsafe ledger report audit_status must be passed",
    )
    summary_unsafe_count = int(summary.get("safety_check", {}).get("unsafe_count", 0))
    scan_unsafe_count = int(unsafe_scan.get("unsafe_count", 0))
    require(
        scan_unsafe_count == summary_unsafe_count,
        f"L2 unsafe scan count drift: {scan_unsafe_count} != {summary_unsafe_count}",
    )
    ledger_unsafe_count = int(unsafe_ledger.get("first_party_non_test_unsafe_count", scan_unsafe_count))
    require(
        ledger_unsafe_count == scan_unsafe_count,
        f"L2 unsafe ledger count drift: {ledger_unsafe_count} != {scan_unsafe_count}",
    )

    slice_reports = []
    slices = summary.get("diff_check", {}).get("slices", [])
    require(slices, "L2 summary contains no accepted slices")
    require(
        summary.get("diff_check", {}).get("status") == "passed",
        "L2 diff_check.status must be passed",
    )
    require(
        summary.get("negative_diff_check", {}).get("status") == "passed",
        "L2 negative_diff_check.status must be passed",
    )
    negative_reports = {
        item.get("slice_id"): item for item in summary.get("negative_diff_check", {}).get("reports", [])
    }
    for item in slices:
        slice_id = str(item.get("slice_id", ""))
        if item.get("l2_status") != "passed":
            continue
        require(slice_id in negative_reports, f"{slice_id} missing negative diff report entry")
        expected_negative_report = expected_negative_report_path(slice_id)
        declared_negative_report = negative_reports[slice_id].get("report")
        require(
            declared_negative_report == expected_negative_report,
            f"{slice_id} negative diff report path drift: {declared_negative_report} != {expected_negative_report}",
        )
        require(
            negative_reports[slice_id].get("status") == "passed",
            f"{slice_id} negative diff report status must be passed",
        )
        slice_reports.append(validate_slice(evidence_root, l2_root, slice_id))

    require(slice_reports, "L2 summary contains no passed slices")
    return {
        "schema_version": 1,
        "status": "passed",
        "evidence_root": rel(evidence_root),
        "slice_count": len(slice_reports),
        "slices": slice_reports,
    }


def validate_slice(evidence_root: Path, l2_root: Path, slice_id: str) -> dict[str, Any]:
    base, prefix, level = evidence_location(evidence_root, l2_root, slice_id)
    rust_report_path = base / f"{prefix}-rust-report.json"
    diff_path = base / f"{prefix}-diff.json"
    negative_path = base / f"{prefix}-negative-diff.json"
    test_translation_path = base / f"{prefix}-test-translation.json"

    rust_report = require_json(rust_report_path, slice_id, "rust report")
    diff = require_json(diff_path, slice_id, "positive diff")
    negative = require_json(negative_path, slice_id, "negative diff")
    tests = require_json(test_translation_path, slice_id, "test translation")

    require_status(rust_report, slice_id, "rust report", {"passed"})
    require_status(diff, slice_id, "positive diff", {"passed"})
    require(diff.get("first_mismatch") is None, f"{slice_id} positive diff has first_mismatch")
    require_status(negative, slice_id, "negative diff", {"passed", "expected_failed"})
    require(
        bool(negative.get("detected") or negative.get("mutation_detected")),
        f"{slice_id} negative diff did not detect mutation",
    )

    coverage = tests.get("coverage", {})
    require_status(tests, slice_id, "test translation", {"recorded"})
    require(coverage.get("main_paths"), f"{slice_id} test translation main_paths is empty")
    require(coverage.get("negative_cases"), f"{slice_id} test translation negative_cases is empty")
    mappings = tests.get("translation_mappings", [])
    require(
        any(mapping.get("coverage_kind") == "main_path" and mapping.get("status") == "mapped" for mapping in mappings),
        f"{slice_id} test translation lacks mapped main_path",
    )
    require(
        any(mapping.get("coverage_kind") == "negative_case" and mapping.get("status") == "mapped" for mapping in mappings),
        f"{slice_id} test translation lacks mapped negative_case",
    )

    return {
        "slice_id": slice_id,
        "level": level,
        "rust_report": "passed",
        "positive_diff": "passed",
        "negative_diff": "passed",
        "test_translation": "recorded",
        "evidence": {
            "rust_report": rel(rust_report_path),
            "positive_diff": rel(diff_path),
            "negative_diff": rel(negative_path),
            "test_translation": rel(test_translation_path),
        },
    }


def evidence_location(evidence_root: Path, l2_root: Path, slice_id: str) -> tuple[Path, str, str]:
    if slice_id == "libuv-ip4-addr":
        return evidence_root / "libuv", "l3-ip4-addr", "L3"
    if slice_id == "demo-store-add-one":
        return evidence_root / "demo", "l3-store-add-one", "L3"
    if slice_id == "demo-sum-i32-buffer":
        return evidence_root / "demo", "l3-sum-i32-buffer", "L3"
    if slice_id == "demo-call-expression":
        return evidence_root / "demo", "l3-call-expression", "L3"
    if slice_id == "demo-signed-rshift-contract":
        return evidence_root / "demo", "l3-signed-rshift-contract", "L3"
    if slice_id == "demo-external-direct-callee":
        return evidence_root / "demo", "l3-external-direct-callee", "L3"
    if slice_id == "demo-sum-i32-ptr-arith":
        return evidence_root / "demo", "l3-sum-i32-ptr-arith", "L3"
    if slice_id == "demo-copy-i32-ptr-arith":
        return evidence_root / "demo", "l3-copy-i32-ptr-arith", "L3"
    if slice_id == "demo-add-i32-pair-ptr-arith":
        return evidence_root / "demo", "l3-add-i32-pair-ptr-arith", "L3"
    return l2_root, slice_id, "L2"


def expected_negative_report_path(slice_id: str) -> str:
    if slice_id == "libuv-ip4-addr":
        return "validation/evidence/libuv/l3-ip4-addr-negative-diff.json"
    if slice_id == "demo-store-add-one":
        return "validation/evidence/demo/l3-store-add-one-negative-diff.json"
    if slice_id == "demo-sum-i32-buffer":
        return "validation/evidence/demo/l3-sum-i32-buffer-negative-diff.json"
    if slice_id == "demo-call-expression":
        return "validation/evidence/demo/l3-call-expression-negative-diff.json"
    if slice_id == "demo-signed-rshift-contract":
        return "validation/evidence/demo/l3-signed-rshift-contract-negative-diff.json"
    if slice_id == "demo-external-direct-callee":
        return "validation/evidence/demo/l3-external-direct-callee-negative-diff.json"
    if slice_id == "demo-sum-i32-ptr-arith":
        return "validation/evidence/demo/l3-sum-i32-ptr-arith-negative-diff.json"
    if slice_id == "demo-copy-i32-ptr-arith":
        return "validation/evidence/demo/l3-copy-i32-ptr-arith-negative-diff.json"
    if slice_id == "demo-add-i32-pair-ptr-arith":
        return "validation/evidence/demo/l3-add-i32-pair-ptr-arith-negative-diff.json"
    return f"validation/evidence/l2-slices/{slice_id}-negative-diff.json"


def require_json(path: Path, slice_id: str, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{slice_id} missing {label}: {path}")
    return load_json(path)


def require_status(report: dict[str, Any], slice_id: str, label: str, allowed: set[str]) -> None:
    status = str(report.get("status", ""))
    require(status in allowed, f"{slice_id} {label} status {status!r} not in {sorted(allowed)}")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
