#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GROUPS = {
    "network-protocol": ["haproxy", "memcached", "libpcap", "tcpdump", "openvpn"],
    "security-parser": ["libxml2", "wolfssl", "openssh-portable", "libgit2"],
    "media-data": ["x264", "hdf5", "imagemagick", "mupdf"],
    "system-virt": ["vim", "qemu", "systemd", "linux"],
    "messaging": ["librdkafka"],
}

DEFAULT_TIMEOUTS = {
    "clone": 1200,
    "tool_versions": 60,
    "build": 1800,
    "test": 600,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_catalog() -> dict[str, dict[str, Any]]:
    catalog_path = repo_root() / "validation" / "projects.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {str(target["id"]): target for target in catalog["targets"]}


def run_command(
    command: str,
    cwd: Path,
    log_dir: Path,
    label: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"{label}.stdout.log"
    stderr_path = log_dir / f"{label}.stderr.log"
    started = time.monotonic()
    timed_out = False

    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout, stderr_path.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr:
        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout_seconds,
                check=False,
            )
            exit_code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = 124
            stderr.write(f"\nTIMEOUT after {timeout_seconds} seconds\n")

    elapsed = round(time.monotonic() - started, 3)
    return {
        "label": label,
        "command": command,
        "cwd": str(cwd),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": elapsed,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "logs": [str(stdout_path), str(stderr_path)],
    }


def shell_json(command: str, cwd: Path) -> str | None:
    completed = subprocess.run(
        ["bash", "-lc", command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def collect_tool_versions(cwd: Path) -> dict[str, str | None]:
    version_commands = {
        "git": "git --version",
        "gcc": "gcc --version | head -n 1",
        "make": "make --version | head -n 1",
        "cmake": "cmake --version | head -n 1",
        "ninja": "ninja --version",
        "meson": "meson --version",
        "python3": "python3 --version",
        "uname": "uname -a",
    }
    return {name: shell_json(command, cwd) for name, command in version_commands.items()}


def failure_summary(step: dict[str, Any]) -> str:
    if step["timed_out"]:
        return f"{step['label']} timed out after {step['timeout_seconds']} seconds"
    return f"{step['label']} exited {step['exit_code']}"


def run_project(project_id: str, target: dict[str, Any], work_root: Path) -> dict[str, Any]:
    repos_dir = work_root / "repos"
    logs_dir = work_root / "logs" / project_id
    repo_dir = repos_dir / project_id
    repos_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []
    status = "passed"
    failed_step: dict[str, Any] | None = None

    clone_command = (
        f"git clone --depth 1 --branch {shlex.quote(str(target['expected_default_branch']))} "
        f"--single-branch {shlex.quote(str(target['repo_url']))} {shlex.quote(str(repo_dir))}"
    )
    step = run_command(clone_command, work_root, logs_dir, "01_clone", DEFAULT_TIMEOUTS["clone"])
    steps.append(step)
    if step["exit_code"] != 0:
        status = "failed"
        failed_step = step

    commit = None
    if status == "passed":
        commit = shell_json("git rev-parse HEAD", repo_dir)
        for index, command in enumerate(target["build_smoke"], start=2):
            step = run_command(
                command,
                repo_dir,
                logs_dir,
                f"{index:02d}_build_{index - 1}",
                DEFAULT_TIMEOUTS["build"],
            )
            steps.append(step)
            if step["exit_code"] != 0:
                status = "failed"
                failed_step = step
                break

    if status == "passed":
        offset = 2 + len(target["build_smoke"])
        for index, command in enumerate(target["test_smoke"], start=offset):
            step = run_command(
                command,
                repo_dir,
                logs_dir,
                f"{index:02d}_test_{index - offset + 1}",
                DEFAULT_TIMEOUTS["test"],
            )
            steps.append(step)
            if step["exit_code"] != 0:
                status = "failed"
                failed_step = step
                break

    return {
        "schema_version": 1,
        "level": "L1",
        "target_id": project_id,
        "project_name": target["name"],
        "repo_url": target["repo_url"],
        "expected_default_branch": target["expected_default_branch"],
        "status": status,
        "source_commit": commit,
        "external_clone_dir": str(repo_dir),
        "work_root": str(work_root),
        "tool_versions": collect_tool_versions(work_root),
        "steps": steps,
        "failed_step": failed_step["label"] if failed_step else None,
        "failure_summary": failure_summary(failed_step) if failed_step else None,
        "started_at_utc": None,
        "finished_at_utc": utc_now(),
        "reporting_boundary": (
            "L1 proves only pinned native C build/test smoke reproducibility. "
            "It is not Rust migration or C/Rust semantic equivalence evidence."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run wave2 L1 native C build/test smoke.")
    parser.add_argument("--work-root", required=True, help="External work root, preferably under c-to-rust-l1-work.")
    parser.add_argument("--group", choices=sorted(GROUPS), help="Named project group to run.")
    parser.add_argument("--projects", nargs="*", help="Explicit project ids to run.")
    parser.add_argument("--metadata-only", action="store_true", help="Print groups and exit without cloning.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = load_catalog()
    if args.metadata_only:
        print(json.dumps({"groups": GROUPS, "project_count": len(catalog)}, indent=2))
        return 0

    project_ids: list[str] = []
    if args.group:
        project_ids.extend(GROUPS[args.group])
    if args.projects:
        project_ids.extend(args.projects)
    project_ids = list(dict.fromkeys(project_ids))
    if not project_ids:
        raise SystemExit("Provide --group or --projects")

    unknown = [project_id for project_id in project_ids if project_id not in catalog]
    if unknown:
        raise SystemExit(f"Unknown project ids: {unknown}")

    work_root = Path(args.work_root).resolve()
    work_root.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    results = []
    for project_id in project_ids:
        project_result = run_project(project_id, catalog[project_id], work_root)
        project_result["started_at_utc"] = started_at
        results.append(project_result)

    summary = {
        "schema_version": 1,
        "command": "run-wave2-l1-native-validation",
        "level": "L1",
        "group": args.group,
        "work_root": str(work_root),
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "attempted_count": len(results),
        "passed_count": sum(1 for result in results if result["status"] == "passed"),
        "failed_count": sum(1 for result in results if result["status"] == "failed"),
        "projects": results,
    }
    output_path = work_root / "results.json"
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
