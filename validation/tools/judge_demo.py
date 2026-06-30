#!/usr/bin/env python3
"""Run the judge-facing harness demo and bind its public reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import opencode_agent_harness as harness
from validation.tools import validate_competition_run_summary

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        type=Path,
        default=Path("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"),
    )
    parser.add_argument("--run-id", default="competition-flashdb-before-after-exhibit")
    parser.add_argument("--out-root", type=Path, default=Path("target/competition-out-flashdb-before-after-exhibit"))
    parser.add_argument("--milestone-output", type=Path)
    args = parser.parse_args()

    report = run_judge_demo(
        profile_path=args.profile,
        run_id=args.run_id,
        out_root=args.out_root,
        milestone_output=args.milestone_output,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


def run_judge_demo(
    *,
    profile_path: Path,
    run_id: str,
    out_root: Path,
    milestone_output: Path | None = None,
    repo_root: Path = REPO_ROOT,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    profile_path = harness.repo_path(profile_path, repo_root=repo_root)
    out_root = harness.repo_path(out_root, repo_root=repo_root)
    summary_dir = out_root / "summary"
    harness_dir = out_root / "harness"
    summary_dir.mkdir(parents=True, exist_ok=True)
    harness_dir.mkdir(parents=True, exist_ok=True)

    summary_path = summary_dir / "competition-run-summary.json"
    batch_profile_report_path = harness_dir / "batch-profile-report.json"
    milestone_output = (
        harness.repo_path(milestone_output, repo_root=repo_root)
        if milestone_output is not None
        else summary_dir / "milestone-release-report.json"
    )

    commands: list[dict[str, Any]] = []
    commands.append(
        run_stage(
            stage="run_batch_profile",
            argv=[
                sys.executable,
                "-B",
                "-m",
                "validation.tools.opencode_agent_harness",
                "run-batch-profile",
                "--profile",
                harness.repo_relative(profile_path, repo_root=repo_root),
                "--run-id",
                run_id,
                "--out-root",
                harness.repo_relative(out_root, repo_root=repo_root),
            ],
            log_dir=harness_dir,
            repo_root=repo_root,
            command_runner=command_runner,
        )
    )
    if commands[-1]["exit_code"] == 0:
        commands.append(
            run_stage(
                stage="validate_summary",
                argv=[
                    sys.executable,
                    "-B",
                    "validation/tools/validate_competition_run_summary.py",
                    "--summary",
                    harness.repo_relative(summary_path, repo_root=repo_root),
                ],
                log_dir=harness_dir,
                repo_root=repo_root,
                command_runner=command_runner,
            )
        )
    if commands[-1]["exit_code"] == 0:
        commands.append(
            run_stage(
                stage="milestone_release_report",
                argv=[
                    sys.executable,
                    "-B",
                    "validation/tools/milestone_release_report.py",
                    "--competition-summary",
                    harness.repo_relative(summary_path, repo_root=repo_root),
                    "--batch-profile-report",
                    harness.repo_relative(batch_profile_report_path, repo_root=repo_root),
                    "--output",
                    harness.repo_relative(milestone_output, repo_root=repo_root),
                ],
                log_dir=harness_dir,
                repo_root=repo_root,
                command_runner=command_runner,
            )
        )

    report = build_report(
        profile_path=profile_path,
        run_id=run_id,
        out_root=out_root,
        summary_path=summary_path,
        batch_profile_report_path=batch_profile_report_path,
        milestone_report_path=milestone_output,
        commands=commands,
        repo_root=repo_root,
    )
    report_path = summary_dir / "judge-demo-report.json"
    report["artifacts"]["judge_demo_report"] = {
        "path": harness.repo_relative(report_path, repo_root=repo_root),
        "status": "present",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def run_stage(
    *,
    stage: str,
    argv: list[str],
    log_dir: Path,
    repo_root: Path,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    completed = command_runner(argv, cwd=repo_root, text=True, capture_output=True)
    stdout_path = log_dir / f"judge-demo-{stage}.stdout.log"
    stderr_path = log_dir / f"judge-demo-{stage}.stderr.log"
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    return {
        "stage": stage,
        "argv": portable_argv(argv),
        "exit_code": int(completed.returncode),
        "logs": {
            "stdout": harness.repo_relative(stdout_path, repo_root=repo_root),
            "stderr": harness.repo_relative(stderr_path, repo_root=repo_root),
        },
    }


def portable_argv(argv: list[str]) -> list[str]:
    if not argv:
        return []
    executable = Path(argv[0]).name.lower()
    if executable.startswith("python"):
        return ["python", *argv[1:]]
    return list(argv)


def build_report(
    *,
    profile_path: Path,
    run_id: str,
    out_root: Path,
    summary_path: Path,
    batch_profile_report_path: Path,
    milestone_report_path: Path,
    commands: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    profile = load_json_if_exists(profile_path)
    summary = load_json_if_exists(summary_path)
    workflow_metrics_path = resolve_workflow_metrics_path(summary, summary_path, repo_root=repo_root)
    workflow_metrics = load_json_if_exists(workflow_metrics_path) if workflow_metrics_path is not None else {}
    batch_profile_report = load_json_if_exists(batch_profile_report_path)
    before_after_path = resolve_report_path(
        batch_profile_report.get("before_after_exhibit_report"),
        fallback=summary_path.parent / "before-after-exhibit.json",
        repo_root=repo_root,
    )
    before_after_exhibit = load_json_if_exists(before_after_path) if before_after_path is not None else {}
    milestone_report = load_json_if_exists(milestone_report_path)
    command_status = "passed" if commands and all(command["exit_code"] == 0 for command in commands) else "failed"
    final_gate_status = str(summary.get("final_gate", {}).get("status", "missing"))
    exhibit_status = str(before_after_exhibit.get("status", "missing"))
    milestone_status = str(milestone_report.get("status", "missing"))
    status = (
        "passed"
        if command_status == "passed"
        and final_gate_status == "passed"
        and exhibit_status == "passed"
        and milestone_status in {"internal_preview", "release_candidate", "passed"}
        else "failed"
    )

    return {
        "schema_version": 1,
        "report_kind": "judge-demo-run-report",
        "status": status,
        "run_id": run_id,
        "profile_id": str(profile.get("profile_id", batch_profile_report.get("profile_id", "unknown"))),
        "proof_class": str(summary.get("proof_class", profile.get("proof_class", "unknown"))),
        "out_root": harness.repo_relative(out_root, repo_root=repo_root),
        "commands": commands,
        "artifacts": {
            "profile": artifact_ref(profile_path, repo_root=repo_root),
            "competition_summary": artifact_ref(summary_path, repo_root=repo_root),
            "workflow_metrics": artifact_ref(workflow_metrics_path, repo_root=repo_root),
            "batch_profile_report": artifact_ref(batch_profile_report_path, repo_root=repo_root),
            "before_after_exhibit": artifact_ref(before_after_path, repo_root=repo_root),
            "milestone_release_report": artifact_ref(milestone_report_path, repo_root=repo_root),
        },
        "metrics": {
            "final_gate": final_gate_status,
            "semantic_pass": nonnegative_int(summary.get("semantic_pass")),
            "units_total": nonnegative_int(workflow_metrics.get("units_total")),
            "units_converged": nonnegative_int(workflow_metrics.get("units_converged")),
            "unsafe_reduction": workflow_metrics.get("unsafe_reduction", {"status": "not_measured"}),
            "translation_before_after": workflow_metrics.get(
                "translation_before_after",
                {"status": "not_provided", "unit_count": 0},
            ),
            "stage_contracts": before_after_exhibit.get("stage_contracts", {}),
            "translation_coverage_numerator": (
                milestone_report.get("metrics", {}).get("translation_coverage_numerator")
                if isinstance(milestone_report.get("metrics"), dict)
                else None
            ),
            "milestone_status": milestone_status,
        },
        "claim_boundary": {
            "semantic_claim_source": "competition-run-summary.final_gate",
            "before_after_exhibit_role": (
                "judge-facing artifact binding and unsafe delta; not a translator-generated semantic pass claim"
            ),
            "must_not_claim": [
                "C2Rust-generated baseline when the profile says baseline output is skipped",
                "translator-generated semantic pass from accepted-evidence-authoritative runs",
                "translation coverage numerator increase from before/after exhibits alone",
            ],
        },
    }


def resolve_workflow_metrics_path(
    summary: dict[str, Any],
    summary_path: Path,
    *,
    repo_root: Path,
) -> Path | None:
    workflow_ref = summary.get("workflow_metrics")
    if not isinstance(workflow_ref, dict) or not workflow_ref.get("path"):
        return None
    return validate_competition_run_summary.resolve_summary_artifact(
        str(workflow_ref["path"]),
        summary_path=summary_path,
        repo_root=repo_root,
    )


def resolve_report_path(binding: Any, *, fallback: Path, repo_root: Path) -> Path | None:
    if isinstance(binding, dict) and binding.get("path"):
        return harness.repo_path(Path(str(binding["path"])), repo_root=repo_root)
    return fallback if fallback.exists() else None


def artifact_ref(path: Path | None, *, repo_root: Path) -> dict[str, Any]:
    if path is None:
        return {"status": "missing"}
    if not path.exists():
        return {"path": harness.repo_relative(path, repo_root=repo_root), "status": "missing"}
    return {
        "path": harness.repo_relative(path, repo_root=repo_root),
        "sha256": harness.sha256_file(path),
        "status": "present",
    }


def load_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def nonnegative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


if __name__ == "__main__":
    raise SystemExit(main())
