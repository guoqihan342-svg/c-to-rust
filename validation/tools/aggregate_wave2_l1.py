#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WAVE2_TARGETS = [
    "linux",
    "qemu",
    "systemd",
    "vim",
    "haproxy",
    "libxml2",
    "wolfssl",
    "libpcap",
    "tcpdump",
    "memcached",
    "libgit2",
    "librdkafka",
    "x264",
    "openvpn",
    "imagemagick",
    "mupdf",
    "hdf5",
    "openssh-portable",
]

REPORTING_BOUNDARY = (
    "This L1 summary proves native C baseline build/test smoke only. "
    "It does not prove Rust slice compilation, unsafe budget, C/Rust semantic "
    "equivalence, or performance preservation."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def repo_relative(path: Path) -> str:
    return path.relative_to(repo_root()).as_posix()


def normalize_result_path(path_text: str) -> str:
    return path_text.replace("\\", "/")


def load_catalog() -> tuple[list[str], dict[str, dict[str, Any]]]:
    catalog_path = repo_root() / "validation" / "projects.json"
    catalog = read_json(catalog_path)
    targets = {target["id"]: target for target in catalog["targets"]}
    return list(targets), targets


def normalize_step(step: dict[str, Any]) -> dict[str, Any]:
    logs = step.get("logs") or []
    stdout_log = step.get("stdout_log")
    stderr_log = step.get("stderr_log")
    log_paths = [normalize_result_path(str(log)) for log in logs]
    if not log_paths:
        log_paths = [
            normalize_result_path(str(path))
            for path in (stdout_log, stderr_log)
            if path
        ]
    return {
        "label": step.get("label"),
        "command": step.get("command"),
        "cwd": normalize_result_path(str(step.get("cwd", ""))),
        "exit_code": step.get("exit_code"),
        "timed_out": bool(step.get("timed_out", False)),
        "timeout_seconds": step.get("timeout_seconds"),
        "elapsed_seconds": step.get("elapsed_seconds"),
        "stdout_log": normalize_result_path(str(stdout_log)) if stdout_log else None,
        "stderr_log": normalize_result_path(str(stderr_log)) if stderr_log else None,
        "log_paths": log_paths,
    }


def normalize_project(
    project: dict[str, Any],
    source_group: str,
    source_path: Path,
) -> dict[str, Any]:
    commands = [normalize_step(step) for step in project.get("steps", [])]
    log_paths = []
    for command in commands:
        log_paths.extend(command.get("log_paths", []))

    return {
        "schema_version": 1,
        "level": "L1",
        "project_id": project["target_id"],
        "project_name": project.get("project_name"),
        "status": project.get("status"),
        "commit": project.get("source_commit"),
        "branch": project.get("expected_default_branch"),
        "repo_url": project.get("repo_url"),
        "external_clone_dir": normalize_result_path(str(project.get("external_clone_dir", ""))),
        "source_group": source_group,
        "source_results_path": normalize_result_path(str(source_path)),
        "work_root": normalize_result_path(str(project.get("work_root", ""))),
        "tool_versions": project.get("tool_versions", {}),
        "commands": commands,
        "failed_step": project.get("failed_step"),
        "failure_summary": project.get("failure_summary") or "",
        "started_at_utc": project.get("started_at_utc"),
        "finished_at_utc": project.get("finished_at_utc"),
        "log_paths": log_paths,
        "notes": [],
        "reporting_boundary": project.get("reporting_boundary") or REPORTING_BOUNDARY,
    }


def summarize_worker_source(path: Path, payload: dict[str, Any] | None, loaded: bool, error: str | None) -> dict[str, Any]:
    group = payload.get("group") if payload else None
    return {
        "path": normalize_result_path(str(path)),
        "loaded": loaded,
        "error": error,
        "group": group,
        "work_root": normalize_result_path(str(payload.get("work_root", ""))) if payload else None,
        "started_at_utc": payload.get("started_at_utc") if payload else None,
        "finished_at_utc": payload.get("finished_at_utc") if payload else None,
        "attempted_count": payload.get("attempted_count") if payload else 0,
        "passed_count": payload.get("passed_count") if payload else 0,
        "failed_count": payload.get("failed_count") if payload else 0,
    }


def collect_all_project_evidence(catalog_ids: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    evidence_root = repo_root() / "validation" / "evidence"
    evidence_paths: dict[str, str] = {}
    statuses: dict[str, str] = {}

    for project_id in catalog_ids:
        path = evidence_root / project_id / "l1-native-build.json"
        if not path.exists():
            continue
        evidence_paths[project_id] = repo_relative(path)
        try:
            statuses[project_id] = str(read_json(path).get("status", "other"))
        except json.JSONDecodeError:
            statuses[project_id] = "other"

    return evidence_paths, statuses


def build_l1_summary(
    catalog_ids: list[str],
    worker_sources: dict[str, dict[str, Any]],
    previous_worker_sources: dict[str, Any],
) -> dict[str, Any]:
    evidence_paths, statuses = collect_all_project_evidence(catalog_ids)
    passed = sorted(project_id for project_id, status in statuses.items() if status == "passed")
    failed = sorted(project_id for project_id, status in statuses.items() if status == "failed")
    other = sorted(
        project_id
        for project_id, status in statuses.items()
        if status not in {"passed", "failed"}
    )
    not_attempted = [project_id for project_id in catalog_ids if project_id not in evidence_paths]
    pass_threshold = 12
    return {
        "schema_version": 1,
        "command": "aggregate-l1-native-validation",
        "level": "L1",
        "generated_at_utc": utc_now(),
        "milestone_status": "passed" if len(passed) >= pass_threshold else "incomplete",
        "pass_threshold": pass_threshold,
        "catalog_target_count": len(catalog_ids),
        "attempted_count": len(evidence_paths),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "other_count": len(other),
        "passed_projects": passed,
        "failed_projects": failed,
        "other_projects": other,
        "not_attempted_catalog_projects": not_attempted,
        "external_workspace_root": "C:/Users/Administrator/Documents/c-to-rust-l1-work",
        "worker_result_sources": {**previous_worker_sources, **worker_sources},
        "per_project_evidence": evidence_paths,
        "reporting_boundary": REPORTING_BOUNDARY,
    }


def build_wave2_summary(
    worker_sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    evidence_paths, statuses = collect_all_project_evidence(WAVE2_TARGETS)
    attempted = [project_id for project_id in WAVE2_TARGETS if project_id in evidence_paths]
    passed = sorted(project_id for project_id in attempted if statuses.get(project_id) == "passed")
    failed = sorted(project_id for project_id in attempted if statuses.get(project_id) == "failed")
    other = sorted(
        project_id
        for project_id in attempted
        if statuses.get(project_id) not in {"passed", "failed"}
    )
    return {
        "schema_version": 1,
        "command": "aggregate-wave2-l1-native-validation",
        "level": "L1",
        "generated_at_utc": utc_now(),
        "wave2_target_count": len(WAVE2_TARGETS),
        "minimum_attempted_count": 12,
        "status": "passed" if len(attempted) >= 12 else "incomplete",
        "attempted_count": len(attempted),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "other_count": len(other),
        "attempted_projects": attempted,
        "passed_projects": passed,
        "failed_projects": failed,
        "other_projects": other,
        "not_attempted_wave2_projects": [
            project_id for project_id in WAVE2_TARGETS if project_id not in evidence_paths
        ],
        "worker_result_sources": worker_sources,
        "per_project_evidence": {project_id: evidence_paths[project_id] for project_id in attempted},
        "reporting_boundary": REPORTING_BOUNDARY,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate wave2 L1 worker results.")
    parser.add_argument(
        "--previous-summary",
        help="Optional existing l1-native-summary.json whose worker_result_sources should be preserved.",
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
        previous_summary_path = Path(args.previous_summary).expanduser().resolve()
        try:
            previous_worker_sources = read_json(previous_summary_path).get("worker_result_sources", {})
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

    wave2_summary = build_wave2_summary(worker_sources)
    l1_summary = build_l1_summary(catalog_ids, worker_sources, previous_worker_sources)
    write_json(repo_root() / "validation" / "evidence" / "wave2-l1-native-summary.json", wave2_summary)
    write_json(repo_root() / "validation" / "evidence" / "l1-native-summary.json", l1_summary)

    print(
        json.dumps(
            {
                "imported_project_evidence": imported,
                "wave2_status": wave2_summary["status"],
                "wave2_attempted_count": wave2_summary["attempted_count"],
                "wave2_passed_count": wave2_summary["passed_count"],
                "wave2_failed_count": wave2_summary["failed_count"],
                "l1_attempted_count": l1_summary["attempted_count"],
                "l1_passed_count": l1_summary["passed_count"],
                "l1_failed_count": l1_summary["failed_count"],
            },
            indent=2,
        )
    )
    return 0 if wave2_summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
