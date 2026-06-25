#!/usr/bin/env python3
"""Validate test-translation coverage evidence."""

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
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()

    paths = args.paths or discover_test_translation_paths(args.evidence_root)
    report = validate_test_translation_coverage(paths)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def discover_test_translation_paths(evidence_root: Path) -> list[Path]:
    return sorted(evidence_root.glob("**/*test-translation*.json"))


def validate_test_translation_coverage(paths: list[Path]) -> dict[str, Any]:
    require(paths, "no test translation evidence paths found")
    reports = []
    for path in paths:
        evidence = load_json(path)
        status = evidence.get("status")
        if status == "not_applicable":
            continue
        require(status == "recorded", f"{path} status must be recorded or not_applicable")
        coverage = evidence.get("coverage", {})
        require(coverage.get("main_paths"), f"{path} coverage.main_paths is empty")
        require(coverage.get("negative_cases"), f"{path} coverage.negative_cases is empty")
        mappings = evidence.get("translation_mappings", [])
        require(
            any(
                item.get("coverage_kind") in {"main_path", "oracle_replay"} and item.get("status") == "mapped"
                for item in mappings
            ),
            f"{path} translation_mappings lacks mapped main_path or oracle_replay",
        )
        negative_ref = evidence.get("evidence_links", {}).get("negative_diff", {})
        has_negative_mapping = any(
            item.get("coverage_kind") == "negative_case" and item.get("status") == "mapped" for item in mappings
        )
        has_negative_link = isinstance(negative_ref, dict) and negative_ref.get("status") in {"passed", "expected_failed"}
        require(
            has_negative_mapping or has_negative_link,
            f"{path} translation_mappings lacks mapped negative_case or negative_diff evidence link",
        )
        if has_negative_link:
            link = negative_ref.get("path")
            require(link, f"{path} negative_diff evidence link must include path")
            require(
                resolve_link(path, str(link)).exists(),
                f"{path} missing evidence link negative_diff: {link}",
            )
        for label, ref in evidence.get("evidence_links", {}).items():
            link = ref.get("path") if isinstance(ref, dict) else None
            if link:
                require(
                    resolve_link(path, link).exists(),
                    f"{path} missing evidence link {label}: {link}",
                )
        reports.append(
            {
                "path": rel(path),
                "target_id": evidence.get("target_id"),
                "slice_id": evidence.get("slice_id"),
                "main_path_count": len(coverage.get("main_paths", [])),
                "error_path_count": len(coverage.get("error_paths", [])),
                "negative_case_count": len(coverage.get("negative_cases", [])),
            }
        )
    require(reports, "no recorded test translation evidence was validated")
    return {
        "schema_version": 1,
        "status": "passed",
        "evidence_count": len(reports),
        "evidence": reports,
        "coverage_boundary": "Validates declared test translation coverage only; does not claim llvm-cov percentage or exhaustive semantic equivalence.",
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_link(owner: Path, link: str) -> Path:
    path = Path(link)
    if path.is_absolute():
        return path
    repo_candidate = REPO_ROOT / path
    if repo_candidate.exists():
        return repo_candidate
    return owner.parent / path


def require(condition: Any, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
