#!/usr/bin/env python3
"""Validate consumable FlashDB L3 evidence packages for full regression."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools.validate_flashdb_version_binding import sha256, validate_version_binding


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=REPO_ROOT / "validation" / "evidence")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    report = validate_flashdb_l3_evidence(args.evidence_root)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def validate_flashdb_l3_evidence(evidence_root: Path) -> dict[str, Any]:
    flashdb_root = evidence_root / "flashdb"
    require(flashdb_root.exists(), f"FlashDB evidence directory is missing: {flashdb_root}")
    summaries = sorted(flashdb_root.glob("l3-*-summary.json"))
    require(summaries, f"no FlashDB L3 summaries found under {flashdb_root}")

    accepted = []
    legacy_incomplete = []
    for summary_path in summaries:
        prefix = summary_path.name.removesuffix("-summary.json")
        summary = load_json(summary_path)
        if summary.get("status") != "passed":
            continue
        if not is_consumable_package(flashdb_root, prefix, summary):
            legacy_incomplete.append(
                {
                    "slice_id": str(summary.get("slice_id") or prefix.removeprefix("l3-")),
                    "summary": rel(summary_path),
                    "reason": "legacy summary lacks final-verification or negative-diff entry point",
                }
            )
            continue
        if not (flashdb_root / f"{prefix}-version-config-binding.json").exists():
            legacy_incomplete.append(
                {
                    "slice_id": str(summary.get("slice_id") or prefix.removeprefix("l3-")),
                    "summary": rel(summary_path),
                    "reason": "legacy summary lacks strict version/config binding marker",
                }
            )
            continue
        accepted.append(validate_package(flashdb_root, prefix, summary_path, summary))

    if legacy_incomplete:
        slices = ", ".join(item["slice_id"] for item in legacy_incomplete)
        raise SystemExit(f"incomplete strict FlashDB L3 evidence for passed summaries: {slices}")
    require(accepted, "no consumable FlashDB L3 evidence packages found")
    return {
        "schema_version": 1,
        "status": "passed",
        "target_id": "flashdb",
        "evidence_root": rel(evidence_root),
        "slice_count": len(accepted),
        "legacy_incomplete_count": len(legacy_incomplete),
        "legacy_incomplete": legacy_incomplete,
        "slices": accepted,
    }


def is_consumable_package(root: Path, prefix: str, summary: dict[str, Any]) -> bool:
    negative = summary_path_value(summary, ["negative_diff", "report"]) or summary_path_value(summary, ["diff", "negative"])
    final = root / f"{prefix}-final-verification.json"
    negative_file = root / f"{prefix}-negative-diff.json"
    return final.exists() and (bool(negative) or negative_file.exists())


def validate_package(root: Path, prefix: str, summary_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    slice_id = str(summary.get("slice_id") or prefix.removeprefix("l3-"))
    require(slice_id, f"{prefix} summary missing slice_id")

    required = {
        "cache-metadata": resolve_report(root, prefix, "cache-metadata", summary, ["evidence", "cache_metadata", "path"]),
        "config-profile": resolve_report(root, prefix, "config-profile", summary, ["evidence", "config_profile", "path"]),
        "context-pack": root / f"{prefix}-context-pack.json",
        "slice-contract": root / f"{prefix}-slice-contract.json",
        "pointer-graph": resolve_report(
            root,
            prefix,
            "pointer-graph",
            summary,
            ["evidence", "pointer_dependency_graph", "path"],
        ),
        "test-translation": resolve_report(root, prefix, "test-translation", summary, ["evidence", "test_translation", "path"]),
        "c-oracle": resolve_report(root, prefix, "c-oracle", summary, ["c_oracle", "report"], ["c_oracle_report"]),
        "rust-report": root / f"{prefix}-rust-report.json",
        "diff": resolve_report(root, prefix, "diff", summary, ["diff", "report"], ["diff", "positive"], ["diff_report"]),
        "negative-diff": resolve_report(
            root,
            prefix,
            "negative-diff",
            summary,
            ["negative_diff", "report"],
            ["diff", "negative"],
            ["negative_diff_report"],
        ),
        "rust-check": resolve_report(root, prefix, "rust-check", summary, ["rust_check", "report"]),
        "unsafe-scan": resolve_report(root, prefix, "unsafe-scan", summary, ["unsafe", "report"]),
        "unsafe-ledger": root / f"{prefix}-unsafe-ledger.json",
        "performance-smoke": resolve_report(
            root,
            prefix,
            "performance-smoke",
            summary,
            ["performance_smoke", "report"],
        ),
        "final-verification": root / f"{prefix}-final-verification.json",
        "summary": summary_path,
        "version-config-binding": resolve_report(
            root,
            prefix,
            "version-config-binding",
            summary,
            ["evidence", "version_or_config_binding", "path"],
        ),
    }

    loaded = {}
    for label, path in required.items():
        if not path.exists():
            raise SystemExit(f"{slice_id} missing {label}: {path}")
        loaded[label] = load_json(path)

    c_oracle = summary.get("c_oracle", {})
    require(
        c_oracle.get("marker") == "C_ORACLE_GENERATED"
        or c_oracle.get("toolchain_status") == "C_ORACLE_GENERATED"
        or c_oracle.get("status") == "passed"
        or summary.get("c_oracle_status") == "C_ORACLE_GENERATED"
        or loaded["c-oracle"].get("toolchain_status") == "C_ORACLE_GENERATED",
        f"{slice_id} c oracle is not accepted",
    )
    require(
        summary.get("diff_status") in (None, "passed"),
        f"{slice_id} schema diff status {summary.get('diff_status')!r} not in ['passed']",
    )
    require_status(summary.get("diff", {}), slice_id, "schema diff", {"passed"}, optional_key="status")
    require_positive_diff(slice_id, loaded["diff"])
    require_final_verification(slice_id, loaded["final-verification"])
    require_summary_evidence_hashes(slice_id, root, summary)
    require_negative_diff(slice_id, summary, loaded["negative-diff"])
    require_unsafe(slice_id, summary, loaded["unsafe-scan"], loaded["unsafe-ledger"])
    require_version_binding(slice_id, root, loaded["version-config-binding"])
    require_same_slice_binding(slice_id, summary, loaded)

    return {
        "slice_id": slice_id,
        "summary": rel(summary_path),
        "status": "passed",
        "c_oracle": "passed",
        "schema_diff": "passed",
        "negative_diff": "passed",
        "unsafe": "passed",
        "strict_manifest_complete": True,
        "evidence": {label: rel(path) for label, path in required.items()},
    }


def require_positive_diff(slice_id: str, diff_report: dict[str, Any]) -> None:
    status = diff_report.get("status")
    require(status == "passed", f"{slice_id} positive diff status must be passed: {status!r}")
    mismatch = diff_report.get("first_mismatch")
    require(not mismatch, f"{slice_id} positive diff recorded first_mismatch: {mismatch!r}")


def require_final_verification(slice_id: str, final_report: dict[str, Any]) -> None:
    status = final_report.get("status")
    require(status == "passed", f"{slice_id} final verification status must be passed: {status!r}")

    diff_status = final_report.get("diff_status")
    if diff_status is not None:
        require(diff_status == "passed", f"{slice_id} final verification diff_status must be passed: {diff_status!r}")

    c_oracle_status = final_report.get("c_oracle_toolchain_status")
    if c_oracle_status is not None:
        require(
            c_oracle_status == "C_ORACLE_GENERATED",
            f"{slice_id} final verification c_oracle_toolchain_status must be C_ORACLE_GENERATED: {c_oracle_status!r}",
        )

    checks = final_report.get("checks")
    if checks is None:
        return
    require(isinstance(checks, list), f"{slice_id} final verification checks must be a list")
    for index, check in enumerate(checks):
        require(isinstance(check, dict), f"{slice_id} final verification check {index} must be an object")
        check_name = str(check.get("name") or check.get("id") or index)
        check_status = check.get("status")
        if check_status is not None:
            require(
                str(check_status) not in {"failed", "error", "blocked"},
                f"{slice_id} final verification check {check_name} failed with status {check_status!r}",
            )
        exit_code = check.get("exit_code")
        if exit_code is not None:
            require(
                int(exit_code) == 0,
                f"{slice_id} final verification check {check_name} failed with exit_code {exit_code!r}",
            )


def require_summary_evidence_hashes(slice_id: str, root: Path, summary: dict[str, Any]) -> None:
    for label, value in iter_summary_evidence_refs(summary.get("evidence"), []):
        if not isinstance(value, dict):
            continue
        declared = value.get("sha256")
        path_value = value.get("path") or value.get("report")
        if not declared or not path_value:
            continue
        path = resolve_evidence_path(root, str(path_value))
        require(path.exists(), f"{slice_id} evidence hash target is missing for {'.'.join(label)}: {path_value}")
        actual = sha256(path)
        require(
            str(declared) == actual,
            f"{slice_id} evidence sha256 mismatch for {'.'.join(label)}: declared {declared}, actual {actual}",
        )


def iter_summary_evidence_refs(value: Any, path: list[str]) -> list[tuple[list[str], Any]]:
    if isinstance(value, dict):
        refs = [(path, value)] if ("sha256" in value and ("path" in value or "report" in value)) else []
        for key, child in value.items():
            refs.extend(iter_summary_evidence_refs(child, [*path, str(key)]))
        return refs
    if isinstance(value, list):
        refs = []
        for index, child in enumerate(value):
            refs.extend(iter_summary_evidence_refs(child, [*path, str(index)]))
        return refs
    return []


def require_same_slice_binding(slice_id: str, summary: dict[str, Any], loaded: dict[str, dict[str, Any]]) -> None:
    target_id = str(summary.get("target_id") or "flashdb")
    source_commit = str(summary.get("source_commit") or "")
    fixture = summary.get("fixture", {})
    fixture_hash = ""
    if isinstance(fixture, dict):
        fixture_hash = str(fixture.get("hash_short") or fixture.get("fixture_hash") or fixture.get("hash") or "")

    for label, report in loaded.items():
        report_slice = report.get("slice_id")
        if report_slice is not None:
            require(str(report_slice) == slice_id, f"{slice_id} {label} slice_id mismatch: {report_slice}")
        report_target = report.get("target_id")
        if report_target is not None:
            require(str(report_target) == target_id, f"{slice_id} {label} target_id mismatch: {report_target}")
        report_source = report.get("source_commit") or summary_path_value(report, ["source", "commit"])
        if report_source is not None and source_commit:
            require(str(report_source) == source_commit, f"{slice_id} {label} source_commit mismatch: {report_source}")
        report_fixture_hash = report.get("fixture_hash") or summary_path_value(report, ["fixture", "hash_short"])
        if report_fixture_hash is not None and fixture_hash:
            require(
                str(report_fixture_hash) == fixture_hash,
                f"{slice_id} {label} fixture hash mismatch: {report_fixture_hash}",
            )


def resolve_report(root: Path, prefix: str, suffix: str, summary: dict[str, Any], *paths: list[str]) -> Path:
    for path_keys in paths:
        value = summary_path_value(summary, path_keys)
        if value:
            return resolve_evidence_path(root, str(value))
    return root / f"{prefix}-{suffix}.json"


def summary_path_value(summary: dict[str, Any], keys: list[str]) -> Any:
    value: Any = summary
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def resolve_evidence_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    parts = path.parts
    if len(parts) >= 3 and parts[0] == "validation" and parts[1] == "evidence" and parts[2] == "flashdb":
        return root.joinpath(*parts[3:])
    candidate = REPO_ROOT / path
    if candidate.exists():
        return candidate
    if len(parts) == 1:
        return root / path.name
    return candidate


def require_negative_diff(slice_id: str, summary: dict[str, Any], negative_report: dict[str, Any]) -> None:
    mismatch = (
        summary_path_value(summary, ["negative_diff", "first_mismatch"])
        or summary_path_value(summary, ["diff", "negative_first_mismatch"])
        or negative_report.get("first_mismatch")
        or negative_report.get("mutation_detected")
        or negative_report.get("detected")
    )
    require(bool(mismatch), f"{slice_id} negative diff did not record detected mismatch")
    status = str(negative_report.get("status") or summary_path_value(summary, ["negative_diff", "status"]) or "")
    require(
        status in {"expected_failed", "passed", "failed"},
        f"{slice_id} negative diff status is not recognized: {status!r}",
    )


def require_unsafe(
    slice_id: str,
    summary: dict[str, Any],
    unsafe_scan: dict[str, Any],
    unsafe_ledger: dict[str, Any],
) -> None:
    summary_unsafe = summary.get("unsafe") or summary.get("implementation") or {}
    scan_status = str(unsafe_scan.get("status") or summary_unsafe.get("status") or "passed")
    require(scan_status == "passed", f"{slice_id} unsafe scan status must be passed")
    count = int_value(
        unsafe_scan.get("first_party_non_test_unsafe_count"),
        unsafe_scan.get("unsafe_count"),
        summary_unsafe.get("first_party_non_test_unsafe_count"),
        summary_unsafe.get("unsafe_blocks"),
        0,
    )
    ratio = float_value(unsafe_scan.get("unsafe_ratio"), summary_unsafe.get("unsafe_ratio"), 0.0)
    require(count == 0 or ratio < 0.10, f"{slice_id} unsafe ratio must remain below 10%")
    ledger_count = int_value(
        unsafe_ledger.get("first_party_non_test_unsafe_count"),
        unsafe_ledger.get("unsafe_count"),
        count,
    )
    require(ledger_count == count, f"{slice_id} unsafe ledger count does not match scan")


def require_version_binding(slice_id: str, root: Path, version_binding: dict[str, Any]) -> None:
    version_manifest = version_binding.get("version_manifest")
    require(isinstance(version_manifest, dict), f"{slice_id} version binding missing version_manifest")
    manifest_value = version_manifest.get("path")
    require(manifest_value, f"{slice_id} version binding missing version_manifest.path")
    manifest_path = resolve_evidence_path(root, str(manifest_value))
    require(manifest_path.exists(), f"{slice_id} version manifest is missing: {manifest_value}")
    try:
        validate_version_binding(manifest_path, REPO_ROOT / "flashDB_rust" / "Cargo.toml")
    except SystemExit as exc:
        raise SystemExit(f"{slice_id} version manifest binding failed: {exc}") from exc


def require_status(
    report: dict[str, Any],
    slice_id: str,
    label: str,
    allowed: set[str],
    *,
    optional_key: str = "status",
) -> None:
    status = report.get(optional_key)
    if status is None:
        return
    require(str(status) in allowed, f"{slice_id} {label} status {status!r} not in {sorted(allowed)}")


def int_value(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        return int(value)
    return 0


def float_value(*values: Any) -> float:
    for value in values:
        if value is None:
            continue
        return float(value)
    return 0.0


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
