#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aggregate_wave2_l1 import (
    REPORTING_BOUNDARY,
    build_l1_summary,
    collect_all_project_evidence,
    load_catalog,
    normalize_project,
    normalize_result_path,
    read_json,
    repo_root,
    summarize_worker_source,
    utc_now,
    write_json,
)


REMAINING_TARGETS = ["ffmpeg", "micropython", "zephyr", "freertos-kernel"]


def build_remaining_summary(worker_sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    evidence_paths, statuses = collect_all_project_evidence(REMAINING_TARGETS)
    attempted = [project_id for project_id in REMAINING_TARGETS if project_id in evidence_paths]
    passed = sorted(project_id for project_id in attempted if statuses.get(project_id) == "passed")
    failed = sorted(project_id for project_id in attempted if statuses.get(project_id) == "failed")
    other = sorted(
        project_id
        for project_id in attempted
        if statuses.get(project_id) not in {"passed", "failed"}
    )
    return {
        "schema_version": 1,
        "command": "aggregate-remaining-l1-native-validation",
        "level": "L1",
        "generated_at_utc": utc_now(),
        "remaining_target_count": len(REMAINING_TARGETS),
        "status": "passed" if len(attempted) == len(REMAINING_TARGETS) else "incomplete",
        "attempted_count": len(attempted),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "other_count": len(other),
        "attempted_projects": attempted,
        "passed_projects": passed,
        "failed_projects": failed,
        "other_projects": other,
        "not_attempted_remaining_projects": [
            project_id for project_id in REMAINING_TARGETS if project_id not in evidence_paths
        ],
        "worker_result_sources": worker_sources,
        "per_project_evidence": {project_id: evidence_paths[project_id] for project_id in attempted},
        "reporting_boundary": REPORTING_BOUNDARY,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate remaining catalog L1 worker results.")
    parser.add_argument(
        "--previous-summary",
        default=str(repo_root() / "validation" / "evidence" / "l1-native-summary.json"),
        help="Existing l1-native-summary.json whose worker_result_sources should be preserved.",
    )
    parser.add_argument("results", nargs="+", help="Path(s) to worker results.json files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog_ids, _catalog = load_catalog()
    worker_sources: dict[str, dict[str, Any]] = {}
    previous_worker_sources: dict[str, Any] = {}
    imported = 0

    if args.previous_summary:
        try:
            previous_worker_sources = read_json(Path(args.previous_summary)).get("worker_result_sources", {})
        except (FileNotFoundError, json.JSONDecodeError):
            previous_worker_sources = {}

    for raw_path in args.results:
        path = Path(raw_path).expanduser().resolve()
        source_key = path.parent.name
        try:
            payload = read_json(path)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            worker_sources[source_key] = summarize_worker_source(path, None, False, str(exc))
            continue

        worker_sources[source_key] = summarize_worker_source(path, payload, True, None)
        source_group = str(payload.get("group") or source_key)
        for project in payload.get("projects", []):
            normalized = normalize_project(project, source_group, path)
            project_id = normalized["project_id"]
            output = repo_root() / "validation" / "evidence" / project_id / "l1-native-build.json"
            write_json(output, normalized)
            imported += 1

    remaining_summary = build_remaining_summary(worker_sources)
    l1_summary = build_l1_summary(catalog_ids, worker_sources, previous_worker_sources)
    write_json(repo_root() / "validation" / "evidence" / "remaining-l1-native-summary.json", remaining_summary)
    write_json(repo_root() / "validation" / "evidence" / "l1-native-summary.json", l1_summary)

    print(
        json.dumps(
            {
                "imported_project_evidence": imported,
                "remaining_status": remaining_summary["status"],
                "remaining_attempted_count": remaining_summary["attempted_count"],
                "remaining_passed_count": remaining_summary["passed_count"],
                "remaining_failed_count": remaining_summary["failed_count"],
                "l1_attempted_count": l1_summary["attempted_count"],
                "l1_passed_count": l1_summary["passed_count"],
                "l1_failed_count": l1_summary["failed_count"],
                "not_attempted_catalog_projects": l1_summary["not_attempted_catalog_projects"],
            },
            indent=2,
        )
    )
    return 0 if remaining_summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
