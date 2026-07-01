#!/usr/bin/env python3
"""Run judge-facing harness entrypoints and persist a readiness report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools import validate_judge_entrypoints as validator
from validation.tools import judge_milestone_bundle

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]

DEFAULT_REPORT = Path("target/competition-out-flashdb-judge-entrypoints/summary/judge-entrypoints-run-report.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=validator.DEFAULT_CONFIG)
    parser.add_argument(
        "--entrypoint-id",
        action="append",
        default=[],
        help="Entrypoint id to run. Omit to run every entrypoint in config order.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the plan without executing commands or requiring local artifacts.",
    )
    args = parser.parse_args()

    report = run_judge_entrypoints(
        config_path=args.config,
        entrypoint_ids=args.entrypoint_id,
        out_path=args.out,
        dry_run=args.dry_run,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"passed", "planned"} else 1


def run_judge_entrypoints(
    *,
    config_path: Path,
    entrypoint_ids: list[str],
    out_path: Path,
    dry_run: bool = False,
    repo_root: Path = REPO_ROOT,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    out_path = resolve_output_path(out_path, repo_root=repo_root)
    log_dir = out_path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    try:
        config_path = resolve_input_path(config_path, repo_root=repo_root)
        config = validator.load_json(config_path)
        config_ref = artifact_ref(config_path, repo_root=repo_root)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return write_run_report(
            out_path=out_path,
            status="failed",
            dry_run=dry_run,
            config_ref=invalid_config_ref(config_path, error),
            configured_entrypoint_count=0,
            command_results=[],
            preflight_validation={"status": "failed", "errors": [str(error)]},
            validation={"status": "skipped", "reason": "preflight_failed"},
            readiness_ref=None,
        )

    preflight_validation = validator.validate_config(config_path, require_local_artifacts=False, repo_root=repo_root)
    if preflight_validation.get("status") != "passed":
        return write_run_report(
            out_path=out_path,
            status="failed",
            dry_run=dry_run,
            config_ref=config_ref,
            configured_entrypoint_count=configured_entrypoint_count(config),
            command_results=[],
            preflight_validation=preflight_validation,
            validation={"status": "skipped", "reason": "preflight_failed"},
            readiness_ref=None,
        )

    try:
        selected = select_entrypoints(config, entrypoint_ids)
    except SystemExit as error:
        return write_run_report(
            out_path=out_path,
            status="failed",
            dry_run=dry_run,
            config_ref=config_ref,
            configured_entrypoint_count=configured_entrypoint_count(config),
            command_results=[],
            preflight_validation=preflight_validation,
            validation={"status": "skipped", "reason": "entrypoint_selection_failed", "errors": [str(error)]},
            readiness_ref=None,
        )

    command_results: list[dict[str, Any]] = []
    for entry in selected:
        command_results.append(
            run_entrypoint_command(
                entry,
                dry_run=dry_run,
                log_dir=log_dir,
                repo_root=repo_root,
                command_runner=command_runner,
            )
        )

    if dry_run:
        validation = {"status": "skipped", "reason": "dry_run", "preflight_status": preflight_validation.get("status")}
    elif all(result["exit_code"] == 0 for result in command_results):
        validation = validator.validate_config(config_path, require_local_artifacts=True, repo_root=repo_root)
    else:
        validation = {"status": "skipped", "reason": "failed_command"}

    readiness_path = out_path.parent / "judge-entrypoints-readiness.json"
    readiness_ref: dict[str, Any] | None = None
    if not dry_run and validation.get("status") == "passed":
        validator.write_readiness_report(validation, readiness_path, repo_root=repo_root)
        readiness_ref = artifact_ref(readiness_path, repo_root=repo_root)

    status = (
        "passed"
        if command_results
        and all(result["exit_code"] == 0 for result in command_results)
        and validation.get("status") == "passed"
        else "failed"
    )
    if dry_run:
        status = "planned"

    report = write_run_report(
        out_path=out_path,
        status=status,
        dry_run=dry_run,
        config_ref=config_ref,
        configured_entrypoint_count=configured_entrypoint_count(config),
        command_results=command_results,
        preflight_validation=preflight_validation,
        validation=validation,
        readiness_ref=readiness_ref,
    )
    if not dry_run and status == "passed":
        attach_milestone_bundle(report, out_path=out_path, repo_root=repo_root)
    return report


def write_run_report(
    *,
    out_path: Path,
    status: str,
    dry_run: bool,
    config_ref: dict[str, Any],
    configured_entrypoint_count: int,
    command_results: list[dict[str, Any]],
    preflight_validation: dict[str, Any],
    validation: dict[str, Any],
    readiness_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "report_kind": "judge-entrypoints-run-report",
        "status": status,
        "dry_run": dry_run,
        "config": config_ref,
        "entrypoint_count": len(command_results),
        "entrypoints": command_results,
        "preflight_validation": preflight_validation,
        "validation": validation,
        "readiness_report": readiness_ref,
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_claim_source": "validator-owned-artifacts",
            "boundary": (
                "This runner executes judge entrypoint commands and then invokes the existing validator. "
                "It is orchestration evidence only; semantic acceptance remains owned by summaries, "
                "workflow metrics, oracle evidence, and validators."
            ),
        },
    }
    report["summary"] = build_judge_run_summary(
        status=status,
        dry_run=dry_run,
        configured_entrypoint_count=configured_entrypoint_count,
        command_results=command_results,
        validation=validation,
        readiness_ref=readiness_ref,
        claim_boundary=report["claim_boundary"],
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def attach_milestone_bundle(report: dict[str, Any], *, out_path: Path, repo_root: Path) -> None:
    bundle_path = out_path.parent / "judge-milestone-bundle.json"
    report["milestone_bundle"] = {
        "path": validator.repo_relative(bundle_path, repo_root),
        "status": "present",
        "hash_boundary": "bundle_hashes_this_run_report",
    }
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    judge_milestone_bundle.build_judge_milestone_bundle(
        run_report_path=out_path,
        out_path=bundle_path,
        repo_root=repo_root,
    )


def select_entrypoints(config: dict[str, Any], entrypoint_ids: list[str]) -> list[dict[str, Any]]:
    raw_entrypoints = config.get("entrypoints")
    if not isinstance(raw_entrypoints, list) or not raw_entrypoints:
        raise SystemExit("judge config entrypoints must be a non-empty list")
    entrypoints = [entry for entry in raw_entrypoints if isinstance(entry, dict)]
    if not entrypoint_ids:
        return entrypoints
    by_id = {str(entry.get("id")): entry for entry in entrypoints}
    missing = [entrypoint_id for entrypoint_id in entrypoint_ids if entrypoint_id not in by_id]
    if missing:
        raise SystemExit(f"unknown judge entrypoint id(s): {', '.join(missing)}")
    return [by_id[entrypoint_id] for entrypoint_id in entrypoint_ids]


def configured_entrypoint_count(config: dict[str, Any]) -> int:
    entrypoints = config.get("entrypoints")
    return len([entry for entry in entrypoints if isinstance(entry, dict)]) if isinstance(entrypoints, list) else 0


def build_judge_run_summary(
    *,
    status: str,
    dry_run: bool,
    configured_entrypoint_count: int,
    command_results: list[dict[str, Any]],
    validation: dict[str, Any],
    readiness_ref: dict[str, Any] | None,
    claim_boundary: dict[str, Any],
) -> dict[str, Any]:
    executed_count = len(command_results)
    all_entrypoints_executed = (
        not dry_run
        and status == "passed"
        and configured_entrypoint_count > 0
        and executed_count == configured_entrypoint_count
    )
    validation_status = str(validation.get("status", "unknown")) if isinstance(validation, dict) else "unknown"
    entrypoint_summaries = [
        {
            "id": result.get("id"),
            "purpose": result.get("purpose"),
            "status": result.get("status"),
            "exit_code": result.get("exit_code"),
            "proof_class": result.get("proof_class", "unknown"),
            "run_id": result.get("run_id", "unknown"),
            "judge_focus": result.get("judge_focus", []),
            "key_artifacts": result.get("key_artifacts", {}),
        }
        for result in command_results
    ]
    return {
        "report_kind": "judge-entrypoints-summary",
        "headline": (
            f"Judge entrypoints {status}: {executed_count}/{configured_entrypoint_count} "
            f"{'executed' if not dry_run else 'planned'}; semantic_gate=false"
        ),
        "readiness": {
            "status": status,
            "dry_run": dry_run,
            "all_entrypoints_executed": all_entrypoints_executed,
            "executed_count": executed_count,
            "configured_count": configured_entrypoint_count,
            "validation_status": validation_status,
            "readiness_report": readiness_ref,
        },
        "claim_boundary": {
            "semantic_gate": False,
            "semantic_claim_source": claim_boundary.get("semantic_claim_source", "validator-owned-artifacts"),
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
        "entrypoints": entrypoint_summaries,
    }


def run_entrypoint_command(
    entry: dict[str, Any],
    *,
    dry_run: bool,
    log_dir: Path,
    repo_root: Path,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    entry_id = str(entry.get("id", "unknown"))
    command = str(entry.get("command", ""))
    if not command:
        raise SystemExit(f"judge entrypoint missing command: {entry_id}")
    argv = shlex.split(command)
    stdout_path = log_dir / f"{safe_file_component(entry_id)}.stdout.log"
    stderr_path = log_dir / f"{safe_file_component(entry_id)}.stderr.log"
    result = {
        "id": entry_id,
        "purpose": entry.get("purpose"),
        "priority": entry.get("priority"),
        "proof_class": entry.get("proof_class", "unknown"),
        "run_id": entry.get("run_id", "unknown"),
        "judge_focus": list(entry.get("judge_focus", [])) if isinstance(entry.get("judge_focus"), list) else [],
        "key_artifacts": dict(entry.get("expected_artifacts", {})) if isinstance(entry.get("expected_artifacts"), dict) else {},
        "command": command,
        "argv": argv,
        "exit_code": None if dry_run else 1,
        "logs": {
            "stdout": artifact_ref(stdout_path, repo_root=repo_root),
            "stderr": artifact_ref(stderr_path, repo_root=repo_root),
        },
    }
    if dry_run:
        result["status"] = "planned"
        return result

    try:
        completed = command_runner(argv, cwd=repo_root, text=True, capture_output=True)
    except Exception as error:
        stdout_text = stream_text(getattr(error, "stdout", ""))
        stderr_text = stream_text(getattr(error, "stderr", ""))
        stderr_text += f"{type(error).__name__}: {error}\n"
        stdout_path.write_text(stdout_text, encoding="utf-8")
        stderr_path.write_text(stderr_text, encoding="utf-8")
        result["exit_code"] = command_exception_exit_code(error)
        result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
        result["logs"] = {
            "stdout": artifact_ref(stdout_path, repo_root=repo_root),
            "stderr": artifact_ref(stderr_path, repo_root=repo_root),
        }
        return result

    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    result["exit_code"] = int(completed.returncode)
    result["status"] = "passed" if completed.returncode == 0 else "failed"
    result["logs"] = {
        "stdout": artifact_ref(stdout_path, repo_root=repo_root),
        "stderr": artifact_ref(stderr_path, repo_root=repo_root),
    }
    return result


def resolve_input_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root.resolve())
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def resolve_output_path(path: Path, *, repo_root: Path) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
        resolved.relative_to(repo_root.resolve())
        return resolved
    path_text = path.as_posix()
    validator.assert_repo_relative_posix(path_text)
    return validator.repo_path(path_text, repo_root=repo_root)


def artifact_ref(path: Path, *, repo_root: Path) -> dict[str, Any]:
    ref = {
        "path": validator.repo_relative(path, repo_root),
        "status": "present" if path.is_file() else "missing",
    }
    if path.is_file():
        ref["sha256"] = validator.sha256_file(path)
    return ref


def invalid_config_ref(path: Path, error: BaseException) -> dict[str, Any]:
    return {"path": path.name if path.is_absolute() else path.as_posix(), "status": "invalid", "error": str(error)}


def stream_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def command_exception_exit_code(error: Exception) -> int:
    if isinstance(error, subprocess.TimeoutExpired):
        return 124
    if isinstance(error, OSError):
        return 127
    return 1


def safe_file_component(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value.strip())
    return safe or "entrypoint"


if __name__ == "__main__":
    raise SystemExit(main())
