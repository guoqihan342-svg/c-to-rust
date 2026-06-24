#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aggregate_wave2_l1 import (
    REPORTING_BOUNDARY,
    build_l1_summary,
    load_catalog,
    normalize_project,
    normalize_result_path,
    read_json,
    repo_root,
    summarize_worker_source,
    utc_now,
    write_json,
)


REMEDIATION_TARGETS = [
    "ffmpeg",
    "hdf5",
    "libgit2",
    "librdkafka",
    "openvpn",
    "libpcap",
    "tcpdump",
    "libuv",
    "libevent",
]

DEFERRED_PROJECTS = {
    "freertos-kernel": "Needs an application/config wrapper or an explicit official-example scope decision.",
    "systemd": "Needs Meson availability.",
    "zephyr": "Needs west and Zephyr toolchain setup.",
    "qemu": "Needs glib development package availability.",
    "micropython": "Needs libffi development package or an explicit minimal-variant scope decision.",
    "linux": "Needs network retry or mirror policy.",
    "mbedtls": "Needs fresh filesystem/timestamp normalization before command repair.",
    "mupdf": "Needs third-party submodule remediation in a separate batch.",
    "openvpn": "DCO was disabled, but Linux configure still requires libcap-ng development package availability.",
}

RECIPE_CHANGES = {
    "ffmpeg": "Disable x86 assembly and run the repo-local ffmpeg binary.",
    "hdf5": "Replace full upstream ctest with bounded HDF5 tool version smoke commands.",
    "libgit2": "Disable NTLM auth when HTTPS is disabled.",
    "librdkafka": "Build rdkafka_example before running its config-list smoke.",
    "openvpn": "Disable DCO for the L1 smoke; rerun exposed mandatory libcap-ng dependency.",
    "libpcap": "Run autogen for git checkouts and smoke pcap-config.",
    "tcpdump": "Run autogen for git checkouts; dependency on discoverable libpcap remains auditable.",
    "libuv": "Use UV_RUN_AS_ROOT=1 for a root-safe test-list smoke.",
    "libevent": "Use an explicit short CTest smoke to close the previous evidence gap.",
}


def collect_current_projects(payloads: list[tuple[Path, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    current: dict[str, dict[str, Any]] = {}
    for source_path, payload in payloads:
        for project in payload.get("projects", []):
            project_id = str(project.get("target_id"))
            current[project_id] = {
                "status": project.get("status", "other"),
                "failed_step": project.get("failed_step"),
                "failure_summary": project.get("failure_summary") or "",
                "source_results_path": normalize_result_path(str(source_path)),
                "work_root": normalize_result_path(str(project.get("work_root", ""))),
            }
    return current


def build_remediation_summary(
    worker_sources: dict[str, dict[str, Any]],
    current_projects: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    attempted = [project_id for project_id in REMEDIATION_TARGETS if project_id in current_projects]
    passed = sorted(
        project_id
        for project_id in attempted
        if current_projects[project_id].get("status") == "passed"
    )
    failed = sorted(
        project_id
        for project_id in attempted
        if current_projects[project_id].get("status") == "failed"
    )
    other = sorted(
        project_id
        for project_id in attempted
        if current_projects[project_id].get("status") not in {"passed", "failed"}
    )
    return {
        "schema_version": 1,
        "command": "aggregate-l1-low-cost-remediation",
        "level": "L1",
        "generated_at_utc": utc_now(),
        "candidate_projects": REMEDIATION_TARGETS,
        "attempted_count": len(attempted),
        "passed_count": len(passed),
        "failed_count": len(failed),
        "other_count": len(other),
        "attempted_projects": attempted,
        "passed_projects": passed,
        "failed_projects": failed,
        "other_projects": other,
        "not_attempted_candidate_projects": [
            project_id for project_id in REMEDIATION_TARGETS if project_id not in current_projects
        ],
        "project_results": {
            project_id: current_projects[project_id] for project_id in attempted
        },
        "recipe_changes": RECIPE_CHANGES,
        "deferred_projects": DEFERRED_PROJECTS,
        "worker_result_sources": worker_sources,
        "reporting_boundary": REPORTING_BOUNDARY,
    }


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# L1 Low-Cost Remediation",
        "",
        "中文：本报告只记录 L1 native C build/test smoke 的低成本命令修复重跑结果，不证明 Rust 迁移、unsafe 比例、性能保持或 C/Rust 语义等价。",
        "English: this report only records low-cost command remediation reruns for L1 native C build/test smoke. It does not prove Rust migration, unsafe budget compliance, performance preservation, or C/Rust semantic equivalence.",
        "",
        "## Summary",
        "",
        f"- Generated at UTC: `{summary['generated_at_utc']}`",
        f"- Candidate project count: `{len(summary['candidate_projects'])}`",
        f"- Attempted count: `{summary['attempted_count']}`",
        f"- Passed count: `{summary['passed_count']}`",
        f"- Failed count: `{summary['failed_count']}`",
        f"- Other count: `{summary['other_count']}`",
        "",
        "## Attempted Projects",
        "",
        "| Project | Status | Failed step | Failure summary |",
        "|---|---|---|---|",
    ]
    for project_id in summary["attempted_projects"]:
        result = summary["project_results"][project_id]
        lines.append(
            "| `{}` | `{}` | `{}` | {} |".format(
                project_id,
                result.get("status", ""),
                result.get("failed_step") or "",
                str(result.get("failure_summary") or "").replace("|", "\\|"),
            )
        )

    lines.extend(
        [
            "",
            "## Recipe Changes",
            "",
            "| Project | Change |",
            "|---|---|",
        ]
    )
    for project_id in summary["candidate_projects"]:
        lines.append(f"| `{project_id}` | {summary['recipe_changes'].get(project_id, '')} |")

    lines.extend(
        [
            "",
            "## Deferred Projects",
            "",
            "| Project | Reason |",
            "|---|---|",
        ]
    )
    for project_id, reason in summary["deferred_projects"].items():
        lines.append(f"| `{project_id}` | {reason} |")

    lines.extend(
        [
            "",
            "## Boundary",
            "",
            summary["reporting_boundary"],
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate low-cost L1 remediation worker results.")
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
    payloads: list[tuple[Path, dict[str, Any]]] = []
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

        payloads.append((path, payload))
        worker_sources[source_key] = summarize_worker_source(path, payload, True, None)
        source_group = str(payload.get("group") or source_key)
        for project in payload.get("projects", []):
            normalized = normalize_project(project, source_group, path)
            project_id = normalized["project_id"]
            output = repo_root() / "validation" / "evidence" / project_id / "l1-native-build.json"
            write_json(output, normalized)
            imported += 1

    current_projects = collect_current_projects(payloads)
    remediation_summary = build_remediation_summary(worker_sources, current_projects)
    l1_summary = build_l1_summary(catalog_ids, worker_sources, previous_worker_sources)

    evidence_root = repo_root() / "validation" / "evidence"
    write_json(evidence_root / "l1-low-cost-remediation-summary.json", remediation_summary)
    write_json(evidence_root / "l1-native-summary.json", l1_summary)
    write_markdown_report(evidence_root / "l1-low-cost-remediation-summary.md", remediation_summary)

    print(
        json.dumps(
            {
                "imported_project_evidence": imported,
                "remediation_attempted_count": remediation_summary["attempted_count"],
                "remediation_passed_count": remediation_summary["passed_count"],
                "remediation_failed_count": remediation_summary["failed_count"],
                "not_attempted_candidate_projects": remediation_summary[
                    "not_attempted_candidate_projects"
                ],
                "l1_attempted_count": l1_summary["attempted_count"],
                "l1_passed_count": l1_summary["passed_count"],
                "l1_failed_count": l1_summary["failed_count"],
            },
            indent=2,
        )
    )
    return 0 if imported > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
