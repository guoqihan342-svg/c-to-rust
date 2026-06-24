#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORTING_BOUNDARY = (
    "L1 failure classification is diagnostic only. It does not change project "
    "L1 status, prove remediation, or imply C/Rust semantic equivalence."
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


def normalize_path(path_text: str | None) -> str | None:
    if not path_text:
        return None
    return str(path_text).replace("\\", "/")


def path_from_log(log_path: str) -> Path:
    normalized = normalize_path(log_path) or ""
    if normalized.startswith("/mnt/c/"):
        if Path("/mnt/c").exists():
            return Path(normalized)
        return Path("C:/") / normalized[len("/mnt/c/") :]
    return Path(normalized)


def tail_text(path_text: str | None, max_lines: int) -> tuple[str, bool]:
    if not path_text:
        return "", False
    path = path_from_log(path_text)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", False
    return "\n".join(lines[-max_lines:]), True


def collect_excerpt(command: dict[str, Any], fallback_logs: list[str], max_lines: int) -> tuple[str, list[str], list[str]]:
    candidate_logs: list[str] = []
    for key in ("stderr_log", "stdout_log"):
        value = normalize_path(command.get(key))
        if value:
            candidate_logs.append(value)
    for value in command.get("log_paths", []) or []:
        value = normalize_path(value)
        if value and value not in candidate_logs:
            candidate_logs.append(value)
    for value in fallback_logs:
        value = normalize_path(value)
        if value and value not in candidate_logs:
            candidate_logs.append(value)

    excerpts = []
    loaded = []
    for log_path in candidate_logs:
        text, ok = tail_text(log_path, max_lines)
        if ok:
            loaded.append(log_path)
        if text.strip():
            excerpts.append(f"--- {log_path} ---\n{text}")
    return "\n".join(excerpts).strip(), candidate_logs, loaded


def failed_command(evidence: dict[str, Any]) -> dict[str, Any]:
    commands = evidence.get("commands", []) or []
    failed_step = evidence.get("failed_step")
    if failed_step:
        for command in commands:
            if command.get("label") == failed_step:
                return command
    for command in commands:
        if command.get("timed_out") or command.get("exit_code") not in (0, None):
            return command
    if commands:
        return commands[-1]
    return {}


def marker(text: str, *patterns: str) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def classify(evidence: dict[str, Any], command: dict[str, Any], excerpt: str) -> tuple[str, str, str]:
    project_id = str(evidence.get("project_id", ""))
    summary = str(evidence.get("failure_summary") or "")
    command_text = str(command.get("command") or "")
    combined = "\n".join([summary, command_text, excerpt])
    exit_code = command.get("exit_code")

    if not evidence.get("failed_step") and evidence.get("status") == "failed":
        commands = evidence.get("commands", []) or []
        if commands and all(command.get("exit_code") in (0, None) for command in commands):
            return (
                "evidence-gap",
                "high",
                "Regenerate this L1 evidence with an explicit smoke command or failed step before attempting remediation.",
            )
    if command.get("timed_out") or "timed out" in summary.lower():
        return (
            "timeout",
            "high",
            "Create a bounded smoke subset or raise timeout only after measuring where the test stalls.",
        )
    if marker(combined, "nasm not found or too old"):
        return (
            "missing-assembler",
            "high",
            "Install or update nasm, or change the FFmpeg L1 recipe to disable x86 assembly explicitly.",
        )
    if marker(combined, "freertos_config target not specified", "FreeRTOSConfig.h"):
        return (
            "invalid-build-recipe",
            "high",
            "Add a minimal FreeRTOS app/config wrapper that provides freertos_config and FreeRTOSConfig.h.",
        )
    if marker(combined, "Package 'libffi'", "ffi.h: No such file or directory"):
        return (
            "missing-dev-package",
            "high",
            "Install libffi development/pkg-config files or disable the MicroPython unix FFI option in a separate change.",
        )
    if marker(combined, "Unable to use libgit2's HTTPS backend"):
        return (
            "build-config-conflict",
            "high",
            "Adjust the libgit2 L1 recipe so NTLM crypto is not enabled with the HTTPS backend disabled.",
        )
    if marker(combined, "./configure: No such file or directory"):
        return (
            "bootstrap-required",
            "high",
            "Run the project's bootstrap/autogen step for git checkouts or use a release tarball with generated configure.",
        )
    if marker(combined, "mujs.h: No such file or directory"):
        return (
            "missing-vendored-dependency",
            "high",
            "Clone or initialize MuPDF third-party dependencies recursively, or disable tool targets that require MuJS.",
        )
    if marker(combined, "libnl-genl-3.0 package not found", "libnl-genl-3.0"):
        return (
            "missing-dev-package",
            "high",
            "Install libnl-genl-3 development/pkg-config files or disable OpenVPN DCO if it is outside L1 scope.",
        )
    if marker(combined, 'Dependency "glib-2.0" not found', "glib-2.0"):
        return (
            "missing-dev-package",
            "high",
            "Install glib-2.0 development/pkg-config files before retrying QEMU L1 configure.",
        )
    if marker(combined, "meson: command not found"):
        return (
            "missing-build-tool",
            "high",
            "Install or expose Meson, or use a project-supported Python/venv Meson entrypoint.",
        )
    if marker(combined, "cannot be run as root"):
        return (
            "environment-restriction",
            "high",
            "Rerun this smoke under a non-root WSL user or choose a root-safe smoke command.",
        )
    if str(command.get("label", "")).lower().endswith("clone") or "clone" in str(command.get("label", "")).lower():
        if exit_code not in (0, None):
            return (
                "clone-or-network-failure",
                "medium",
                "Retry with a fresh external work root; if repeated, use a pinned mirror or non-shallow clone policy.",
            )
    if exit_code == 127 or marker(combined, "command not found", "not found"):
        if marker(command_text, "west "):
            return (
                "missing-build-tool",
                "high",
                "Install or provide Zephyr west/toolchain prerequisites in a separate dependency-prep change.",
            )
        if marker(command_text, "./examples/"):
            return (
                "missing-built-artifact-or-command-mismatch",
                "medium",
                "Inspect build output and adjust the smoke binary path or build target in a separate command-repair change.",
            )
        return (
            "missing-build-tool-or-command",
            "medium",
            "Inspect the failed command and stderr; install the missing tool or repair the command in a separate change.",
        )
    if marker(combined, "no such file or directory"):
        return (
            "missing-file-or-command-mismatch",
            "medium",
            "Verify generated paths and build targets, then update the smoke command if the binary moved.",
        )
    if marker(combined, "configure: error", "ERROR:", "ERROR:"):
        return (
            "configure-or-dependency-failure",
            "medium",
            "Inspect configure logs and add a dependency-prep or feature-reduction change.",
        )
    if marker(combined, "clock skew detected"):
        return (
            "build-environment-clock-skew",
            "medium",
            "Retry in a fresh work root after normalizing filesystem timestamps; then classify remaining compiler errors.",
        )
    if marker(combined, "fatal:", "early eof", "rpc failed", "gnutls recv error"):
        return (
            "clone-or-network-failure",
            "medium",
            "Retry clone in a fresh work root and consider reducing shallow-clone assumptions for this target.",
        )
    if project_id in {"freertos-kernel", "qemu", "libgit2", "openvpn", "mupdf", "micropython", "ffmpeg"}:
        return (
            "build-or-command-failure",
            "low",
            "Inspect the full failed-step logs and split remediation into dependency-prep or smoke-command repair.",
        )
    return (
        "build-failure",
        "low",
        "Inspect full logs before changing dependencies or commands; keep the project failed until a rerun passes.",
    )


def markdown_table(rows: list[dict[str, Any]], category_counts: dict[str, int]) -> str:
    lines = [
        "# L1 Failure Classification",
        "",
        "中文：本报告只对 L1 native C build/test smoke 失败进行诊断分类，不代表项目已经修复，也不代表 Rust 迁移或语义等价已经证明。",
        "",
        "English: this report only classifies failed L1 native C build/test smoke attempts. It does not claim remediation, Rust migration, or C/Rust semantic equivalence.",
        "",
        "## Summary",
        "",
        f"- Generated at UTC: `{utc_now()}`",
        f"- Failed project count: `{len(rows)}`",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for category, count in sorted(category_counts.items()):
        lines.append(f"| `{category}` | {count} |")
    lines.extend(
        [
            "",
            "## Projects",
            "",
            "| Project | Category | Confidence | Failed step | Exit | Recommendation |",
            "|---|---|---|---|---:|---|",
        ]
    )
    for row in rows:
        recommendation = str(row["recommended_next_action"]).replace("|", "\\|")
        lines.append(
            "| `{project}` | `{category}` | `{confidence}` | `{step}` | {exit_code} | {recommendation} |".format(
                project=row["project_id"],
                category=row["category"],
                confidence=row["confidence"],
                step=row.get("failed_step") or "",
                exit_code=row.get("exit_code") if row.get("exit_code") is not None else "",
                recommendation=recommendation,
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            REPORTING_BOUNDARY,
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify failed L1 native validation attempts.")
    parser.add_argument("--tail-lines", type=int, default=80, help="Number of log tail lines to capture per log.")
    parser.add_argument(
        "--summary",
        default=str(repo_root() / "validation" / "evidence" / "l1-native-summary.json"),
        help="Path to l1-native-summary.json.",
    )
    parser.add_argument(
        "--json-output",
        default=str(repo_root() / "validation" / "evidence" / "l1-failure-classification.json"),
    )
    parser.add_argument(
        "--markdown-output",
        default=str(repo_root() / "validation" / "evidence" / "l1-failure-classification.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_path = Path(args.summary)
    summary = read_json(summary_path)
    failed_projects = list(summary.get("failed_projects", []))
    per_project = summary.get("per_project_evidence", {})

    rows: list[dict[str, Any]] = []
    for project_id in failed_projects:
        evidence_path = repo_root() / per_project[project_id]
        evidence = read_json(evidence_path)
        command = failed_command(evidence)
        fallback_logs = [normalize_path(path) for path in evidence.get("log_paths", []) or [] if normalize_path(path)]
        excerpt, candidate_logs, loaded_logs = collect_excerpt(command, fallback_logs, args.tail_lines)
        category, confidence, next_action = classify(evidence, command, excerpt)
        rows.append(
            {
                "project_id": project_id,
                "project_name": evidence.get("project_name") or project_id,
                "status": evidence.get("status"),
                "category": category,
                "confidence": confidence,
                "recommended_next_action": next_action,
                "evidence_path": repo_relative(evidence_path),
                "source_results_path": normalize_path(evidence.get("source_results_path")),
                "failed_step": evidence.get("failed_step") or command.get("label"),
                "failed_command": command.get("command"),
                "exit_code": command.get("exit_code"),
                "timed_out": bool(command.get("timed_out", False)),
                "failure_summary": evidence.get("failure_summary") or "",
                "log_paths": candidate_logs,
                "loaded_log_paths": loaded_logs,
                "log_excerpt": excerpt,
            }
        )

    category_counts = dict(Counter(row["category"] for row in rows))
    payload = {
        "schema_version": 1,
        "command": "classify-l1-native-failures",
        "generated_at_utc": utc_now(),
        "summary_path": repo_relative(summary_path) if summary_path.is_relative_to(repo_root()) else str(summary_path),
        "failed_project_count": len(failed_projects),
        "classified_count": len(rows),
        "category_counts": category_counts,
        "projects": rows,
        "reporting_boundary": REPORTING_BOUNDARY,
    }

    json_output = Path(args.json_output)
    markdown_output = Path(args.markdown_output)
    write_json(json_output, payload)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.write_text(markdown_table(rows, category_counts), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("failed_project_count", "classified_count", "category_counts")}, indent=2))
    return 0 if len(rows) == len(failed_projects) else 1


if __name__ == "__main__":
    raise SystemExit(main())
