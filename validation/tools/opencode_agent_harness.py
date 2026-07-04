#!/usr/bin/env python3
"""OpenCode-only multi-agent harness ledger.

This module intentionally stays below the semantic validator. It records
worker assignments, leases, artifacts, and merge plans so OpenCode can resume
and audit parallel work, while correctness remains owned by on-disk evidence
and the existing validators.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools.extract_source_slice import find_matching, mask_comments_and_strings
from validation.tools import route_governance_metrics_report, validate_competition_run_summary

PROFILE_PATH = REPO_ROOT / "config" / "competition-env" / "environment.json"
DB_REL_PATH = Path("state") / "opencode-agent-harness.sqlite3"
SCHEMA_VERSION = 1
PROFILE_ID = "huawei-competition-ubuntu-24.04"
REPAIR_ROUND_CAP = 5
REPAIR_LOG_TAIL_CHARS = 4096
PROCESS_TIMEOUT_EXIT_CODE = 124
DEFAULT_SUBPROCESS_TIMEOUT_SECONDS = 600
PORTABLE_PYTHON_COMMAND = "python3"
PYTHON_COMMAND_OVERRIDE_ENV = "C2RUST_HARNESS_PYTHON"
HARNESS_MODULE = "validation.tools.opencode_agent_harness"
COMPETITION_OPENCODE_MODEL = "GLM-5.1"
COMPETITION_OPENCODE_COMMAND = "opencode"
COMPETITION_OPENCODE_AGENT = "c2rust-migrator"
COMPETITION_OPENCODE_VARIANT = "max"
COMPETITION_EXACT_HOST_ENV = "COMPETITION_EXACT_HOST"
ALLOWED_PROOF_CLASSES = frozenset(
    {"competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"}
)
_RESOLVED_PYTHON_COMMAND: list[str] | None = None
LOCAL_ABSOLUTE_PATH_TEXT = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"[A-Za-z]:[\\/][^\s\"'`,;)]*|"
    r"/mnt/[A-Za-z]/[^\s\"'`,;)]*|"
    r"/home/[^\s\"'`,;)]*|/Users/[^\s\"'`,;)]*|/tmp/[^\s\"'`,;)]*|/var/[^\s\"'`,;)]*|"
    r"\\\\wsl\$\\[^\s\"'`,;)]*|"
    r"//wsl\$/[^\s\"'`,;)]*|"
    r"\\\\wsl\.localhost\\[^\s\"'`,;)]*|"
    r"//wsl\.localhost/[^\s\"'`,;)]*"
    r")"
)
OPENCODE_WORKER_EVIDENCE_FIELDS = (
    "handoff_contract",
    "opencode_session_evidence",
    "opencode_contract_verification",
    "opencode_safety_transform_attempt",
    "opencode_preflight_report",
    "opencode_runtime_env",
)
BLOCKED_PREFLIGHT_STALE_ARTIFACT_PATHS = (
    Path("summary") / "competition-run-summary.json",
    Path("summary") / "workflow-metrics.json",
    Path("summary") / "route-governance-metrics-report.json",
    Path("summary") / "before-after-exhibit.json",
    Path("harness") / "run-plan-report.json",
    Path("harness") / "judge-evidence-index.json",
    Path("harness") / "context-pack.json",
    Path("harness") / "agent-index.json",
    Path("harness") / "merge-plan.json",
    Path("state") / "opencode-agent-harness.sqlite3",
)
BLOCKED_PREFLIGHT_STALE_ARTIFACT_DIRS = (
    Path("workers"),
    Path("harness") / "plans",
)
OPENCODE_RUNTIME_ENV_KEYS = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
)
LF_STABLE_TEXT_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hh",
    ".hpp",
    ".json",
    ".jsonl",
    ".md",
    ".rs",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def opencode_h9_blocker(
    *,
    root_cause_key: str,
    launch_policy: dict[str, Any],
    opencode_run_launched: bool,
    model_availability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blocker: dict[str, Any] = {
        "status": "blocked",
        "root_cause_key": root_cause_key,
        "required_agent_tool": COMPETITION_OPENCODE_COMMAND,
        "required_agent": COMPETITION_OPENCODE_AGENT,
        "required_model": COMPETITION_OPENCODE_MODEL,
        "required_variant": COMPETITION_OPENCODE_VARIANT,
        "required_proof_class": "competition-exact",
        "actual_agent_tool": launch_policy.get("opencode_command", ""),
        "actual_agent": launch_policy.get("opencode_agent", ""),
        "actual_model": launch_policy.get("opencode_model", ""),
        "actual_variant": launch_policy.get("opencode_variant", ""),
        "opencode_run_launched": opencode_run_launched,
        "local_simulation_closes_p0_h9": False,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "next_required_action": "rerun_on_real_opencode_glm51_max_host",
        "boundary": (
            "This blocker is a competition-host readiness signal only. "
            "It cannot be resolved by local simulation, non-GLM models, or chat output."
        ),
    }
    if model_availability is not None:
        blocker["observed_model_availability"] = {
            "status": model_availability.get("status"),
            "required_model": model_availability.get("required_model"),
            "model_listed": model_availability.get("model_listed"),
            "failure_reason": model_availability.get("failure_reason"),
        }
    return blocker


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    init_parser = subcommands.add_parser("init-run")
    init_parser.add_argument("--out-root", type=Path, default=Path("target/competition-out"))
    init_parser.add_argument("--run-id", required=True)
    init_parser.add_argument(
        "--proof-class",
        required=True,
        choices=["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"],
    )

    assign_parser = subcommands.add_parser("assign-slice")
    assign_parser.add_argument("--db", type=Path, required=True)
    assign_parser.add_argument("--run-id", required=True)
    assign_parser.add_argument("--worker-id", required=True)
    assign_parser.add_argument("--target-id", required=True)
    assign_parser.add_argument("--slice-id", required=True)
    assign_parser.add_argument("--source-repo-root", type=Path, required=True)
    assign_parser.add_argument("--source-repository")
    assign_parser.add_argument("--source-branch")
    assign_parser.add_argument("--source-file", required=True)
    assign_parser.add_argument("--function", required=True)
    assign_parser.add_argument("--source-commit", required=True)
    assign_parser.add_argument("--require-source-commit")
    assign_parser.add_argument("--compiler-command-source")
    assign_parser.add_argument("--include-path", action="append", default=[])
    assign_parser.add_argument("--define", action="append", default=[])
    assign_parser.add_argument("--reuse-accepted-evidence", action="store_true")
    assign_parser.add_argument("--accepted-evidence-root")
    assign_parser.add_argument("--slice-spec")
    assign_parser.add_argument("--out-root", type=Path, required=True)
    assign_parser.add_argument("--lease-ttl-seconds", type=int, default=3600)

    plan_parser = subcommands.add_parser("plan-source-file")
    plan_parser.add_argument("--db", type=Path, required=True)
    plan_parser.add_argument("--run-id", required=True)
    plan_parser.add_argument("--target-id", required=True)
    plan_parser.add_argument("--source-repo-root", type=Path, required=True)
    plan_parser.add_argument("--source-repository")
    plan_parser.add_argument("--source-branch")
    plan_parser.add_argument("--source-file", required=True)
    plan_parser.add_argument("--function", action="append", dest="functions", default=[])
    plan_parser.add_argument("--source-commit", required=True)
    plan_parser.add_argument("--require-source-commit")
    plan_parser.add_argument("--slice-spec", action="append", dest="slice_specs", default=[])
    plan_parser.add_argument("--compiler-command-source")
    plan_parser.add_argument("--include-path", action="append", default=[])
    plan_parser.add_argument("--define", action="append", default=[])
    plan_parser.add_argument("--reuse-accepted-evidence", action="store_true")
    plan_parser.add_argument("--accepted-evidence-root")
    plan_parser.add_argument("--out-root", type=Path, required=True)
    plan_parser.add_argument("--slice-id-prefix", required=True)
    plan_parser.add_argument("--worker-prefix", default="worker")
    plan_parser.add_argument("--limit", type=int)
    plan_parser.add_argument("--lease-ttl-seconds", type=int, default=3600)

    run_plan_parser = subcommands.add_parser("run-plan")
    run_plan_parser.add_argument("--db", type=Path, required=True)
    run_plan_parser.add_argument("--run-id", required=True)
    run_plan_parser.add_argument("--plan", type=Path, required=True)
    run_plan_parser.add_argument("--out-root", type=Path, default=Path("target/competition-out"))
    run_plan_parser.add_argument(
        "--proof-class",
        required=True,
        choices=["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"],
    )
    run_plan_parser.add_argument("--mode", choices=["deterministic", "opencode"], default="deterministic")
    run_plan_parser.add_argument("--opencode-command", default="opencode")
    run_plan_parser.add_argument("--opencode-model")
    run_plan_parser.add_argument("--opencode-agent")
    run_plan_parser.add_argument("--opencode-variant", default="max")
    run_plan_parser.add_argument("--opencode-skip-permissions", action="store_true")
    run_plan_parser.add_argument("--opencode-allow-non-competition-model", action="store_true")
    run_plan_parser.add_argument("--opencode-preflight-report", type=Path)
    run_plan_parser.add_argument("--execute-merge", action="store_true")
    run_plan_parser.add_argument("--auto-retry", action="store_true")
    run_plan_parser.add_argument("--max-workers", type=int, default=1)
    run_plan_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_SUBPROCESS_TIMEOUT_SECONDS)

    batch_profile_parser = subcommands.add_parser("run-batch-profile")
    batch_profile_parser.add_argument("--profile", type=Path, required=True)
    batch_profile_parser.add_argument("--run-id", required=True)
    batch_profile_parser.add_argument("--out-root", type=Path, required=True)
    batch_profile_parser.add_argument(
        "--proof-class",
        choices=["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"],
    )
    batch_profile_parser.add_argument("--timeout-seconds", type=int)

    evaluate_parser = subcommands.add_parser("evaluate")
    evaluate_parser.add_argument("--profile", type=Path)
    evaluate_parser.add_argument("--run-id", required=True)
    evaluate_parser.add_argument("--target-id")
    evaluate_parser.add_argument("--source-repo-root", type=Path)
    evaluate_parser.add_argument("--source-repository")
    evaluate_parser.add_argument("--source-branch")
    evaluate_parser.add_argument("--source-file")
    evaluate_parser.add_argument("--function", action="append", dest="functions", default=[])
    evaluate_parser.add_argument("--source-commit")
    evaluate_parser.add_argument("--require-source-commit")
    evaluate_parser.add_argument("--slice-spec", action="append", dest="slice_specs", default=[])
    evaluate_parser.add_argument("--compiler-command-source")
    evaluate_parser.add_argument("--include-path", action="append", default=[])
    evaluate_parser.add_argument("--define", action="append", default=[])
    evaluate_parser.add_argument("--reuse-accepted-evidence", action="store_true")
    evaluate_parser.add_argument("--accepted-evidence-root")
    evaluate_parser.add_argument("--out-root", type=Path, required=True)
    evaluate_parser.add_argument("--slice-id-prefix")
    evaluate_parser.add_argument("--worker-prefix", default="worker")
    evaluate_parser.add_argument("--limit", type=int)
    evaluate_parser.add_argument(
        "--proof-class",
        choices=["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"],
    )
    evaluate_parser.add_argument("--mode", choices=["deterministic", "opencode"], default="deterministic")
    evaluate_parser.add_argument("--opencode-command", default="opencode")
    evaluate_parser.add_argument("--opencode-model")
    evaluate_parser.add_argument("--opencode-agent")
    evaluate_parser.add_argument("--opencode-variant", default="max")
    evaluate_parser.add_argument("--opencode-skip-permissions", action="store_true")
    evaluate_parser.add_argument("--opencode-allow-non-competition-model", action="store_true")
    evaluate_parser.add_argument("--opencode-preflight-report", type=Path)
    evaluate_parser.add_argument("--no-execute-merge", action="store_true")
    evaluate_parser.add_argument("--no-auto-retry", action="store_true")
    evaluate_parser.add_argument("--max-workers", type=int, default=1)
    evaluate_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_SUBPROCESS_TIMEOUT_SECONDS)

    preflight_parser = subcommands.add_parser("opencode-preflight")
    preflight_parser.add_argument("--run-id", required=True)
    preflight_parser.add_argument("--out-root", type=Path, required=True)
    preflight_parser.add_argument("--opencode-command", default="opencode")
    preflight_parser.add_argument("--opencode-model")
    preflight_parser.add_argument("--opencode-agent")
    preflight_parser.add_argument("--opencode-variant", default="max")
    preflight_parser.add_argument("--opencode-skip-permissions", action="store_true")
    preflight_parser.add_argument("--opencode-allow-non-competition-model", action="store_true")
    preflight_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_SUBPROCESS_TIMEOUT_SECONDS)

    preflight_marker_parser = subcommands.add_parser("write-preflight-marker")
    preflight_marker_parser.add_argument("--marker", type=Path, required=True)
    preflight_marker_parser.add_argument("--run-id", required=True)

    run_parser = subcommands.add_parser("run-worker")
    run_parser.add_argument("--db", type=Path, required=True)
    run_parser.add_argument("--run-id", required=True)
    run_parser.add_argument("--worker-id", required=True)
    run_parser.add_argument("--mode", choices=["deterministic", "opencode"], default="deterministic")
    run_parser.add_argument("--opencode-command", default="opencode")
    run_parser.add_argument("--opencode-model")
    run_parser.add_argument("--opencode-agent")
    run_parser.add_argument("--opencode-variant", default="max")
    run_parser.add_argument("--opencode-skip-permissions", action="store_true")
    run_parser.add_argument("--opencode-allow-non-competition-model", action="store_true")
    run_parser.add_argument("--opencode-preflight-report", type=Path)
    run_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_SUBPROCESS_TIMEOUT_SECONDS)

    retry_parser = subcommands.add_parser("retry-worker")
    retry_parser.add_argument("--db", type=Path, required=True)
    retry_parser.add_argument("--run-id", required=True)
    retry_parser.add_argument("--worker-id", required=True)
    retry_parser.add_argument("--hint-id")
    retry_parser.add_argument("--mode", choices=["deterministic", "opencode"], default="deterministic")
    retry_parser.add_argument("--opencode-command", default="opencode")
    retry_parser.add_argument("--opencode-model")
    retry_parser.add_argument("--opencode-agent")
    retry_parser.add_argument("--opencode-variant", default="max")
    retry_parser.add_argument("--opencode-skip-permissions", action="store_true")
    retry_parser.add_argument("--opencode-allow-non-competition-model", action="store_true")
    retry_parser.add_argument("--opencode-preflight-report", type=Path)
    retry_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_SUBPROCESS_TIMEOUT_SECONDS)

    record_parser = subcommands.add_parser("record-worker-summary")
    record_parser.add_argument("--db", type=Path, required=True)
    record_parser.add_argument("--run-id", required=True)
    record_parser.add_argument("--worker-id", required=True)
    record_parser.add_argument("--summary", type=Path, required=True)

    merge_parser = subcommands.add_parser("write-merge-plan")
    merge_parser.add_argument("--db", type=Path, required=True)
    merge_parser.add_argument("--run-id", required=True)
    merge_parser.add_argument("--out-root", type=Path, default=Path("target/competition-out"))
    merge_parser.add_argument(
        "--proof-class",
        required=True,
        choices=["competition-exact", "ci-approximation", "wsl-local-simulation", "local-simulation"],
    )

    finalize_parser = subcommands.add_parser("finalize-run")
    finalize_parser.add_argument("--db", type=Path, required=True)
    finalize_parser.add_argument("--run-id", required=True)
    finalize_parser.add_argument("--status", required=True)
    finalize_parser.add_argument("--summary", type=Path, required=True)
    finalize_parser.add_argument("--final-gate-status")

    args = parser.parse_args()
    if args.command == "init-run":
        result = {"db_path": repo_relative(init_run(out_root=args.out_root, run_id=args.run_id, proof_class=args.proof_class))}
    elif args.command == "assign-slice":
        result = assign_slice(
            db_path=args.db,
            run_id=args.run_id,
            worker_id=args.worker_id,
            target_id=args.target_id,
            slice_id=args.slice_id,
            source_repo_root=args.source_repo_root,
            source_repository=args.source_repository,
            source_branch=args.source_branch,
            source_file=args.source_file,
            function=args.function,
            source_commit=args.source_commit,
            require_source_commit=args.require_source_commit,
            compiler_command_source=args.compiler_command_source,
            include_paths=args.include_path,
            defines=args.define,
            reuse_accepted_evidence=args.reuse_accepted_evidence,
            accepted_evidence_root=args.accepted_evidence_root,
            slice_spec=args.slice_spec,
            out_root=args.out_root,
            lease_ttl_seconds=args.lease_ttl_seconds,
        )
    elif args.command == "plan-source-file":
        result = plan_source_file(
            db_path=args.db,
            run_id=args.run_id,
            target_id=args.target_id,
            source_repo_root=args.source_repo_root,
            source_repository=args.source_repository,
            source_branch=args.source_branch,
            source_file=args.source_file,
            functions=args.functions,
            source_commit=args.source_commit,
            require_source_commit=args.require_source_commit,
            slice_specs=args.slice_specs,
            compiler_command_source=args.compiler_command_source,
            include_paths=args.include_path,
            defines=args.define,
            reuse_accepted_evidence=args.reuse_accepted_evidence,
            accepted_evidence_root=args.accepted_evidence_root,
            out_root=args.out_root,
            slice_id_prefix=args.slice_id_prefix,
            worker_prefix=args.worker_prefix,
            limit=args.limit,
            lease_ttl_seconds=args.lease_ttl_seconds,
        )
    elif args.command == "run-plan":
        result = run_plan(
            db_path=args.db,
            run_id=args.run_id,
            plan_path=args.plan,
            out_root=args.out_root,
            proof_class=args.proof_class,
            mode=args.mode,
            opencode_command=args.opencode_command,
            opencode_model=args.opencode_model,
            opencode_agent=args.opencode_agent,
            opencode_variant=args.opencode_variant,
            opencode_skip_permissions=args.opencode_skip_permissions,
            opencode_allow_non_competition_model=args.opencode_allow_non_competition_model,
            opencode_preflight_report=args.opencode_preflight_report,
            execute_merge=args.execute_merge,
            auto_retry=args.auto_retry,
            max_workers=args.max_workers,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "run-batch-profile":
        result = run_batch_profile(
            profile_path=args.profile,
            run_id=args.run_id,
            out_root=args.out_root,
            proof_class_override=args.proof_class,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "evaluate":
        if args.profile:
            batch_result = run_batch_profile(
                profile_path=args.profile,
                run_id=args.run_id,
                out_root=args.out_root,
                proof_class_override=args.proof_class,
                timeout_seconds=args.timeout_seconds,
            )
            result = write_evaluate_profile_report(
                batch_result=batch_result,
                profile_path=args.profile,
                run_id=args.run_id,
                out_root=args.out_root,
            )
        else:
            missing = [
                flag
                for flag, value in [
                    ("--target-id", args.target_id),
                    ("--source-repo-root", args.source_repo_root),
                    ("--source-file", args.source_file),
                    ("--source-commit", args.source_commit),
                    ("--proof-class", args.proof_class),
                ]
                if value is None
            ]
            if missing:
                parser.error("evaluate requires " + ", ".join(missing) + " unless --profile is provided")
            result = evaluate(
                run_id=args.run_id,
                target_id=args.target_id,
                source_repo_root=args.source_repo_root,
                source_repository=args.source_repository,
                source_branch=args.source_branch,
                source_file=args.source_file,
                functions=args.functions,
                source_commit=args.source_commit,
                require_source_commit=args.require_source_commit,
                slice_specs=args.slice_specs,
                compiler_command_source=args.compiler_command_source,
                include_paths=args.include_path,
                defines=args.define,
                reuse_accepted_evidence=args.reuse_accepted_evidence,
                accepted_evidence_root=args.accepted_evidence_root,
                out_root=args.out_root,
                slice_id_prefix=args.slice_id_prefix,
                worker_prefix=args.worker_prefix,
                limit=args.limit,
                proof_class=args.proof_class,
                mode=args.mode,
                opencode_command=args.opencode_command,
                opencode_model=args.opencode_model,
                opencode_agent=args.opencode_agent,
                opencode_variant=args.opencode_variant,
                opencode_skip_permissions=args.opencode_skip_permissions,
                opencode_allow_non_competition_model=args.opencode_allow_non_competition_model,
                opencode_preflight_report=args.opencode_preflight_report,
                execute_merge=not args.no_execute_merge,
                auto_retry=not args.no_auto_retry,
                max_workers=args.max_workers,
                timeout_seconds=args.timeout_seconds,
            )
    elif args.command == "opencode-preflight":
        result = run_opencode_preflight(
            out_root=args.out_root,
            run_id=args.run_id,
            opencode_command=args.opencode_command,
            opencode_model=args.opencode_model,
            opencode_agent=args.opencode_agent,
            opencode_variant=args.opencode_variant,
            opencode_skip_permissions=args.opencode_skip_permissions,
            opencode_allow_non_competition_model=args.opencode_allow_non_competition_model,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "write-preflight-marker":
        result = write_opencode_preflight_marker(
            marker_path=args.marker,
            run_id=args.run_id,
        )
    elif args.command == "run-worker":
        result = run_worker(
            db_path=args.db,
            run_id=args.run_id,
            worker_id=args.worker_id,
            mode=args.mode,
            opencode_command=args.opencode_command,
            opencode_model=args.opencode_model,
            opencode_agent=args.opencode_agent,
            opencode_variant=args.opencode_variant,
            opencode_skip_permissions=args.opencode_skip_permissions,
            opencode_allow_non_competition_model=args.opencode_allow_non_competition_model,
            opencode_preflight_report=args.opencode_preflight_report,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "retry-worker":
        result = retry_worker(
            db_path=args.db,
            run_id=args.run_id,
            worker_id=args.worker_id,
            hint_id=args.hint_id,
            mode=args.mode,
            opencode_command=args.opencode_command,
            opencode_model=args.opencode_model,
            opencode_agent=args.opencode_agent,
            opencode_variant=args.opencode_variant,
            opencode_skip_permissions=args.opencode_skip_permissions,
            opencode_allow_non_competition_model=args.opencode_allow_non_competition_model,
            opencode_preflight_report=args.opencode_preflight_report,
            timeout_seconds=args.timeout_seconds,
        )
    elif args.command == "record-worker-summary":
        result = record_worker_summary(
            db_path=args.db,
            run_id=args.run_id,
            worker_id=args.worker_id,
            summary_path=args.summary,
        )
    elif args.command == "write-merge-plan":
        result = write_merge_plan(
            db_path=args.db,
            run_id=args.run_id,
            out_root=args.out_root,
            proof_class=args.proof_class,
        )
    else:
        result = finalize_run(
            db_path=args.db,
            run_id=args.run_id,
            status=args.status,
            summary_path=args.summary,
            final_gate_status=args.final_gate_status,
        )

    print(json.dumps(result, indent=2, sort_keys=True))
    return int(result.get("exit_code", 0)) if args.command in {"run-worker", "retry-worker", "run-plan", "run-batch-profile", "evaluate", "opencode-preflight"} else 0


def init_run(
    *,
    out_root: Path,
    run_id: str,
    proof_class: str,
    repo_root: Path = REPO_ROOT,
) -> Path:
    require_competition_exact_host_attestation(proof_class, context="init-run")
    out_root = repo_path(out_root, repo_root=repo_root)
    db_path = out_root / DB_REL_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        profile_sha256 = sha256_file(PROFILE_PATH)
        now = now_text()
        connection.execute(
            """
            insert into profiles(profile_id, profile_path, profile_sha256, payload_json, created_at)
            values (?, ?, ?, ?, ?)
            on conflict(profile_id) do update set
              profile_path=excluded.profile_path,
              profile_sha256=excluded.profile_sha256,
              payload_json=excluded.payload_json
            """,
            (
                PROFILE_ID,
                "config/competition-env/environment.json",
                profile_sha256,
                json.dumps(load_json(PROFILE_PATH), sort_keys=True),
                now,
            ),
        )
        connection.execute(
            """
            insert into runs(
              run_id, out_root, proof_class, profile_id, profile_sha256,
              schema_version, status, started_at, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(run_id) do update set
              out_root=excluded.out_root,
              proof_class=excluded.proof_class,
              profile_id=excluded.profile_id,
              profile_sha256=excluded.profile_sha256,
              payload_json=excluded.payload_json
            """,
            (
                run_id,
                repo_relative(out_root, repo_root=repo_root),
                proof_class,
                PROFILE_ID,
                profile_sha256,
                SCHEMA_VERSION,
                "initialized",
                now,
                json.dumps({"runtime": "opencode"}, sort_keys=True),
            ),
        )
        connection.commit()
    return db_path


def reset_batch_profile_ledger(*, out_root: Path, repo_root: Path = REPO_ROOT) -> None:
    out_root = repo_path(out_root, repo_root=repo_root)
    db_path = out_root / DB_REL_PATH
    for path in [db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")]:
        if not path.exists():
            continue
        if not path.is_file():
            raise SystemExit(f"batch profile ledger reset refused non-file path: {repo_relative(path, repo_root=repo_root)}")
        path.unlink()


def assign_slice(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    target_id: str,
    slice_id: str,
    source_repo_root: Path,
    source_repository: str | None = None,
    source_branch: str | None = None,
    source_file: str,
    function: str,
    source_commit: str,
    source_sha256: str | None = None,
    require_source_commit: str | None = None,
    compiler_command_source: str | None = None,
    include_paths: list[str] | None = None,
    defines: list[str] | None = None,
    reuse_accepted_evidence: bool = False,
    accepted_evidence_root: str | None = None,
    slice_spec: str | None = None,
    out_root: Path,
    lease_ttl_seconds: int = 3600,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    source_repo_root_rel = repo_relative(repo_root / checked_relative_path(path_text(source_repo_root)), repo_root=repo_root)
    source_file_rel = checked_relative_path(source_file).as_posix()
    compiler_command_source_rel = checked_relative_path(compiler_command_source).as_posix() if compiler_command_source else None
    include_path_values = [checked_relative_path(include_path).as_posix() for include_path in (include_paths or [])]
    define_values = list(defines or [])
    accepted_evidence_root_rel = (
        checked_relative_path(accepted_evidence_root).as_posix() if accepted_evidence_root else None
    )
    slice_spec_rel = checked_relative_path(slice_spec).as_posix() if slice_spec else None
    slice_spec_sha256 = sha256_file(repo_path(Path(slice_spec_rel), repo_root=repo_root)) if slice_spec_rel else None
    out_root_rel = repo_relative(out_root, repo_root=repo_root)
    resource_key = f"slice:{target_id}/{slice_id}"
    task_id = f"{run_id}:{worker_id}:{target_id}:{slice_id}"
    now = now_text()
    expires_at = str(int(time.time()) + lease_ttl_seconds)
    assignment = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "role": "slice-worker",
        "out_root": out_root_rel,
        "lease": {
            "resource_key": resource_key,
            "ttl_seconds": lease_ttl_seconds,
            "expires_at": expires_at,
        },
        "slice": {
            "target_id": target_id,
            "slice_id": slice_id,
            "source_repo_root": source_repo_root_rel,
            "source_file": source_file_rel,
            "function": function,
            "source_commit": source_commit,
        },
        "runner": {
            "command": "python3 -B validation/tools/run_competition.py",
            "out_root": out_root_rel,
            "reuse_accepted_evidence": reuse_accepted_evidence,
        },
    }
    if compiler_command_source_rel:
        assignment["slice"]["compiler_command_source"] = compiler_command_source_rel
    if source_repository:
        assignment["slice"]["source_repository"] = source_repository
    if source_branch:
        assignment["slice"]["source_branch"] = source_branch
    if require_source_commit:
        assignment["slice"]["require_source_commit"] = require_source_commit
    if source_sha256:
        assignment["slice"]["source_sha256"] = source_sha256
    if include_path_values:
        assignment["slice"]["include_paths"] = include_path_values
    if define_values:
        assignment["slice"]["defines"] = define_values
    if accepted_evidence_root_rel:
        assignment["runner"]["accepted_evidence_root"] = accepted_evidence_root_rel
    if slice_spec_rel:
        assignment["slice"]["slice_spec"] = slice_spec_rel
        assignment["slice"]["slice_spec_sha256"] = slice_spec_sha256
    request = {
        "source_repo_root": source_repo_root_rel,
        "source_file": source_file_rel,
        "function": function,
        "target_id": target_id,
        "slice_id": slice_id,
        "source_commit": source_commit,
        "proof_class": run_proof_class(db_path, run_id),
        "out_root": out_root_rel,
        "run_id": f"{run_id}-{worker_id}",
    }
    if source_repository:
        request["source_repository"] = source_repository
    if source_branch:
        request["source_branch"] = source_branch
    if require_source_commit:
        request["require_source_commit"] = require_source_commit
    if source_sha256:
        request["source_sha256"] = source_sha256
    if compiler_command_source_rel:
        request["compiler_command_source"] = compiler_command_source_rel
    if include_path_values:
        request["include_paths"] = include_path_values
    if define_values:
        request["defines"] = define_values
    if reuse_accepted_evidence:
        request["reuse_accepted_evidence"] = True
    if accepted_evidence_root_rel:
        request["accepted_evidence_root"] = accepted_evidence_root_rel
    if slice_spec_rel:
        request["slice_specs"] = [slice_spec_rel]

    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        active_owner = connection.execute(
            "select lease_owner from leases where resource_key=? and status='active'",
            (resource_key,),
        ).fetchone()
        if active_owner is not None and active_owner[0] != worker_id:
            raise SystemExit(f"active lease already exists for {resource_key}: {active_owner[0]}")
        out_root_owner = connection.execute(
            """
            select agent_id from agents
            where run_id=? and isolated_out_root=? and agent_id<>?
            """,
            (run_id, out_root_rel, worker_id),
        ).fetchone()
        if out_root_owner is not None:
            raise SystemExit(f"isolated out_root already assigned for run {run_id}: {out_root_rel} by {out_root_owner[0]}")

        connection.execute(
            """
            insert into agents(agent_id, run_id, runtime, worker_name, role, isolated_out_root, status, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(agent_id) do update set
              run_id=excluded.run_id,
              isolated_out_root=excluded.isolated_out_root,
              status=excluded.status
            """,
            (
                worker_id,
                run_id,
                "opencode",
                worker_id,
                "slice-worker",
                out_root_rel,
                "assigned",
                now,
            ),
        )
        connection.execute(
            """
            insert into slices(
              target_id, slice_id, source_repo_root_rel, source_file_rel,
              function_name, source_commit, slice_spec_path, slice_spec_sha256,
              payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(target_id, slice_id) do update set
              source_repo_root_rel=excluded.source_repo_root_rel,
              source_file_rel=excluded.source_file_rel,
              function_name=excluded.function_name,
              source_commit=excluded.source_commit,
              slice_spec_path=excluded.slice_spec_path,
              slice_spec_sha256=excluded.slice_spec_sha256,
              payload_json=excluded.payload_json
            """,
            (
                target_id,
                slice_id,
                source_repo_root_rel,
                source_file_rel,
                function,
                source_commit,
                slice_spec_rel,
                slice_spec_sha256,
                json.dumps(assignment["slice"], sort_keys=True),
            ),
        )
        connection.execute(
            """
            insert into agent_tasks(
              task_id, run_id, agent_id, target_id, slice_id, phase,
              status, attempt, allowed_paths_json, started_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(task_id) do update set status=excluded.status
            """,
            (
                task_id,
                run_id,
                worker_id,
                target_id,
                slice_id,
                "migrate",
                "assigned",
                1,
                json.dumps([out_root_rel], sort_keys=True),
                now,
            ),
        )
        connection.execute(
            """
            insert into leases(resource_key, run_id, lease_owner, status, expires_at, heartbeat_at, fencing_token)
            values (?, ?, ?, ?, ?, ?, ?)
            on conflict(resource_key) do update set
              run_id=excluded.run_id,
              lease_owner=excluded.lease_owner,
              status=excluded.status,
              expires_at=excluded.expires_at,
              heartbeat_at=excluded.heartbeat_at,
              fencing_token=leases.fencing_token + 1
            """,
            (resource_key, run_id, worker_id, "active", expires_at, now, 1),
        )
        assignment_path = assignment_file_path(db_path, worker_id)
        assignment_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(assignment_path, assignment)
        request_path = assignment_path.with_name(f"{worker_id}-request.json")
        atomic_write_json(request_path, request)
        record_event(connection, run_id=run_id, event_type="assignment_created", payload=assignment)
        connection.commit()
    return assignment


def plan_source_file(
    *,
    db_path: Path,
    run_id: str,
    target_id: str,
    source_repo_root: Path,
    source_file: str,
    source_commit: str,
    source_repository: str | None = None,
    source_branch: str | None = None,
    require_source_commit: str | None = None,
    compiler_command_source: str | None = None,
    include_paths: list[str] | None = None,
    defines: list[str] | None = None,
    reuse_accepted_evidence: bool = False,
    accepted_evidence_root: str | None = None,
    functions: list[str] | None = None,
    slice_specs: list[str] | None = None,
    out_root: Path,
    slice_id_prefix: str,
    worker_prefix: str = "worker",
    limit: int | None = None,
    lease_ttl_seconds: int = 3600,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    source_repo_root_path = repo_path(source_repo_root, repo_root=repo_root)
    source_repo_root_rel = repo_relative(source_repo_root_path, repo_root=repo_root)
    source_file_rel = checked_relative_path(source_file).as_posix()
    source_path = repo_path(source_repo_root_path / source_file_rel, repo_root=repo_root)
    discovered_functions = discover_top_level_function_names(source_path.read_text(encoding="utf-8"))
    slice_specs_by_function = load_slice_specs_by_function(
        slice_specs or [],
        target_id=target_id,
        source_commit=source_commit,
        repo_root=repo_root,
    )
    requested_functions = list(functions or [])
    if requested_functions:
        missing_functions = [function for function in requested_functions if function not in discovered_functions]
        if missing_functions:
            raise SystemExit(
                f"requested functions not discovered in {source_file_rel}: {', '.join(missing_functions)}"
            )
        planned_functions = requested_functions
    elif slice_specs_by_function:
        planned_functions = [function for function in discovered_functions if function in slice_specs_by_function]
    else:
        planned_functions = discovered_functions
    if limit is not None:
        if limit < 1:
            raise SystemExit("plan-source-file --limit must be positive")
        planned_functions = planned_functions[:limit]
    if not planned_functions:
        raise SystemExit(f"no top-level function definitions discovered in {source_file_rel}")

    source_sha256 = sha256_file(source_path)
    units: list[dict[str, str]] = []
    for index, function in enumerate(planned_functions, start=1):
        function_slug = slug_id(function)
        worker_id = f"{worker_prefix}-{index:03d}-{function_slug}"
        slice_spec = slice_specs_by_function.get(function)
        slice_id = str(slice_spec["slice_id"]) if slice_spec else f"{slice_id_prefix}-{function_slug}"
        worker_out_root = out_root / "workers" / worker_id
        assign_slice(
            db_path=db_path,
            run_id=run_id,
            worker_id=worker_id,
            target_id=target_id,
            slice_id=slice_id,
            source_repo_root=Path(source_repo_root_rel),
            source_repository=source_repository,
            source_branch=source_branch,
            source_file=source_file_rel,
            function=function,
            source_commit=source_commit,
            source_sha256=source_sha256,
            require_source_commit=require_source_commit,
            compiler_command_source=compiler_command_source,
            include_paths=include_paths,
            defines=defines,
            reuse_accepted_evidence=reuse_accepted_evidence,
            accepted_evidence_root=accepted_evidence_root,
            slice_spec=str(slice_spec["path"]) if slice_spec else None,
            out_root=worker_out_root,
            lease_ttl_seconds=lease_ttl_seconds,
            repo_root=repo_root,
        )
        request_path = assignment_file_path(db_path, worker_id).with_name(f"{worker_id}-request.json")
        units.append(
            {
                "worker_id": worker_id,
                "slice_id": slice_id,
                "function": function,
                "out_root": repo_relative(worker_out_root, repo_root=repo_root),
                "assignment_path": repo_relative(assignment_file_path(db_path, worker_id), repo_root=repo_root),
                "request_path": repo_relative(request_path, repo_root=repo_root),
                "source_repo_root": source_repo_root_rel,
                "source_file": source_file_rel,
                "source_commit": source_commit,
                "source_sha256": source_sha256,
            }
        )
        if require_source_commit:
            units[-1]["require_source_commit"] = require_source_commit
        if source_repository:
            units[-1]["source_repository"] = source_repository
        if source_branch:
            units[-1]["source_branch"] = source_branch
        if slice_spec:
            units[-1]["slice_spec"] = str(slice_spec["path"])

    plan_path = out_root / "harness" / "plans" / f"{target_id}-{slug_id(Path(source_file_rel).stem)}-workers.json"
    plan = {
        "schema_version": SCHEMA_VERSION,
        "status": "planned",
        "run_id": run_id,
        "target_id": target_id,
        "source_repo_root": source_repo_root_rel,
        "source_file": source_file_rel,
        "source_sha256": source_sha256,
        "source_commit": source_commit,
        "slice_id_prefix": slice_id_prefix,
        "worker_prefix": worker_prefix,
        "plan_path": repo_relative(plan_path, repo_root=repo_root),
        "units": units,
    }
    if require_source_commit:
        plan["require_source_commit"] = require_source_commit
    if source_repository:
        plan["source_repository"] = source_repository
    if source_branch:
        plan["source_branch"] = source_branch
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(plan_path, plan)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="source-file-worker-plan",
            path=plan_path,
            status="planned",
            semantic_role="worker-plan",
            payload=plan,
            repo_root=repo_root,
        )
        record_event(connection, run_id=run_id, event_type="source_file_planned", payload=plan)
        connection.commit()
    return plan


def plan_explicit_workers(
    *,
    db_path: Path,
    run_id: str,
    profile: dict[str, Any],
    out_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    target_id = profile_required_string(profile, "target_id")
    workers = profile_worker_list(profile)
    units: list[dict[str, Any]] = []
    seen_worker_ids: set[str] = set()
    for worker in workers:
        worker_id = profile_required_string(worker, "worker_id")
        if worker_id in seen_worker_ids:
            raise SystemExit(f"duplicate explicit worker_id in batch profile: {worker_id}")
        seen_worker_ids.add(worker_id)
        worker_target_id = profile_string(worker, "target_id", default=target_id)
        if worker_target_id != target_id:
            raise SystemExit(f"explicit worker target_id mismatch for {worker_id}: {worker_target_id} != {target_id}")
        slice_id = profile_required_string(worker, "slice_id")
        function = profile_required_string(worker, "function")
        source_commit = profile_required_string(worker, "source_commit")
        worker_out_root_text = profile_string(worker, "out_root")
        worker_out_root = repo_path(Path(worker_out_root_text), repo_root=repo_root) if worker_out_root_text else out_root / "workers" / worker_id
        source_repo_root = Path(profile_required_string(worker, "source_repo_root"))
        source_file = profile_required_string(worker, "source_file")
        source_repo_root_path = repo_path(source_repo_root, repo_root=repo_root)
        source_repo_root_rel = repo_relative(source_repo_root_path, repo_root=repo_root)
        source_file_rel = checked_relative_path(source_file).as_posix()
        source_path = repo_path(source_repo_root_path / source_file_rel, repo_root=repo_root)
        if not source_path.exists():
            raise SystemExit(f"explicit worker source file not found for {worker_id}: {source_repo_root_rel}/{source_file_rel}")
        source_sha256 = sha256_file(source_path)
        source_repository = profile_string(worker, "source_repository", default=profile_string(profile, "source_repository"))
        source_branch = profile_string(worker, "source_branch", default=profile_string(profile, "source_branch"))
        slice_spec = profile_string(worker, "slice_spec")
        if slice_spec:
            slice_spec = load_explicit_worker_slice_spec(
                slice_spec,
                target_id=target_id,
                slice_id=slice_id,
                function=function,
                source_commit=source_commit,
                source_file=source_file_rel,
                source_sha256=source_sha256,
                source_repository=source_repository,
                source_branch=source_branch,
                repo_root=repo_root,
            )
        require_source_commit = profile_string(worker, "require_source_commit")
        compiler_command_source = profile_string(worker, "compiler_command_source")
        include_paths = profile_string_list(worker, "include_paths")
        defines = profile_string_list(worker, "defines")
        assign_slice(
            db_path=db_path,
            run_id=run_id,
            worker_id=worker_id,
            target_id=target_id,
            slice_id=slice_id,
            source_repo_root=source_repo_root,
            source_repository=source_repository,
            source_branch=source_branch,
            source_file=source_file_rel,
            function=function,
            source_commit=source_commit,
            source_sha256=source_sha256,
            require_source_commit=require_source_commit,
            compiler_command_source=compiler_command_source,
            include_paths=include_paths,
            defines=defines,
            reuse_accepted_evidence=profile_bool(
                worker,
                "reuse_accepted_evidence",
                default=profile_bool(profile, "reuse_accepted_evidence", default=False),
            ),
            accepted_evidence_root=profile_string(
                worker,
                "accepted_evidence_root",
                default=profile_string(profile, "accepted_evidence_root"),
            ),
            slice_spec=slice_spec,
            out_root=worker_out_root,
            lease_ttl_seconds=profile_int(worker, "lease_ttl_seconds", default=profile_int(profile, "lease_ttl_seconds", default=3600)) or 3600,
            repo_root=repo_root,
        )
        request_path = assignment_file_path(db_path, worker_id).with_name(f"{worker_id}-request.json")
        unit: dict[str, Any] = {
            "worker_id": worker_id,
            "slice_id": slice_id,
            "function": function,
            "out_root": repo_relative(worker_out_root, repo_root=repo_root),
            "assignment_path": repo_relative(assignment_file_path(db_path, worker_id), repo_root=repo_root),
            "request_path": repo_relative(request_path, repo_root=repo_root),
            "source_repo_root": source_repo_root_rel,
            "source_file": source_file_rel,
            "source_commit": source_commit,
            "source_sha256": source_sha256,
        }
        if source_repository:
            unit["source_repository"] = source_repository
        if source_branch:
            unit["source_branch"] = source_branch
        if require_source_commit:
            unit["require_source_commit"] = require_source_commit
        if compiler_command_source:
            unit["compiler_command_source"] = compiler_command_source
        if include_paths:
            unit["include_paths"] = include_paths
        if defines:
            unit["defines"] = defines
        if slice_spec:
            unit["slice_spec"] = slice_spec
        units.append(unit)

    plan_path = out_root / "harness" / "plans" / f"{target_id}-{slug_id(profile_required_string(profile, 'profile_id'))}-workers.json"
    plan = {
        "schema_version": SCHEMA_VERSION,
        "status": "planned",
        "planning_mode": "explicit_workers",
        "run_id": run_id,
        "target_id": target_id,
        "worker_prefix": profile_string(profile, "worker_prefix", default="worker"),
        "plan_path": repo_relative(plan_path, repo_root=repo_root),
        "units": units,
    }
    if profile.get("source_repository"):
        plan["source_repository"] = profile_string(profile, "source_repository")
    if profile.get("source_branch"):
        plan["source_branch"] = profile_string(profile, "source_branch")
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(plan_path, plan)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="explicit-worker-plan",
            path=plan_path,
            status="planned",
            semantic_role="worker-plan",
            payload=plan,
            repo_root=repo_root,
        )
        record_event(connection, run_id=run_id, event_type="explicit_workers_planned", payload=plan)
        connection.commit()
    return plan


def load_slice_specs_by_function(
    slice_specs: list[str],
    *,
    target_id: str,
    source_commit: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, dict[str, str]]:
    specs_by_function: dict[str, dict[str, str]] = {}
    for slice_spec in slice_specs:
        slice_spec_rel = checked_relative_path(slice_spec).as_posix()
        spec = load_json(repo_path(Path(slice_spec_rel), repo_root=repo_root))
        function = spec.get("function_name")
        if not isinstance(function, str) or not function:
            raise SystemExit(f"slice spec missing function_name: {slice_spec_rel}")
        spec_target_id = spec.get("target_id")
        if spec_target_id != target_id:
            raise SystemExit(f"slice spec target_id mismatch for {function}: {spec_target_id or 'missing'} != {target_id}")
        source_block = spec.get("source") if isinstance(spec.get("source"), dict) else {}
        spec_source_commit = spec.get("source_commit") or source_block.get("source_commit")
        if spec_source_commit != source_commit:
            raise SystemExit(
                f"slice spec source_commit mismatch for {function}: {spec_source_commit or 'missing'} != {source_commit}"
            )
        slice_id = spec.get("slice_id")
        if not isinstance(slice_id, str) or not slice_id:
            raise SystemExit(f"slice spec missing slice_id: {slice_spec_rel}")
        if function in specs_by_function:
            raise SystemExit(f"duplicate slice spec for function {function}: {slice_spec_rel}")
        specs_by_function[function] = {"path": slice_spec_rel, "slice_id": slice_id}
    return specs_by_function


def load_explicit_worker_slice_spec(
    slice_spec: str,
    *,
    target_id: str,
    slice_id: str,
    function: str,
    source_commit: str,
    source_file: str,
    source_sha256: str,
    source_repository: str | None = None,
    source_branch: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> str:
    slice_spec_rel = checked_relative_path(slice_spec).as_posix()
    spec = load_json(repo_path(Path(slice_spec_rel), repo_root=repo_root))
    spec_target_id = spec.get("target_id")
    if spec_target_id != target_id:
        raise SystemExit(f"slice spec target_id mismatch for {function}: {spec_target_id or 'missing'} != {target_id}")
    spec_function = spec.get("function_name")
    if spec_function != function:
        raise SystemExit(f"slice spec function_name mismatch for {function}: {spec_function or 'missing'} != {function}")
    source_block = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    spec_source_commit = spec.get("source_commit") or source_block.get("source_commit")
    if spec_source_commit != source_commit:
        raise SystemExit(
            f"slice spec source_commit mismatch for {function}: {spec_source_commit or 'missing'} != {source_commit}"
        )
    spec_repository = source_block.get("source_repository")
    if source_repository and isinstance(spec_repository, str) and spec_repository != source_repository:
        raise SystemExit(f"slice spec source_repository mismatch for {function}: {spec_repository} != {source_repository}")
    spec_branch = source_block.get("source_branch")
    if source_branch and isinstance(spec_branch, str) and spec_branch != source_branch:
        raise SystemExit(f"slice spec source_branch mismatch for {function}: {spec_branch} != {source_branch}")
    spec_source_sha256 = explicit_worker_slice_spec_source_sha256(spec, source_file)
    if spec_source_sha256 is not None and spec_source_sha256 != source_sha256:
        raise SystemExit(
            f"slice spec source file sha256 mismatch for {function}: {spec_source_sha256} != {source_sha256}"
        )
    spec_slice_id = spec.get("slice_id")
    if spec_slice_id != slice_id:
        raise SystemExit(f"slice spec slice_id mismatch for {function}: {spec_slice_id or 'missing'} != {slice_id}")
    return slice_spec_rel


def explicit_worker_slice_spec_source_sha256(spec: dict[str, Any], source_file: str) -> str | None:
    source_block = spec.get("source") if isinstance(spec.get("source"), dict) else {}
    source_file_hashes = source_block.get("source_file_hashes")
    if isinstance(source_file_hashes, dict):
        value = source_file_hashes.get(source_file)
        if isinstance(value, str) and value:
            return value
    c_boundary = spec.get("c_boundary") if isinstance(spec.get("c_boundary"), dict) else {}
    files = c_boundary.get("files")
    if isinstance(files, list):
        for item in files:
            if not isinstance(item, dict):
                continue
            if item.get("path") == source_file and isinstance(item.get("sha256"), str) and item["sha256"]:
                return str(item["sha256"])
    return None


def write_blocked_batch_preflight_report(
    *,
    profile: dict[str, Any],
    profile_path: Path,
    run_id: str,
    out_root: Path,
    profile_proof_class: str,
    proof_class: str,
    proof_class_resolution: dict[str, Any],
    mode: str,
    preflight_result: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    report_path = out_root / "harness" / "batch-profile-report.json"
    raw_preflight_path = preflight_result.get("report_path", out_root / "harness" / "opencode-preflight-report.json")
    preflight_report_path = repo_path(Path(str(raw_preflight_path)), repo_root=repo_root)
    stale_artifact_cleanup = cleanup_blocked_batch_preflight_stale_artifacts(
        out_root=out_root,
        repo_root=repo_root,
    )
    preflight_binding: dict[str, Any] = {
        "path": repo_relative(preflight_report_path, repo_root=repo_root),
        "sha256": sha256_file(preflight_report_path) if preflight_report_path.is_file() else "",
        "status": str(preflight_result.get("status", "failed")),
        "root_cause_key": str(preflight_result.get("root_cause_key", "")),
    }
    if isinstance(preflight_result.get("contract_verification"), dict):
        preflight_binding["contract_status"] = str(preflight_result["contract_verification"].get("status", ""))
    if isinstance(preflight_result.get("opencode_model_availability"), dict):
        preflight_binding["opencode_model_availability"] = preflight_result["opencode_model_availability"]

    h9_blocker = preflight_result.get("h9_blocker") if isinstance(preflight_result.get("h9_blocker"), dict) else None
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "batch-profile-report",
        "status": "blocked",
        "exit_code": 1,
        "blocked_phase": "opencode-preflight",
        "root_cause_key": str(preflight_result.get("root_cause_key", "opencode_preflight_failed")),
        "profile_id": profile_required_string(profile, "profile_id"),
        "profile_path": repo_relative(profile_path, repo_root=repo_root),
        "profile_sha256": sha256_file(profile_path),
        "run_id": run_id,
        "out_root": repo_relative(out_root, repo_root=repo_root),
        "profile_proof_class": profile_proof_class,
        "proof_class": proof_class,
        "proof_class_resolution": proof_class_resolution,
        "mode": mode,
        "worker_count": 0,
        "opencode_preflight_report": preflight_binding,
        "stale_artifact_cleanup": stale_artifact_cleanup,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "local_simulation_closes_p0_h9": False,
        "evidence_boundary": (
            "Batch profile stopped before planning because OpenCode preflight did not pass. "
            "No SQLite ledger, worker plan, OpenCode worker, semantic gate, or translation coverage claim was produced."
        ),
        "next_required_action": "rerun_on_real_opencode_glm51_max_host",
        "report_path": repo_relative(report_path, repo_root=repo_root),
    }
    if h9_blocker is not None:
        result["h9_blocker"] = h9_blocker
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, result)
    return result


def cleanup_blocked_batch_preflight_stale_artifacts(
    *,
    out_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    out_root = repo_path(out_root, repo_root=repo_root)
    out_root_resolved = out_root.resolve()
    removed_artifacts: list[str] = []
    errors: list[dict[str, str]] = []

    def remove_artifact(relative_path: Path) -> None:
        path = out_root / relative_path
        if not path.exists():
            return
        resolved = path.resolve()
        try:
            resolved.relative_to(out_root_resolved)
        except ValueError:
            errors.append(
                {
                    "path": str(relative_path.as_posix()),
                    "error": "refusing_to_remove_outside_out_root",
                }
            )
            return
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as exc:
            errors.append(
                {
                    "path": repo_relative(path, repo_root=repo_root),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return
        removed_artifacts.append(repo_relative(path, repo_root=repo_root))

    for relative_path in BLOCKED_PREFLIGHT_STALE_ARTIFACT_PATHS:
        remove_artifact(relative_path)
    for relative_path in BLOCKED_PREFLIGHT_STALE_ARTIFACT_DIRS:
        remove_artifact(relative_path)

    return {
        "status": "passed" if not errors else "failed",
        "scope": "blocked-opencode-preflight-stale-artifacts",
        "removed_artifacts": removed_artifacts,
        "error_count": len(errors),
        "errors": errors,
    }


def resolve_batch_profile_proof_class(
    profile: dict[str, Any],
    *,
    proof_class_override: str | None,
) -> tuple[str, str, dict[str, Any]]:
    profile_proof_class = profile_required_string(profile, "proof_class")
    if profile_proof_class not in ALLOWED_PROOF_CLASSES:
        raise SystemExit(f"unsupported proof_class in batch profile: {profile_proof_class}")
    if proof_class_override is not None and proof_class_override not in ALLOWED_PROOF_CLASSES:
        raise SystemExit(f"unsupported proof_class override: {proof_class_override}")
    effective_proof_class = proof_class_override or profile_proof_class
    resolution: dict[str, Any] = {
        "source": "cli-override" if proof_class_override is not None else "profile",
        "profile_proof_class": profile_proof_class,
        "effective_proof_class": effective_proof_class,
        "override_requested": proof_class_override is not None,
        "changed": proof_class_override is not None and proof_class_override != profile_proof_class,
    }
    if proof_class_override is not None:
        resolution["override_proof_class"] = proof_class_override
    return profile_proof_class, effective_proof_class, resolution


def proof_class_override_cli_suffix(
    *,
    proof_class_resolution: dict[str, Any] | None,
    fallback_proof_class: str | None,
) -> str:
    if not isinstance(proof_class_resolution, dict) or proof_class_resolution.get("source") != "cli-override":
        return ""
    proof_class = proof_class_resolution.get("effective_proof_class") or proof_class_resolution.get("override_proof_class")
    if proof_class is None:
        proof_class = fallback_proof_class
    if proof_class not in ALLOWED_PROOF_CLASSES:
        raise SystemExit(f"invalid proof_class override resolution: {proof_class}")
    return f" --proof-class {proof_class}"


def run_batch_profile(
    *,
    profile_path: Path,
    run_id: str,
    out_root: Path,
    proof_class_override: str | None = None,
    timeout_seconds: int | None = None,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    profile_path = repo_path(profile_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    profile = load_json(profile_path)
    acceptance_boundary = profile.get("acceptance_boundary")
    if acceptance_boundary is not None and not isinstance(acceptance_boundary, dict):
        raise SystemExit("batch profile field must be an object: acceptance_boundary")
    attempt_evidence_policy = profile.get("attempt_evidence_policy")
    if attempt_evidence_policy is not None and not isinstance(attempt_evidence_policy, dict):
        raise SystemExit("batch profile field must be an object: attempt_evidence_policy")
    if profile.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"unsupported batch profile schema_version: {profile.get('schema_version')}")
    profile_id = profile_required_string(profile, "profile_id")
    profile_proof_class, proof_class, proof_class_resolution = resolve_batch_profile_proof_class(
        profile,
        proof_class_override=proof_class_override,
    )
    require_competition_exact_host_attestation(proof_class, context="run-batch-profile")
    mode = profile_string(profile, "mode", default="deterministic")
    if mode not in {"deterministic", "opencode"}:
        raise SystemExit(f"unsupported mode in batch profile: {mode}")
    hostless_rehearsal_enabled = profile_bool(profile, "opencode_hostless_rehearsal", default=False)
    if hostless_rehearsal_enabled:
        if mode != "opencode":
            raise SystemExit("opencode_hostless_rehearsal requires mode=opencode")
        if proof_class != "local-simulation":
            raise SystemExit("opencode_hostless_rehearsal must use proof_class=local-simulation")
    opencode_preflight_report_text = profile_string(profile, "opencode_preflight_report")
    opencode_preflight_report = (
        Path(opencode_preflight_report_text) if opencode_preflight_report_text is not None else None
    )
    if mode == "opencode" and opencode_preflight_report is None:
        effective_timeout_seconds = profile_int(
            profile,
            "timeout_seconds",
            default=timeout_seconds or DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
        )
        preflight_result = run_opencode_preflight(
            out_root=out_root,
            run_id=run_id,
            opencode_command=profile_string(profile, "opencode_command", default="opencode") or "opencode",
            opencode_model=profile_string(profile, "opencode_model"),
            opencode_agent=profile_string(profile, "opencode_agent"),
            opencode_variant=profile_string(profile, "opencode_variant", default="max") or "max",
            opencode_skip_permissions=profile_bool(profile, "opencode_skip_permissions", default=False),
            opencode_allow_non_competition_model=profile_bool(
                profile,
                "opencode_allow_non_competition_model",
                default=False,
            ),
            timeout_seconds=effective_timeout_seconds,
            command_runner=command_runner,
            repo_root=repo_root,
        )
        opencode_preflight_report = Path(
            str(preflight_result.get("report_path", out_root / "harness" / "opencode-preflight-report.json"))
        )
        if preflight_result.get("status") != "passed" or int(preflight_result.get("exit_code", 1)) != 0:
            return write_blocked_batch_preflight_report(
                profile=profile,
                profile_path=profile_path,
                run_id=run_id,
                out_root=out_root,
                profile_proof_class=profile_proof_class,
                proof_class=proof_class,
                proof_class_resolution=proof_class_resolution,
                mode=mode,
                preflight_result=preflight_result,
                repo_root=repo_root,
            )

    reset_batch_profile_ledger(out_root=out_root, repo_root=repo_root)
    db_path = init_run(
        out_root=out_root,
        run_id=run_id,
        proof_class=proof_class,
        repo_root=repo_root,
    )
    if profile.get("workers") is not None:
        plan = plan_explicit_workers(
            db_path=db_path,
            run_id=run_id,
            profile=profile,
            out_root=out_root,
            repo_root=repo_root,
        )
    else:
        plan = plan_source_file(
            db_path=db_path,
            run_id=run_id,
            target_id=profile_required_string(profile, "target_id"),
            source_repo_root=Path(profile_required_string(profile, "source_repo_root")),
            source_repository=profile_string(profile, "source_repository"),
            source_branch=profile_string(profile, "source_branch"),
            source_file=profile_required_string(profile, "source_file"),
            functions=profile_string_list(profile, "functions"),
            source_commit=profile_required_string(profile, "source_commit"),
            require_source_commit=profile_string(profile, "require_source_commit"),
            slice_specs=profile_string_list(profile, "slice_specs"),
            compiler_command_source=profile_string(profile, "compiler_command_source"),
            include_paths=profile_string_list(profile, "include_paths"),
            defines=profile_string_list(profile, "defines"),
            reuse_accepted_evidence=profile_bool(profile, "reuse_accepted_evidence", default=False),
            accepted_evidence_root=profile_string(profile, "accepted_evidence_root"),
            out_root=out_root,
            slice_id_prefix=profile_required_string(profile, "slice_id_prefix"),
            worker_prefix=profile_string(profile, "worker_prefix", default="worker"),
            limit=profile_int(profile, "limit"),
            lease_ttl_seconds=profile_int(profile, "lease_ttl_seconds", default=3600),
            repo_root=repo_root,
        )
    run_result = run_plan(
        db_path=db_path,
        run_id=run_id,
        plan_path=Path(str(plan["plan_path"])),
        out_root=out_root,
        proof_class=proof_class,
        mode=mode,
        opencode_command=profile_string(profile, "opencode_command", default="opencode"),
        opencode_model=profile_string(profile, "opencode_model"),
        opencode_agent=profile_string(profile, "opencode_agent"),
        opencode_variant=profile_string(profile, "opencode_variant", default="max"),
        opencode_skip_permissions=profile_bool(profile, "opencode_skip_permissions", default=False),
        opencode_allow_non_competition_model=profile_bool(
            profile,
            "opencode_allow_non_competition_model",
            default=False,
        ),
        opencode_preflight_report=opencode_preflight_report,
        execute_merge=profile_bool(profile, "execute_merge", default=False),
        auto_retry=profile_bool(profile, "auto_retry", default=False),
        max_workers=profile_int(profile, "max_workers", default=1),
        timeout_seconds=profile_int(
            profile,
            "timeout_seconds",
            default=timeout_seconds or DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
        ),
        repair_trace=attempt_evidence_policy,
        command_runner=command_runner,
        repo_root=repo_root,
    )
    route_metrics_artifact = write_route_governance_metrics_profile_report(
        profile=profile,
        out_root=out_root,
        repo_root=repo_root,
    )
    before_after_exhibit_artifact = write_before_after_exhibit_profile_report(
        profile=profile,
        profile_path=profile_path,
        run_id=run_id,
        proof_class=proof_class,
        mode=mode,
        plan=plan,
        run_result=run_result,
        route_metrics_artifact=route_metrics_artifact,
        proof_class_resolution=proof_class_resolution,
        out_root=out_root,
        repo_root=repo_root,
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": run_result["status"],
        "exit_code": int(run_result["exit_code"]),
        "profile_id": profile_id,
        "profile_path": repo_relative(profile_path, repo_root=repo_root),
        "profile_sha256": sha256_file(profile_path),
        "run_id": run_id,
        "out_root": repo_relative(out_root, repo_root=repo_root),
        "db_path": repo_relative(db_path, repo_root=repo_root),
        "profile_proof_class": profile_proof_class,
        "proof_class": proof_class,
        "proof_class_resolution": proof_class_resolution,
        "mode": mode,
        "worker_count": len(plan["units"]),
        "plan_path": plan["plan_path"],
        "plan": plan,
        "run_plan": run_result,
    }
    if acceptance_boundary is not None:
        result["acceptance_boundary"] = acceptance_boundary
    if attempt_evidence_policy is not None:
        result["attempt_evidence_policy"] = attempt_evidence_policy
    if route_metrics_artifact is not None:
        result["route_governance_metrics_report"] = route_metrics_artifact["binding"]
    if before_after_exhibit_artifact is not None:
        result["before_after_exhibit_report"] = before_after_exhibit_artifact["binding"]
    if isinstance(run_result.get("opencode_preflight_report"), dict):
        result["opencode_preflight_report"] = run_result["opencode_preflight_report"]
    report_path = out_root / "harness" / "batch-profile-report.json"
    result["report_path"] = repo_relative(report_path, repo_root=repo_root)
    report_artifacts: dict[str, dict[str, Any]] = {}
    if isinstance(run_result.get("opencode_preflight_report"), dict):
        report_artifacts["opencode_preflight_report"] = run_result["opencode_preflight_report"]
    if route_metrics_artifact is not None:
        report_artifacts["route_governance_metrics_report"] = route_metrics_artifact["binding"]
    if before_after_exhibit_artifact is not None:
        report_artifacts["before_after_exhibit_report"] = before_after_exhibit_artifact["binding"]
    verified_baseline_ref = verified_unsafe_baseline_binding_from_sources(
        {"attempt_evidence_policy": attempt_evidence_policy} if attempt_evidence_policy is not None else None,
        repo_root=repo_root,
    )
    if verified_baseline_ref is not None:
        report_artifacts["verified_unsafe_baseline"] = verified_baseline_ref
    context_refs = write_context_pack_and_agent_index(
        db_path=db_path,
        run_id=run_id,
        target_id=profile_required_string(profile, "target_id"),
        proof_class=proof_class,
        mode=mode,
        out_root=out_root,
        plan=plan,
        run_result=run_result,
        primary_report_path=report_path,
        report_entrypoint="batch_profile_report",
        acceptance_boundary=acceptance_boundary,
        attempt_evidence_policy=attempt_evidence_policy,
        report_artifacts=report_artifacts,
        proof_class_resolution=proof_class_resolution,
        repo_root=repo_root,
    )
    result.update(context_refs)
    result["judge_summary"] = build_judge_summary(
        entrypoint="run-batch-profile",
        proof_class=proof_class,
        mode=mode,
        plan=plan,
        run_result=run_result,
        context_refs=context_refs,
        acceptance_boundary=acceptance_boundary,
        route_metrics_artifact=route_metrics_artifact,
        before_after_exhibit_artifact=before_after_exhibit_artifact,
        repo_root=repo_root,
    )
    hostless_rehearsal_artifact = None
    if hostless_rehearsal_enabled:
        hostless_rehearsal_artifact = write_opencode_hostless_rehearsal_report(
            profile=profile,
            run_id=run_id,
            proof_class=proof_class,
            mode=mode,
            run_result=run_result,
            context_refs=context_refs,
            batch_profile_report_path=report_path,
            out_root=out_root,
            repo_root=repo_root,
        )
        result["opencode_hostless_rehearsal_report"] = hostless_rehearsal_artifact["binding"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, result)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="batch-profile-report",
            path=report_path,
            status=str(result["status"]),
            semantic_role="batch-profile-report",
            payload=result,
            repo_root=repo_root,
        )
        if route_metrics_artifact is not None:
            binding = route_metrics_artifact["binding"]
            record_artifact(
                connection,
                run_id=run_id,
                worker_id="planner",
                kind="route-governance-metrics-report",
                path=repo_path(Path(binding["path"]), repo_root=repo_root),
                status=str(binding["status"]),
                semantic_role="route-governance-metrics",
                payload=route_metrics_artifact["payload"],
                repo_root=repo_root,
            )
        if before_after_exhibit_artifact is not None:
            binding = before_after_exhibit_artifact["binding"]
            record_artifact(
                connection,
                run_id=run_id,
                worker_id="planner",
                kind="before-after-exhibit-report",
                path=repo_path(Path(binding["path"]), repo_root=repo_root),
                status=str(binding["status"]),
                semantic_role="before-after-exhibit",
                payload=before_after_exhibit_artifact["payload"],
                repo_root=repo_root,
            )
        if hostless_rehearsal_artifact is not None:
            binding = hostless_rehearsal_artifact["binding"]
            record_artifact(
                connection,
                run_id=run_id,
                worker_id="planner",
                kind="opencode-hostless-rehearsal-report",
                path=repo_path(Path(binding["path"]), repo_root=repo_root),
                status=str(binding["status"]),
                semantic_role="opencode-hostless-rehearsal",
                payload=hostless_rehearsal_artifact["payload"],
                repo_root=repo_root,
            )
        record_event(connection, run_id=run_id, event_type="batch_profile_executed", payload=result)
        connection.commit()
    return result


def write_opencode_hostless_rehearsal_report(
    *,
    profile: dict[str, Any],
    run_id: str,
    proof_class: str,
    mode: str,
    run_result: dict[str, Any],
    context_refs: dict[str, dict[str, str]],
    batch_profile_report_path: Path,
    out_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if mode != "opencode":
        raise SystemExit("hostless OpenCode rehearsal requires mode=opencode")
    if proof_class != "local-simulation":
        raise SystemExit("hostless OpenCode rehearsal cannot close P0-H9")
    out_root = repo_path(out_root, repo_root=repo_root)
    report_path = out_root / "harness" / "opencode-hostless-rehearsal-report.json"
    rehearsal_runner = profile_string(profile, "opencode_hostless_rehearsal_runner", default="fake/fixture")
    rehearsal_runner = rehearsal_runner or "fake/fixture"
    preflight = artifact_binding_from_value(run_result.get("opencode_preflight_report"), repo_root=repo_root)
    runtime = opencode_agent_runtime_evidence(run_result, repo_root=repo_root)
    workers = []
    for worker in run_result.get("workers") if isinstance(run_result.get("workers"), list) else []:
        if not isinstance(worker, dict):
            continue
        entry: dict[str, Any] = {
            "worker_id": str(worker.get("worker_id", "")),
            "slice_id": worker.get("slice_id"),
            "function": worker.get("function"),
            "summary_status": worker.get("summary_status"),
            "exit_code": int(worker.get("exit_code", 1)),
            "recorded": bool(worker.get("recorded")),
            "semantic_gate": False,
        }
        for field in ("summary_path", "report_path"):
            binding = path_ref_from_text(worker.get(field), repo_root=repo_root)
            if binding is not None:
                entry[field.removesuffix("_path")] = binding
        for field in (
            "handoff_contract",
            "opencode_session_evidence",
            "opencode_safety_transform_attempt",
            "opencode_preflight_report",
        ):
            binding = artifact_binding_from_value(worker.get(field), repo_root=repo_root)
            if binding is not None:
                entry[field] = binding
        if isinstance(worker.get("opencode_contract_verification"), dict):
            entry["opencode_contract_verification"] = json.loads(json.dumps(worker["opencode_contract_verification"]))
        if isinstance(worker.get("opencode_runtime_env"), dict):
            entry["opencode_runtime_env"] = json.loads(json.dumps(worker["opencode_runtime_env"]))
        if isinstance(worker.get("final_decision"), dict):
            entry["final_decision"] = json.loads(json.dumps(worker["final_decision"]))
        workers.append(entry)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "opencode-hostless-rehearsal-report",
        "status": str(run_result.get("status", "unknown")),
        "exit_code": int(run_result.get("exit_code", 1)),
        "run_id": run_id,
        "profile_id": profile.get("profile_id"),
        "proof_class": proof_class,
        "mode": mode,
        "rehearsal_runner": rehearsal_runner,
        "closes_p0_h9": False,
        "semantic_gate": False,
        "chat_output_is_evidence": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "h9_contract": {
            "status": "blocked",
            "reason": "hostless_rehearsal_is_not_real_opencode_glm51_max_host_evidence",
            "required_agent_tool": COMPETITION_OPENCODE_COMMAND,
            "required_agent": COMPETITION_OPENCODE_AGENT,
            "required_model": COMPETITION_OPENCODE_MODEL,
            "required_variant": COMPETITION_OPENCODE_VARIANT,
            "required_proof_class": "competition-exact",
            "local_simulation_closes_p0_h9": False,
        },
        "batch_profile_report": {
            "path": repo_relative(batch_profile_report_path, repo_root=repo_root),
            "sha256": sha256_file(batch_profile_report_path) if batch_profile_report_path.is_file() else "",
        },
        "run_plan_report": path_ref_from_text(run_result.get("report_path"), repo_root=repo_root),
        "context_pack": context_refs.get("context_pack"),
        "agent_index": context_refs.get("agent_index"),
        "opencode_preflight_report": preflight,
        "opencode_runtime": runtime,
        "workers": workers,
        "worker_count": len(workers),
        "boundary": (
            "This report is a local hostless rehearsal of the OpenCode harness path. "
            "It can catch wiring regressions but cannot close P0-H9 or replace a real "
            "OpenCode + GLM-5.1 + max competition-host run."
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, payload)
    binding = artifact_ref(report_path, repo_root=repo_root)
    binding.update(
        {
            "status": str(payload["status"]),
            "report_kind": "opencode-hostless-rehearsal-report",
            "closes_p0_h9": False,
        }
    )
    return {"binding": binding, "payload": payload}


def write_evaluate_profile_report(
    *,
    batch_result: dict[str, Any],
    profile_path: Path,
    run_id: str,
    out_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    profile_path = repo_path(profile_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    report_path = out_root / "harness" / "evaluate-report.json"
    judge_index_path = out_root / "harness" / "judge-evidence-index.json"
    judge_index_rel = repo_relative(judge_index_path, repo_root=repo_root)
    batch_report_path_text = batch_result.get("report_path")
    batch_report_path: Path | None = None
    batch_report_ref = {"path": str(batch_report_path_text or ""), "sha256": ""}
    if isinstance(batch_report_path_text, str) and batch_report_path_text:
        batch_report_path = repo_path(Path(batch_report_path_text), repo_root=repo_root)
        batch_report_ref = (
            artifact_ref(batch_report_path, repo_root=repo_root)
            if batch_report_path.is_file()
            else {"path": batch_report_path_text, "sha256": ""}
        )
    run_plan = batch_result.get("run_plan") if isinstance(batch_result.get("run_plan"), dict) else {}
    merge_execution = (
        run_plan.get("merge_execution") if isinstance(run_plan.get("merge_execution"), dict) else {}
    )
    summary_path_text = merge_execution.get("summary_path")
    summary_validation: dict[str, Any] | None = None
    if isinstance(summary_path_text, str) and summary_path_text:
        summary_path = repo_path(Path(summary_path_text), repo_root=repo_root)
        if summary_path.exists():
            summary_validation = validate_competition_run_summary.validate_summary(summary_path, repo_root=repo_root)

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "evaluate-report",
        "entrypoint": "evaluate --profile",
        "status": str(batch_result.get("status", "unknown")),
        "exit_code": int(batch_result.get("exit_code", 1)),
        "run_id": run_id,
        "out_root": repo_relative(out_root, repo_root=repo_root),
        "profile": artifact_ref(profile_path, repo_root=repo_root),
        "profile_id": batch_result.get("profile_id"),
        "profile_proof_class": batch_result.get("profile_proof_class"),
        "proof_class": batch_result.get("proof_class"),
        "proof_class_resolution": batch_result.get("proof_class_resolution"),
        "mode": batch_result.get("mode"),
        "batch_profile_report": batch_report_ref,
        "context_pack": batch_result.get("context_pack"),
        "agent_index": batch_result.get("agent_index"),
        "summary_validation": summary_validation,
        "judge_summary": evaluate_profile_judge_summary(batch_result.get("judge_summary")),
        "sidecar_reports": {
            "judge_evidence_index": {
                "path": judge_index_rel,
                "report_kind": "judge-evidence-index",
                "status": str(batch_result.get("status", "unknown")),
            },
        },
        "claim_boundary": (
            "This evaluate wrapper is the judge-facing entrypoint for a full batch-profile run. "
            "It indexes verified reports only; semantic acceptance remains owned by the final "
            "competition summary, workflow metrics, and validators; it is not a new semantic gate."
        ),
    }
    if "acceptance_boundary" in batch_result:
        payload["acceptance_boundary"] = batch_result["acceptance_boundary"]
    if "route_governance_metrics_report" in batch_result:
        payload["route_governance_metrics_report"] = batch_result["route_governance_metrics_report"]
    if "before_after_exhibit_report" in batch_result:
        payload["before_after_exhibit_report"] = batch_result["before_after_exhibit_report"]
    if isinstance(batch_result.get("opencode_preflight_report"), dict):
        payload["opencode_preflight_report"] = batch_result["opencode_preflight_report"]
    elif isinstance(run_plan.get("opencode_preflight_report"), dict):
        payload["opencode_preflight_report"] = run_plan["opencode_preflight_report"]
    architecture = payload.get("judge_summary", {}).get("harness_architecture")
    if isinstance(architecture, dict):
        graph = run_plan.get("graph") if isinstance(run_plan.get("graph"), dict) else {}
        architecture.setdefault("architecture_contracts", build_architecture_contracts(graph))
    payload["judge_headline"] = build_judge_headline(
        entrypoint="evaluate",
        status=str(payload["status"]),
        proof_class=str(payload.get("proof_class", "")),
        mode=str(payload.get("mode", "")),
        judge_summary=payload.get("judge_summary"),
        acceptance_boundary=payload.get("acceptance_boundary"),
        route_metrics=payload.get("route_governance_metrics_report"),
        opencode_runtime=opencode_agent_runtime_evidence(run_plan, repo_root=repo_root),
    )

    payload["report_path"] = repo_relative(report_path, repo_root=repo_root)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, payload)

    db_path: Path | None = None
    db_path_text = batch_result.get("db_path")
    if isinstance(db_path_text, str) and db_path_text:
        db_path = repo_path(Path(db_path_text), repo_root=repo_root)
        context_refs = update_evaluate_profile_context_refs(
            db_path=db_path,
            run_id=run_id,
            out_root=out_root,
            evaluate_report_path=report_path,
            batch_profile_report_path=batch_report_ref["path"],
            judge_evidence_index_path=judge_index_path,
            status=str(payload["status"]),
            attempt_evidence_policy=batch_result.get("attempt_evidence_policy")
            if isinstance(batch_result.get("attempt_evidence_policy"), dict)
            else None,
            repo_root=repo_root,
        )
        if batch_report_path is not None and batch_report_path.is_file():
            batch_report_ref = update_batch_profile_report_context_refs(
                batch_report_path=batch_report_path,
                context_refs=context_refs,
                repo_root=repo_root,
            )
            payload["batch_profile_report"] = batch_report_ref
        payload.update(context_refs)
        architecture = payload.get("judge_summary", {}).get("harness_architecture")
        if isinstance(architecture, dict):
            architecture["context_pack"] = context_refs["context_pack"]
            architecture["agent_index"] = context_refs["agent_index"]
        payload["judge_headline"] = build_judge_headline(
            entrypoint="evaluate",
            status=str(payload["status"]),
            proof_class=str(payload.get("proof_class", "")),
            mode=str(payload.get("mode", "")),
            judge_summary=payload.get("judge_summary"),
            acceptance_boundary=payload.get("acceptance_boundary"),
            route_metrics=payload.get("route_governance_metrics_report"),
            opencode_runtime=opencode_agent_runtime_evidence(run_plan, repo_root=repo_root),
        )
        atomic_write_json(report_path, payload)
        with closing(connect(db_path)) as connection:
            ensure_schema(connection)
            record_artifact(
                connection,
                run_id=run_id,
                worker_id="planner",
                kind="evaluate-report",
                path=report_path,
                status=str(payload["status"]),
                semantic_role="evaluate-report",
                payload=payload,
                repo_root=repo_root,
            )
            if batch_report_path is not None and batch_report_path.is_file():
                record_artifact(
                    connection,
                    run_id=run_id,
                    worker_id="planner",
                    kind="batch-profile-report",
                    path=batch_report_path,
                    status=str(batch_result.get("status", payload["status"])),
                    semantic_role="batch-profile-report",
                    payload=load_json(batch_report_path),
                    repo_root=repo_root,
                )
            record_event(connection, run_id=run_id, event_type="evaluate_profile_executed", payload=payload)
            connection.commit()
    judge_index_artifact = write_judge_evidence_index(
        evaluate_report=payload,
        evaluate_report_path=report_path,
        batch_result=batch_result,
        profile_path=profile_path,
        run_id=run_id,
        out_root=out_root,
        extra_artifact_refs={"resume_manifest": payload["resume_manifest"]}
        if isinstance(payload.get("resume_manifest"), dict)
        else None,
        repo_root=repo_root,
    )
    if db_path is not None:
        with closing(connect(db_path)) as connection:
            ensure_schema(connection)
            record_artifact(
                connection,
                run_id=run_id,
                worker_id="planner",
                kind="judge-evidence-index",
                path=repo_path(Path(judge_index_artifact["binding"]["path"]), repo_root=repo_root),
                status=str(judge_index_artifact["binding"]["status"]),
                semantic_role="judge-evidence-index",
                payload=judge_index_artifact["payload"],
                repo_root=repo_root,
            )
            record_event(
                connection,
                run_id=run_id,
                event_type="judge_evidence_index_written",
                payload=judge_index_artifact["binding"],
            )
            connection.commit()
    return payload


def write_judge_evidence_index(
    *,
    evaluate_report: dict[str, Any],
    evaluate_report_path: Path,
    batch_result: dict[str, Any],
    profile_path: Path,
    run_id: str,
    out_root: Path,
    entrypoint_name: str = "evaluate --profile",
    primary_report_ref_name: str = "evaluate_report",
    reproduction_commands: dict[str, str] | None = None,
    extra_artifact_refs: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    out_root = repo_path(out_root, repo_root=repo_root)
    profile_path = repo_path(profile_path, repo_root=repo_root)
    evaluate_report_path = repo_path(evaluate_report_path, repo_root=repo_root)
    index_path = out_root / "harness" / "judge-evidence-index.json"
    judge_summary = evaluate_report.get("judge_summary") if isinstance(evaluate_report.get("judge_summary"), dict) else {}
    architecture = (
        json.loads(json.dumps(judge_summary.get("harness_architecture")))
        if isinstance(judge_summary.get("harness_architecture"), dict)
        else {}
    )
    core_quality = (
        json.loads(json.dumps(judge_summary.get("core_translation_quality")))
        if isinstance(judge_summary.get("core_translation_quality"), dict)
        else {}
    )
    if "architecture_contracts" not in architecture:
        run_plan = batch_result.get("run_plan") if isinstance(batch_result.get("run_plan"), dict) else {}
        graph = run_plan.get("graph") if isinstance(run_plan.get("graph"), dict) else {}
        architecture["architecture_contracts"] = build_architecture_contracts(graph)
    artifact_refs: dict[str, dict[str, Any]] = {}

    def add_binding(name: str, value: Any) -> None:
        binding = artifact_binding_from_value(value, repo_root=repo_root)
        if binding is not None:
            artifact_refs[name] = binding

    def add_path(name: str, value: Any) -> None:
        if not isinstance(value, str) or not value:
            return
        path = repo_path(Path(value), repo_root=repo_root)
        artifact_refs[name] = (
            artifact_ref(path, repo_root=repo_root)
            if path.is_file()
            else {"path": value, "sha256": ""}
        )

    if not primary_report_ref_name or primary_report_ref_name == "judge_evidence_index":
        raise ValueError("primary_report_ref_name must be a non-self evidence ref name")
    artifact_refs[primary_report_ref_name] = artifact_ref(evaluate_report_path, repo_root=repo_root)
    artifact_refs["profile"] = artifact_ref(profile_path, repo_root=repo_root)
    add_binding("batch_profile_report", evaluate_report.get("batch_profile_report"))
    add_binding("context_pack", evaluate_report.get("context_pack"))
    add_binding("agent_index", evaluate_report.get("agent_index"))
    add_binding("route_governance_metrics_report", evaluate_report.get("route_governance_metrics_report"))
    add_binding("before_after_exhibit_report", evaluate_report.get("before_after_exhibit_report"))
    add_binding(
        "verified_unsafe_baseline",
        verified_unsafe_baseline_ref_from_sources(batch_result, evaluate_report, core_quality),
    )

    summary_validation = (
        evaluate_report.get("summary_validation")
        if isinstance(evaluate_report.get("summary_validation"), dict)
        else {}
    )
    summary_path_text = summary_validation.get("summary") if isinstance(summary_validation, dict) else None
    if isinstance(summary_path_text, str) and summary_path_text:
        add_path("competition_run_summary", summary_path_text)
        summary_path = repo_path(Path(summary_path_text), repo_root=repo_root)
        if summary_path.is_file():
            summary = load_json(summary_path)
            workflow_metrics_ref = summary.get("workflow_metrics")
            if isinstance(workflow_metrics_ref, dict) and isinstance(workflow_metrics_ref.get("path"), str):
                workflow_metrics_path = validate_competition_run_summary.resolve_summary_artifact(
                    workflow_metrics_ref["path"],
                    summary_path=summary_path,
                    repo_root=repo_root,
                )
                if workflow_metrics_path is not None and workflow_metrics_path.is_file():
                    artifact_refs["workflow_metrics"] = artifact_ref(workflow_metrics_path, repo_root=repo_root)
                else:
                    add_binding("workflow_metrics", workflow_metrics_ref)
            else:
                add_binding("workflow_metrics", workflow_metrics_ref)

    run_plan = batch_result.get("run_plan") if isinstance(batch_result.get("run_plan"), dict) else {}
    add_path("run_plan_report", run_plan.get("report_path"))
    add_binding("opencode_preflight_report", evaluate_report.get("opencode_preflight_report"))
    add_binding("opencode_preflight_report", batch_result.get("opencode_preflight_report"))
    add_binding("opencode_preflight_report", run_plan.get("opencode_preflight_report"))
    for worker in run_plan.get("workers") if isinstance(run_plan.get("workers"), list) else []:
        if not isinstance(worker, dict):
            continue
        binding = artifact_binding_from_value(worker.get("opencode_safety_transform_attempt"), repo_root=repo_root)
        if binding is not None:
            artifact_refs["opencode_safety_transform_attempt"] = binding
            break
    merge_plan = run_plan.get("merge_plan") if isinstance(run_plan.get("merge_plan"), dict) else {}
    add_path("merge_plan", merge_plan.get("path"))
    add_path("worker_plan", batch_result.get("plan_path"))
    if isinstance(extra_artifact_refs, dict):
        for name, value in sorted(extra_artifact_refs.items()):
            if name == "judge_evidence_index":
                raise ValueError("judge_evidence_index must not be listed as an evidence artifact ref")
            if isinstance(value, dict):
                binding = artifact_binding_from_value(value, repo_root=repo_root)
                if binding is not None:
                    artifact_refs[name] = binding
            elif isinstance(value, str) and value:
                add_path(name, value)

    profile_rel = repo_relative(profile_path, repo_root=repo_root)
    out_root_rel = repo_relative(out_root, repo_root=repo_root)
    proof_class_suffix = proof_class_override_cli_suffix(
        proof_class_resolution=evaluate_report.get("proof_class_resolution")
        if isinstance(evaluate_report.get("proof_class_resolution"), dict)
        else None,
        fallback_proof_class=str(evaluate_report.get("proof_class", "")),
    )
    if reproduction_commands is None:
        reproduction_commands = {
            "evaluate_profile": (
                "python3 -B -m validation.tools.opencode_agent_harness evaluate "
                f"--profile {profile_rel} --run-id {run_id} --out-root {out_root_rel}"
                f"{proof_class_suffix}"
            ),
            "run_batch_profile": (
                "python3 -B -m validation.tools.opencode_agent_harness run-batch-profile "
                f"--profile {profile_rel} --run-id {run_id} --out-root {out_root_rel}"
                f"{proof_class_suffix}"
            ),
        }
        if isinstance(summary_path_text, str) and summary_path_text:
            reproduction_commands["summary_validation"] = (
                "python3 -B validation/tools/validate_competition_run_summary.py "
                f"--summary {summary_path_text}"
            )
    else:
        reproduction_commands = dict(reproduction_commands)

    acceptance_boundary = (
        evaluate_report.get("acceptance_boundary")
        if isinstance(evaluate_report.get("acceptance_boundary"), dict)
        else {}
    )
    route_metrics = (
        evaluate_report.get("route_governance_metrics_report")
        if isinstance(evaluate_report.get("route_governance_metrics_report"), dict)
        else {}
    )
    generated_draft_semantic_pass = acceptance_boundary.get(
        "generated_draft_semantic_pass",
        core_quality.get("generated_draft_semantic_pass", False),
    )
    if not isinstance(generated_draft_semantic_pass, bool):
        generated_draft_semantic_pass = False
    translation_coverage_numerator = route_metrics.get("translation_coverage_numerator", 0)
    if isinstance(translation_coverage_numerator, bool):
        translation_coverage_numerator = 0
    try:
        translation_coverage_numerator_int = int(translation_coverage_numerator)
    except (TypeError, ValueError):
        translation_coverage_numerator_int = 0
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "judge-evidence-index",
        "entrypoint": entrypoint_name,
        "status": str(evaluate_report.get("status", "unknown")),
        "exit_code": int(evaluate_report.get("exit_code", 1)),
        "run_id": run_id,
        "out_root": out_root_rel,
        "profile": artifact_ref(profile_path, repo_root=repo_root),
        "profile_id": evaluate_report.get("profile_id"),
        "proof_class": evaluate_report.get("proof_class"),
        "mode": evaluate_report.get("mode"),
        "harness_architecture": architecture,
        "core_translation_quality": core_quality,
        "evidence_artifact_refs": artifact_refs,
        "reproduction_commands": reproduction_commands,
        "claim_boundary": {
            "index_is_semantic_gate": False,
            "semantic_claim_source": core_quality.get(
                "semantic_claim_source",
                acceptance_boundary.get("semantic_claim_source", "unknown"),
            ),
            "generated_draft_semantic_pass": generated_draft_semantic_pass,
            "translation_coverage_numerator": translation_coverage_numerator_int,
            "boundary": (
                "This file is a compact judge-facing index over existing verified artifacts. "
                "It does not add a semantic acceptance gate, does not self-reference its own hash, "
                "and does not count accepted-evidence bindings as translator-generated semantic pass."
            ),
        },
    }
    opencode_runtime = opencode_agent_runtime_evidence(run_plan, repo_root=repo_root)
    if opencode_runtime is not None:
        payload["opencode_agent_runtime"] = opencode_runtime
    payload["judge_headline"] = build_judge_headline(
        entrypoint="evaluate",
        status=str(payload["status"]),
        proof_class=str(payload.get("proof_class", "")),
        mode=str(payload.get("mode", "")),
        judge_summary=judge_summary,
        acceptance_boundary=acceptance_boundary,
        claim_boundary=payload["claim_boundary"],
        route_metrics=route_metrics,
        opencode_runtime=opencode_runtime,
    )
    index_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(index_path, payload)
    binding = artifact_ref(index_path, repo_root=repo_root)
    binding.update(
        {
            "status": str(payload["status"]),
            "report_kind": "judge-evidence-index",
        }
    )
    return {"binding": binding, "payload": payload}


def opencode_agent_runtime_evidence(
    run_plan: dict[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any] | None:
    preflight = artifact_binding_from_value(run_plan.get("opencode_preflight_report"), repo_root=repo_root)
    workers: list[dict[str, Any]] = []
    raw_workers = run_plan.get("workers") if isinstance(run_plan.get("workers"), list) else []
    for worker in raw_workers:
        if not isinstance(worker, dict):
            continue
        runtime_entry: dict[str, Any] = {
            "worker_id": str(worker.get("worker_id", "")),
            "chat_output_is_evidence": False,
            "semantic_gate": False,
        }
        summary_binding = path_ref_from_text(worker.get("summary_path"), repo_root=repo_root)
        if summary_binding is not None:
            runtime_entry["summary"] = summary_binding
        worker_report_binding = path_ref_from_text(worker.get("report_path"), repo_root=repo_root)
        if worker_report_binding is not None:
            runtime_entry["worker_report"] = worker_report_binding
        logs = worker.get("logs") if isinstance(worker.get("logs"), dict) else {}
        log_refs = {}
        for name in ("stdout", "stderr"):
            log_ref = path_ref_from_text(logs.get(name), repo_root=repo_root)
            if log_ref is not None:
                log_refs[name] = log_ref
        if log_refs:
            runtime_entry["logs"] = log_refs
        for field in (
            "handoff_contract",
            "opencode_session_evidence",
            "opencode_safety_transform_attempt",
            "opencode_preflight_report",
        ):
            binding = artifact_binding_from_value(worker.get(field), repo_root=repo_root)
            if binding is not None:
                runtime_entry[field] = binding
        if isinstance(worker.get("opencode_runtime_env"), dict):
            runtime_entry["opencode_runtime_env"] = json.loads(json.dumps(worker["opencode_runtime_env"]))
        verification = worker.get("opencode_contract_verification")
        if isinstance(verification, dict):
            runtime_entry["opencode_contract_verification"] = json.loads(json.dumps(verification))
            runtime_entry["contract_verification_status"] = str(verification.get("status", "unknown"))
        if isinstance(worker.get("final_decision"), dict):
            runtime_entry["final_decision"] = json.loads(json.dumps(worker["final_decision"]))
        if any(field in runtime_entry for field in OPENCODE_WORKER_EVIDENCE_FIELDS):
            workers.append(runtime_entry)
    if preflight is None and not workers:
        return None
    contract_status_counts: dict[str, int] = {}
    failed_or_missing_contract_workers = []
    for worker in workers:
        contract_status = str(worker.get("contract_verification_status", "missing"))
        contract_status_counts[contract_status] = contract_status_counts.get(contract_status, 0) + 1
        if contract_status != "executed":
            failed_or_missing_contract_workers.append(str(worker.get("worker_id", "")))
    payload: dict[str, Any] = {
        "runtime": "opencode",
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "worker_count": len(workers),
        "contract_status_counts": contract_status_counts,
        "all_contracts_executed": bool(workers) and not failed_or_missing_contract_workers,
        "failed_or_missing_contract_workers": failed_or_missing_contract_workers,
        "workers": workers,
        "boundary": (
            "OpenCode chat/session output is indexed for command-contract audit only; "
            "semantic acceptance remains owned by validator artifacts and final summaries."
        ),
    }
    if preflight is not None:
        payload["opencode_preflight_report"] = preflight
    return payload


def evaluate_profile_judge_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    summary = json.loads(json.dumps(value))
    summary["entrypoint"] = "evaluate"
    architecture = summary.get("harness_architecture")
    if isinstance(architecture, dict):
        architecture["entrypoint"] = "evaluate"
    return summary


def update_evaluate_profile_context_refs(
    *,
    db_path: Path,
    run_id: str,
    out_root: Path,
    evaluate_report_path: Path,
    batch_profile_report_path: str,
    judge_evidence_index_path: Path,
    status: str,
    attempt_evidence_policy: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, dict[str, str]]:
    context_pack_path = out_root / "harness" / "context-pack.json"
    agent_index_path = out_root / "harness" / "agent-index.json"
    resume_manifest_path = out_root / "harness" / "resume-manifest.json"
    evaluate_report_rel = repo_relative(evaluate_report_path, repo_root=repo_root)
    judge_index_rel = repo_relative(judge_evidence_index_path, repo_root=repo_root)
    resume_manifest_rel = repo_relative(resume_manifest_path, repo_root=repo_root)
    context_graph: dict[str, Any] = {}
    verified_policy: dict[str, Any] | None = None
    verified_baseline_ref: dict[str, Any] | None = None

    if context_pack_path.exists():
        context_pack = load_json(context_pack_path)
        context_graph = context_pack.get("graph") if isinstance(context_pack.get("graph"), dict) else {}
        verified_policy = attempt_evidence_policy_from_sources(attempt_evidence_policy, context_pack)
        verified_baseline_ref = verified_unsafe_baseline_binding_from_sources(
            {"attempt_evidence_policy": verified_policy} if verified_policy is not None else None,
            context_pack,
            repo_root=repo_root,
        )
        entrypoints = context_pack.setdefault("entrypoints", {})
        if isinstance(entrypoints, dict):
            entrypoints["primary_report"] = evaluate_report_rel
            entrypoints["evaluate_report"] = evaluate_report_rel
            entrypoints["judge_evidence_index"] = judge_index_rel
            entrypoints["resume_manifest"] = resume_manifest_rel
            if batch_profile_report_path:
                entrypoints["batch_profile_report"] = batch_profile_report_path
            if verified_baseline_ref is not None:
                entrypoints["verified_unsafe_baseline"] = verified_baseline_ref["path"]
        if verified_policy is not None:
            context_pack["attempt_evidence_policy"] = bind_verified_baseline_into_policy(
                verified_policy,
                verified_baseline_ref,
            )
        if verified_baseline_ref is not None:
            report_artifacts = context_pack.setdefault("report_artifacts", {})
            if isinstance(report_artifacts, dict):
                report_artifacts["verified_unsafe_baseline"] = verified_baseline_ref
        context_pack["context_management_contract"] = build_context_management_contract(
            graph=context_graph,
            db_path=db_path,
            primary_report_path=evaluate_report_path,
            context_pack_path=context_pack_path,
            agent_index_path=agent_index_path,
            report_entrypoint="evaluate_report",
            repo_root=repo_root,
        )
        atomic_write_json(context_pack_path, context_pack)

    if agent_index_path.exists():
        agent_index = load_json(agent_index_path)
        verified_policy = attempt_evidence_policy_from_sources(verified_policy, attempt_evidence_policy, agent_index)
        verified_baseline_ref = verified_unsafe_baseline_binding_from_sources(
            {"attempt_evidence_policy": verified_policy} if verified_policy is not None else None,
            agent_index,
            repo_root=repo_root,
        ) or verified_baseline_ref
        reports = agent_index.setdefault("reports", {})
        if isinstance(reports, dict):
            reports["evaluate_report"] = {
                "path": evaluate_report_rel,
                "report_kind": "evaluate-report",
                "status": status,
            }
            reports["judge_evidence_index"] = {
                "path": judge_index_rel,
                "report_kind": "judge-evidence-index",
                "status": status,
            }
            reports["resume_manifest"] = {
                "path": resume_manifest_rel,
                "report_kind": "resume-manifest",
                "status": status,
            }
            if batch_profile_report_path:
                reports["batch_profile_report"] = {
                    "path": batch_profile_report_path,
                    "report_kind": "batch-profile-report",
                    "status": status,
                }
            if verified_baseline_ref is not None:
                reports["verified_unsafe_baseline"] = verified_baseline_ref
        if verified_policy is not None:
            agent_index["attempt_evidence_policy"] = bind_verified_baseline_into_policy(
                verified_policy,
                verified_baseline_ref,
            )
        agents = agent_index.get("agents") if isinstance(agent_index.get("agents"), list) else []
        agent_index["agent_coordination_contract"] = build_agent_coordination_contract(
            graph=context_graph,
            db_path=db_path,
            worker_count=len(agents),
            mode=str(agent_index.get("mode")) if isinstance(agent_index.get("mode"), str) else None,
            repo_root=repo_root,
        )
        atomic_write_json(agent_index_path, agent_index)

    context_pack_ref = artifact_ref(context_pack_path, repo_root=repo_root)
    agent_index_ref = artifact_ref(agent_index_path, repo_root=repo_root)
    context_pack = load_json(context_pack_path)
    agent_index = load_json(agent_index_path)
    resume_manifest_ref: dict[str, str] | None = None
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        resume_manifest_payload = build_resume_manifest(
            db_path=db_path,
            run_id=run_id,
            out_root=out_root,
            status=status,
            context_pack=context_pack,
            context_pack_ref=context_pack_ref,
            agent_index=agent_index,
            agent_index_ref=agent_index_ref,
            evaluate_report_path=evaluate_report_path,
            batch_profile_report_path=batch_profile_report_path,
            judge_evidence_index_path=judge_evidence_index_path,
            resume_manifest_path=resume_manifest_path,
            repair_hints=repair_hint_resume_summary(connection, run_id=run_id),
            attempt_evidence_policy=verified_policy,
            repo_root=repo_root,
        )
        atomic_write_json(resume_manifest_path, resume_manifest_payload)
        resume_manifest_ref = artifact_ref(resume_manifest_path, repo_root=repo_root)
        resume_manifest_ref.update({"status": status, "report_kind": "resume-manifest"})
        connection.execute(
            """
            insert into context_packs(
              context_pack_id, run_id, target_id, slice_id, depth, max_tokens,
              artifact_path, artifact_sha256, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(context_pack_id) do update set
              run_id=excluded.run_id,
              target_id=excluded.target_id,
              slice_id=excluded.slice_id,
              depth=excluded.depth,
              max_tokens=excluded.max_tokens,
              artifact_path=excluded.artifact_path,
              artifact_sha256=excluded.artifact_sha256,
              payload_json=excluded.payload_json
            """,
            (
                str(context_pack.get("context_pack_id", f"{run_id}-context-pack")),
                run_id,
                str(context_pack.get("target_id", "")),
                None,
                int(context_pack.get("budget", {}).get("depth", 1)),
                int(context_pack.get("budget", {}).get("max_tokens", 20000)),
                context_pack_ref["path"],
                context_pack_ref["sha256"],
                json.dumps(context_pack, sort_keys=True),
            ),
        )
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="context-pack",
            path=context_pack_path,
            status=status,
            semantic_role="agent-context-pack",
            payload=context_pack,
            repo_root=repo_root,
        )
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="agent-index",
            path=agent_index_path,
            status=status,
            semantic_role="agent-index",
            payload=agent_index,
            repo_root=repo_root,
        )
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="resume-manifest",
            path=resume_manifest_path,
            status=status,
            semantic_role="resume-manifest",
            payload=resume_manifest_payload,
            repo_root=repo_root,
        )
        record_event(
            connection,
            run_id=run_id,
            event_type="evaluate_profile_context_refs_updated",
            payload={
                "context_pack": context_pack_ref,
                "agent_index": agent_index_ref,
                "resume_manifest": resume_manifest_ref,
            },
        )
        record_event(
            connection,
            run_id=run_id,
            event_type="resume_manifest_written",
            payload=resume_manifest_ref,
        )
        connection.commit()
    return {"context_pack": context_pack_ref, "agent_index": agent_index_ref, "resume_manifest": resume_manifest_ref}


def repair_hint_resume_summary(connection: sqlite3.Connection, *, run_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        select hint_id, slice_id, root_cause_key, status, payload_json
        from repair_hints
        where run_id=?
        order by created_at, hint_id
        """,
        (run_id,),
    ).fetchall()
    hints = []
    for row in rows:
        payload = safe_json_object(row[4])
        worker_id = payload.get("worker_id") if isinstance(payload.get("worker_id"), str) else None
        hints.append(
            {
                "hint_id": str(row[0]),
                "slice_id": row[1],
                "root_cause_key": str(row[2]),
                "status": str(row[3]),
                **({"worker_id": worker_id} if worker_id else {}),
            }
        )
    return {
        "source": "sqlite repair_hints",
        "total_count": len(hints),
        "open_count": sum(1 for hint in hints if hint["status"] == "open"),
        "hints": hints,
    }


def safe_json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, str):
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_resume_manifest(
    *,
    db_path: Path,
    run_id: str,
    out_root: Path,
    status: str,
    context_pack: dict[str, Any],
    context_pack_ref: dict[str, str],
    agent_index: dict[str, Any],
    agent_index_ref: dict[str, str],
    evaluate_report_path: Path,
    batch_profile_report_path: str,
    judge_evidence_index_path: Path,
    resume_manifest_path: Path,
    repair_hints: dict[str, Any],
    attempt_evidence_policy: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    context_entrypoints = (
        json.loads(json.dumps(context_pack.get("entrypoints")))
        if isinstance(context_pack.get("entrypoints"), dict)
        else {}
    )
    context_entrypoints["resume_manifest"] = repo_relative(resume_manifest_path, repo_root=repo_root)
    policy = attempt_evidence_policy_from_sources(attempt_evidence_policy, context_pack, agent_index)
    verified_baseline_ref = verified_unsafe_baseline_binding_from_sources(
        {"attempt_evidence_policy": policy} if policy is not None else None,
        context_pack,
        agent_index,
        repo_root=repo_root,
    )
    if verified_baseline_ref is not None:
        context_entrypoints["verified_unsafe_baseline"] = verified_baseline_ref["path"]
    workers = resume_manifest_workers(
        context_pack,
        agent_index,
        db_path=db_path,
        run_id=run_id,
        repair_hints=repair_hints,
        repo_root=repo_root,
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "resume-manifest",
        "run_id": run_id,
        "status": status,
        "out_root": repo_relative(out_root, repo_root=repo_root),
        "semantic_gate": False,
        "chat_output_is_evidence": False,
        "claim_boundary": {
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "boundary": (
                "This manifest is a current-state resume map over on-disk harness artifacts. "
                "It is not a semantic gate and does not treat OpenCode chat output as evidence."
            ),
        },
        "ledger": {
            "path": repo_relative(db_path, repo_root=repo_root),
            "checkpoint_backend": "sqlite",
            "state_role": "checkpoint-index-only",
        },
        "context_pack": context_pack_ref,
        "agent_index": agent_index_ref,
        "entrypoints": context_entrypoints,
        "evaluate_report": {
            "path": repo_relative(evaluate_report_path, repo_root=repo_root),
            "status": status,
        },
        "batch_profile_report": {
            "path": batch_profile_report_path,
            "status": status,
        }
        if batch_profile_report_path
        else None,
        "expected_judge_evidence_index": repo_relative(judge_evidence_index_path, repo_root=repo_root),
        "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
        "repair_hints": repair_hints,
        "worker_count": len(workers),
        "worker_ids": [str(worker["worker_id"]) for worker in workers],
        "workers": workers,
    }
    if policy is not None:
        payload["attempt_evidence_policy"] = bind_verified_baseline_into_policy(policy, verified_baseline_ref)
    if verified_baseline_ref is not None:
        payload["verified_unsafe_baseline"] = verified_baseline_ref
    if isinstance(context_pack.get("proof_class_resolution"), dict):
        payload["proof_class_resolution"] = json.loads(json.dumps(context_pack["proof_class_resolution"]))
    return payload


def resume_manifest_workers(
    context_pack: dict[str, Any],
    agent_index: dict[str, Any],
    *,
    db_path: Path,
    run_id: str,
    repair_hints: dict[str, Any],
    repo_root: Path = REPO_ROOT,
) -> list[dict[str, Any]]:
    agents_by_worker_id = (
        agent_index.get("agents_by_worker_id")
        if isinstance(agent_index.get("agents_by_worker_id"), dict)
        else {}
    )
    workers = context_pack.get("workers") if isinstance(context_pack.get("workers"), list) else []
    default_mode = str(context_pack.get("mode")) if context_pack.get("mode") in {"deterministic", "opencode"} else None
    open_hints_by_worker_id = open_repair_hints_by_worker_id(repair_hints, run_id=run_id)
    entries: list[dict[str, Any]] = []
    copied_fields = [
        "worker_id",
        "slice_id",
        "function",
        "assignment_path",
        "request_path",
        "summary_path",
        "report_path",
        "out_root",
        "source_commit",
        "source_sha256",
        "summary_status",
        "recorded",
        "exit_code",
        "handoff_contract",
        "opencode_session_evidence",
        "opencode_safety_transform_attempt",
        "opencode_preflight_report",
        "opencode_runtime_env",
    ]
    for worker in workers:
        if not isinstance(worker, dict) or not worker.get("worker_id"):
            continue
        worker_id = str(worker["worker_id"])
        agent = agents_by_worker_id.get(worker_id)
        entry = {
            field: worker.get(field)
            for field in copied_fields
            if field in worker and worker.get(field) is not None
        }
        entry["worker_id"] = worker_id
        if isinstance(agent, dict):
            entry["agent_status"] = agent.get("status")
            if "isolated_out_root" not in entry and agent.get("isolated_out_root") is not None:
                entry["isolated_out_root"] = agent.get("isolated_out_root")
        mode = resume_worker_replay_mode(worker, agent, default_mode=default_mode)
        open_hint = open_hints_by_worker_id.get(worker_id)
        entry["replay_commands"] = resume_worker_replay_commands(
            entry,
            db_path=db_path,
            run_id=run_id,
            mode=mode,
            open_hint=open_hint,
            repo_root=repo_root,
        )
        entries.append(entry)
    return entries


def open_repair_hints_by_worker_id(repair_hints: dict[str, Any], *, run_id: str) -> dict[str, dict[str, Any]]:
    hints = repair_hints.get("hints") if isinstance(repair_hints.get("hints"), list) else []
    result: dict[str, dict[str, Any]] = {}
    for hint in hints:
        if not isinstance(hint, dict) or hint.get("status") != "open":
            continue
        worker_id = hint.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id:
            worker_id = worker_id_from_repair_hint_id(str(hint.get("hint_id", "")), run_id=run_id)
        if worker_id:
            result[worker_id] = hint
    return result


def worker_id_from_repair_hint_id(hint_id: str, *, run_id: str) -> str | None:
    prefix = f"repair:{run_id}:"
    if not hint_id.startswith(prefix):
        return None
    remainder = hint_id[len(prefix) :]
    if ":" not in remainder:
        return None
    worker_id, _root_cause = remainder.rsplit(":", 1)
    return worker_id or None


def resume_worker_replay_mode(
    worker: dict[str, Any],
    agent: Any,
    *,
    default_mode: str | None,
) -> str:
    for source in (worker, agent if isinstance(agent, dict) else {}):
        runtime = source.get("runtime")
        if runtime == "opencode":
            return "opencode"
        mode = source.get("mode")
        if mode in {"deterministic", "opencode"}:
            return str(mode)
    if default_mode in {"deterministic", "opencode"}:
        return default_mode
    if isinstance(worker.get("opencode_preflight_report"), dict):
        return "opencode"
    return "deterministic"


def resume_worker_replay_commands(
    worker: dict[str, Any],
    *,
    db_path: Path,
    run_id: str,
    mode: str,
    open_hint: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any]:
    run_worker = resume_worker_replay_command(
        "run-worker",
        worker=worker,
        db_path=db_path,
        run_id=run_id,
        mode=mode,
        repo_root=repo_root,
    )
    commands: dict[str, Any] = {"run_worker": run_worker}
    if open_hint is not None and isinstance(open_hint.get("hint_id"), str):
        commands["retry_worker"] = resume_worker_replay_command(
            "retry-worker",
            worker=worker,
            db_path=db_path,
            run_id=run_id,
            mode=mode,
            repo_root=repo_root,
            hint_id=str(open_hint["hint_id"]),
        )
    return commands


def resume_worker_replay_command(
    subcommand: str,
    *,
    worker: dict[str, Any],
    db_path: Path,
    run_id: str,
    mode: str,
    repo_root: Path,
    hint_id: str | None = None,
) -> dict[str, Any]:
    worker_id = str(worker["worker_id"])
    argv = portable_python_module_argv(
        HARNESS_MODULE,
        subcommand,
        "--db",
        repo_relative(db_path, repo_root=repo_root),
        "--run-id",
        run_id,
        "--worker-id",
        worker_id,
    )
    if hint_id is not None:
        argv.extend(["--hint-id", hint_id])
    argv.extend(["--mode", mode])
    if mode == "opencode":
        append_opencode_replay_flags(argv, worker)
    payload = {
        "argv": argv,
        "command": shell_command_line(argv),
        "replay_safety": resume_worker_replay_safety(worker, mode=mode, repo_root=repo_root),
        "assignment_path": worker.get("assignment_path"),
        "request_path": worker.get("request_path"),
        "summary_path": worker.get("summary_path"),
        "report_path": worker.get("report_path"),
        "out_root": worker.get("isolated_out_root") or worker.get("out_root"),
    }
    return {key: value for key, value in payload.items() if value is not None}


def resume_worker_replay_safety(worker: dict[str, Any], *, mode: str, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    if mode != "opencode":
        return {
            "status": "ready",
            "reason": "deterministic_replay_command",
        }
    missing: list[str] = []
    preflight = worker.get("opencode_preflight_report")
    if not isinstance(preflight, dict):
        missing.append("opencode_preflight_report")
        preflight = {}
    if preflight.get("status") != "passed":
        missing.append("opencode_preflight_report.status")
    preflight_path = preflight.get("path")
    if not isinstance(preflight_path, str) or not preflight_path:
        missing.append("opencode_preflight_report.path")
    preflight_sha256 = preflight.get("sha256")
    if not is_sha256_hex(preflight_sha256):
        missing.append("opencode_preflight_report.sha256")
    if isinstance(preflight_path, str) and preflight_path and is_sha256_hex(preflight_sha256):
        try:
            preflight_file = repo_path(Path(preflight_path), repo_root=repo_root)
        except SystemExit:
            missing.append("opencode_preflight_report.path")
        else:
            if not preflight_file.is_file():
                missing.append("opencode_preflight_report.path_missing")
            elif sha256_file(preflight_file) != preflight_sha256:
                missing.append("opencode_preflight_report.sha256_mismatch")
            else:
                try:
                    preflight_payload = load_json(preflight_file)
                except (OSError, ValueError, json.JSONDecodeError):
                    missing.append("opencode_preflight_report.file_readable")
                else:
                    if preflight_payload.get("status") != "passed":
                        missing.append("opencode_preflight_report.file_status")
                    file_contract = (
                        preflight_payload.get("contract_verification")
                        if isinstance(preflight_payload.get("contract_verification"), dict)
                        else {}
                    )
                    if file_contract.get("status") != "executed":
                        missing.append("opencode_preflight_report.file_contract_status")
    if preflight.get("contract_status") != "executed":
        missing.append("opencode_preflight_report.contract_status")
    policy = preflight.get("launch_policy")
    if not isinstance(policy, dict):
        missing.append("opencode_preflight_report.launch_policy")
        policy = {}
    opencode_command = policy.get("opencode_command")
    if opencode_command != COMPETITION_OPENCODE_COMMAND:
        missing.append("opencode_preflight_report.launch_policy.opencode_command")
    opencode_model = policy.get("opencode_model")
    if opencode_model != COMPETITION_OPENCODE_MODEL:
        missing.append("opencode_preflight_report.launch_policy.opencode_model")
    opencode_agent = policy.get("opencode_agent")
    if opencode_agent != COMPETITION_OPENCODE_AGENT:
        missing.append("opencode_preflight_report.launch_policy.opencode_agent")
    opencode_variant = policy.get("opencode_variant")
    if opencode_variant != COMPETITION_OPENCODE_VARIANT:
        missing.append("opencode_preflight_report.launch_policy.opencode_variant")
    if not isinstance(policy.get("opencode_skip_permissions"), bool):
        missing.append("opencode_preflight_report.launch_policy.opencode_skip_permissions")
    runtime_env = preflight.get("opencode_runtime_env")
    if not isinstance(runtime_env, dict):
        missing.append("opencode_preflight_report.opencode_runtime_env")
        runtime_env = {}
    runtime_env_sha256 = runtime_env.get("env_sha256")
    if not isinstance(runtime_env_sha256, str) or not runtime_env_sha256:
        missing.append("opencode_preflight_report.opencode_runtime_env.env_sha256")
    availability = preflight.get("opencode_model_availability")
    if not isinstance(availability, dict):
        missing.append("opencode_preflight_report.opencode_model_availability")
        availability = {}
    if availability.get("status") != "available":
        missing.append("opencode_preflight_report.opencode_model_availability.status")
    if availability.get("opencode_command") != opencode_command:
        missing.append("opencode_preflight_report.opencode_model_availability.opencode_command")
    if availability.get("required_model") != COMPETITION_OPENCODE_MODEL:
        missing.append("opencode_preflight_report.opencode_model_availability.required_model")
    if availability.get("model_listed") is not True:
        missing.append("opencode_preflight_report.opencode_model_availability.model_listed")
    try:
        model_probe_returncode = int(availability.get("process_returncode", 1))
    except (TypeError, ValueError):
        model_probe_returncode = 1
    if model_probe_returncode != 0:
        missing.append("opencode_preflight_report.opencode_model_availability.process_returncode")
    if missing:
        return {
            "status": "blocked",
            "reason": "opencode_preflight_required_for_replay",
            "missing_constraints": missing,
            "boundary": (
                "OpenCode replay commands require the preflight launch contract; "
                "otherwise the command is only an index entry, not a safe replay recipe."
            ),
        }
    return {
        "status": "ready",
        "reason": "opencode_preflight_contract_bound",
        "preflight_report": preflight_path,
        "preflight_report_sha256": preflight_sha256,
        "preflight_status": "passed",
        "contract_status": "executed",
        "launch_policy_sha256": preflight.get("launch_policy_sha256")
        or opencode_launch_policy_sha256(normalize_opencode_launch_policy(policy)),
        "opencode_runtime_env_sha256": runtime_env_sha256,
        "opencode_model_availability": {
            "status": "available",
            "opencode_command": COMPETITION_OPENCODE_COMMAND,
            "required_model": COMPETITION_OPENCODE_MODEL,
            "required_agent": COMPETITION_OPENCODE_AGENT,
            "process_returncode": model_probe_returncode,
            "model_listed": True,
        },
    }


def is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def append_opencode_replay_flags(argv: list[str], worker: dict[str, Any]) -> None:
    preflight = worker.get("opencode_preflight_report")
    if not isinstance(preflight, dict):
        return
    policy = preflight.get("launch_policy") if isinstance(preflight.get("launch_policy"), dict) else {}
    opencode_command = policy.get("opencode_command") if isinstance(policy.get("opencode_command"), str) else None
    argv.extend(["--opencode-command", opencode_command or COMPETITION_OPENCODE_COMMAND])
    opencode_model = policy.get("opencode_model")
    if isinstance(opencode_model, str) and opencode_model:
        argv.extend(["--opencode-model", opencode_model])
        if opencode_model != COMPETITION_OPENCODE_MODEL:
            argv.append("--opencode-allow-non-competition-model")
    else:
        argv.extend(["--opencode-model", COMPETITION_OPENCODE_MODEL])
    opencode_agent = policy.get("opencode_agent")
    if isinstance(opencode_agent, str) and opencode_agent:
        argv.extend(["--opencode-agent", opencode_agent])
    opencode_variant = policy.get("opencode_variant")
    if isinstance(opencode_variant, str) and opencode_variant:
        argv.extend(["--opencode-variant", opencode_variant])
    if policy.get("opencode_skip_permissions") is True:
        argv.append("--opencode-skip-permissions")
    preflight_path = preflight.get("path")
    if isinstance(preflight_path, str) and preflight_path:
        argv.extend(["--opencode-preflight-report", preflight_path])


def update_batch_profile_report_context_refs(
    *,
    batch_report_path: Path,
    context_refs: dict[str, dict[str, str]],
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    report = load_json(batch_report_path)
    report.update(context_refs)
    architecture = report.get("judge_summary", {}).get("harness_architecture")
    if isinstance(architecture, dict):
        architecture["context_pack"] = context_refs["context_pack"]
        architecture["agent_index"] = context_refs["agent_index"]
    atomic_write_json(batch_report_path, report)
    return artifact_ref(batch_report_path, repo_root=repo_root)


def evaluate(
    *,
    run_id: str,
    target_id: str,
    source_repo_root: Path,
    source_file: str,
    source_commit: str,
    out_root: Path,
    proof_class: str,
    source_repository: str | None = None,
    source_branch: str | None = None,
    functions: list[str] | None = None,
    require_source_commit: str | None = None,
    slice_specs: list[str] | None = None,
    compiler_command_source: str | None = None,
    include_paths: list[str] | None = None,
    defines: list[str] | None = None,
    reuse_accepted_evidence: bool = False,
    accepted_evidence_root: str | None = None,
    slice_id_prefix: str | None = None,
    worker_prefix: str = "worker",
    limit: int | None = None,
    mode: str = "deterministic",
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    opencode_preflight_report: Path | None = None,
    execute_merge: bool = True,
    auto_retry: bool = True,
    max_workers: int = 1,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if proof_class not in ALLOWED_PROOF_CLASSES:
        raise SystemExit(f"unsupported proof_class: {proof_class}")
    require_competition_exact_host_attestation(proof_class, context="evaluate")
    if mode not in {"deterministic", "opencode"}:
        raise SystemExit(f"unsupported mode: {mode}")
    out_root = repo_path(out_root, repo_root=repo_root)
    if slice_id_prefix is None:
        slice_id_prefix = f"{slug_id(target_id)}-{slug_id(Path(source_file).stem)}"
    db_path = init_run(
        out_root=out_root,
        run_id=run_id,
        proof_class=proof_class,
        repo_root=repo_root,
    )
    plan = plan_source_file(
        db_path=db_path,
        run_id=run_id,
        target_id=target_id,
        source_repo_root=source_repo_root,
        source_repository=source_repository,
        source_branch=source_branch,
        source_file=source_file,
        functions=functions or [],
        source_commit=source_commit,
        require_source_commit=require_source_commit,
        slice_specs=slice_specs or [],
        compiler_command_source=compiler_command_source,
        include_paths=include_paths or [],
        defines=defines or [],
        reuse_accepted_evidence=reuse_accepted_evidence,
        accepted_evidence_root=accepted_evidence_root,
        out_root=out_root,
        slice_id_prefix=slice_id_prefix,
        worker_prefix=worker_prefix,
        limit=limit,
        repo_root=repo_root,
    )
    run_result = run_plan(
        db_path=db_path,
        run_id=run_id,
        plan_path=Path(str(plan["plan_path"])),
        out_root=out_root,
        proof_class=proof_class,
        mode=mode,
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        opencode_preflight_report=opencode_preflight_report,
        execute_merge=execute_merge,
        auto_retry=auto_retry,
        max_workers=max_workers,
        timeout_seconds=timeout_seconds,
        command_runner=command_runner,
        repo_root=repo_root,
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "entrypoint": "evaluate",
        "status": run_result["status"],
        "exit_code": int(run_result["exit_code"]),
        "run_id": run_id,
        "out_root": repo_relative(out_root, repo_root=repo_root),
        "db_path": repo_relative(db_path, repo_root=repo_root),
        "proof_class": proof_class,
        "mode": mode,
        "target_id": target_id,
        "source_repo_root": repo_relative(repo_path(source_repo_root, repo_root=repo_root), repo_root=repo_root),
        "source_file": source_file,
        "source_commit": source_commit,
        "worker_count": len(plan["units"]),
        "plan_path": plan["plan_path"],
        "plan": plan,
        "run_plan": run_result,
    }
    if source_repository:
        result["source_repository"] = source_repository
    if source_branch:
        result["source_branch"] = source_branch
    report_path = out_root / "harness" / "evaluate-report.json"
    result["report_path"] = repo_relative(report_path, repo_root=repo_root)
    context_refs = write_context_pack_and_agent_index(
        db_path=db_path,
        run_id=run_id,
        target_id=target_id,
        proof_class=proof_class,
        mode=mode,
        out_root=out_root,
        plan=plan,
        run_result=run_result,
        primary_report_path=report_path,
        report_entrypoint="evaluate_report",
        acceptance_boundary=None,
        repo_root=repo_root,
    )
    result.update(context_refs)
    result["judge_summary"] = build_judge_summary(
        entrypoint="evaluate",
        proof_class=proof_class,
        mode=mode,
        plan=plan,
        run_result=run_result,
        context_refs=context_refs,
        acceptance_boundary=None,
        repo_root=repo_root,
    )
    result["judge_headline"] = build_judge_headline(
        entrypoint="evaluate",
        status=str(result["status"]),
        proof_class=proof_class,
        mode=mode,
        judge_summary=result["judge_summary"],
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, result)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="evaluate-report",
            path=report_path,
            status=str(result["status"]),
            semantic_role="evaluate-report",
            payload=result,
            repo_root=repo_root,
        )
        record_event(connection, run_id=run_id, event_type="evaluate_executed", payload=result)
        connection.commit()
    return result


def graph_checkpoint_backend(graph: dict[str, Any]) -> str:
    backend = graph.get("checkpoint_backend")
    return str(backend) if isinstance(backend, str) and backend else "sqlite"


def graph_retry_round_cap(graph: dict[str, Any]) -> int:
    retry_policy = graph.get("retry_policy") if isinstance(graph.get("retry_policy"), dict) else {}
    try:
        return int(retry_policy.get("round_cap", REPAIR_ROUND_CAP))
    except (TypeError, ValueError):
        return REPAIR_ROUND_CAP


def build_context_management_contract(
    *,
    graph: dict[str, Any],
    db_path: Path | None = None,
    primary_report_path: Path | None = None,
    context_pack_path: Path | None = None,
    agent_index_path: Path | None = None,
    report_entrypoint: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_kind": "context-management",
        "role": "context-index-and-resume-map",
        "semantic_gate": False,
        "chat_output_is_evidence": False,
        "evidence_policy": "on-disk-artifacts-only",
        "managed_state": [
            "entrypoints",
            "source pins",
            "worker handoffs",
            "graph",
            "retry policy",
            "artifact refs",
        ],
        "pipeline": [
            {
                "stage": "plan",
                "role": "planner",
                "evidence": "entrypoints.worker_plan",
            },
            {
                "stage": "translate",
                "role": "worker",
                "evidence": "workers[*].summary_path",
                "fanout": True,
            },
            {
                "stage": "verify",
                "role": "verifier",
                "evidence": "entrypoints.merge_summary",
                "reduce": "merge",
                "on_failure": "repair",
            },
            {
                "stage": "repair",
                "role": "repairer",
                "trigger": "exit_code != 0",
                "loopback_to": "translate",
                "max_rounds": graph_retry_round_cap(graph),
            },
        ],
        "update_rules": [
            "all reusable paths are repo-relative",
            "semantic acceptance remains owned by validators and final summaries",
            "judge sidecars are path-only in context indexes to avoid hash cycles",
        ],
        "resume_protocol": {
            "checkpoint_backend": graph_checkpoint_backend(graph),
            "worker_state_source": "agent-index.agents_by_worker_id",
            "open_repair_hint_source": "sqlite repair_hints plus worker auto_retry records",
            "merge_precondition": "required worker summaries recorded or final summary fails closed",
        },
    }
    if db_path is not None:
        contract["resume_protocol"]["ledger_path"] = repo_relative(db_path, repo_root=repo_root)
    if primary_report_path is not None:
        contract["primary_report"] = repo_relative(primary_report_path, repo_root=repo_root)
    if context_pack_path is not None:
        contract["context_pack"] = repo_relative(context_pack_path, repo_root=repo_root)
    if agent_index_path is not None:
        contract["agent_index"] = repo_relative(agent_index_path, repo_root=repo_root)
    if report_entrypoint:
        contract["report_entrypoint"] = report_entrypoint
    return contract


def build_agent_coordination_contract(
    *,
    graph: dict[str, Any],
    db_path: Path | None = None,
    worker_count: int = 0,
    mode: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_kind": "agent-coordination",
        "semantic_gate": False,
        "chat_output_is_evidence": False,
        "coordination_state": "sqlite-ledger-and-on-disk-reports",
        "checkpoint_backend": graph_checkpoint_backend(graph),
        "runtime": graph.get("runtime"),
        "mode": mode,
        "worker_count": int(worker_count),
        "planner_ownership": {
            "mode": "single-planner-per-run",
            "assignment_transaction": "BEGIN IMMEDIATE before lease/out_root checks and writes",
            "worker_fanout_starts_after": "worker plan and assignment artifacts are written",
        },
        "lease_policy": {
            "fencing_token": "audit-only-monotonic-counter",
            "enforced_guards": ["resource_key active lease owner", "per-run isolated_out_root uniqueness"],
            "not_acceptance_gate": True,
        },
        "roles": {
            "planner": {
                "stage": "plan",
                "inputs": ["batch profile", "source pins", "slice specs"],
                "outputs": ["worker plan", "assignments", "context pack", "agent index"],
                "status_source": "planner artifacts and SQLite ledger",
                "acceptance_authority": "none",
            },
            "worker": {
                "stage": "fanout-worker",
                "inputs": ["assignment_path", "request_path"],
                "outputs": ["summary_path", "report_path", "attempts", "final_decision"],
                "isolation": "per-worker out_root",
                "status_source": "worker summary and run-worker-report",
                "acceptance_authority": "none",
            },
            "repairer": {
                "stage": "repair-retry",
                "inputs": ["repair_hints", "failed worker summary", "stderr tail"],
                "outputs": ["retry attempt", "auto_retry", "attempts"],
                "status_source": "repair_hints ledger and worker attempts",
                "acceptance_authority": "none",
                "round_cap": graph_retry_round_cap(graph),
            },
            "verifier": {
                "stage": "merge-verify",
                "inputs": ["worker summaries", "workflow metrics", "oracle evidence"],
                "outputs": ["competition-run-summary", "workflow-metrics"],
                "status_source": "validate_competition_run_summary",
                "acceptance_authority": "competition-run-summary validator",
            },
            "reporter": {
                "stage": "report",
                "inputs": ["evaluate report", "context pack", "agent index", "judge evidence index"],
                "outputs": ["judge-facing indexes"],
                "status_source": "on-disk artifacts with sha256 where hash-stable",
                "acceptance_authority": "none",
            },
        },
        "resume_protocol": {
            "checkpoint_backend": graph_checkpoint_backend(graph),
            "worker_state_source": "agent-index.agents_by_worker_id",
            "open_repair_hint_source": "sqlite repair_hints",
            "merge_precondition": "all required worker summaries recorded before merge",
            "resume_entrypoints": ["run-plan --plan", "run-worker --assignment", "evaluate --profile"],
        },
    }
    if db_path is not None:
        contract["resume_protocol"]["ledger_path"] = repo_relative(db_path, repo_root=repo_root)
    return contract


def build_architecture_contracts(graph: dict[str, Any]) -> dict[str, Any]:
    context_contract = build_context_management_contract(graph=graph)
    agent_contract = build_agent_coordination_contract(graph=graph)
    return {
        "context_management": {
            "contract_kind": context_contract["contract_kind"],
            "role": context_contract["role"],
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "evidence_policy": context_contract["evidence_policy"],
            "pipeline": context_contract["pipeline"],
            "resume_protocol": context_contract["resume_protocol"],
        },
        "agent_coordination": {
            "contract_kind": agent_contract["contract_kind"],
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "coordination_state": agent_contract["coordination_state"],
            "checkpoint_backend": agent_contract["checkpoint_backend"],
            "planner_ownership": agent_contract["planner_ownership"],
            "lease_policy": agent_contract["lease_policy"],
            "roles": list(agent_contract["roles"]),
            "resume_protocol": agent_contract["resume_protocol"],
        },
    }


def build_judge_summary(
    *,
    entrypoint: str,
    proof_class: str,
    mode: str,
    plan: dict[str, Any],
    run_result: dict[str, Any],
    context_refs: dict[str, dict[str, str]],
    acceptance_boundary: dict[str, Any] | None = None,
    route_metrics_artifact: dict[str, Any] | None = None,
    before_after_exhibit_artifact: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    graph = run_result.get("graph") if isinstance(run_result.get("graph"), dict) else {}
    merge_execution = (
        run_result.get("merge_execution")
        if isinstance(run_result.get("merge_execution"), dict)
        else {}
    )
    final_summary = load_merge_summary(merge_execution, repo_root=repo_root)
    workflow_metrics = load_merge_workflow_metrics(merge_execution, repo_root=repo_root)
    slices = final_summary.get("slices") if isinstance(final_summary.get("slices"), dict) else {}
    final_gate = final_summary.get("final_gate") if isinstance(final_summary.get("final_gate"), dict) else {}
    final_gate_status = merge_execution.get("final_gate_status") or final_gate.get("status")
    workers = [
        {
            "worker_id": worker.get("worker_id"),
            "slice_id": worker.get("slice_id"),
            "function": worker.get("function"),
            "summary_status": worker.get("summary_status"),
            "exit_code": int(worker.get("exit_code", 1)),
            "recorded": bool(worker.get("recorded")),
            "final_decision": worker.get("final_decision"),
        }
        for worker in run_result.get("workers", [])
        if isinstance(worker, dict)
    ]
    semantic_claim_source = "final_gate_and_worker_summaries"
    generated_draft_semantic_pass = None
    if isinstance(acceptance_boundary, dict):
        semantic_claim_source = str(acceptance_boundary.get("semantic_claim_source", semantic_claim_source))
        if "generated_draft_semantic_pass" in acceptance_boundary:
            generated_draft_semantic_pass = bool(acceptance_boundary["generated_draft_semantic_pass"])

    core_translation_quality: dict[str, Any] = {
        "final_gate_status": final_gate_status,
        "semantic_claim_source": semantic_claim_source,
        "generated_draft_semantic_pass": generated_draft_semantic_pass,
        "semantic_pass_count": int(slices.get("semantic_pass", 0) or 0),
        "compiled_count": int(slices.get("compiled", 0) or 0),
        "failed_count": int(slices.get("failed", 0) or 0),
        "workers": workers,
    }
    if workflow_metrics:
        unsafe_reduction = workflow_metrics.get("unsafe_reduction")
        if isinstance(unsafe_reduction, dict):
            core_translation_quality["unsafe_reduction"] = unsafe_reduction
        translation_before_after = workflow_metrics.get("translation_before_after")
        if isinstance(translation_before_after, dict):
            core_translation_quality["translation_before_after"] = translation_before_after
        core_translation_quality["repair_summary"] = summarize_workflow_repair_metrics(workflow_metrics)
    if route_metrics_artifact is not None:
        core_translation_quality["route_governance_metrics"] = route_metrics_artifact.get("binding", {})
    if before_after_exhibit_artifact is not None:
        binding = before_after_exhibit_artifact.get("binding", {})
        payload = before_after_exhibit_artifact.get("payload", {})
        core_translation_quality["before_after_exhibit"] = binding
        if isinstance(payload, dict):
            translation_before_after = payload.get("translation_before_after")
            if isinstance(translation_before_after, dict):
                core_translation_quality["translation_before_after"] = translation_before_after
            unsafe_reduction = summarize_before_after_unsafe_reduction(payload)
            if unsafe_reduction is not None:
                core_translation_quality["unsafe_reduction"] = unsafe_reduction

    return {
        "report_kind": "judge-summary",
        "entrypoint": entrypoint,
        "proof_class": proof_class,
        "mode": mode,
        "harness_architecture": {
            "entrypoint": entrypoint,
            "planning_mode": plan.get("planning_mode", "source_file"),
            "pipeline": [
                "init-run",
                "plan-explicit-workers" if plan.get("planning_mode") == "explicit_workers" else "plan-source-file",
                "run-plan",
                "merge",
                "report",
            ],
            "graph_runtime": graph.get("runtime"),
            "graph_nodes": graph.get("nodes", []),
            "parallelism": run_result.get("parallelism"),
            "auto_retry": run_result.get("auto_retry"),
            "retry_policy": graph.get("retry_policy"),
            "context_pack": context_refs.get("context_pack"),
            "agent_index": context_refs.get("agent_index"),
            "architecture_contracts": build_architecture_contracts(graph),
            "worker_count": len(plan.get("units", [])) if isinstance(plan.get("units"), list) else 0,
        },
        "core_translation_quality": core_translation_quality,
        "claim_boundary": (
            "This summary is an index over verified on-disk reports; semantic acceptance remains owned by "
            "competition-run-summary.json, workflow metrics, before/after evidence, and validators."
        ),
    }


def build_judge_headline(
    *,
    entrypoint: str,
    status: str,
    proof_class: str,
    mode: str,
    judge_summary: Any,
    acceptance_boundary: Any = None,
    claim_boundary: Any = None,
    route_metrics: Any = None,
    opencode_runtime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = judge_summary if isinstance(judge_summary, dict) else {}
    architecture = summary.get("harness_architecture") if isinstance(summary.get("harness_architecture"), dict) else {}
    core_quality = (
        summary.get("core_translation_quality")
        if isinstance(summary.get("core_translation_quality"), dict)
        else {}
    )
    boundary = claim_boundary if isinstance(claim_boundary, dict) else {}
    acceptance = acceptance_boundary if isinstance(acceptance_boundary, dict) else {}
    route = route_metrics if isinstance(route_metrics, dict) else {}
    retry_policy = architecture.get("retry_policy") if isinstance(architecture.get("retry_policy"), dict) else {}
    parallelism = architecture.get("parallelism") if isinstance(architecture.get("parallelism"), dict) else {}
    worker_count = architecture.get("worker_count")
    if not isinstance(worker_count, int):
        workers = core_quality.get("workers")
        worker_count = len(workers) if isinstance(workers, list) else 0

    generated_draft_semantic_pass = boundary.get(
        "generated_draft_semantic_pass",
        acceptance.get("generated_draft_semantic_pass", core_quality.get("generated_draft_semantic_pass", False)),
    )
    if not isinstance(generated_draft_semantic_pass, bool):
        generated_draft_semantic_pass = False

    translation_coverage_numerator = boundary.get(
        "translation_coverage_numerator",
        route.get("translation_coverage_numerator", 0),
    )
    if isinstance(translation_coverage_numerator, bool):
        translation_coverage_numerator = 0
    try:
        translation_coverage_numerator = int(translation_coverage_numerator)
    except (TypeError, ValueError):
        translation_coverage_numerator = 0

    opencode_enabled = opencode_runtime is not None
    headline = {
        "report_kind": "judge-headline",
        "entrypoint": entrypoint,
        "status": status,
        "proof_class": proof_class,
        "mode": mode,
        "graph_runtime": architecture.get("graph_runtime"),
        "planning_mode": architecture.get("planning_mode"),
        "pipeline": architecture.get("pipeline", []),
        "worker_count": worker_count,
        "parallelism": parallelism,
        "repair_round_cap": retry_policy.get("round_cap", REPAIR_ROUND_CAP),
        "repair_checkpoint": retry_policy.get("checkpoint", "repair_hints"),
        "semantic_gate": False,
        "semantic_claim_source": boundary.get(
            "semantic_claim_source",
            acceptance.get("semantic_claim_source", core_quality.get("semantic_claim_source", "unknown")),
        ),
        "generated_draft_semantic_pass": generated_draft_semantic_pass,
        "translation_coverage_numerator": translation_coverage_numerator,
        "final_gate_status": core_quality.get("final_gate_status"),
        "semantic_pass_count": int(core_quality.get("semantic_pass_count", 0) or 0),
        "compiled_count": int(core_quality.get("compiled_count", 0) or 0),
        "failed_count": int(core_quality.get("failed_count", 0) or 0),
        "context_pack": architecture.get("context_pack"),
        "agent_index": architecture.get("agent_index"),
        "context_index": {
            "context_pack": architecture.get("context_pack"),
            "agent_index": architecture.get("agent_index"),
            "evidence_policy": "on-disk-artifacts-only",
            "worker_state_source": "agent-index.agents_by_worker_id",
        },
        "opencode_runtime": {
            "enabled": opencode_enabled,
            "worker_count": int(opencode_runtime.get("worker_count", 0)) if opencode_runtime else 0,
            "all_contracts_executed": bool(opencode_runtime.get("all_contracts_executed")) if opencode_runtime else False,
            "chat_output_is_evidence": False,
            "semantic_gate": False,
        },
    }
    unsafe_reduction = core_quality.get("unsafe_reduction")
    if isinstance(unsafe_reduction, dict):
        headline["unsafe_reduction"] = unsafe_reduction
    repair_summary = core_quality.get("repair_summary")
    if isinstance(repair_summary, dict):
        headline["repair_summary"] = repair_summary
    return headline


def load_merge_summary(merge_execution: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    summary_path_text = merge_execution.get("summary_path")
    if not isinstance(summary_path_text, str) or not summary_path_text:
        return {}
    summary_path = repo_path(Path(summary_path_text), repo_root=repo_root)
    if not summary_path.exists():
        return {}
    return load_json(summary_path)


def load_merge_workflow_metrics(merge_execution: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    summary_path_text = merge_execution.get("summary_path")
    if not isinstance(summary_path_text, str) or not summary_path_text:
        return {}
    summary_path = repo_path(Path(summary_path_text), repo_root=repo_root)
    if not summary_path.exists():
        return {}
    summary = load_json(summary_path)
    binding = summary.get("workflow_metrics")
    if not isinstance(binding, dict):
        return {}
    metrics_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(metrics_ref, str) or not isinstance(expected_sha, str):
        return {}
    metrics_path = validate_competition_run_summary.resolve_summary_artifact(
        metrics_ref,
        summary_path=summary_path,
        repo_root=repo_root,
    )
    if metrics_path is None or sha256_file(metrics_path) != expected_sha:
        return {}
    metrics = load_json(metrics_path)
    return metrics if isinstance(metrics, dict) else {}


def summarize_workflow_repair_metrics(workflow_metrics: dict[str, Any]) -> dict[str, Any]:
    per_unit_statuses = workflow_metrics.get("per_unit_statuses")
    units = [unit for unit in per_unit_statuses if isinstance(unit, dict)] if isinstance(per_unit_statuses, list) else []
    histories = [unit for unit in units if isinstance(unit.get("repair_history"), dict)]
    root_cause_counts = workflow_metrics.get("root_cause_counts")
    return {
        "avg_repair_rounds": float(workflow_metrics.get("avg_repair_rounds", 0.0) or 0.0),
        "auto_recovery_rate": float(workflow_metrics.get("auto_recovery_rate", 0.0) or 0.0),
        "human_interventions": int(workflow_metrics.get("human_interventions", 0) or 0),
        "repair_history_unit_count": len(histories),
        "auto_recovered_units": sum(1 for unit in units if unit.get("auto_recovered") is True),
        "root_cause_counts": root_cause_counts if isinstance(root_cause_counts, dict) else {},
    }


def summarize_before_after_unsafe_reduction(payload: dict[str, Any]) -> dict[str, Any] | None:
    units = payload.get("units")
    if not isinstance(units, list):
        return None
    baseline_total = 0
    current_total = 0
    reduced_by_total = 0
    measured = 0
    for unit in units:
        if not isinstance(unit, dict):
            continue
        unsafe_reduction = unit.get("unsafe_reduction")
        if not isinstance(unsafe_reduction, dict) or unsafe_reduction.get("status") != "measured":
            continue
        baseline_total += int(unsafe_reduction.get("baseline_total_unsafe", 0) or 0)
        current_total += int(unsafe_reduction.get("current_total_unsafe", 0) or 0)
        reduced_by_total += int(unsafe_reduction.get("reduced_by", 0) or 0)
        measured += 1
    if measured == 0:
        return None
    return {
        "status": "measured",
        "unit_count": measured,
        "baseline_total_unsafe": baseline_total,
        "current_total_unsafe": current_total,
        "reduced_by": reduced_by_total,
    }


def write_context_pack_and_agent_index(
    *,
    db_path: Path,
    run_id: str,
    target_id: str,
    proof_class: str,
    mode: str,
    out_root: Path,
    plan: dict[str, Any],
    run_result: dict[str, Any],
    primary_report_path: Path,
    report_entrypoint: str,
    acceptance_boundary: dict[str, Any] | None = None,
    attempt_evidence_policy: dict[str, Any] | None = None,
    report_artifacts: dict[str, dict[str, Any]] | None = None,
    proof_class_resolution: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, dict[str, str]]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    harness_dir = out_root / "harness"
    harness_dir.mkdir(parents=True, exist_ok=True)
    context_pack_path = harness_dir / "context-pack.json"
    agent_index_path = harness_dir / "agent-index.json"
    worker_results_by_id = {
        str(worker.get("worker_id")): worker
        for worker in run_result.get("workers", [])
        if isinstance(worker, dict) and worker.get("worker_id")
    }
    workers = []
    agents = []
    for unit in plan.get("units", []):
        if not isinstance(unit, dict):
            continue
        worker_id = str(unit.get("worker_id", ""))
        worker_result = worker_results_by_id.get(worker_id, {})
        worker_entry = {
            "worker_id": worker_id,
            "slice_id": unit.get("slice_id"),
            "function": unit.get("function"),
            "out_root": unit.get("out_root"),
            "assignment_path": unit.get("assignment_path"),
            "request_path": unit.get("request_path"),
            "slice_spec": unit.get("slice_spec"),
            "source_repo_root": unit.get("source_repo_root"),
            "source_file": unit.get("source_file"),
            "source_commit": unit.get("source_commit"),
            "require_source_commit": unit.get("require_source_commit"),
            "source_repository": unit.get("source_repository"),
            "source_branch": unit.get("source_branch"),
            "source_sha256": unit.get("source_sha256"),
            "summary_path": worker_result.get("summary_path"),
            "report_path": worker_result.get("report_path"),
            "summary_status": worker_result.get("summary_status"),
            "exit_code": int(worker_result.get("exit_code", 1)),
            "recorded": bool(worker_result.get("recorded")),
        }
        if isinstance(worker_result.get("attempts"), list):
            worker_entry["attempts"] = worker_result["attempts"]
        if isinstance(worker_result.get("final_decision"), dict):
            worker_entry["final_decision"] = worker_result["final_decision"]
        copy_opencode_worker_evidence(worker_result, worker_entry)
        agent_entry = {
            "worker_id": worker_id,
            "role": "slice-worker",
            "runtime": mode,
            "status": worker_entry["summary_status"] or "missing-summary",
            "slice_id": unit.get("slice_id"),
            "function": unit.get("function"),
            "isolated_out_root": unit.get("out_root"),
            "assignment_path": unit.get("assignment_path"),
            "request_path": unit.get("request_path"),
            "source_repo_root": unit.get("source_repo_root"),
            "source_file": unit.get("source_file"),
            "source_commit": unit.get("source_commit"),
            "require_source_commit": unit.get("require_source_commit"),
            "source_repository": unit.get("source_repository"),
            "source_branch": unit.get("source_branch"),
            "source_sha256": unit.get("source_sha256"),
            "summary_path": worker_result.get("summary_path"),
            "report_path": worker_result.get("report_path"),
            "exit_code": worker_entry["exit_code"],
            "recorded": worker_entry["recorded"],
        }
        if isinstance(worker_result.get("attempts"), list):
            agent_entry["attempts"] = worker_result["attempts"]
        if isinstance(worker_result.get("final_decision"), dict):
            agent_entry["final_decision"] = worker_result["final_decision"]
        copy_opencode_worker_evidence(worker_result, agent_entry)
        if isinstance(worker_result.get("auto_retry"), dict):
            worker_entry["auto_retry"] = worker_result["auto_retry"]
            agent_entry["auto_retry"] = worker_result["auto_retry"]
        if isinstance(worker_result.get("auto_retry_suppressed"), dict):
            worker_entry["auto_retry_suppressed"] = worker_result["auto_retry_suppressed"]
            agent_entry["auto_retry_suppressed"] = worker_result["auto_retry_suppressed"]
        workers.append(worker_entry)
        agents.append(agent_entry)
    graph = run_result.get("graph") if isinstance(run_result.get("graph"), dict) else {}
    context_pack_id = f"{run_id}-context-pack"
    report_artifacts = dict(report_artifacts or {})
    if isinstance(run_result.get("opencode_preflight_report"), dict):
        report_artifacts.setdefault("opencode_preflight_report", run_result["opencode_preflight_report"])
    verified_baseline_ref = verified_unsafe_baseline_binding_from_sources(
        {"attempt_evidence_policy": attempt_evidence_policy} if attempt_evidence_policy is not None else None,
        run_result,
        repo_root=repo_root,
    )
    if verified_baseline_ref is not None:
        report_artifacts.setdefault("verified_unsafe_baseline", verified_baseline_ref)
    report_entrypoints = {
        name: artifact.get("path")
        for name, artifact in report_artifacts.items()
        if isinstance(artifact, dict) and isinstance(artifact.get("path"), str)
    }
    context_management_contract = build_context_management_contract(
        graph=graph,
        db_path=db_path,
        primary_report_path=primary_report_path,
        context_pack_path=context_pack_path,
        agent_index_path=agent_index_path,
        report_entrypoint=report_entrypoint,
        repo_root=repo_root,
    )
    context_pack = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "context-pack",
        "context_pack_id": context_pack_id,
        "run_id": run_id,
        "target_id": target_id,
        "proof_class": proof_class,
        **({"proof_class_resolution": proof_class_resolution} if proof_class_resolution is not None else {}),
        "mode": mode,
        "status": run_result.get("status"),
        "budget": {
            "depth": 1,
            "max_tokens": 20000,
        },
        "source": {
            "planning_mode": plan.get("planning_mode", "source_file"),
            "repo_root": plan.get("source_repo_root"),
            "source_file": plan.get("source_file"),
            "source_commit": plan.get("source_commit"),
            "require_source_commit": plan.get("require_source_commit"),
            "source_repository": plan.get("source_repository"),
            "source_branch": plan.get("source_branch"),
            "source_sha256": plan.get("source_sha256"),
            "worker_sources": [
                {
                    "worker_id": worker.get("worker_id"),
                    "slice_id": worker.get("slice_id"),
                    "function": worker.get("function"),
                    "source_repo_root": worker.get("source_repo_root"),
                    "source_file": worker.get("source_file"),
                    "source_commit": worker.get("source_commit"),
                    "require_source_commit": worker.get("require_source_commit"),
                    "source_repository": worker.get("source_repository"),
                    "source_branch": worker.get("source_branch"),
                    "source_sha256": worker.get("source_sha256"),
                }
                for worker in workers
                if isinstance(worker, dict) and worker.get("source_commit")
            ],
        },
        "entrypoints": {
            "primary_report": repo_relative(primary_report_path, repo_root=repo_root),
            report_entrypoint: repo_relative(primary_report_path, repo_root=repo_root),
            "run_plan_report": run_result.get("report_path"),
            "worker_plan": plan.get("plan_path"),
            "merge_plan": run_result.get("merge_plan", {}).get("path") if isinstance(run_result.get("merge_plan"), dict) else None,
            "merge_summary": run_result.get("merge_execution", {}).get("summary_path")
            if isinstance(run_result.get("merge_execution"), dict)
            else None,
            "agent_index": repo_relative(agent_index_path, repo_root=repo_root),
            **report_entrypoints,
        },
        "graph": graph,
        "parallelism": run_result.get("parallelism"),
        "retry_policy": graph.get("retry_policy"),
        "workers": workers,
        "context_management_contract": context_management_contract,
        "acceptance_boundary": {
            "semantic_acceptance": "final verification and worker summaries decide acceptance; this pack is an index only",
            "candidate_sources": ["c2rust-baseline", "deterministic-worker", "opencode-worker"],
        },
    }
    if acceptance_boundary is not None:
        context_pack["acceptance_boundary"]["profile"] = acceptance_boundary
    if attempt_evidence_policy is not None:
        context_pack["attempt_evidence_policy"] = attempt_evidence_policy
    if report_artifacts:
        context_pack["report_artifacts"] = report_artifacts
    agents_by_worker_id = {
        str(agent["worker_id"]): agent
        for agent in agents
        if isinstance(agent, dict) and agent.get("worker_id")
    }
    agent_index = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "agent-index",
        "run_id": run_id,
        "target_id": target_id,
        "proof_class": proof_class,
        **({"proof_class_resolution": proof_class_resolution} if proof_class_resolution is not None else {}),
        "checkpoint_backend": graph.get("checkpoint_backend", "sqlite"),
        "agent_coordination_contract": build_agent_coordination_contract(
            graph=graph,
            db_path=db_path,
            worker_count=len(workers),
            mode=mode,
            repo_root=repo_root,
        ),
        "planner": {
            "plan_path": plan.get("plan_path"),
            "worker_count": len(workers),
        },
        "agents": agents,
        "agents_by_worker_id": agents_by_worker_id,
        "merge": {
            "status": run_result.get("status"),
            "merge_plan": run_result.get("merge_plan"),
            "merge_execution": run_result.get("merge_execution"),
        },
    }
    if report_artifacts:
        agent_index["reports"] = report_artifacts
    if attempt_evidence_policy is not None:
        agent_index["attempt_evidence_policy"] = attempt_evidence_policy
    atomic_write_json(context_pack_path, context_pack)
    atomic_write_json(agent_index_path, agent_index)
    context_pack_ref = {"path": repo_relative(context_pack_path, repo_root=repo_root), "sha256": sha256_file(context_pack_path)}
    agent_index_ref = {"path": repo_relative(agent_index_path, repo_root=repo_root), "sha256": sha256_file(agent_index_path)}
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        connection.execute(
            """
            insert into context_packs(
              context_pack_id, run_id, target_id, slice_id, depth, max_tokens,
              artifact_path, artifact_sha256, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(context_pack_id) do update set
              run_id=excluded.run_id,
              target_id=excluded.target_id,
              slice_id=excluded.slice_id,
              depth=excluded.depth,
              max_tokens=excluded.max_tokens,
              artifact_path=excluded.artifact_path,
              artifact_sha256=excluded.artifact_sha256,
              payload_json=excluded.payload_json
            """,
            (
                context_pack_id,
                run_id,
                target_id,
                None,
                int(context_pack["budget"]["depth"]),
                int(context_pack["budget"]["max_tokens"]),
                context_pack_ref["path"],
                context_pack_ref["sha256"],
                json.dumps(context_pack, sort_keys=True),
            ),
        )
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="context-pack",
            path=context_pack_path,
            status=str(run_result.get("status", "unknown")),
            semantic_role="agent-context-pack",
            payload=context_pack,
            repo_root=repo_root,
        )
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="agent-index",
            path=agent_index_path,
            status=str(run_result.get("status", "unknown")),
            semantic_role="agent-index",
            payload=agent_index,
            repo_root=repo_root,
        )
        record_event(
            connection,
            run_id=run_id,
            event_type="context_pack_written",
            payload={"context_pack": context_pack_ref, "agent_index": agent_index_ref},
        )
        connection.commit()
    return {"context_pack": context_pack_ref, "agent_index": agent_index_ref}


def write_route_governance_metrics_profile_report(
    *,
    profile: dict[str, Any],
    out_root: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any] | None:
    if not profile_bool(profile, "emit_route_governance_metrics_report", default=False):
        return None
    coverage_report_text = profile_string(profile, "route_governance_metrics_coverage_report")
    evidence_root_text = profile_string(
        profile,
        "route_governance_metrics_evidence_root",
        default="validation/evidence",
    )
    payload = route_governance_metrics_report.build_report(
        repo_root,
        coverage_report_path=Path(coverage_report_text) if coverage_report_text is not None else None,
        evidence_root=Path(evidence_root_text or "validation/evidence"),
        competition_summary_paths=route_governance_competition_summary_paths(out_root),
    )
    report_path = out_root / "summary" / "route-governance-metrics-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, payload)
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    s2_workflow_metrics = metrics.get("s2_workflow_metrics") if isinstance(metrics.get("s2_workflow_metrics"), dict) else {}
    unsafe_reduction = (
        s2_workflow_metrics.get("unsafe_reduction")
        if isinstance(s2_workflow_metrics.get("unsafe_reduction"), dict)
        else {}
    )
    translation_before_after = (
        s2_workflow_metrics.get("translation_before_after")
        if isinstance(s2_workflow_metrics.get("translation_before_after"), dict)
        else {}
    )
    binding = {
        "path": repo_relative(report_path, repo_root=repo_root),
        "sha256": sha256_file(report_path),
        "status": str(payload.get("status", "unknown")),
        "report_kind": str(payload.get("report_kind", "route-governance-metrics")),
        "translation_coverage_numerator": int(metrics.get("translation_coverage_numerator", 0)),
        "accepted_evidence_semantic_pass_count": int(metrics.get("accepted_evidence_semantic_pass_count", 0)),
        "tracked_slice_gate_contexts": int(metrics.get("tracked_slice_gate_contexts", 0)),
        "s2_workflow_run_count": int(s2_workflow_metrics.get("run_count", 0)),
        "s2_unsafe_reduction_status": str(unsafe_reduction.get("status", "not_measured")),
        "s2_translation_before_after_status": str(translation_before_after.get("status", "not_provided")),
        "s2_translation_before_after_unit_count": int(translation_before_after.get("unit_count", 0)),
        "s2_translation_before_after_measured_unsafe_unit_count": int(
            translation_before_after.get("measured_unsafe_unit_count", 0)
        ),
        "s2_translation_before_after_accepted_patch_unit_count": int(
            translation_before_after.get("accepted_patch_unit_count", 0)
        ),
        "claim_boundary": str(payload.get("claim_boundary", "")),
    }
    return {"binding": binding, "payload": payload}


def write_before_after_exhibit_profile_report(
    *,
    profile: dict[str, Any],
    profile_path: Path,
    run_id: str,
    proof_class: str,
    mode: str,
    plan: dict[str, Any],
    run_result: dict[str, Any],
    route_metrics_artifact: dict[str, Any] | None,
    out_root: Path,
    proof_class_resolution: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any] | None:
    if not profile_bool(profile, "emit_before_after_exhibit_report", default=False):
        return None
    summary_path = out_root / "summary" / "competition-run-summary.json"
    report_path = out_root / "summary" / "before-after-exhibit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    if not summary_path.exists():
        reproduction = before_after_reproduction_commands(
            profile_path=profile_path,
            run_id=run_id,
            out_root=out_root,
            summary_path=summary_path,
            proof_class_resolution=proof_class_resolution,
            repo_root=repo_root,
        )
        payload = {
            "schema_version": SCHEMA_VERSION,
            "report_kind": "before-after-exhibit",
            "status": "failed",
            "reason": "competition_summary_missing",
            "run_id": run_id,
            "profile_id": profile_required_string(profile, "profile_id"),
            "profile_proof_class": profile.get("proof_class"),
            "proof_class": proof_class,
            "proof_class_resolution": proof_class_resolution,
            "mode": mode,
            "claim_boundary": {
                "source": "batch_profile_acceptance_boundary",
                "value": profile.get("acceptance_boundary", {}),
                "boundary": (
                    "This fail-closed exhibit records that the batch profile did not produce a "
                    "validated competition summary. It is harness failure evidence only and does "
                    "not create a translation or semantic acceptance claim."
                ),
            },
            "inputs": {
                "profile": artifact_ref(profile_path, repo_root=repo_root),
                "competition_summary": {
                    "path": repo_relative(summary_path, repo_root=repo_root),
                    "status": "missing",
                },
                "summary_validation": {
                    "status": "missing",
                    "reason": "competition_summary_missing",
                },
            },
            "core_translation_quality": {
                "final_gate_status": "missing",
                "semantic_pass_count": 0,
                "translation_before_after": {"status": "not_provided", "unit_count": 0},
                "unsafe_reduction": {"status": "not_measured"},
            },
            "harness_architecture": {
                "entrypoint": "before-after-exhibit",
                "command_status": str(run_result.get("status", "unknown")),
                "pipeline": [
                    "run-batch-profile",
                    "validate-summary",
                    "before-after-exhibit",
                ],
                "merge_execution": run_result.get("merge_execution")
                if isinstance(run_result.get("merge_execution"), dict)
                else {},
            },
            "translation_before_after": {
                "status": "not_provided",
                "unit_count": 0,
                "measured_unsafe_unit_count": 0,
                "accepted_patch_unit_count": 0,
            },
            "safety_loop_provenance": before_after_safety_loop_provenance_rollup([]),
            "units": [],
            "stage_contracts": {},
            "failure_path": before_after_failure_path(
                reason="competition_summary_missing",
                translation_before_after={"status": "not_provided", "unit_count": 0},
                reproduction=reproduction,
            ),
            "reproduction": reproduction,
        }
        atomic_write_json(report_path, payload)
        binding = {
            "path": repo_relative(report_path, repo_root=repo_root),
            "sha256": sha256_file(report_path),
            "status": "failed",
            "reason": "competition_summary_missing",
            "report_kind": "before-after-exhibit",
            "unit_count": 0,
            "measured_unsafe_unit_count": 0,
            "accepted_patch_unit_count": 0,
        }
        return {"binding": binding, "payload": payload}

    summary_validation = validate_competition_run_summary.validate_summary(summary_path, repo_root=repo_root)
    summary = load_json(summary_path)
    workflow_ref = summary["workflow_metrics"]
    workflow_path = validate_competition_run_summary.resolve_summary_artifact(
        str(workflow_ref["path"]),
        summary_path=summary_path,
        repo_root=repo_root,
    )
    if workflow_path is None:
        raise SystemExit("before-after exhibit requires an existing workflow metrics artifact")
    workflow_metrics = load_json(workflow_path)
    translation_before_after = (
        workflow_metrics.get("translation_before_after")
        if isinstance(workflow_metrics.get("translation_before_after"), dict)
        else {"status": "not_provided", "unit_count": 0}
    )
    units = before_after_exhibit_units(workflow_metrics)
    status = "passed" if units and translation_before_after.get("status") == "bound" else "not_provided"
    stage_contracts = before_after_stage_contracts(
        mode=mode,
        plan=plan,
        run_result=run_result,
        route_metrics_artifact=route_metrics_artifact,
        summary=summary,
        workflow_metrics=workflow_metrics,
        summary_path=summary_path,
        workflow_path=workflow_path,
        repo_root=repo_root,
    )
    if (
        profile_bool(profile, "require_repair_trace", default=False)
        and status == "passed"
        and stage_contracts.get("repairer", {}).get("status") != "verified"
    ):
        raise SystemExit(
            "before-after exhibit requires verified repair trace when profile require_repair_trace is true"
        )
    verified_baseline = verified_unsafe_baseline_ref_from_sources(profile)
    if profile_bool(profile, "require_repair_trace", default=False) and status == "passed":
        if verified_baseline is None:
            raise SystemExit(
                "before-after exhibit requires verified unsafe baseline when profile require_repair_trace is true"
            )
        before_after_require_verified_baseline(
            units=units,
            verified_baseline=verified_baseline,
        )
        repairer_contract = stage_contracts.setdefault("repairer", {})
        repairer_contract["verified_baseline_required"] = True
        repairer_contract["verified_baseline"] = {
            key: verified_baseline[key]
            for key in ("path", "sha256", "status")
            if isinstance(verified_baseline.get(key), str)
        }
        repairer_contract["baseline_verification_unit_count"] = len(units)
        repairer_contract["baseline_verification_status"] = "verified"
    reproduction = before_after_reproduction_commands(
        profile_path=profile_path,
        run_id=run_id,
        out_root=out_root,
        summary_path=summary_path,
        proof_class_resolution=proof_class_resolution,
        repo_root=repo_root,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "before-after-exhibit",
        "status": status,
        "run_id": run_id,
        "profile_id": profile_required_string(profile, "profile_id"),
        "profile_proof_class": profile.get("proof_class"),
        "proof_class": proof_class,
        "proof_class_resolution": proof_class_resolution,
        "mode": mode,
        "claim_boundary": {
            "source": "batch_profile_acceptance_boundary",
            "value": profile.get("acceptance_boundary", {}),
            "boundary": (
                "This exhibit binds before/after artifacts from a validated competition summary. "
                "It does not convert accepted-evidence-authoritative runs into translator-generated semantic pass."
            ),
        },
        "inputs": {
            "profile": artifact_ref(profile_path, repo_root=repo_root),
            "competition_summary": artifact_ref(summary_path, repo_root=repo_root),
            "workflow_metrics": artifact_ref(workflow_path, repo_root=repo_root),
            "summary_validation": summary_validation,
        },
        "translation_before_after": {
            "status": str(translation_before_after.get("status", "not_provided")),
            "unit_count": int(translation_before_after.get("unit_count", 0)),
            "measured_unsafe_unit_count": int(translation_before_after.get("measured_unsafe_unit_count", 0)),
            "accepted_patch_unit_count": int(translation_before_after.get("accepted_patch_unit_count", 0)),
        },
        "safety_loop_provenance": before_after_safety_loop_provenance_rollup(units),
        "units": units,
        "stage_contracts": stage_contracts,
        "reproduction": reproduction,
    }
    if status != "passed":
        payload["failure_path"] = before_after_failure_path(
            reason="before_after_not_bound",
            translation_before_after=translation_before_after,
            reproduction=reproduction,
        )
    atomic_write_json(report_path, payload)
    binding = {
        "path": repo_relative(report_path, repo_root=repo_root),
        "sha256": sha256_file(report_path),
        "status": status,
        "report_kind": "before-after-exhibit",
        "unit_count": len(units),
        "measured_unsafe_unit_count": int(payload["translation_before_after"]["measured_unsafe_unit_count"]),
        "accepted_patch_unit_count": int(payload["translation_before_after"]["accepted_patch_unit_count"]),
    }
    return {"binding": binding, "payload": payload}


def before_after_reproduction_commands(
    *,
    profile_path: Path,
    run_id: str,
    out_root: Path,
    summary_path: Path,
    proof_class_resolution: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    proof_class_suffix = proof_class_override_cli_suffix(
        proof_class_resolution=proof_class_resolution,
        fallback_proof_class=None,
    )
    return {
        "run_command": (
            "python3 -B -m validation.tools.opencode_agent_harness run-batch-profile "
            f"--profile {repo_relative(profile_path, repo_root=repo_root)} "
            f"--run-id {run_id} --out-root {repo_relative(out_root, repo_root=repo_root)}"
            f"{proof_class_suffix}"
        ),
        "verify_command": (
            "python3 -B validation/tools/validate_competition_run_summary.py "
            f"--summary {repo_relative(summary_path, repo_root=repo_root)}"
        ),
    }


def before_after_failure_path(
    *,
    reason: str,
    translation_before_after: dict[str, Any],
    reproduction: dict[str, str],
) -> dict[str, Any]:
    return {
        "status": "harness_exhibit_only",
        "reason": reason,
        "baseline_role": "handwritten_or_accepted_evidence_baseline",
        "public_text": (
            "The reviewed unsafe baseline remains a harness exhibit unless a passed verified unsafe "
            "baseline is bound into before/after evidence. Do not describe this path as a C2Rust "
            "semantic pass or translator-generated coverage."
        ),
        "translation_before_after_status": str(translation_before_after.get("status", "not_provided")),
        "next_repair_hint": {
            "status": "open",
            "root_cause_key": reason,
            "repair_round_cap": REPAIR_ROUND_CAP,
            "action": "rerun the before/after batch, inspect workflow metrics, and bind a passed verified unsafe baseline before publishing a C2Rust baseline claim",
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        "observable_diff": {
            "status": "not_available",
            "reason": reason,
            "required_for_c2rust_baseline_claim": True,
        },
        "smallest_replay_command": {
            "command": reproduction["run_command"],
            "verify_command": reproduction["verify_command"],
        },
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }


def before_after_safety_loop_provenance_rollup(units: list[dict[str, Any]]) -> dict[str, Any]:
    accepted_evidence_bound = 0
    opencode_session_bound = 0
    repair_history_bound = 0
    measured_unsafe_reduction = 0
    for unit in units:
        patch_origin = unit.get("patch_origin") if isinstance(unit.get("patch_origin"), dict) else {}
        provenance = (
            unit.get("safety_loop_provenance")
            if isinstance(unit.get("safety_loop_provenance"), dict)
            else {}
        )
        if patch_origin.get("accepted_patch_bound") is True:
            accepted_evidence_bound += 1
        if provenance.get("opencode_session_bound") is True:
            opencode_session_bound += 1
        if provenance.get("repair_history_bound") is True:
            repair_history_bound += 1
        unsafe_delta = provenance.get("unsafe_delta") if isinstance(provenance.get("unsafe_delta"), dict) else {}
        if unsafe_delta.get("status") == "measured":
            measured_unsafe_reduction += 1
    return {
        "status": "bound" if units else "not_provided",
        "unit_count": len(units),
        "accepted_evidence_bound_unit_count": accepted_evidence_bound,
        "opencode_session_bound_unit_count": opencode_session_bound,
        "repair_history_bound_unit_count": repair_history_bound,
        "measured_unsafe_reduction_unit_count": measured_unsafe_reduction,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "evidence_boundary": (
            "This rollup is a judge-facing provenance summary only. "
            "It does not convert patch origin, repair history, or OpenCode sessions into semantic acceptance."
        ),
    }


def before_after_exhibit_units(workflow_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    units = []
    for unit in workflow_metrics.get("per_unit_statuses", []):
        if not isinstance(unit, dict):
            continue
        evidence = unit.get("translation_before_after")
        if not isinstance(evidence, dict) or evidence.get("status") != "bound":
            continue
        exhibit_unit = {
            "unit_id": str(unit.get("unit_id", "unknown")),
            "source": str(unit.get("source", "unknown")),
            "status": str(unit.get("status", "unknown")),
            "baseline": evidence.get("baseline", {}),
            "final": evidence.get("final", {}),
            "oracle_evidence": evidence.get("oracle_evidence", {}),
            "accepted_patch": evidence.get("accepted_patch", {}),
            "unsafe_reduction": evidence.get("unsafe_reduction", {}),
        }
        exhibit_unit["patch_origin"] = before_after_patch_origin(evidence=evidence, unit=unit)
        exhibit_unit["safety_loop_provenance"] = before_after_safety_loop_provenance(
            evidence=evidence,
            unit=unit,
            patch_origin=exhibit_unit["patch_origin"],
        )
        if "repair_rounds" in unit:
            exhibit_unit["repair_rounds"] = int(unit.get("repair_rounds", 0) or 0)
        if "auto_recovered" in unit:
            exhibit_unit["auto_recovered"] = bool(unit.get("auto_recovered"))
        if isinstance(unit.get("root_cause_key"), str):
            exhibit_unit["root_cause_key"] = unit["root_cause_key"]
        if isinstance(unit.get("repair_history"), dict):
            exhibit_unit["repair_history"] = unit["repair_history"]
        if isinstance(evidence.get("patch_log"), dict):
            exhibit_unit["patch_log"] = evidence["patch_log"]
        if isinstance(evidence.get("baseline_verification"), dict):
            exhibit_unit["baseline_verification"] = evidence["baseline_verification"]
        if isinstance(evidence.get("claim_boundary"), dict):
            exhibit_unit["claim_boundary"] = evidence["claim_boundary"]
        units.append(exhibit_unit)
    return units


def before_after_require_verified_baseline(
    *,
    units: list[dict[str, Any]],
    verified_baseline: dict[str, Any],
) -> None:
    expected_path = str(verified_baseline.get("path", ""))
    expected_sha = str(verified_baseline.get("sha256", ""))
    if not expected_path or not expected_sha:
        raise SystemExit("before-after exhibit requires verified unsafe baseline path and sha256")
    for unit in units:
        baseline_verification = unit.get("baseline_verification")
        if not isinstance(baseline_verification, dict):
            raise SystemExit(
                "before-after exhibit requires baseline_verification to match verified unsafe baseline "
                "when profile require_repair_trace is true"
            )
        if baseline_verification.get("path") != expected_path or baseline_verification.get("sha256") != expected_sha:
            raise SystemExit(
                "before-after exhibit baseline_verification must match verified unsafe baseline path and sha256"
            )


def before_after_patch_origin(*, evidence: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    accepted_patch = evidence.get("accepted_patch")
    accepted_patch_bound = isinstance(accepted_patch, dict) and isinstance(accepted_patch.get("path"), str)
    opencode_session_bound = any(
        isinstance(unit.get(field), dict) or isinstance(evidence.get(field), dict)
        for field in (
            "opencode_session_evidence",
            "opencode_contract_verification",
            "handoff_contract",
        )
    )
    claim_boundary = evidence.get("claim_boundary") if isinstance(evidence.get("claim_boundary"), dict) else {}
    semantic_claim_source = str(claim_boundary.get("semantic_claim_source") or "accepted_evidence_binding")
    source = "accepted_safe_evidence" if accepted_patch_bound else "unbound"
    return {
        "source": source,
        "accepted_patch_bound": accepted_patch_bound,
        "opencode_session_bound": opencode_session_bound,
        "repair_history_bound": isinstance(unit.get("repair_history"), dict),
        "semantic_claim_source": semantic_claim_source,
        "generated_draft_semantic_pass": bool(claim_boundary.get("generated_draft_semantic_pass", False)),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "evidence_boundary": (
            "Patch origin is an audit label for the before/after exhibit. "
            "It does not turn accepted evidence or OpenCode session output into a semantic gate."
        ),
    }


def before_after_safety_loop_provenance(
    *,
    evidence: dict[str, Any],
    unit: dict[str, Any],
    patch_origin: dict[str, Any],
) -> dict[str, Any]:
    unsafe_reduction = evidence.get("unsafe_reduction") if isinstance(evidence.get("unsafe_reduction"), dict) else {}
    baseline_verification = (
        evidence.get("baseline_verification")
        if isinstance(evidence.get("baseline_verification"), dict)
        else unit.get("baseline_verification")
        if isinstance(unit.get("baseline_verification"), dict)
        else {}
    )
    opencode_session_bound = patch_origin.get("opencode_session_bound") is True
    repair_history_bound = patch_origin.get("repair_history_bound") is True
    status = "accepted_evidence_bound" if patch_origin.get("accepted_patch_bound") is True else "not_bound"
    if opencode_session_bound:
        status = "opencode_session_bound"
    return {
        "status": status,
        "patch_source": str(patch_origin.get("source", "unbound")),
        "baseline_verification_status": str(baseline_verification.get("status", "not_bound")),
        "unsafe_delta": json.loads(json.dumps(unsafe_reduction)),
        "opencode_session_bound": opencode_session_bound,
        "repair_history_bound": repair_history_bound,
        "repair_rounds": int(unit.get("repair_rounds", 0) or 0),
        "auto_recovered": bool(unit.get("auto_recovered", False)),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
        "evidence_boundary": (
            "Safety-loop provenance summarizes bound artifacts only. "
            "Semantic acceptance remains owned by oracle/diff/summary validators."
        ),
    }


def before_after_stage_contracts(
    *,
    mode: str,
    plan: dict[str, Any],
    run_result: dict[str, Any],
    route_metrics_artifact: dict[str, Any] | None,
    summary: dict[str, Any],
    workflow_metrics: dict[str, Any],
    summary_path: Path,
    workflow_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    run_plan = run_result
    workers = run_plan.get("workers") if isinstance(run_plan.get("workers"), list) else []
    merge_execution = (
        run_plan.get("merge_execution") if isinstance(run_plan.get("merge_execution"), dict) else {}
    )
    workflow_metrics_ref = summary.get("workflow_metrics") if isinstance(summary.get("workflow_metrics"), dict) else {}
    repair_histories = before_after_repair_histories(workflow_metrics)
    repair_status = (
        "verified"
        if any(history.get("verified") for history in repair_histories)
        else ("recorded" if repair_histories else "not_exercised")
    )
    return {
        "planner": {
            "stage": "planner",
            "status": str(plan.get("status", "unknown")),
            "plan": path_ref_from_text(plan.get("plan_path"), repo_root=repo_root),
            "source_sha256": plan.get("source_sha256"),
            "slice_id_prefix": plan.get("slice_id_prefix"),
            "worker_prefix": plan.get("worker_prefix"),
            "units": plan.get("units", []),
        },
        "worker": {
            "stage": "worker",
            "status": "passed" if workers and all(worker.get("exit_code") == 0 for worker in workers) else "unknown",
            "mode": mode,
            "workers": workers,
        },
        "verifier": {
            "stage": "verifier",
            "status": str(summary.get("final_gate", {}).get("status", "unknown")),
            "summary": artifact_ref(summary_path, repo_root=repo_root),
            "workflow_metrics": {
                "path": str(workflow_metrics_ref.get("path", repo_relative(workflow_path, repo_root=repo_root))),
                "sha256": str(workflow_metrics_ref.get("sha256", sha256_file(workflow_path))),
            },
            "semantic_pass": int(summary.get("slices", {}).get("semantic_pass", 0)),
            "generated_draft_semantic_pass": False,
            "semantic_claim_source": "accepted_evidence_binding",
        },
        "repairer": {
            "stage": "repairer",
            "status": repair_status,
            "repair_round_cap": REPAIR_ROUND_CAP,
            "observed_repair_unit_count": len(repair_histories),
            "avg_repair_rounds": float(workflow_metrics.get("avg_repair_rounds", 0.0) or 0.0),
            "auto_recovery_rate": float(workflow_metrics.get("auto_recovery_rate", 0.0) or 0.0),
            "root_cause_counts": (
                workflow_metrics["root_cause_counts"]
                if isinstance(workflow_metrics.get("root_cause_counts"), dict)
                else {}
            ),
            "histories": repair_histories,
            "evidence_boundary": (
                "Repair history is shown only when workflow metrics bind measured repair or retry evidence."
            ),
        },
        "reporter": {
            "stage": "reporter",
            "status": "passed",
            "report_path": run_plan.get("report_path"),
            "merge_execution": merge_execution,
            "route_governance_metrics_report": (
                route_metrics_artifact["binding"] if route_metrics_artifact is not None else None
            ),
            "workflow_metrics": artifact_ref(workflow_path, repo_root=repo_root),
        },
    }


def before_after_repair_histories(workflow_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    histories = []
    for unit in workflow_metrics.get("per_unit_statuses", []):
        if not isinstance(unit, dict) or not isinstance(unit.get("repair_history"), dict):
            continue
        history = unit["repair_history"]
        item = {
            "unit_id": str(unit.get("unit_id", "unknown")),
            "source": str(unit.get("source", "unknown")),
            "status": str(unit.get("status", "unknown")),
            "repair_rounds": int(unit.get("repair_rounds", 0) or 0),
            "auto_recovered": bool(unit.get("auto_recovered", False)),
            "verified": bool(history.get("verified", False)),
            "repair_history": history,
        }
        if isinstance(unit.get("root_cause_key"), str):
            item["root_cause_key"] = unit["root_cause_key"]
        histories.append(item)
    return histories


def artifact_ref(path: Path, *, repo_root: Path) -> dict[str, str]:
    return {
        "path": repo_relative(path, repo_root=repo_root),
        "sha256": sha256_file(path),
    }


def path_ref_from_text(value: Any, *, repo_root: Path) -> dict[str, str] | None:
    if not isinstance(value, str) or not value:
        return None
    path = repo_path(Path(value), repo_root=repo_root)
    if not path.exists():
        return {"path": value, "sha256": ""}
    return artifact_ref(path, repo_root=repo_root)


def artifact_binding_from_value(value: Any, *, repo_root: Path) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not isinstance(value.get("path"), str) or not value["path"]:
        return None
    binding = dict(value)
    path = repo_path(Path(value["path"]), repo_root=repo_root)
    if path.is_file():
        binding["sha256"] = sha256_file(path)
    else:
        binding["sha256"] = str(value.get("sha256", ""))
    return binding


def verified_unsafe_baseline_ref_from_value(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    direct_keys = ("verified_unsafe_baseline", "baseline_verification")
    for key in direct_keys:
        candidate = value.get(key)
        if isinstance(candidate, dict) and isinstance(candidate.get("path"), str) and candidate["path"]:
            return dict(candidate)
    attempt_policy = value.get("attempt_evidence_policy")
    if isinstance(attempt_policy, dict):
        candidate = verified_unsafe_baseline_ref_from_value(attempt_policy)
        if candidate is not None:
            return candidate
    baseline_attempt = value.get("baseline_attempt")
    if isinstance(baseline_attempt, dict):
        candidate = baseline_attempt.get("verified_unsafe_baseline")
        if isinstance(candidate, dict) and isinstance(candidate.get("path"), str) and candidate["path"]:
            return dict(candidate)
    translation_before_after = value.get("translation_before_after")
    if isinstance(translation_before_after, dict):
        candidate = translation_before_after.get("baseline_verification")
        if isinstance(candidate, dict) and isinstance(candidate.get("path"), str) and candidate["path"]:
            return dict(candidate)
    return None


def verified_unsafe_baseline_ref_from_sources(*sources: Any) -> dict[str, Any] | None:
    for source in sources:
        candidate = verified_unsafe_baseline_ref_from_value(source)
        if candidate is not None:
            return candidate
    return None


def verified_unsafe_baseline_binding_from_sources(*sources: Any, repo_root: Path) -> dict[str, Any] | None:
    candidate = verified_unsafe_baseline_ref_from_sources(*sources)
    if candidate is None:
        return None
    return artifact_binding_from_value(candidate, repo_root=repo_root)


def attempt_evidence_policy_from_sources(*sources: Any) -> dict[str, Any] | None:
    for source in sources:
        if not isinstance(source, dict):
            continue
        if "baseline_attempt" in source or "verified_unsafe_baseline" in source:
            return json.loads(json.dumps(source))
        policy = source.get("attempt_evidence_policy")
        if isinstance(policy, dict):
            return json.loads(json.dumps(policy))
    return None


def bind_verified_baseline_into_policy(
    policy: dict[str, Any],
    verified_baseline_ref: dict[str, Any] | None,
) -> dict[str, Any]:
    result = json.loads(json.dumps(policy))
    if verified_baseline_ref is None:
        return result
    baseline_attempt = result.setdefault("baseline_attempt", {})
    if isinstance(baseline_attempt, dict):
        baseline_attempt["verified_unsafe_baseline"] = verified_baseline_ref
    return result


def route_governance_competition_summary_paths(out_root: Path) -> list[Path]:
    summary_path = out_root / "summary" / "competition-run-summary.json"
    if not summary_path.exists():
        return []
    summary = load_json(summary_path)
    return [summary_path] if isinstance(summary.get("workflow_metrics"), dict) else []


def require_competition_exact_host_attestation(proof_class: str, *, context: str) -> None:
    if proof_class != "competition-exact":
        return
    if os.environ.get(COMPETITION_EXACT_HOST_ENV) == "1":
        return
    raise SystemExit(
        f"{context} proof_class=competition-exact requires {COMPETITION_EXACT_HOST_ENV}=1 "
        "from the real competition host"
    )


def profile_required_string(profile: dict[str, Any], field: str) -> str:
    value = profile.get(field)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"batch profile field must be a non-empty string: {field}")
    return value


def profile_string(profile: dict[str, Any], field: str, *, default: str | None = None) -> str | None:
    value = profile.get(field, default)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise SystemExit(f"batch profile field must be a non-empty string: {field}")
    return value


def profile_string_list(profile: dict[str, Any], field: str) -> list[str]:
    value = profile.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise SystemExit(f"batch profile field must be a list of non-empty strings: {field}")
    return list(value)


def profile_worker_list(profile: dict[str, Any]) -> list[dict[str, Any]]:
    value = profile.get("workers")
    if not isinstance(value, list) or not value:
        raise SystemExit("batch profile field must be a non-empty array: workers")
    workers: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise SystemExit(f"batch profile workers[{index}] must be an object")
        workers.append(item)
    return workers


def profile_bool(profile: dict[str, Any], field: str, *, default: bool) -> bool:
    value = profile.get(field, default)
    if not isinstance(value, bool):
        raise SystemExit(f"batch profile field must be boolean: {field}")
    return value


def profile_int(profile: dict[str, Any], field: str, *, default: int | None = None) -> int | None:
    value = profile.get(field, default)
    if value is None:
        return None
    if not isinstance(value, int) or value < 1:
        raise SystemExit(f"batch profile field must be a positive integer: {field}")
    return value


def run_plan_attempt_from_worker_result(result: dict[str, Any]) -> dict[str, Any]:
    attempt = repair_attempt_from_result(result)
    copy_opencode_worker_evidence(result, attempt)
    repair_hint = result.get("repair_hint")
    if isinstance(repair_hint, dict):
        if isinstance(repair_hint.get("hint_id"), str):
            attempt["hint_id"] = repair_hint["hint_id"]
        attempt["hint_status"] = "opened"
    if isinstance(result.get("hint_id"), str):
        attempt["hint_id"] = result["hint_id"]
    if isinstance(result.get("hint_status"), str):
        attempt["hint_status"] = result["hint_status"]
    elif int(result.get("exit_code", 1)) == 0 and result.get("summary_status") == "passed":
        attempt["hint_status"] = "passed"
    for field in ("repair_round_cap", "repair_rounds", "retry_limit"):
        if field in result:
            attempt[field] = result[field]
    return attempt


def copy_opencode_worker_evidence(source: dict[str, Any], target: dict[str, Any]) -> None:
    for field in OPENCODE_WORKER_EVIDENCE_FIELDS:
        value = source.get(field)
        if value is not None:
            target[field] = value


def run_plan_auto_retry_suppression(result: dict[str, Any], *, hint_id: str | None) -> dict[str, Any] | None:
    repair_hint = result.get("repair_hint")
    if not isinstance(repair_hint, dict):
        return None
    root_cause_key = repair_hint.get("root_cause_key")
    if root_cause_key != "opencode_database_locked_after_worker_command_seen":
        return None
    return {
        "status": "suppressed",
        "hint_id": hint_id,
        "root_cause_key": root_cause_key,
        "reason": "assigned worker command already reached the shell; retry would risk duplicate execution",
        "evidence_boundary": "opencode_contract_verification.status=executed",
    }


def run_plan_worker_final_decision(worker_result: dict[str, Any]) -> dict[str, str]:
    if int(worker_result.get("exit_code", 1)) == 0 and worker_result.get("summary_status") == "passed":
        return {"status": "accepted", "reason": "worker_summary_passed"}
    auto_retry = worker_result.get("auto_retry")
    if isinstance(auto_retry, dict) and auto_retry.get("final_hint_status") == "retry_limit_exceeded":
        return {"status": "refused", "reason": "retry_limit_exceeded"}
    if not worker_result.get("recorded"):
        return {"status": "refused", "reason": "worker_summary_missing"}
    return {"status": "refused", "reason": "worker_summary_failed"}


def run_plan(
    *,
    db_path: Path,
    run_id: str,
    plan_path: Path,
    out_root: Path,
    proof_class: str,
    mode: str = "deterministic",
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    opencode_preflight_report: Path | None = None,
    execute_merge: bool = False,
    auto_retry: bool = False,
    max_workers: int = 1,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    repair_trace: dict[str, Any] | None = None,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    plan_path = repo_path(plan_path, repo_root=repo_root)
    plan = load_json(plan_path)
    if plan.get("run_id") != run_id:
        raise SystemExit(f"plan run_id {plan.get('run_id')} does not match requested run_id {run_id}")
    units = plan.get("units")
    if not isinstance(units, list) or not units:
        raise SystemExit("run-plan requires a planner artifact with at least one unit")
    if max_workers < 1:
        raise SystemExit("run-plan max_workers must be a positive integer")
    opencode_preflight_binding = None
    if mode == "opencode":
        opencode_preflight_binding = validate_opencode_preflight_report(
            opencode_preflight_report,
            expected_run_id=run_id,
            opencode_command=opencode_command,
            opencode_model=opencode_model,
            opencode_agent=opencode_agent,
            opencode_variant=opencode_variant,
            opencode_skip_permissions=opencode_skip_permissions,
            opencode_allow_non_competition_model=opencode_allow_non_competition_model,
            repo_root=repo_root,
        )

    started = time.monotonic()
    planned_units = []
    for index, unit in enumerate(units, start=1):
        if not isinstance(unit, dict) or not isinstance(unit.get("worker_id"), str) or not unit["worker_id"]:
            raise SystemExit(f"run-plan unit {index} missing worker_id")
        planned_units.append(unit)

    effective_workers = min(max_workers, len(planned_units))

    def execute_unit(unit: dict[str, Any]) -> dict[str, Any]:
        result = run_worker(
            db_path=db_path,
            run_id=run_id,
            worker_id=unit["worker_id"],
            mode=mode,
            opencode_command=opencode_command,
            opencode_model=opencode_model,
            opencode_agent=opencode_agent,
            opencode_variant=opencode_variant,
            opencode_skip_permissions=opencode_skip_permissions,
            opencode_allow_non_competition_model=opencode_allow_non_competition_model,
            opencode_preflight_report=opencode_preflight_report,
            repair_trace=repair_trace,
            timeout_seconds=timeout_seconds,
            command_runner=command_runner,
            repo_root=repo_root,
        )
        worker_result = {
            "worker_id": unit["worker_id"],
            "slice_id": unit.get("slice_id"),
            "function": unit.get("function"),
            "exit_code": int(result.get("exit_code", 1)),
            "process_returncode": result.get("process_returncode"),
            "summary_status": result.get("summary_status"),
            "summary_path": result.get("summary_path"),
            "report_path": result.get("report_path"),
            "logs": result.get("logs"),
            "recorded": bool(result.get("recorded")),
        }
        copy_opencode_worker_evidence(result, worker_result)
        attempt_timeline = [run_plan_attempt_from_worker_result(result)]
        retry_results = []
        if auto_retry and worker_result["exit_code"] != 0:
            hint_id = None
            repair_hint = result.get("repair_hint")
            if isinstance(repair_hint, dict) and isinstance(repair_hint.get("hint_id"), str):
                hint_id = repair_hint["hint_id"]
            suppression = run_plan_auto_retry_suppression(result, hint_id=hint_id)
            if suppression is not None:
                worker_result["auto_retry_suppressed"] = suppression
            else:
                outer_round_cap = REPAIR_ROUND_CAP + 2
                for _outer_round in range(outer_round_cap):
                    retry_result = retry_worker(
                        db_path=db_path,
                        run_id=run_id,
                        worker_id=unit["worker_id"],
                        hint_id=hint_id,
                        mode=mode,
                        opencode_command=opencode_command,
                        opencode_model=opencode_model,
                        opencode_agent=opencode_agent,
                        opencode_variant=opencode_variant,
                        opencode_skip_permissions=opencode_skip_permissions,
                        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
                        opencode_preflight_report=opencode_preflight_report,
                        repair_trace=repair_trace,
                        timeout_seconds=timeout_seconds,
                        command_runner=command_runner,
                        repo_root=repo_root,
                        keep_open_on_failure=True,
                    )
                    retry_entry = {
                        "exit_code": int(retry_result.get("exit_code", 1)),
                        "summary_status": retry_result.get("summary_status"),
                        "hint_id": retry_result.get("hint_id", hint_id),
                        "hint_status": retry_result.get("hint_status"),
                        "summary_path": retry_result.get("summary_path"),
                        "report_path": retry_result.get("report_path"),
                        "logs": retry_result.get("logs"),
                        "process_returncode": retry_result.get("process_returncode"),
                    }
                    copy_opencode_worker_evidence(retry_result, retry_entry)
                    for field in ("repair_round_cap", "repair_rounds", "retry_limit", "rollback_evidence", "diagnostics"):
                        if field in retry_result:
                            retry_entry[field] = retry_result[field]
                    retry_results.append(retry_entry)
                    if retry_result.get("status") != "retry_limit_exceeded":
                        attempt_timeline.append(run_plan_attempt_from_worker_result(retry_result))
                    if retry_result.get("hint_id"):
                        hint_id = str(retry_result["hint_id"])
                    if int(retry_result.get("exit_code", 1)) == 0:
                        worker_result.update(
                            {
                                "exit_code": 0,
                                "summary_status": retry_result.get("summary_status"),
                                "summary_path": retry_result.get("summary_path"),
                                "report_path": retry_result.get("report_path"),
                                "recorded": bool(retry_result.get("recorded")),
                            }
                        )
                        copy_opencode_worker_evidence(retry_result, worker_result)
                        break
                    if retry_result.get("status") == "retry_limit_exceeded":
                        break
                else:
                    if retry_results:
                        retry_results[-1]["status"] = "outer_retry_limit_exceeded"
                        retry_results[-1]["hint_status"] = "outer_retry_limit_exceeded"
                        retry_results[-1]["outer_retry_limit"] = {
                            "max_outer_rounds": outer_round_cap,
                            "reason": "retry_worker did not return success or retry_limit_exceeded",
                        }
        if retry_results:
            worker_result["auto_retry"] = {
                "attempt_count": len(retry_results),
                "attempts": retry_results,
                "final_hint_status": retry_results[-1].get("hint_status"),
                "outer_round_cap": REPAIR_ROUND_CAP + 2,
            }
            if retry_results[-1].get("status") == "outer_retry_limit_exceeded":
                worker_result["auto_retry"]["outer_retry_limit_exceeded"] = True
        worker_result["attempts"] = attempt_timeline
        worker_result["final_decision"] = run_plan_worker_final_decision(worker_result)
        return worker_result

    if effective_workers == 1:
        worker_results = [execute_unit(unit) for unit in planned_units]
    else:
        worker_results_by_index: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = {
                executor.submit(execute_unit, unit): index
                for index, unit in enumerate(planned_units)
            }
            for future in as_completed(futures):
                worker_results_by_index[futures[future]] = future.result()
        worker_results = [worker_results_by_index[index] for index in range(len(planned_units))]

    failed_workers = sum(1 for worker in worker_results if int(worker["exit_code"]) != 0)
    ordered_summary_paths = [
        str(worker["summary_path"])
        for worker in worker_results
        if worker["recorded"] and worker["summary_path"]
    ]

    merge_plan = write_merge_plan(
        db_path=db_path,
        run_id=run_id,
        out_root=out_root,
        proof_class=proof_class,
        worker_summary_paths=ordered_summary_paths,
        repo_root=repo_root,
    )
    merge_execution = None
    merge_failed = False
    if execute_merge:
        unrecorded_workers = [worker["worker_id"] for worker in worker_results if not worker["recorded"]]
        if unrecorded_workers:
            merge_execution = {
                "status": "skipped",
                "reason": "unrecorded-worker-summaries",
                "exit_code": 1,
                "unrecorded_workers": unrecorded_workers,
            }
        else:
            merge_execution = execute_merge_plan(
                db_path=db_path,
                run_id=run_id,
                out_root=out_root,
                merge_plan=merge_plan,
                timeout_seconds=timeout_seconds,
                command_runner=command_runner,
                repo_root=repo_root,
            )
        merge_failed = int(merge_execution["exit_code"]) != 0
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed" if failed_workers == 0 and not merge_failed else "failed",
        "run_id": run_id,
        "mode": mode,
        "plan_path": repo_relative(plan_path, repo_root=repo_root),
        "worker_count": len(worker_results),
        "failed_workers": failed_workers,
        "graph": build_run_plan_graph_contract(
            mode=mode,
            auto_retry=auto_retry,
            max_workers=max_workers,
            effective_workers=effective_workers,
            opencode_variant=opencode_variant,
            opencode_preflight_report=opencode_preflight_binding,
        ),
        "parallelism": {
            "max_workers": max_workers,
            "effective_workers": effective_workers,
        },
        "auto_retry": {
            "enabled": auto_retry,
            "retried_worker_count": sum(1 for worker in worker_results if isinstance(worker.get("auto_retry"), dict)),
        },
        "exit_code": 0 if failed_workers == 0 and not merge_failed else 1,
        "elapsed_seconds": int(time.monotonic() - started),
        "workers": worker_results,
        "merge_plan": merge_plan,
    }
    if opencode_preflight_binding is not None:
        report["opencode_preflight_report"] = opencode_preflight_binding
    if merge_execution is not None:
        report["merge_execution"] = merge_execution
    report_path = out_root / "harness" / "run-plan-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_path, report)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        record_artifact(
            connection,
            run_id=run_id,
            worker_id="planner",
            kind="planned-worker-batch-report",
            path=report_path,
            status=report["status"],
            semantic_role="worker-batch-report",
            payload=report,
            repo_root=repo_root,
        )
        record_event(connection, run_id=run_id, event_type="planned_workers_executed", payload=report)
        connection.commit()
    result = dict(report)
    result["report_path"] = repo_relative(report_path, repo_root=repo_root)
    return result


def build_run_plan_graph_contract(
    *,
    mode: str,
    auto_retry: bool,
    max_workers: int,
    effective_workers: int,
    opencode_variant: str,
    opencode_preflight_report: dict[str, Any] | None,
) -> dict[str, Any]:
    opencode_worker = {
        "enabled": mode == "opencode",
        "preflight_required": mode == "opencode",
        "preflight_bound": opencode_preflight_report is not None,
    }
    if mode == "opencode":
        opencode_worker["opencode_variant"] = opencode_variant
    if opencode_preflight_report is not None:
        opencode_worker["preflight_report"] = {
            "path": opencode_preflight_report.get("path"),
            "sha256": opencode_preflight_report.get("sha256"),
            "status": opencode_preflight_report.get("status"),
            "contract_status": opencode_preflight_report.get("contract_status"),
            "launch_policy": opencode_preflight_report.get("launch_policy"),
            "launch_policy_sha256": opencode_preflight_report.get("launch_policy_sha256"),
            "opencode_runtime_env": opencode_preflight_report.get("opencode_runtime_env"),
        }
    return {
        "runtime": "opencode-harness-langgraph-inspired",
        "state_schema": "run-plan-state/v1",
        "checkpoint_backend": "sqlite",
        "nodes": [
            "load_plan",
            "fanout_workers",
            "worker",
            "repair_retry",
            "merge",
            "report",
        ],
        "edges": [
            {"from": "load_plan", "to": "fanout_workers", "condition": "units > 0"},
            {"from": "fanout_workers", "to": "worker", "condition": "map(unit)"},
            {"from": "worker", "to": "repair_retry", "condition": "exit_code != 0 and auto_retry"},
            {"from": "repair_retry", "to": "worker", "condition": "hint_open and repair_round < 5"},
            {"from": "fanout_workers", "to": "merge", "condition": "all_workers_recorded"},
            {"from": "merge", "to": "report", "condition": "always"},
        ],
        "parallel_map": {
            "node": "worker",
            "max_workers": max_workers,
            "effective_workers": effective_workers,
            "result_order": "planner_order",
        },
        "retry_policy": {
            "enabled": auto_retry,
            "round_cap": REPAIR_ROUND_CAP,
            "checkpoint": "repair_hints",
        },
        "opencode_worker": opencode_worker,
    }


def execute_merge_plan(
    *,
    db_path: Path,
    run_id: str,
    out_root: Path,
    merge_plan: dict[str, Any],
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    argv = list(merge_plan.get("argv", []))
    if not argv:
        raise SystemExit("merge plan argv is required before execute-merge")
    logs_dir = out_root / "harness"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / "run-plan-merge.stdout.log"
    stderr_path = logs_dir / "run-plan-merge.stderr.log"
    try:
        if command_runner is subprocess.run:
            completed = run_captured_process_with_timeout(
                argv,
                cwd=repo_root,
                timeout_seconds=timeout_seconds,
            )
        else:
            completed = command_runner(
                argv,
                cwd=repo_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
            )
    except subprocess.TimeoutExpired as exc:
        completed = completed_process_from_timeout(argv, exc, timeout_seconds)
    except OSError as exc:
        completed = subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}\n",
        )
    atomic_write_text(stdout_path, completed.stdout or "")
    atomic_write_text(stderr_path, completed.stderr or "")
    timed_out = completed_process_timed_out(completed)

    summary_path = out_root / "summary" / "competition-run-summary.json"
    summary_exists = summary_path.exists()
    final_gate_status = None
    finalized = None
    effective_exit_code = int(completed.returncode)
    if summary_exists:
        summary = load_json(summary_path)
        final_gate_status = str(summary.get("final_gate", {}).get("status", "failed"))
        if effective_exit_code == 0 and final_gate_status != "passed":
            effective_exit_code = 1
        finalized = finalize_run(
            db_path=db_path,
            run_id=run_id,
            status="completed" if effective_exit_code == 0 else "failed",
            summary_path=summary_path,
            final_gate_status=final_gate_status,
            repo_root=repo_root,
        )
    elif effective_exit_code == 0:
        effective_exit_code = 1

    result = {
        "exit_code": effective_exit_code,
        "process_returncode": int(completed.returncode),
        "argv": argv,
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "summary_exists": summary_exists,
        "final_gate_status": final_gate_status,
        "finalized": finalized,
    }
    if timed_out:
        result["timed_out"] = True
        result["timeout_seconds"] = timeout_seconds
        result["root_cause_key"] = "process_timeout"
    return result


def record_worker_summary(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    summary_path: Path,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    summary_path = repo_path(summary_path, repo_root=repo_root)
    now = now_text()
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        expected_summary_path = assigned_worker_summary_path(
            connection,
            run_id=run_id,
            worker_id=worker_id,
            repo_root=repo_root,
        )
        summary_rel = repo_relative(summary_path, repo_root=repo_root)
        expected_summary_rel = repo_relative(expected_summary_path, repo_root=repo_root)
        if summary_rel != expected_summary_rel:
            raise SystemExit(
                f"worker summary path {summary_rel} does not match assigned out_root summary {expected_summary_rel}"
            )
        summary = load_json(summary_path)
        status = str(summary.get("final_gate", {}).get("status", "failed"))
        summary_hash = sha256_file(summary_path)
        connection.execute(
            """
            insert into artifacts(run_id, agent_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(repo_rel_path) do update set
              run_id=excluded.run_id,
              agent_id=excluded.agent_id,
              kind=excluded.kind,
              sha256=excluded.sha256,
              status=excluded.status,
              semantic_role=excluded.semantic_role,
              payload_json=excluded.payload_json
            """,
            (
                run_id,
                worker_id,
                "competition-run-summary",
                summary_rel,
                summary_hash,
                status,
                "run-summary",
                json.dumps(summary, sort_keys=True),
                now,
            ),
        )
        connection.execute(
            "update agents set status=? where agent_id=? and run_id=?",
            (status, worker_id, run_id),
        )
        connection.execute(
            "update agent_tasks set status=?, ended_at=? where agent_id=? and run_id=?",
            (status, now, worker_id, run_id),
        )
        record_event(
            connection,
            run_id=run_id,
            event_type="worker_summary_recorded",
            payload={"worker_id": worker_id, "summary_path": summary_rel, "sha256": summary_hash, "status": status},
        )
        connection.commit()
    return {"status": "recorded", "summary": summary_rel, "sha256": summary_hash}


def record_artifact(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    worker_id: str,
    kind: str,
    path: Path,
    status: str,
    semantic_role: str,
    payload: dict[str, Any],
    repo_root: Path,
) -> dict[str, str]:
    artifact_rel = repo_relative(path, repo_root=repo_root)
    artifact_sha = sha256_file(path)
    connection.execute(
        """
        insert into artifacts(run_id, agent_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(repo_rel_path) do update set
          run_id=excluded.run_id,
          agent_id=excluded.agent_id,
          kind=excluded.kind,
          sha256=excluded.sha256,
          status=excluded.status,
          semantic_role=excluded.semantic_role,
          payload_json=excluded.payload_json
        """,
        (
            run_id,
            worker_id,
            kind,
            artifact_rel,
            artifact_sha,
            status,
            semantic_role,
            json.dumps(payload, sort_keys=True),
            now_text(),
        ),
    )
    return {"path": artifact_rel, "sha256": artifact_sha}


def worker_attempt_request(
    request: dict[str, Any],
    *,
    attempt_number: int,
    retry_of: str | None = None,
    repair_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempt_request = dict(request)
    attempt_request["harness_attempt"] = {
        "attempt": attempt_number,
        "repair_round": max(0, attempt_number - 1),
        "repair_round_cap": REPAIR_ROUND_CAP,
    }
    attempt_request["harness_attempt_number"] = attempt_number
    if retry_of:
        attempt_request["harness_retry_of"] = retry_of
        attempt_request["harness_repair_hint_id"] = retry_of
        attempt_request["harness_attempt"]["retry_of"] = retry_of
    if repair_trace is not None:
        attempt_request["harness_repair_trace"] = repair_trace
    return attempt_request


def run_worker_process(
    *,
    argv: list[str],
    mode: str,
    command_runner: Any,
    repo_root: Path,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
    worker_command: list[str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    retry_delays = [1, 2, 4, 8, 16] if mode == "opencode" else []
    attempts: list[dict[str, Any]] = []
    for index in range(len(retry_delays) + 1):
        completed = run_worker_process_once(
            argv=argv,
            command_runner=command_runner,
            repo_root=repo_root,
            timeout_seconds=timeout_seconds,
            env=env,
        )
        database_locked = mode == "opencode" and opencode_database_locked(completed)
        worker_command_observed = database_locked and opencode_worker_command_observed(completed, worker_command)
        transient_lock = database_locked and not worker_command_observed
        attempts.append(
            {
                "attempt": index + 1,
                "process_returncode": int(completed.returncode),
                "transient_lock": transient_lock,
                "database_locked": database_locked,
                "worker_command_observed": worker_command_observed,
                "stderr_tail": tail_text(completed.stderr or "", 512),
            }
        )
        if not transient_lock or index == len(retry_delays):
            break
        time.sleep(retry_delays[index])
    if len(attempts) == 1:
        return completed, None
    final_lock = attempts[-1]["transient_lock"] is True
    return completed, {
        "status": "exhausted" if final_lock else "recovered",
        "reason": "opencode_database_locked",
        "attempt_count": len(attempts),
        "transient_lock_retry_count": len(attempts) - 1,
        "max_transient_lock_retries": len(retry_delays),
        "attempts": attempts,
        "evidence_boundary": (
            "OpenCode process retry only handles transient agent database locks before the worker command executes; "
            "semantic acceptance still requires the worker summary and contract verifier."
        ),
        "semantic_gate": False,
    }


def timeout_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def completed_process_from_timeout(
    argv: list[str],
    exc: subprocess.TimeoutExpired,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    stdout = timeout_output_text(exc.output)
    stderr = timeout_output_text(exc.stderr).rstrip("\n")
    message = f"timed out after {timeout_seconds} seconds"
    stderr = f"{stderr}\n{message}\n" if stderr else f"{message}\n"
    return subprocess.CompletedProcess(argv, PROCESS_TIMEOUT_EXIT_CODE, stdout=stdout, stderr=stderr)


def completed_process_timed_out(completed: subprocess.CompletedProcess[str]) -> bool:
    return int(completed.returncode) == PROCESS_TIMEOUT_EXIT_CODE


def kill_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            return
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (OSError, ProcessLookupError):
            pass
    try:
        process.kill()
    except OSError:
        pass


def run_captured_process_with_timeout(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    env: dict[str, str] | None = None,
    popen_factory: Any = subprocess.Popen,
    process_tree_killer: Any = kill_process_tree,
) -> subprocess.CompletedProcess[str]:
    popen_kwargs: dict[str, Any] = {
        "cwd": cwd,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    process = popen_factory(argv, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return subprocess.CompletedProcess(argv, int(process.returncode), stdout=stdout, stderr=stderr)
    except subprocess.TimeoutExpired as exc:
        process_tree_killer(process)
        try:
            process.communicate(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return completed_process_from_timeout(argv, exc, timeout_seconds)


def run_worker_process_once(
    *,
    argv: list[str],
    command_runner: Any,
    repo_root: Path,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        if command_runner is subprocess.run:
            return run_captured_process_with_timeout(
                argv,
                cwd=repo_root,
                timeout_seconds=timeout_seconds,
                env=env,
            )
        return command_runner(
            argv,
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        return completed_process_from_timeout(argv, exc, timeout_seconds)
    except OSError as exc:
        return subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}\n",
        )


def opencode_database_locked(completed: subprocess.CompletedProcess[str]) -> bool:
    if int(completed.returncode) == 0:
        return False
    stderr = (completed.stderr or "").lower()
    return any(
        marker in stderr
        for marker in (
            "database is locked",
            "database table is locked",
            "sqlite_busy",
            "sqlite busy",
        )
    )


def opencode_worker_command_observed(
    completed: subprocess.CompletedProcess[str],
    worker_command: list[str] | None,
) -> bool:
    if worker_command is None:
        return False
    expected_worker_command_line = shell_command_line(worker_command)
    session_evidence = parse_opencode_stdout_session(completed.stdout or "")
    return any(
        command_matches_for_contract(command, expected_worker_command_line)
        for command in extract_opencode_shell_commands(session_evidence)
    )


def tail_text(value: str, max_chars: int) -> str:
    return value[-max_chars:]


def run_worker(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    mode: str = "deterministic",
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    opencode_preflight_report: Path | None = None,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
    attempt_number: int = 1,
    retry_of: str | None = None,
    repair_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    started = time.monotonic()
    assignment_path = assignment_file_path(db_path, worker_id)
    request_path = assignment_path.with_name(f"{worker_id}-request.json")
    if not request_path.exists():
        raise SystemExit(f"worker request does not exist: {repo_relative(request_path, repo_root=repo_root)}")
    request = load_json(request_path)
    if not request.get("out_root"):
        raise SystemExit("worker out_root is required in request")
    request_out_root = repo_path(Path(str(request.get("out_root", ""))), repo_root=repo_root)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        assigned_out_root_rel = assigned_worker_out_root_rel(connection, run_id=run_id, worker_id=worker_id)
    request_out_root_rel = repo_relative(request_out_root, repo_root=repo_root)
    if request_out_root_rel != assigned_out_root_rel:
        raise SystemExit(
            f"worker request out_root {request_out_root_rel} does not match ledger assignment {assigned_out_root_rel}"
        )
    worker_out_root = repo_path(Path(assigned_out_root_rel), repo_root=repo_root)
    summary_path = worker_out_root / "summary" / "competition-run-summary.json"
    logs_dir = worker_out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_dir = worker_out_root / "harness"
    report_dir.mkdir(parents=True, exist_ok=True)
    attempt_request = worker_attempt_request(
        request,
        attempt_number=attempt_number,
        retry_of=retry_of,
        repair_trace=repair_trace,
    )
    attempt_request_path = report_dir / f"{worker_id}-request-attempt-{attempt_number}.json"
    atomic_write_json(attempt_request_path, attempt_request)
    rollback_evidence = None
    stale_summary_cleanup_error: OSError | None = None
    if summary_path.exists():
        if retry_of:
            rollback_evidence = write_worker_rollback_evidence(
                hint_id=retry_of,
                run_id=run_id,
                worker_id=worker_id,
                summary_path=summary_path,
                report_dir=report_dir,
                repo_root=repo_root,
            )
        try:
            summary_path.unlink()
        except OSError as exc:
            stale_summary_cleanup_error = exc

    worker_command = portable_python_script_argv(
        "scripts/c2rust-migrator.py",
        "--phase",
        "migrate",
        "--input",
        repo_relative(attempt_request_path, repo_root=repo_root),
    )
    preflight_binding = None
    opencode_runtime_env = None
    opencode_process_env = None
    if mode == "opencode" and stale_summary_cleanup_error is None:
        preflight_binding = validate_opencode_preflight_report(
            opencode_preflight_report,
            expected_run_id=run_id,
            opencode_command=opencode_command,
            opencode_model=opencode_model,
            opencode_agent=opencode_agent,
            opencode_variant=opencode_variant,
            opencode_skip_permissions=opencode_skip_permissions,
            opencode_allow_non_competition_model=opencode_allow_non_competition_model,
            repo_root=repo_root,
        )
    if stale_summary_cleanup_error is not None:
        argv = worker_command
        report_argv = argv
        runner_kind = "stale-summary-cleanup"
        handoff_contract = None
        opencode_process_retries = None
        completed = subprocess.CompletedProcess(
            argv,
            1,
            stdout="",
            stderr=(
                f"{type(stale_summary_cleanup_error).__name__}: failed to remove stale summary "
                f"{repo_relative(summary_path, repo_root=repo_root)}: {stale_summary_cleanup_error}\n"
            ),
        )
    elif mode == "deterministic":
        argv = worker_command
        report_argv = argv
        runner_kind = "repo-local-c2rust-migrator"
        handoff_contract = None
        opencode_process_retries = None
    elif mode == "opencode":
        handoff_contract_path = report_dir / "opencode-handoff-contract.json"
        opencode_process_retries = None
        opencode_runtime_env = opencode_runtime_env_contract(
            base_root=worker_out_root,
            scope=worker_id,
            repo_root=repo_root,
        )
        opencode_process_env = opencode_runtime_process_env(opencode_runtime_env, repo_root=repo_root)
        argv = build_opencode_run_argv(
            opencode_command=opencode_command,
            opencode_model=opencode_model,
            opencode_agent=opencode_agent,
            opencode_variant=opencode_variant,
            opencode_skip_permissions=opencode_skip_permissions,
            opencode_allow_non_competition_model=opencode_allow_non_competition_model,
            worker_command=worker_command,
            request_path=attempt_request_path,
            summary_path=summary_path,
            handoff_contract_path=handoff_contract_path,
            repo_root=repo_root,
        )
        report_argv = portable_opencode_evidence_argv(
            argv,
            opencode_command=opencode_command,
        )
        runner_kind = "opencode-run"
        handoff_contract = write_opencode_handoff_contract(
            run_id=run_id,
            worker_id=worker_id,
            attempt_number=attempt_number,
            request_path=attempt_request_path,
            assignment_request_path=request_path,
            summary_path=summary_path,
            contract_path=handoff_contract_path,
            worker_command=worker_command,
            opencode_argv=report_argv,
            launch_policy=opencode_launch_policy(
                opencode_command=opencode_command,
                opencode_model=opencode_model,
                opencode_agent=opencode_agent,
                opencode_variant=opencode_variant,
                opencode_skip_permissions=opencode_skip_permissions,
                opencode_allow_non_competition_model=opencode_allow_non_competition_model,
            ),
            opencode_runtime_env=opencode_runtime_env,
            repo_root=repo_root,
        )
    else:
        raise SystemExit(f"unsupported worker mode: {mode}")

    if stale_summary_cleanup_error is None:
        completed, opencode_process_retries = run_worker_process(
            argv=argv,
            mode=mode,
            command_runner=command_runner,
            repo_root=repo_root,
            timeout_seconds=timeout_seconds,
            env=opencode_process_env,
            worker_command=worker_command,
        )
    timed_out = completed_process_timed_out(completed)
    stdout_path = logs_dir / "harness-worker-executor.stdout.log"
    stderr_path = logs_dir / "harness-worker-executor.stderr.log"
    atomic_write_text(stdout_path, completed.stdout or "")
    atomic_write_text(stderr_path, completed.stderr or "")
    opencode_session_evidence = None
    if mode == "opencode" and stale_summary_cleanup_error is None:
        opencode_session_evidence = write_opencode_session_evidence(
            completed=completed,
            evidence_path=logs_dir / "opencode-session-evidence.json",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            opencode_runtime_env=opencode_runtime_env,
            repo_root=repo_root,
        )
    opencode_contract_verification = None
    if opencode_session_evidence is not None:
        opencode_contract_verification = verify_opencode_contract_execution(
            session_evidence=load_json(repo_path(Path(opencode_session_evidence["path"]), repo_root=repo_root)),
            worker_command=worker_command,
            summary_path=summary_path,
            repo_root=repo_root,
        )
    opencode_safety_transform_attempt = None

    synthetic_failure_root_cause = None
    rejected_summary_evidence = None
    if stale_summary_cleanup_error is not None:
        synthetic_failure_root_cause = "stale_summary_cleanup_failed"
    if (
        synthetic_failure_root_cause is None
        and mode == "opencode"
        and stale_summary_cleanup_error is None
        and int(completed.returncode) != 0
        and opencode_database_locked(completed)
        and opencode_contract_verification is not None
        and opencode_contract_verification.get("status") == "executed"
    ):
        synthetic_failure_root_cause = "opencode_database_locked_after_worker_command_seen"
    opencode_contract_failed = (
        opencode_contract_verification is not None
        and opencode_contract_verification.get("status") != "executed"
        and int(completed.returncode) == 0
    )
    if stale_summary_cleanup_error is None and opencode_contract_failed:
        synthetic_failure_root_cause = "opencode_contract_not_executed"
        if summary_path.exists():
            rejected_summary_evidence = write_rejected_worker_summary_evidence(
                run_id=run_id,
                worker_id=worker_id,
                summary_path=summary_path,
                report_dir=report_dir,
                opencode_contract_verification=opencode_contract_verification,
                repo_root=repo_root,
            )
        write_blocked_worker_summary(
            run_id=run_id,
            proof_class=run_proof_class(db_path, run_id),
            worker_id=worker_id,
            request=request,
            root_cause_key=synthetic_failure_root_cause,
            process_returncode=int(completed.returncode),
            exit_code=1,
            elapsed_seconds=int(time.monotonic() - started),
            summary_path=summary_path,
            metrics_path=summary_path.parent / "workflow-metrics.json",
            opencode_contract_verification=opencode_contract_verification,
            handoff_contract=handoff_contract,
            opencode_session_evidence=opencode_session_evidence,
            repo_root=repo_root,
        )
    elif stale_summary_cleanup_error is None and not summary_path.exists():
        provisional_root_cause = synthetic_failure_root_cause or worker_failure_root_cause(
            process_returncode=int(completed.returncode),
            recorded=False,
            summary_status="missing-summary",
            opencode_contract_verification=opencode_contract_verification,
        )
        if provisional_root_cause in {
            "opencode_contract_not_executed",
            "process_timeout",
            "opencode_database_locked_after_worker_command_seen",
        }:
            synthetic_failure_root_cause = provisional_root_cause
            write_blocked_worker_summary(
                run_id=run_id,
                proof_class=run_proof_class(db_path, run_id),
                worker_id=worker_id,
                request=request,
                root_cause_key=provisional_root_cause,
                process_returncode=int(completed.returncode),
                exit_code=1,
                elapsed_seconds=int(time.monotonic() - started),
                summary_path=summary_path,
                metrics_path=summary_path.parent / "workflow-metrics.json",
                opencode_contract_verification=opencode_contract_verification,
                handoff_contract=handoff_contract,
                opencode_session_evidence=opencode_session_evidence,
                repo_root=repo_root,
            )

    recorded: dict[str, Any] | None = None
    summary_status = "stale-summary-cleanup-failed" if stale_summary_cleanup_error is not None else "missing-summary"
    summary_payload: dict[str, Any] | None = None
    if summary_path.exists() and stale_summary_cleanup_error is None:
        summary_payload = load_json(summary_path)
        summary_status = str(summary_payload.get("final_gate", {}).get("status", "failed"))
        if (
            mode == "opencode"
            and summary_status == "passed"
            and opencode_contract_verification is not None
            and opencode_contract_verification.get("status") == "executed"
        ):
            annotate_opencode_worker_metrics(
                summary_path=summary_path,
                handoff_contract=handoff_contract,
                opencode_session_evidence=opencode_session_evidence,
                opencode_contract_verification=opencode_contract_verification,
                repo_root=repo_root,
            )
            summary_payload = load_json(summary_path)
        if mode == "opencode" and opencode_contract_verification is not None:
            opencode_safety_transform_attempt = write_opencode_safety_transform_attempt(
                run_id=run_id,
                worker_id=worker_id,
                attempt_number=attempt_number,
                attempt_path=report_dir / "opencode-safety-transform-attempt.json",
                summary_path=summary_path,
                summary_payload=summary_payload,
                handoff_contract=handoff_contract,
                opencode_session_evidence=opencode_session_evidence,
                opencode_contract_verification=opencode_contract_verification,
                repo_root=repo_root,
            )
        recorded = record_worker_summary(
            db_path=db_path,
            run_id=run_id,
            worker_id=worker_id,
            summary_path=summary_path,
            repo_root=repo_root,
        )

    effective_exit_code = int(completed.returncode)
    if effective_exit_code == 0 and (recorded is None or summary_status != "passed"):
        effective_exit_code = 1
    status = "recorded" if recorded is not None else "failed"
    report_path = report_dir / "run-worker-report.json"
    repair_hint = None
    if effective_exit_code != 0:
        root_cause_key = (
            synthetic_failure_root_cause
            or worker_summary_root_cause(summary_payload, summary_path=summary_path, repo_root=repo_root)
            or worker_failure_root_cause(
            process_returncode=int(completed.returncode),
            recorded=recorded is not None,
            summary_status=summary_status,
            opencode_contract_verification=opencode_contract_verification,
            )
        )
        diagnostics = worker_repair_diagnostics(
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            process_returncode=int(completed.returncode),
            root_cause_key=root_cause_key,
        )
        repair_hint = worker_repair_hint_payload(
            db_path=db_path,
            run_id=run_id,
            worker_id=worker_id,
            request=request,
            root_cause_key=root_cause_key,
            summary_status=summary_status,
            process_returncode=int(completed.returncode),
            summary_path=summary_path,
            report_path=report_path,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            repo_root=repo_root,
            exit_code=effective_exit_code,
            attempt_number=attempt_number,
            diagnostics=diagnostics,
            retry_of=retry_of,
            rollback_evidence=rollback_evidence,
            rejected_summary_evidence=rejected_summary_evidence,
            handoff_contract=handoff_contract,
            opencode_session_evidence=opencode_session_evidence,
            opencode_contract_verification=opencode_contract_verification,
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "run-worker-report",
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt": attempt_number,
        "mode": mode,
        "runner_kind": runner_kind,
        "request_path": repo_relative(attempt_request_path, repo_root=repo_root),
        "assignment_request_path": repo_relative(request_path, repo_root=repo_root),
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "summary_status": summary_status,
        "recorded": recorded is not None,
        "exit_code": effective_exit_code,
        "process_returncode": int(completed.returncode),
        "argv": report_argv,
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
    }
    if timed_out:
        report["timed_out"] = True
        report["timeout_seconds"] = timeout_seconds
    if handoff_contract is not None:
        report["handoff_contract"] = handoff_contract
    if opencode_process_retries is not None:
        report["opencode_process_retries"] = opencode_process_retries
    if preflight_binding is not None:
        report["opencode_preflight_report"] = preflight_binding
    if opencode_runtime_env is not None:
        report["opencode_runtime_env"] = opencode_runtime_env
    if opencode_session_evidence is not None:
        report["opencode_session_evidence"] = opencode_session_evidence
    if opencode_contract_verification is not None:
        report["opencode_contract_verification"] = opencode_contract_verification
    if opencode_safety_transform_attempt is not None:
        report["opencode_safety_transform_attempt"] = opencode_safety_transform_attempt
    if retry_of:
        report["retry_of"] = retry_of
    if rollback_evidence is not None:
        report["rollback_evidence"] = rollback_evidence
    if rejected_summary_evidence is not None:
        report["rejected_summary_evidence"] = rejected_summary_evidence
    if repair_hint is not None:
        report["repair_hint"] = {
            "hint_id": repair_hint["hint_id"],
            "root_cause_key": repair_hint["root_cause_key"],
            "status": "open",
            "diagnostics": repair_hint["diagnostics"],
        }
    atomic_write_json(report_path, report)

    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        task_status = summary_status if recorded is not None else "failed"
        connection.execute(
            "update leases set status=?, heartbeat_at=? where run_id=? and lease_owner=?",
            (task_status, now_text(), run_id, worker_id),
        )
        event_payload = {
            "worker_id": worker_id,
            "attempt": attempt_number,
            "mode": mode,
            "runner_kind": runner_kind,
            "exit_code": effective_exit_code,
            "process_returncode": int(completed.returncode),
            "summary_path": repo_relative(summary_path, repo_root=repo_root),
            "summary_status": summary_status,
            "recorded": recorded is not None,
            "report_path": repo_relative(report_path, repo_root=repo_root),
        }
        worker_report_ref = record_artifact(
            connection,
            run_id=run_id,
            worker_id=worker_id,
            kind="run-worker-report",
            path=report_path,
            status=task_status,
            semantic_role="worker-execution-report",
            payload=report,
            repo_root=repo_root,
        )
        event_payload["worker_report"] = worker_report_ref
        if retry_of:
            event_payload["retry_of"] = retry_of
        if rollback_evidence is not None:
            event_payload["rollback_evidence"] = rollback_evidence
        if rejected_summary_evidence is not None:
            event_payload["rejected_summary_evidence"] = rejected_summary_evidence
        if handoff_contract is not None:
            event_payload["handoff_contract"] = handoff_contract
            record_artifact(
                connection,
                run_id=run_id,
                worker_id=worker_id,
                kind="opencode-handoff-contract",
                path=repo_path(Path(handoff_contract["path"]), repo_root=repo_root),
                status=summary_status,
                semantic_role="agent-command-contract",
                payload=load_json(repo_path(Path(handoff_contract["path"]), repo_root=repo_root)),
                repo_root=repo_root,
            )
        if opencode_process_retries is not None:
            event_payload["opencode_process_retries"] = opencode_process_retries
        if preflight_binding is not None:
            event_payload["opencode_preflight_report"] = preflight_binding
            record_artifact(
                connection,
                run_id=run_id,
                worker_id=worker_id,
                kind="opencode-preflight-report",
                path=repo_path(Path(preflight_binding["path"]), repo_root=repo_root),
                status=summary_status,
                semantic_role="agent-preflight-evidence",
                payload=load_json(repo_path(Path(preflight_binding["path"]), repo_root=repo_root)),
                repo_root=repo_root,
            )
        if opencode_runtime_env is not None:
            event_payload["opencode_runtime_env"] = opencode_runtime_env
        if opencode_session_evidence is not None:
            event_payload["opencode_session_evidence"] = opencode_session_evidence
            record_artifact(
                connection,
                run_id=run_id,
                worker_id=worker_id,
                kind="opencode-session-evidence",
                path=repo_path(Path(opencode_session_evidence["path"]), repo_root=repo_root),
                status=summary_status,
                semantic_role="agent-session-evidence",
                payload=load_json(repo_path(Path(opencode_session_evidence["path"]), repo_root=repo_root)),
                repo_root=repo_root,
            )
        if opencode_contract_verification is not None:
            event_payload["opencode_contract_verification"] = opencode_contract_verification
        if opencode_safety_transform_attempt is not None:
            event_payload["opencode_safety_transform_attempt"] = opencode_safety_transform_attempt
            record_artifact(
                connection,
                run_id=run_id,
                worker_id=worker_id,
                kind="opencode-safety-transform-attempt",
                path=repo_path(Path(opencode_safety_transform_attempt["path"]), repo_root=repo_root),
                status=summary_status,
                semantic_role="agent-safety-transform-attempt",
                payload=load_json(repo_path(Path(opencode_safety_transform_attempt["path"]), repo_root=repo_root)),
                repo_root=repo_root,
            )
        record_event(connection, run_id=run_id, event_type="worker_executed", payload=event_payload)
        if repair_hint is not None:
            record_repair_hint(connection, hint=repair_hint)
        connection.commit()

    result = dict(report)
    result["report_path"] = repo_relative(report_path, repo_root=repo_root)
    if recorded is not None:
        result["record_worker_summary"] = recorded
    return result


def retry_worker(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    hint_id: str | None = None,
    mode: str = "deterministic",
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    opencode_preflight_report: Path | None = None,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
    keep_open_on_failure: bool = False,
    repair_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        hint = load_open_repair_hint(connection, run_id=run_id, worker_id=worker_id, hint_id=hint_id)
        attempts = hint.get("attempts")
        attempt_number = len(attempts) + 1 if isinstance(attempts, list) else 2
        repair_rounds = max(0, attempt_number - 2)
        if repair_rounds >= REPAIR_ROUND_CAP:
            retry_result = mark_repair_hint_retry_limit_exceeded(
                connection,
                hint=hint,
                repair_rounds=repair_rounds,
            )
            connection.commit()
            return retry_result

    result = run_worker(
        db_path=db_path,
        run_id=run_id,
        worker_id=worker_id,
        mode=mode,
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        opencode_preflight_report=opencode_preflight_report,
        timeout_seconds=timeout_seconds,
        command_runner=command_runner,
        repo_root=repo_root,
        attempt_number=attempt_number,
        retry_of=str(hint["hint_id"]),
        repair_trace=repair_trace,
    )
    hint_status = (
        "revalidated_passed"
        if int(result.get("exit_code", 1)) == 0 and result.get("summary_status") == "passed"
        else "revalidated_failed"
    )
    retry_metrics_annotation = None
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        mark_repair_hint_revalidated(
            connection,
            hint_id=str(hint["hint_id"]),
            status=("open" if keep_open_on_failure and hint_status != "revalidated_passed" else hint_status),
            result=result,
        )
        if hint_status == "revalidated_passed":
            retry_metrics_annotation = annotate_retry_worker_metrics(
                connection,
                hint_id=str(hint["hint_id"]),
                result=result,
                repo_root=repo_root,
            )
        connection.commit()
    if retry_metrics_annotation is not None:
        result["retry_metrics_annotation"] = retry_metrics_annotation
        result["record_worker_summary"] = record_worker_summary(
            db_path=db_path,
            run_id=run_id,
            worker_id=worker_id,
            summary_path=repo_path(Path(str(result["summary_path"])), repo_root=repo_root),
            repo_root=repo_root,
        )

    retry_result = dict(result)
    retry_result["hint_id"] = hint["hint_id"]
    retry_result["hint_status"] = hint_status
    return retry_result


def mark_repair_hint_retry_limit_exceeded(
    connection: sqlite3.Connection,
    *,
    hint: dict[str, Any],
    repair_rounds: int,
) -> dict[str, Any]:
    retry_limit = {
        "status": "retry_limit_exceeded",
        "max_repair_rounds": REPAIR_ROUND_CAP,
        "observed_repair_rounds": repair_rounds,
        "boundary": "retry-worker refuses to launch another worker after the configured repair round cap",
    }
    payload = dict(hint)
    payload["status"] = "retry_limit_exceeded"
    payload["retry_limit"] = retry_limit
    hint_id = str(payload["hint_id"])
    connection.execute(
        "update repair_hints set status=?, payload_json=? where hint_id=?",
        ("retry_limit_exceeded", json.dumps(payload, sort_keys=True), hint_id),
    )
    record_event(
        connection,
        run_id=str(payload["run_id"]),
        event_type="repair_retry_limit_exceeded",
        payload={
            "hint_id": hint_id,
            "worker_id": payload.get("worker_id"),
            "repair_round_cap": REPAIR_ROUND_CAP,
            "repair_rounds": repair_rounds,
        },
    )
    result = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(payload["run_id"]),
        "worker_id": str(payload["worker_id"]),
        "hint_id": hint_id,
        "hint_status": "retry_limit_exceeded",
        "status": "retry_limit_exceeded",
        "exit_code": 1,
        "summary_status": str(payload.get("summary_status", "unknown")),
        "repair_round_cap": REPAIR_ROUND_CAP,
        "repair_rounds": repair_rounds,
        "retry_limit": retry_limit,
    }
    if isinstance(payload.get("summary_path"), str):
        result["summary_path"] = payload["summary_path"]
    if isinstance(payload.get("worker_report_path"), str):
        result["report_path"] = payload["worker_report_path"]
    if isinstance(payload.get("logs"), dict):
        result["logs"] = payload["logs"]
    if isinstance(payload.get("diagnostics"), dict):
        result["diagnostics"] = payload["diagnostics"]
    return result


def run_opencode_preflight(
    *,
    out_root: Path,
    run_id: str,
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    timeout_seconds: int = DEFAULT_SUBPROCESS_TIMEOUT_SECONDS,
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    out_root = repo_path(out_root, repo_root=repo_root)
    harness_dir = out_root / "harness"
    logs_dir = out_root / "logs"
    harness_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    marker_path = harness_dir / "opencode-preflight-marker.json"
    contract_path = harness_dir / "opencode-preflight-contract.json"
    if marker_path.exists():
        marker_path.unlink()
    opencode_runtime_env = opencode_runtime_env_contract(
        base_root=out_root,
        scope="preflight",
        repo_root=repo_root,
    )
    opencode_process_env = opencode_runtime_process_env(opencode_runtime_env, repo_root=repo_root)

    marker_command = portable_python_script_argv(
        "validation/tools/opencode_agent_harness.py",
        "write-preflight-marker",
        "--marker",
        repo_relative(marker_path, repo_root=repo_root),
        "--run-id",
        run_id,
    )
    launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    argv = build_opencode_preflight_argv(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        marker_command=marker_command,
        marker_path=marker_path,
        contract_path=contract_path,
        repo_root=repo_root,
    )
    report_argv = portable_opencode_evidence_argv(
        argv,
        opencode_command=launch_policy["opencode_command"],
    )
    contract_binding = write_opencode_preflight_contract(
        run_id=run_id,
        contract_path=contract_path,
        marker_path=marker_path,
        marker_command=marker_command,
        opencode_argv=report_argv,
        launch_policy=launch_policy,
        opencode_runtime_env=opencode_runtime_env,
        repo_root=repo_root,
    )
    started = time.monotonic()
    model_availability = run_opencode_model_availability_probe(
        opencode_command=launch_policy["opencode_command"],
        opencode_model=launch_policy["opencode_model"],
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        logs_dir=logs_dir,
        opencode_process_env=opencode_process_env,
        timeout_seconds=timeout_seconds,
        command_runner=command_runner,
        repo_root=repo_root,
    )
    if model_availability.get("status") != "available":
        stdout_path = logs_dir / "opencode-preflight.stdout.log"
        stderr_path = logs_dir / "opencode-preflight.stderr.log"
        atomic_write_text(stdout_path, "")
        atomic_write_text(stderr_path, "")
        root_cause_key = "opencode_model_unavailable"
        session_binding = write_opencode_not_launched_session_evidence(
            evidence_path=logs_dir / "opencode-preflight-session-evidence.json",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            root_cause_key=root_cause_key,
            opencode_runtime_env=opencode_runtime_env,
            repo_root=repo_root,
        )
        contract_verification = opencode_contract_not_observed(
            worker_command=marker_command,
            summary_path=marker_path,
            reason=root_cause_key,
            repo_root=repo_root,
        )
        report_path = harness_dir / "opencode-preflight-report.json"
        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": "failed",
            "exit_code": 1,
            "process_returncode": None,
            "elapsed_seconds": int(time.monotonic() - started),
            "argv": report_argv,
            "marker_path": repo_relative(marker_path, repo_root=repo_root),
            "marker_exists": False,
            "opencode_run_launched": False,
            "launch_policy": launch_policy,
            "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
            "opencode_runtime_env": opencode_runtime_env,
            "handoff_contract": contract_binding,
            "opencode_session_evidence": session_binding,
            "opencode_model_availability": model_availability,
            "contract_verification": contract_verification,
            "logs": {
                "stdout": repo_relative(stdout_path, repo_root=repo_root),
                "stderr": repo_relative(stderr_path, repo_root=repo_root),
            },
            "report_path": repo_relative(report_path, repo_root=repo_root),
            "root_cause_key": root_cause_key,
            "h9_blocker": opencode_h9_blocker(
                root_cause_key=root_cause_key,
                launch_policy=launch_policy,
                opencode_run_launched=False,
                model_availability=model_availability,
            ),
            "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
        }
        atomic_write_json(report_path, report)
        return report

    try:
        if command_runner is subprocess.run:
            completed = run_captured_process_with_timeout(
                argv,
                cwd=repo_root,
                timeout_seconds=timeout_seconds,
                env=opencode_process_env,
            )
        else:
            completed = command_runner(
                argv,
                cwd=repo_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                env=opencode_process_env,
            )
    except subprocess.TimeoutExpired as exc:
        completed = completed_process_from_timeout(argv, exc, timeout_seconds)
    except OSError as exc:
        completed = subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}\n",
        )
    stdout_path = logs_dir / "opencode-preflight.stdout.log"
    stderr_path = logs_dir / "opencode-preflight.stderr.log"
    atomic_write_text(stdout_path, completed.stdout or "")
    atomic_write_text(stderr_path, completed.stderr or "")
    timed_out = completed_process_timed_out(completed)
    session_binding = write_opencode_session_evidence(
        completed=completed,
        evidence_path=logs_dir / "opencode-preflight-session-evidence.json",
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        opencode_runtime_env=opencode_runtime_env,
        repo_root=repo_root,
    )
    session_evidence = load_json(repo_path(Path(session_binding["path"]), repo_root=repo_root))
    contract_verification = verify_opencode_contract_execution(
        session_evidence=session_evidence,
        worker_command=marker_command,
        summary_path=marker_path,
        repo_root=repo_root,
        allow_post_contract_artifact_inspection=True,
    )
    marker_exists = marker_path.exists()
    marker_validation = validate_opencode_preflight_marker_payload(
        marker_path,
        run_id=run_id,
        repo_root=repo_root,
    ) if marker_exists else {"status": "missing", "reason": "marker file is absent"}
    marker_binding = {
        "path": repo_relative(marker_path, repo_root=repo_root),
        "sha256": sha256_file(marker_path),
    } if marker_exists else None
    preflight_passed = (
        int(completed.returncode) == 0
        and contract_verification.get("status") == "executed"
        and marker_exists
        and marker_validation.get("status") == "passed"
    )
    root_cause_key = None
    if not preflight_passed:
        if timed_out:
            root_cause_key = "process_timeout"
        elif int(completed.returncode) != 0:
            root_cause_key = "opencode_process_failed"
        elif contract_verification.get("status") != "executed":
            root_cause_key = "opencode_contract_not_executed"
        elif marker_exists and marker_validation.get("status") != "passed":
            root_cause_key = "invalid_preflight_marker"
        else:
            root_cause_key = "missing_preflight_marker"

    report_path = harness_dir / "opencode-preflight-report.json"
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "passed" if preflight_passed else "failed",
        "exit_code": 0 if preflight_passed else 1,
        "process_returncode": int(completed.returncode),
        "elapsed_seconds": int(time.monotonic() - started),
        "argv": report_argv,
        "marker_path": repo_relative(marker_path, repo_root=repo_root),
        "marker_exists": marker_exists,
        "marker": marker_binding,
        "opencode_run_launched": True,
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "opencode_runtime_env": opencode_runtime_env,
        "handoff_contract": contract_binding,
        "opencode_session_evidence": session_binding,
        "opencode_model_availability": model_availability,
        "contract_verification": contract_verification,
        "marker_validation": marker_validation,
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
        "report_path": repo_relative(report_path, repo_root=repo_root),
        "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
    }
    if timed_out:
        report["timed_out"] = True
        report["timeout_seconds"] = timeout_seconds
    if launch_policy["opencode_model"] != COMPETITION_OPENCODE_MODEL:
        report["non_competition_model_rehearsal"] = {
            "status": "local_rehearsal_only",
            "actual_model": launch_policy["opencode_model"],
            "required_competition_model": COMPETITION_OPENCODE_MODEL,
            "local_simulation_closes_p0_h9": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "boundary": (
                "This preflight may prove local OpenCode wiring for a non-competition model, "
                "but it does not satisfy the GLM-5.1 competition host contract."
            ),
        }
        report["h9_blocker"] = opencode_h9_blocker(
            root_cause_key="non_competition_model_rehearsal",
            launch_policy=launch_policy,
            opencode_run_launched=True,
            model_availability=model_availability,
        )
    if root_cause_key is not None:
        report["root_cause_key"] = root_cause_key
        report["h9_blocker"] = opencode_h9_blocker(
            root_cause_key=root_cause_key,
            launch_policy=launch_policy,
            opencode_run_launched=True,
            model_availability=model_availability,
        )
    atomic_write_json(report_path, report)
    return report


def validate_opencode_preflight_report(
    report_path: Path | None,
    *,
    expected_run_id: str | None = None,
    opencode_command: str = "opencode",
    opencode_model: str | None = None,
    opencode_agent: str | None = None,
    opencode_variant: str = "max",
    opencode_skip_permissions: bool = False,
    opencode_allow_non_competition_model: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    if report_path is None:
        raise SystemExit("opencode preflight report is required before --mode opencode")
    report_path = repo_path(report_path, repo_root=repo_root)
    if not report_path.exists():
        raise SystemExit(f"opencode preflight report does not exist: {repo_relative(report_path, repo_root=repo_root)}")
    report = load_json(report_path)
    contract_verification = report.get("contract_verification")
    contract_status = contract_verification.get("status") if isinstance(contract_verification, dict) else None
    if (
        report.get("status") != "passed"
        or int(report.get("exit_code", 1)) != 0
        or report.get("marker_exists") is not True
        or contract_status != "executed"
    ):
        raise SystemExit(
            "opencode preflight report is not passed: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    expected_launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    launch_policy = report.get("launch_policy")
    if not isinstance(launch_policy, dict):
        raise SystemExit(
            "opencode preflight launch policy is missing: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    actual_launch_policy = normalize_opencode_launch_policy(
        launch_policy,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    actual_launch_policy_sha256 = report.get("launch_policy_sha256")
    if actual_launch_policy_sha256 != opencode_launch_policy_sha256(actual_launch_policy):
        raise SystemExit(
            "opencode preflight launch policy sha256 mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if actual_launch_policy != expected_launch_policy:
        raise SystemExit(
            "opencode preflight launch policy mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    model_availability = report.get("opencode_model_availability")
    if not isinstance(model_availability, dict):
        raise SystemExit(
            "opencode preflight model availability is missing: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    try:
        model_probe_returncode = int(model_availability.get("process_returncode", 1))
    except (TypeError, ValueError):
        model_probe_returncode = 1
    availability_binding = {
        "status": str(model_availability.get("status", "")),
        "opencode_command": str(model_availability.get("opencode_command", "")),
        "required_model": str(model_availability.get("required_model", "")),
        "argv": model_availability.get("argv") if isinstance(model_availability.get("argv"), list) else [],
        "process_returncode": model_probe_returncode,
        "model_listed": model_availability.get("model_listed") is True,
    }
    if (
        availability_binding["status"] != "available"
        or availability_binding["opencode_command"] != expected_launch_policy["opencode_command"]
        or availability_binding["required_model"] != expected_launch_policy["opencode_model"]
        or availability_binding["process_returncode"] != 0
        or availability_binding["model_listed"] is not True
    ):
        raise SystemExit(
            "opencode preflight model availability is not passed: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if not opencode_models_argv_matches(
        availability_binding["argv"],
        expected_command=expected_launch_policy["opencode_command"],
    ):
        raise SystemExit(
            "opencode preflight model availability argv must be opencode models: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    validate_opencode_model_probe_log_hashes(
        model_availability,
        repo_root=repo_root,
        report_path=report_path,
    )
    opencode_runtime_env = validate_opencode_runtime_env_contract(
        report.get("opencode_runtime_env"),
        context="opencode preflight report",
        repo_root=repo_root,
    )
    report_run_id = str(report.get("run_id", ""))
    if expected_run_id is not None and report_run_id != expected_run_id:
        raise SystemExit(f"opencode preflight run_id mismatch: {report_run_id} != {expected_run_id}")
    validate_opencode_preflight_session_contract(
        report,
        contract_verification=contract_verification,
        launch_policy=actual_launch_policy,
        run_id=report_run_id,
        report_path=report_path,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
        repo_root=repo_root,
    )
    return {
        "path": repo_relative(report_path, repo_root=repo_root),
        "sha256": sha256_file(report_path),
        "status": "passed",
        "run_id": report_run_id,
        "contract_status": "executed",
        "launch_policy": actual_launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(actual_launch_policy),
        "opencode_model_availability": availability_binding,
        "opencode_runtime_env": opencode_runtime_env,
        "evidence_boundary": str(
            report.get(
                "evidence_boundary",
                "preflight proves exact-command compliance only; it is not semantic acceptance",
            )
        ),
    }


def validate_opencode_preflight_session_contract(
    report: dict[str, Any],
    *,
    contract_verification: dict[str, Any],
    launch_policy: dict[str, Any],
    run_id: str,
    report_path: Path,
    repo_root: Path,
    opencode_allow_non_competition_model: bool = False,
) -> None:
    if report.get("opencode_run_launched") is not True:
        raise SystemExit(
            "opencode preflight opencode_run_launched must be true: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    try:
        process_returncode = int(report.get("process_returncode"))
    except (TypeError, ValueError):
        process_returncode = -1
    if process_returncode != 0:
        raise SystemExit(
            "opencode preflight process_returncode must be 0: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )

    marker_value = report.get("marker_path")
    if not isinstance(marker_value, str) or not marker_value:
        raise SystemExit(
            "opencode preflight marker_path is required: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    marker_path = repo_path(Path(marker_value), repo_root=repo_root)
    if not marker_path.is_file():
        raise SystemExit(
            "opencode preflight marker_path does not exist: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    marker_ref_path = validate_hash_bound_artifact_ref(
        report.get("marker"),
        label="opencode preflight marker",
        report_path=report_path,
        repo_root=repo_root,
    )
    if marker_ref_path.resolve() != marker_path.resolve():
        raise SystemExit(
            "opencode preflight marker.path must match marker_path: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    marker_validation = validate_opencode_preflight_marker_payload(
        marker_path,
        run_id=run_id,
        repo_root=repo_root,
    )
    if marker_validation.get("status") != "passed":
        raise SystemExit(
            "opencode preflight marker payload invalid: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )

    handoff_path = validate_hash_bound_artifact_ref(
        report.get("handoff_contract"),
        label="opencode preflight handoff_contract",
        report_path=report_path,
        repo_root=repo_root,
    )
    handoff = load_json(handoff_path)
    if handoff.get("runner_kind") != "opencode-preflight":
        raise SystemExit(
            "opencode preflight handoff_contract.runner_kind must be opencode-preflight: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("run_id") != run_id:
        raise SystemExit(
            "opencode preflight handoff_contract.run_id mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    handoff_policy = normalize_opencode_launch_policy(
        handoff["launch_policy"] if isinstance(handoff.get("launch_policy"), dict) else {},
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    if handoff_policy != launch_policy:
        raise SystemExit(
            "opencode preflight handoff_contract launch policy mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("launch_policy_sha256") != opencode_launch_policy_sha256(handoff_policy):
        raise SystemExit(
            "opencode preflight handoff_contract launch policy sha256 mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    expected_marker = handoff.get("expected_marker_path")
    if expected_marker != marker_value:
        raise SystemExit(
            "opencode preflight marker_path must match handoff_contract.expected_marker_path: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    worker_command = handoff.get("worker_command")
    if (
        not isinstance(worker_command, list)
        or not worker_command
        or not all(isinstance(item, str) and item for item in worker_command)
    ):
        raise SystemExit(
            "opencode preflight handoff_contract.worker_command must be a non-empty string list: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    worker_command_line = handoff.get("worker_command_line")
    if worker_command_line != shell_command_line(worker_command):
        raise SystemExit(
            "opencode preflight handoff_contract.worker_command_line mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("worker_command_sha256") != sha256_text(str(worker_command_line)):
        raise SystemExit(
            "opencode preflight handoff_contract.worker_command_sha256 mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    report_argv = require_opencode_string_argv(
        report.get("argv"),
        label="opencode preflight report argv",
        report_path=report_path,
        repo_root=repo_root,
    )
    handoff_argv = require_opencode_string_argv(
        handoff.get("opencode_argv"),
        label="opencode preflight handoff_contract.opencode_argv",
        report_path=report_path,
        repo_root=repo_root,
    )
    if report_argv != handoff_argv:
        raise SystemExit(
            "opencode preflight report argv must match handoff_contract.opencode_argv: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    validate_opencode_run_argv_binding(
        report_argv,
        label="opencode preflight report argv",
        launch_policy=launch_policy,
        report_path=report_path,
        repo_root=repo_root,
    )
    handoff_command_line = handoff.get("opencode_command_line")
    if handoff_command_line != shell_command_line(handoff_argv):
        raise SystemExit(
            "opencode preflight handoff_contract.opencode_command_line mismatch: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if handoff.get("prompt") != handoff_argv[-1]:
        raise SystemExit(
            "opencode preflight handoff_contract.prompt must match opencode_argv prompt: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )

    session_path = validate_hash_bound_artifact_ref(
        report.get("opencode_session_evidence"),
        label="opencode preflight opencode_session_evidence",
        report_path=report_path,
        repo_root=repo_root,
    )
    recomputed = verify_opencode_contract_execution(
        session_evidence=load_json(session_path),
        worker_command=worker_command,
        summary_path=marker_path,
        repo_root=repo_root,
        allow_post_contract_artifact_inspection=True,
    )
    if recomputed.get("status") != "executed":
        raise SystemExit(
            "opencode preflight session contract was not executed: "
            f"{recomputed.get('contract_failure_reason', 'unknown')}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    for key in (
        "expected_worker_command_line",
        "expected_summary_path",
        "expected_worker_command_sha256",
        "executed_shell_command_count",
        "executed_shell_commands",
        "first_shell_command",
        "first_shell_tool_name",
        "first_shell_workdir_status",
        "first_shell_command_matches_worker_command",
        "first_shell_workdir_matches_repo_root",
        "tools_before_first_shell",
        "worker_command_seen",
        "summary_exists",
        "status",
    ):
        if contract_verification.get(key) != recomputed.get(key):
            raise SystemExit(
                "opencode preflight session contract mismatch: "
                f"{key}: {repo_relative(report_path, repo_root=repo_root)}"
            )


def validate_hash_bound_artifact_ref(
    value: Any,
    *,
    label: str,
    report_path: Path,
    repo_root: Path,
) -> Path:
    if not isinstance(value, dict):
        raise SystemExit(f"{label} is required: {repo_relative(report_path, repo_root=repo_root)}")
    path_value = value.get("path")
    sha_value = value.get("sha256")
    if not isinstance(path_value, str) or not isinstance(sha_value, str):
        raise SystemExit(
            f"{label}.path and {label}.sha256 are required: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    artifact_path = repo_path(Path(path_value), repo_root=repo_root)
    if not artifact_path.is_file():
        raise SystemExit(f"{label}.path does not exist: {path_value}")
    if sha256_file(artifact_path) != sha_value:
        raise SystemExit(
            f"{label}.sha256 mismatch: {repo_relative(report_path, repo_root=repo_root)}"
        )
    return artifact_path


def validate_opencode_preflight_marker_payload(
    marker_path: Path,
    *,
    run_id: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    try:
        payload = load_json(marker_path)
    except Exception as error:  # noqa: BLE001 - convert malformed marker artifacts into fail-closed evidence.
        return {
            "status": "failed",
            "reason": f"marker_json_invalid:{type(error).__name__}",
        }
    failed_fields: list[str] = []
    if payload.get("report_kind") != "opencode-preflight-marker":
        failed_fields.append("report_kind")
    if payload.get("run_id") != run_id:
        failed_fields.append("run_id")
    if payload.get("status") != "written":
        failed_fields.append("status")
    return {
        "status": "passed" if not failed_fields else "failed",
        "failed_fields": failed_fields,
        "path": repo_relative(marker_path, repo_root=repo_root),
    }


def write_opencode_preflight_marker(
    *,
    marker_path: Path,
    run_id: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    marker_path = repo_path(marker_path, repo_root=repo_root)
    marker = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "opencode-preflight-marker",
        "run_id": run_id,
        "status": "written",
        "created_at": now_text(),
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(marker_path, marker)
    return {
        "status": "written",
        "marker_path": repo_relative(marker_path, repo_root=repo_root),
        "sha256": sha256_file(marker_path),
    }


def worker_failure_root_cause(
    *,
    process_returncode: int,
    recorded: bool,
    summary_status: str,
    opencode_contract_verification: dict[str, Any] | None = None,
) -> str:
    if process_returncode == PROCESS_TIMEOUT_EXIT_CODE:
        return "process_timeout"
    if process_returncode != 0:
        return "worker_process_failed"
    if (
        opencode_contract_verification is not None
        and opencode_contract_verification.get("status") == "not-executed"
        and not recorded
    ):
        return "opencode_contract_not_executed"
    if not recorded:
        return "missing_summary"
    if summary_status != "passed":
        return "final_gate_failed"
    return "worker_failed"


def worker_summary_root_cause(
    summary: dict[str, Any] | None,
    *,
    summary_path: Path,
    repo_root: Path,
) -> str | None:
    if not isinstance(summary, dict):
        return None
    workflow_ref = summary.get("workflow_metrics")
    if not isinstance(workflow_ref, dict) or not isinstance(workflow_ref.get("path"), str):
        return None
    metrics_path = resolve_summary_artifact(str(workflow_ref["path"]), summary_path=summary_path, repo_root=repo_root)
    if metrics_path is None or not metrics_path.exists():
        return None
    try:
        metrics = load_json(metrics_path)
    except (OSError, json.JSONDecodeError):
        return None
    root_cause_counts = metrics.get("root_cause_counts")
    if isinstance(root_cause_counts, dict):
        for key, count in root_cause_counts.items():
            if isinstance(key, str) and key and isinstance(count, int) and count > 0:
                return key
    per_unit_statuses = metrics.get("per_unit_statuses")
    if isinstance(per_unit_statuses, list):
        for unit in per_unit_statuses:
            if isinstance(unit, dict) and isinstance(unit.get("root_cause_key"), str) and unit["root_cause_key"]:
                return str(unit["root_cause_key"])
    return None


def worker_repair_diagnostics(
    *,
    stdout_path: Path,
    stderr_path: Path,
    process_returncode: int,
    root_cause_key: str,
) -> dict[str, Any]:
    stdout_tail = redact_local_absolute_paths(file_tail(stdout_path, REPAIR_LOG_TAIL_CHARS))
    stderr_tail = redact_local_absolute_paths(file_tail(stderr_path, REPAIR_LOG_TAIL_CHARS))
    combined = "\n".join(part for part in [stderr_tail, stdout_tail] if part)
    diagnostics: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "root_cause_key": root_cause_key,
        "process_returncode": process_returncode,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "primary_error": {
            "kind": "process",
            "message": root_cause_key,
        },
    }
    rustc_match = re.search(r"\berror\[(E\d+)\]:\s*(.+)", combined)
    if rustc_match:
        diagnostics["primary_error"] = {
            "kind": "rustc",
            "code": rustc_match.group(1),
            "message": rustc_match.group(2).strip(),
        }
    traceback_text = extract_python_traceback(combined)
    if traceback_text:
        diagnostics["python_traceback"] = traceback_text
        if diagnostics["primary_error"]["kind"] == "process":
            last_line = next((line.strip() for line in reversed(traceback_text.splitlines()) if line.strip()), "")
            diagnostics["primary_error"] = {
                "kind": "python",
                "message": last_line or "python traceback",
            }
    return diagnostics


def redact_local_absolute_paths(text: str) -> str:
    return LOCAL_ABSOLUTE_PATH_TEXT.sub("<local-absolute-path>", text)


def file_tail(path: Path, max_chars: int) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def extract_python_traceback(text: str) -> str:
    marker = "Traceback (most recent call last):"
    index = text.find(marker)
    if index < 0:
        return ""
    return text[index:][-REPAIR_LOG_TAIL_CHARS:]


def worker_repair_hint_payload(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    request: dict[str, Any],
    root_cause_key: str,
    summary_status: str,
    process_returncode: int,
    summary_path: Path,
    report_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    repo_root: Path,
    exit_code: int,
    attempt_number: int,
    diagnostics: dict[str, Any],
    retry_of: str | None = None,
    rollback_evidence: dict[str, Any] | None = None,
    rejected_summary_evidence: dict[str, Any] | None = None,
    handoff_contract: dict[str, Any] | None = None,
    opencode_session_evidence: dict[str, Any] | None = None,
    opencode_contract_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_id = str(request.get("target_id", "unknown"))
    slice_id = str(request.get("slice_id", "unknown"))
    hint_id = f"repair:{run_id}:{worker_id}:{root_cause_key}"
    retry_command = portable_python_script_argv(
        "validation/tools/opencode_agent_harness.py",
        "retry-worker",
        "--db",
        repo_relative(db_path, repo_root=repo_root),
        "--run-id",
        run_id,
        "--worker-id",
        worker_id,
        "--hint-id",
        hint_id,
    )
    hint = {
        "schema_version": SCHEMA_VERSION,
        "hint_id": hint_id,
        "run_id": run_id,
        "worker_id": worker_id,
        "target_id": target_id,
        "slice_id": slice_id,
        "root_cause_key": root_cause_key,
        "status": "open",
        "summary_status": summary_status,
        "process_returncode": process_returncode,
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "worker_report_path": repo_relative(report_path, repo_root=repo_root),
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
        "diagnostics": diagnostics,
        "attempts": [
            repair_attempt_payload(
                attempt_number=attempt_number,
                summary_status=summary_status,
                process_returncode=process_returncode,
                exit_code=exit_code,
                summary_path=repo_relative(summary_path, repo_root=repo_root),
                report_path=repo_relative(report_path, repo_root=repo_root),
                logs={
                    "stdout": repo_relative(stdout_path, repo_root=repo_root),
                    "stderr": repo_relative(stderr_path, repo_root=repo_root),
                },
                root_cause_key=root_cause_key,
                retry_of=retry_of,
                rollback_evidence=rollback_evidence,
                diagnostics=diagnostics,
            )
        ],
        "retry_command": retry_command,
        "revalidate_gate": "competition-run-summary.final_gate.status == passed",
    }
    if rejected_summary_evidence is not None:
        hint["rejected_summary_evidence"] = rejected_summary_evidence
    if handoff_contract is not None:
        hint["handoff_contract"] = handoff_contract
    if opencode_session_evidence is not None:
        hint["opencode_session_evidence"] = opencode_session_evidence
    if opencode_contract_verification is not None:
        hint["opencode_contract_verification"] = opencode_contract_verification
    return hint


def repair_attempt_payload(
    *,
    attempt_number: int,
    summary_status: str,
    process_returncode: int,
    exit_code: int,
    summary_path: str,
    report_path: str,
    logs: dict[str, str],
    root_cause_key: str | None = None,
    retry_of: str | None = None,
    rollback_evidence: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    attempt = {
        "attempt": attempt_number,
        "summary_status": summary_status,
        "process_returncode": process_returncode,
        "exit_code": exit_code,
        "summary_path": summary_path,
        "worker_report_path": report_path,
        "logs": logs,
    }
    if root_cause_key:
        attempt["root_cause_key"] = root_cause_key
    if retry_of:
        attempt["retry_of"] = retry_of
    if rollback_evidence is not None:
        attempt["rollback_evidence"] = rollback_evidence
    if diagnostics is not None:
        attempt["diagnostics"] = diagnostics
    return attempt


def repair_attempt_from_result(result: dict[str, Any]) -> dict[str, Any]:
    repair_hint = result.get("repair_hint")
    root_cause_key = repair_hint.get("root_cause_key") if isinstance(repair_hint, dict) else None
    return repair_attempt_payload(
        attempt_number=int(result.get("attempt", 1)),
        summary_status=str(result.get("summary_status", "unknown")),
        process_returncode=int(result.get("process_returncode", 1)),
        exit_code=int(result.get("exit_code", 1)),
        summary_path=str(result.get("summary_path", "")),
        report_path=str(result.get("report_path", "")),
        logs=dict(result.get("logs", {})),
        root_cause_key=str(root_cause_key) if root_cause_key else None,
        retry_of=str(result.get("retry_of")) if result.get("retry_of") else None,
        rollback_evidence=result.get("rollback_evidence") if isinstance(result.get("rollback_evidence"), dict) else None,
        diagnostics=(
            repair_hint.get("diagnostics")
            if isinstance(repair_hint, dict) and isinstance(repair_hint.get("diagnostics"), dict)
            else None
        ),
    )


def append_repair_attempt(payload: dict[str, Any], attempt: dict[str, Any]) -> None:
    attempts = payload.get("attempts")
    if not isinstance(attempts, list):
        attempts = []
    attempt_number = attempt.get("attempt")
    if not any(isinstance(item, dict) and item.get("attempt") == attempt_number for item in attempts):
        attempts.append(attempt)
    attempts.sort(key=lambda item: int(item.get("attempt", 0)) if isinstance(item, dict) else 0)
    payload["attempts"] = attempts


def write_worker_rollback_evidence(
    *,
    hint_id: str,
    run_id: str,
    worker_id: str,
    summary_path: Path,
    report_dir: Path,
    repo_root: Path,
) -> dict[str, Any]:
    safe_hint_id = "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in hint_id)
    evidence_path = report_dir / f"rollback-before-retry-{safe_hint_id}.json"
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "hint_id": hint_id,
        "action": "removed_stale_summary_before_retry",
        "removed_summary": {
            "path": repo_relative(summary_path, repo_root=repo_root),
            "sha256": sha256_file(summary_path),
        },
        "last_good": {
            "status": "not_available",
            "reason": "opencode harness has no accepted last-good worker summary for this failed retry",
        },
    }
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def write_rejected_worker_summary_evidence(
    *,
    run_id: str,
    worker_id: str,
    summary_path: Path,
    report_dir: Path,
    opencode_contract_verification: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    evidence_path = report_dir / "rejected-summary-opencode-contract.json"
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "action": "rejected_summary_due_to_opencode_contract",
        "rejected_summary": {
            "path": repo_relative(summary_path, repo_root=repo_root),
            "sha256": sha256_file(summary_path),
        },
        "opencode_contract_verification": opencode_contract_verification,
        "replacement": {
            "status": "blocked",
            "reason": "OpenCode did not execute the assigned worker command as the first shell command",
        },
    }
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def record_repair_hint(connection: sqlite3.Connection, *, hint: dict[str, Any]) -> None:
    now = now_text()
    existing = connection.execute("select payload_json from repair_hints where hint_id=?", (hint["hint_id"],)).fetchone()
    if existing is not None:
        existing_payload = json.loads(existing[0])
        existing_attempts = existing_payload.get("attempts")
        if isinstance(existing_attempts, list):
            for attempt in existing_attempts:
                if isinstance(attempt, dict):
                    append_repair_attempt(hint, attempt)
    connection.execute(
        """
        insert into repair_hints(hint_id, run_id, target_id, slice_id, root_cause_key, status, payload_json, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(hint_id) do update set
          target_id=excluded.target_id,
          slice_id=excluded.slice_id,
          root_cause_key=excluded.root_cause_key,
          status=excluded.status,
          payload_json=excluded.payload_json,
          created_at=excluded.created_at
        """,
        (
            hint["hint_id"],
            hint["run_id"],
            hint["target_id"],
            hint["slice_id"],
            hint["root_cause_key"],
            "open",
            json.dumps(hint, sort_keys=True),
            now,
        ),
    )
    record_event(
        connection,
        run_id=str(hint["run_id"]),
        event_type="repair_hint_recorded",
        payload={
            "hint_id": hint["hint_id"],
            "worker_id": hint["worker_id"],
            "root_cause_key": hint["root_cause_key"],
            "attempt": hint["attempts"][-1]["attempt"] if isinstance(hint.get("attempts"), list) else None,
            "attempt_count": len(hint["attempts"]) if isinstance(hint.get("attempts"), list) else 0,
        },
    )


def load_open_repair_hint(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    worker_id: str,
    hint_id: str | None,
) -> dict[str, Any]:
    if hint_id:
        rows = connection.execute(
            "select hint_id, status, payload_json from repair_hints where run_id=? and hint_id=?",
            (run_id, hint_id),
        ).fetchall()
    else:
        rows = connection.execute(
            "select hint_id, status, payload_json from repair_hints where run_id=? and status='open' order by created_at desc",
            (run_id,),
        ).fetchall()
    for row_hint_id, status, payload_json in rows:
        payload = json.loads(payload_json)
        if payload.get("worker_id") != worker_id:
            continue
        if status != "open":
            raise SystemExit(f"repair hint is not open: {row_hint_id} ({status})")
        return payload
    raise SystemExit(f"no open repair hint for worker {worker_id}")


def mark_repair_hint_revalidated(
    connection: sqlite3.Connection,
    *,
    hint_id: str,
    status: str,
    result: dict[str, Any],
) -> None:
    row = connection.execute("select run_id, payload_json from repair_hints where hint_id=?", (hint_id,)).fetchone()
    if row is None:
        raise SystemExit(f"unknown repair hint: {hint_id}")
    run_id, payload_json = row
    payload = json.loads(payload_json)
    append_repair_attempt(payload, repair_attempt_from_result(result))
    payload["status"] = status
    payload["revalidation"] = {
        "exit_code": result.get("exit_code"),
        "summary_status": result.get("summary_status"),
        "report_path": result.get("report_path"),
    }
    connection.execute(
        "update repair_hints set status=?, payload_json=? where hint_id=?",
        (status, json.dumps(payload, sort_keys=True), hint_id),
    )
    attempt = repair_attempt_from_result(result)
    record_event(
        connection,
        run_id=str(run_id),
        event_type="repair_hint_revalidated",
        payload={
            "hint_id": hint_id,
            "status": status,
            "attempt": attempt["attempt"],
            "exit_code": result.get("exit_code"),
            "summary_status": result.get("summary_status"),
            "retry_of": attempt.get("retry_of"),
            "rollback_evidence": attempt.get("rollback_evidence"),
        },
    )


def annotate_retry_worker_metrics(
    connection: sqlite3.Connection,
    *,
    hint_id: str,
    result: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any] | None:
    summary_path = repo_path(Path(str(result.get("summary_path", ""))), repo_root=repo_root)
    if not summary_path.exists():
        return None
    summary = load_json(summary_path)
    binding = summary.get("workflow_metrics")
    if not isinstance(binding, dict):
        return None
    metrics_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(metrics_ref, str) or not isinstance(expected_sha, str):
        raise SystemExit("retry worker summary workflow_metrics.path and workflow_metrics.sha256 are required")
    metrics_path = resolve_summary_artifact(metrics_ref, summary_path=summary_path, repo_root=repo_root)
    if metrics_path is None:
        raise SystemExit(f"retry worker summary workflow_metrics.path does not exist: {metrics_ref}")
    if sha256_file(metrics_path) != expected_sha:
        raise SystemExit("retry worker summary workflow_metrics.sha256 does not match artifact before annotation")
    metrics = load_json(metrics_path)
    units = metrics.get("per_unit_statuses")
    if not isinstance(units, list) or len(units) != 1 or not isinstance(units[0], dict):
        return None

    row = connection.execute("select payload_json from repair_hints where hint_id=?", (hint_id,)).fetchone()
    if row is None:
        raise SystemExit(f"unknown repair hint for retry metrics: {hint_id}")
    hint_payload = json.loads(row[0])
    attempts = hint_payload.get("attempts")
    if not isinstance(attempts, list) or len(attempts) < 2:
        return None

    repair_rounds = len(attempts) - 1
    safe_hint_id = safe_file_component(hint_id)
    history_path = summary_path.parent / f"retry-repair-history-{safe_hint_id}.jsonl"
    history_events = retry_repair_history_events(hint_payload, result)
    atomic_write_text(history_path, "".join(json.dumps(event, sort_keys=True) + "\n" for event in history_events))
    statuses = [str(event.get("status")) for event in history_events if isinstance(event.get("status"), str)]
    rollback_ids = retry_rollback_ids(attempts)
    repair_history = {
        "patch_events_path": repo_relative(history_path, repo_root=repo_root),
        "patch_events_sha256": sha256_file(history_path),
        "statuses": statuses,
        "rollback_ids": rollback_ids,
        "verified": "verified" in statuses,
    }

    unit = units[0]
    root_cause_key = hint_payload.get("root_cause_key")
    if isinstance(root_cause_key, str) and root_cause_key:
        unit["root_cause_key"] = root_cause_key
        metrics["root_cause_counts"] = {root_cause_key: 1}
    unit["repair_rounds"] = repair_rounds
    unit["auto_recovered"] = repair_history["verified"] and result.get("summary_status") == "passed"
    unit["repair_history"] = repair_history
    units_total = int(metrics.get("units_total", 1)) if isinstance(metrics.get("units_total"), int) else 1
    metrics["avg_repair_rounds"] = repair_rounds / max(1, units_total)
    metrics["auto_recovery_rate"] = (1.0 if unit["auto_recovered"] else 0.0) / max(1, units_total)
    atomic_write_json(metrics_path, metrics)

    summary["workflow_metrics"]["sha256"] = sha256_file(metrics_path)
    atomic_write_json(summary_path, summary)

    annotation = {
        "history_path": repo_relative(history_path, repo_root=repo_root),
        "history_sha256": sha256_file(history_path),
        "metrics_path": repo_relative(metrics_path, repo_root=repo_root),
        "metrics_sha256": sha256_file(metrics_path),
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "summary_sha256": sha256_file(summary_path),
        "repair_rounds": repair_rounds,
        "auto_recovered": bool(unit["auto_recovered"]),
        "unsafe_reduction": metrics.get("unsafe_reduction", {}),
    }
    record_artifact(
        connection,
        run_id=str(result["run_id"]),
        worker_id=str(result["worker_id"]),
        kind="retry-repair-history",
        path=history_path,
        status="verified" if annotation["auto_recovered"] else "recorded",
        semantic_role="repair-history",
        payload={"schema_version": SCHEMA_VERSION, "hint_id": hint_id, "events": history_events},
        repo_root=repo_root,
    )
    record_event(
        connection,
        run_id=str(result["run_id"]),
        event_type="retry_worker_metrics_annotated",
        payload={"hint_id": hint_id, **annotation},
    )
    return annotation


def annotate_opencode_worker_metrics(
    *,
    summary_path: Path,
    handoff_contract: dict[str, Any] | None,
    opencode_session_evidence: dict[str, Any] | None,
    opencode_contract_verification: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any] | None:
    if handoff_contract is None or opencode_session_evidence is None:
        return None
    summary = load_json(summary_path)
    binding = summary.get("workflow_metrics")
    if not isinstance(binding, dict):
        return None
    metrics_ref = binding.get("path")
    expected_sha = binding.get("sha256")
    if not isinstance(metrics_ref, str) or not isinstance(expected_sha, str):
        raise SystemExit("opencode worker summary workflow_metrics.path and workflow_metrics.sha256 are required")
    metrics_path = resolve_summary_artifact(metrics_ref, summary_path=summary_path, repo_root=repo_root)
    if metrics_path is None:
        raise SystemExit(f"opencode worker summary workflow_metrics.path does not exist: {metrics_ref}")
    if sha256_file(metrics_path) != expected_sha:
        raise SystemExit("opencode worker summary workflow_metrics.sha256 does not match artifact before annotation")
    metrics = load_json(metrics_path)
    units = metrics.get("per_unit_statuses")
    if not isinstance(units, list):
        return None

    updated_units = 0
    for unit in units:
        if not isinstance(unit, dict):
            continue
        unit["handoff_contract"] = json.loads(json.dumps(handoff_contract))
        unit["opencode_session_evidence"] = json.loads(json.dumps(opencode_session_evidence))
        unit["opencode_contract_verification"] = json.loads(json.dumps(opencode_contract_verification))
        updated_units += 1
    if updated_units == 0:
        return None

    atomic_write_json(metrics_path, metrics)
    summary["workflow_metrics"]["sha256"] = sha256_file(metrics_path)
    atomic_write_json(summary_path, summary)
    return {
        "metrics_path": repo_relative(metrics_path, repo_root=repo_root),
        "metrics_sha256": sha256_file(metrics_path),
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "summary_sha256": sha256_file(summary_path),
        "updated_unit_count": updated_units,
        "semantic_gate": False,
        "evidence_boundary": "OpenCode session fields are audit provenance only; summary validators still own acceptance.",
    }


def write_opencode_safety_transform_attempt(
    *,
    run_id: str,
    worker_id: str,
    attempt_number: int,
    attempt_path: Path,
    summary_path: Path,
    summary_payload: dict[str, Any],
    handoff_contract: dict[str, Any] | None,
    opencode_session_evidence: dict[str, Any] | None,
    opencode_contract_verification: dict[str, Any],
    repo_root: Path,
) -> dict[str, str]:
    final_gate = summary_payload.get("final_gate") if isinstance(summary_payload.get("final_gate"), dict) else {}
    final_gate_status = str(final_gate.get("status", "unknown"))
    contract_status = str(opencode_contract_verification.get("status", "unknown"))
    status = "accepted" if final_gate_status == "passed" and contract_status == "executed" else "blocked"
    workflow_metrics_binding = summary_payload.get("workflow_metrics")
    workflow_metrics_ref: dict[str, Any] | None = None
    workflow_metrics_payload: dict[str, Any] | None = None
    if isinstance(workflow_metrics_binding, dict) and isinstance(workflow_metrics_binding.get("path"), str):
        workflow_metrics_path = resolve_summary_artifact(
            str(workflow_metrics_binding["path"]),
            summary_path=summary_path,
            repo_root=repo_root,
        )
        if workflow_metrics_path is not None and workflow_metrics_path.exists():
            workflow_metrics_ref = {
                "path": str(workflow_metrics_binding["path"]),
                "sha256": sha256_file(workflow_metrics_path),
            }
            workflow_metrics_payload = load_json(workflow_metrics_path)

    safety_transform_units = opencode_safety_transform_units(
        workflow_metrics_payload if workflow_metrics_payload is not None else {},
        attempt_number=attempt_number,
        repo_root=repo_root,
    )

    attempt = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "opencode-safety-transform-attempt",
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt": attempt_number,
        "status": status,
        "summary": {
            "path": repo_relative(summary_path, repo_root=repo_root),
            "sha256": sha256_file(summary_path),
            "final_gate_status": final_gate_status,
        },
        "handoff_contract": json.loads(json.dumps(handoff_contract)) if handoff_contract is not None else None,
        "opencode_session_evidence": (
            json.loads(json.dumps(opencode_session_evidence)) if opencode_session_evidence is not None else None
        ),
        "contract_verification": json.loads(json.dumps(opencode_contract_verification)),
        "chat_output_is_evidence": False,
        "semantic_gate": False,
        "generated_draft_semantic_pass": False,
        "translation_coverage_numerator": 0,
        "attempt_contract": {
            "single_patch_per_round": True,
            "max_repair_rounds": REPAIR_ROUND_CAP,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
        "safety_transform_unit_count": len(safety_transform_units),
        "safety_transform_units": safety_transform_units,
        "evidence_boundary": (
            "This artifact records OpenCode command-contract participation in a safety-transform attempt. "
            "It does not make chat/session output semantic evidence; acceptance remains owned by the summary validators."
        ),
    }
    if workflow_metrics_ref is not None:
        attempt["workflow_metrics"] = workflow_metrics_ref
    root_cause = worker_summary_root_cause(summary_payload, summary_path=summary_path, repo_root=repo_root)
    if root_cause:
        attempt["root_cause_key"] = root_cause
    attempt_path.parent.mkdir(parents=True, exist_ok=True)
    numbered_attempt_path = opencode_numbered_safety_attempt_path(attempt_path, attempt_number=attempt_number)
    atomic_write_json(numbered_attempt_path, attempt)
    if numbered_attempt_path != attempt_path:
        atomic_write_json(attempt_path, attempt)
    return {
        "path": repo_relative(numbered_attempt_path, repo_root=repo_root),
        "sha256": sha256_file(numbered_attempt_path),
    }


def opencode_numbered_safety_attempt_path(attempt_path: Path, *, attempt_number: int) -> Path:
    if attempt_path.stem.endswith(f"-{attempt_number}"):
        return attempt_path
    return attempt_path.with_name(f"{attempt_path.stem}-{attempt_number}{attempt_path.suffix}")


def opencode_safety_transform_units(
    workflow_metrics: dict[str, Any],
    *,
    attempt_number: int,
    repo_root: Path,
) -> list[dict[str, Any]]:
    units = workflow_metrics.get("per_unit_statuses")
    if not isinstance(units, list):
        return []
    result: list[dict[str, Any]] = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        evidence = unit.get("translation_before_after")
        evidence = evidence if isinstance(evidence, dict) else {}
        repair_history = unit.get("repair_history")
        repair_history = repair_history if isinstance(repair_history, dict) else None
        if not evidence and repair_history is None:
            continue

        patch_evidence: dict[str, Any] = {}
        for field in ("baseline", "final", "accepted_patch", "patch_log"):
            value = evidence.get(field)
            if isinstance(value, dict):
                patch_evidence[field] = json.loads(json.dumps(value))

        verification_delta: dict[str, Any] = {}
        for field in (
            "baseline_verification",
            "oracle_evidence",
            "semantic_evidence",
            "unsafe_scan_evidence",
            "unsafe_reduction",
        ):
            value = evidence.get(field)
            if isinstance(value, dict):
                verification_delta[field] = json.loads(json.dumps(value))
        for field in ("compiled", "semantic_pass", "refused", "blocked", "failed"):
            if field in unit:
                verification_delta[field] = bool(unit.get(field))

        transform_unit: dict[str, Any] = {
            "unit_id": str(unit.get("unit_id", "unknown")),
            "status": str(unit.get("status", evidence.get("status", "unknown"))),
            "attempt": attempt_number,
            "round_contract": {
                "single_patch_per_round": True,
                "max_repair_rounds": REPAIR_ROUND_CAP,
            },
            "patch_evidence": patch_evidence,
            "verification_delta": verification_delta,
            "rounds": opencode_safety_transform_rounds(evidence, attempt_number=attempt_number),
            "accepted_retry_hint": opencode_accepted_retry_hint(unit, repair_history=repair_history, repo_root=repo_root),
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        }
        if repair_history is not None:
            transform_unit["repair_history"] = json.loads(json.dumps(repair_history))
        if "repair_rounds" in unit:
            transform_unit["repair_rounds"] = int(unit.get("repair_rounds", 0) or 0)
        if "auto_recovered" in unit:
            transform_unit["auto_recovered"] = bool(unit.get("auto_recovered"))
        root_cause = unit.get("root_cause_key")
        if isinstance(root_cause, str) and root_cause:
            transform_unit["root_cause_key"] = root_cause
        result.append(transform_unit)
    return result


def opencode_safety_transform_rounds(evidence: dict[str, Any], *, attempt_number: int) -> list[dict[str, Any]]:
    if not evidence:
        return []
    round_payload: dict[str, Any] = {
        "round": attempt_number,
        "single_patch_per_round": True,
    }
    field_map = {
        "accepted_patch": "patch",
        "patch_log": "patch_log",
        "oracle_evidence": "oracle_evidence",
        "unsafe_reduction": "unsafe_delta",
        "unsafe_scan_evidence": "unsafe_scan_evidence",
        "baseline_verification": "baseline_verification",
    }
    for source_field, target_field in field_map.items():
        value = evidence.get(source_field)
        if isinstance(value, dict):
            round_payload[target_field] = json.loads(json.dumps(value))
    semantic_evidence = evidence.get("semantic_evidence")
    if isinstance(semantic_evidence, dict) and isinstance(semantic_evidence.get("schema_diff"), dict):
        round_payload["schema_diff"] = json.loads(json.dumps(semantic_evidence["schema_diff"]))
    if set(round_payload) == {"round", "single_patch_per_round"}:
        return []
    return [round_payload]


def opencode_accepted_retry_hint(
    unit: dict[str, Any],
    *,
    repair_history: dict[str, Any] | None,
    repo_root: Path,
) -> dict[str, Any]:
    if repair_history is None:
        return {"status": "not_exercised"}
    statuses = repair_history.get("statuses") if isinstance(repair_history.get("statuses"), list) else []
    rollback_ids = repair_history.get("rollback_ids") if isinstance(repair_history.get("rollback_ids"), list) else []
    verified = bool(repair_history.get("verified"))
    auto_recovered = bool(unit.get("auto_recovered", False))
    rollback_evidence = opencode_rollback_evidence_refs(rollback_ids, repo_root=repo_root)
    rollback_evidence_complete = bool(rollback_evidence) and [
        ref.get("path") for ref in rollback_evidence
    ] == rollback_ids and all(is_sha256_hex(ref.get("sha256")) for ref in rollback_evidence)
    status = "revalidated_passed" if verified and auto_recovered and rollback_evidence_complete else (
        "verified" if verified else "recorded"
    )
    hint = {
        "status": status,
        "repair_rounds": int(unit.get("repair_rounds", 0) or 0),
        "auto_recovered": auto_recovered,
        "statuses": json.loads(json.dumps(statuses)),
        "rollback_ids": json.loads(json.dumps(rollback_ids)),
        "rollback_evidence": rollback_evidence,
    }
    for field in ("patch_events_path", "patch_events_sha256"):
        value = repair_history.get(field)
        if isinstance(value, str) and value:
            hint[field] = value
    return hint


def opencode_rollback_evidence_refs(rollback_ids: list[Any], *, repo_root: Path) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for item in rollback_ids:
        if not isinstance(item, str) or not item:
            continue
        rollback_path = repo_path(Path(item), repo_root=repo_root)
        ref = {"path": repo_relative(rollback_path, repo_root=repo_root)}
        if rollback_path.exists():
            ref["sha256"] = sha256_file(rollback_path)
        refs.append(ref)
    return refs


def retry_repair_history_events(hint_payload: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    events = []
    for attempt in hint_payload.get("attempts", []):
        if not isinstance(attempt, dict):
            continue
        events.append(
            {
                "attempt": attempt.get("attempt"),
                "status": attempt.get("summary_status", "unknown"),
                "exit_code": attempt.get("exit_code"),
                "retry_of": attempt.get("retry_of"),
                "root_cause_key": attempt.get("root_cause_key"),
                "rollback_evidence": attempt.get("rollback_evidence"),
            }
        )
    events.append(
        {
            "attempt": result.get("attempt"),
            "status": "verified",
            "summary_status": result.get("summary_status"),
            "exit_code": result.get("exit_code"),
            "report_path": result.get("report_path"),
        }
    )
    return events


def retry_rollback_ids(attempts: list[Any]) -> list[str]:
    rollback_ids = []
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        rollback = attempt.get("rollback_evidence")
        if not isinstance(rollback, dict):
            continue
        path = rollback.get("path")
        if isinstance(path, str) and path:
            rollback_ids.append(path)
    return rollback_ids


def resolve_summary_artifact(value: str, *, summary_path: Path, repo_root: Path) -> Path | None:
    checked_relative_path(value)
    candidates = [
        repo_root / value,
        summary_path.parent / value,
        summary_path.parent.parent / value,
    ]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            continue
        if resolved.exists():
            return resolved
    return None


def safe_file_component(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "-" for char in value)


def opencode_runtime_env_contract(
    *,
    base_root: Path,
    scope: str,
    repo_root: Path,
) -> dict[str, Any]:
    base_root = repo_path(base_root, repo_root=repo_root)
    scope_text = safe_file_component(scope) or "opencode"
    runtime_root = base_root / "opencode-runtime" / scope_text
    runtime_paths = {
        "XDG_CONFIG_HOME": runtime_root / "config",
        "XDG_DATA_HOME": runtime_root / "data",
        "XDG_CACHE_HOME": runtime_root / "cache",
        "TMPDIR": runtime_root / "tmp",
        "TEMP": runtime_root / "tmp",
        "TMP": runtime_root / "tmp",
    }
    for path in {path for path in runtime_paths.values()}:
        path.mkdir(parents=True, exist_ok=True)
    env = {key: repo_relative(runtime_paths[key], repo_root=repo_root) for key in OPENCODE_RUNTIME_ENV_KEYS}
    runtime_root_rel = repo_relative(runtime_root, repo_root=repo_root)
    digest_payload = {
        "scope": scope_text,
        "runtime_root": runtime_root_rel,
        "env": env,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "isolated",
        "scope": scope_text,
        "runtime_root": runtime_root_rel,
        "env": env,
        "env_sha256": sha256_text(json.dumps(digest_payload, sort_keys=True)),
        "semantic_gate": False,
        "evidence_boundary": (
            "OpenCode runtime env isolation controls process-local agent state only; "
            "semantic acceptance still requires worker summaries and validators."
        ),
    }


def validate_opencode_runtime_env_contract(
    value: Any,
    *,
    context: str,
    repo_root: Path,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit(f"{context} opencode_runtime_env is missing")
    if value.get("status") != "isolated":
        raise SystemExit(f"{context} opencode_runtime_env is not isolated")
    scope = value.get("scope")
    runtime_root = value.get("runtime_root")
    env = value.get("env")
    if not isinstance(scope, str) or not scope:
        raise SystemExit(f"{context} opencode_runtime_env.scope is missing")
    if not isinstance(runtime_root, str) or not runtime_root:
        raise SystemExit(f"{context} opencode_runtime_env.runtime_root is missing")
    runtime_root_path = checked_relative_path(runtime_root)
    if len(runtime_root_path.parts) < 2 or runtime_root_path.parts[-2:] != ("opencode-runtime", scope):
        raise SystemExit(f"{context} opencode_runtime_env.runtime_root must end with opencode-runtime/<scope>")
    repo_path(Path(runtime_root_path.as_posix()), repo_root=repo_root)
    if not isinstance(env, dict):
        raise SystemExit(f"{context} opencode_runtime_env.env is missing")
    expected_env = {
        "XDG_CONFIG_HOME": runtime_root_path / "config",
        "XDG_DATA_HOME": runtime_root_path / "data",
        "XDG_CACHE_HOME": runtime_root_path / "cache",
        "TMPDIR": runtime_root_path / "tmp",
        "TEMP": runtime_root_path / "tmp",
        "TMP": runtime_root_path / "tmp",
    }
    if set(env) != set(expected_env):
        raise SystemExit(f"{context} opencode_runtime_env.env keys mismatch")
    normalized_env: dict[str, str] = {}
    for key in OPENCODE_RUNTIME_ENV_KEYS:
        path_text_value = env.get(key)
        if not isinstance(path_text_value, str) or not path_text_value:
            raise SystemExit(f"{context} opencode_runtime_env.env.{key} is missing")
        env_path = checked_relative_path(path_text_value)
        if env_path != expected_env[key]:
            raise SystemExit(f"{context} opencode_runtime_env.env.{key} must be under runtime_root")
        repo_path(Path(env_path.as_posix()), repo_root=repo_root)
        normalized_env[key] = env_path.as_posix()
    expected_digest = sha256_text(
        json.dumps(
            {
                "scope": scope,
                "runtime_root": runtime_root,
                "env": normalized_env,
            },
            sort_keys=True,
        )
    )
    if value.get("env_sha256") != expected_digest:
        raise SystemExit(f"{context} opencode_runtime_env.env_sha256 mismatch")
    return {
        **value,
        "scope": scope,
        "runtime_root": runtime_root,
        "env": normalized_env,
        "env_sha256": expected_digest,
    }


def opencode_runtime_process_env(
    runtime_env: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, str]:
    process_env = dict(os.environ)
    env = runtime_env.get("env") if isinstance(runtime_env.get("env"), dict) else {}
    for key in OPENCODE_RUNTIME_ENV_KEYS:
        value = env.get(key)
        if isinstance(value, str):
            process_env[key] = str(repo_path(Path(value), repo_root=repo_root))
    return process_env


def opencode_launch_policy(
    *,
    opencode_command: str,
    opencode_model: str | None,
    opencode_agent: str | None,
    opencode_variant: str,
    opencode_skip_permissions: bool,
    opencode_allow_non_competition_model: bool = False,
) -> dict[str, Any]:
    if opencode_command != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit(f"opencode_command must be {COMPETITION_OPENCODE_COMMAND}")
    if opencode_model is None:
        opencode_model = COMPETITION_OPENCODE_MODEL
    if opencode_model != COMPETITION_OPENCODE_MODEL and not opencode_allow_non_competition_model:
        raise SystemExit(f"opencode_model must be {COMPETITION_OPENCODE_MODEL}")
    if opencode_agent is None:
        opencode_agent = COMPETITION_OPENCODE_AGENT
    if opencode_agent != COMPETITION_OPENCODE_AGENT:
        raise SystemExit(f"opencode_agent must be {COMPETITION_OPENCODE_AGENT}")
    if opencode_variant != COMPETITION_OPENCODE_VARIANT:
        raise SystemExit(f"opencode_variant must be {COMPETITION_OPENCODE_VARIANT}")
    return {
        "opencode_command": opencode_command,
        "opencode_model": opencode_model,
        "opencode_agent": opencode_agent,
        "opencode_variant": opencode_variant,
        "opencode_skip_permissions": bool(opencode_skip_permissions),
    }


def normalize_opencode_launch_policy(
    policy: dict[str, Any],
    *,
    opencode_allow_non_competition_model: bool = False,
) -> dict[str, Any]:
    required_fields = {
        "opencode_command",
        "opencode_model",
        "opencode_agent",
        "opencode_variant",
        "opencode_skip_permissions",
    }
    missing_fields = required_fields.difference(policy.keys())
    if missing_fields:
        raise SystemExit("opencode preflight launch policy is missing fields: " + ", ".join(sorted(missing_fields)))
    if not isinstance(policy.get("opencode_agent"), str):
        raise SystemExit(f"opencode preflight launch policy opencode_agent must be {COMPETITION_OPENCODE_AGENT}")
    return opencode_launch_policy(
        opencode_command=str(policy.get("opencode_command", "")),
        opencode_model=policy.get("opencode_model") if isinstance(policy.get("opencode_model"), str) else None,
        opencode_agent=policy.get("opencode_agent"),
        opencode_variant=str(policy.get("opencode_variant", "")),
        opencode_skip_permissions=policy.get("opencode_skip_permissions") is True,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )


def opencode_launch_policy_sha256(policy: dict[str, Any]) -> str:
    return sha256_text(json.dumps(policy, sort_keys=True))


def build_opencode_models_argv(*, opencode_command: str) -> list[str]:
    if opencode_command != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit(f"opencode_command must be {COMPETITION_OPENCODE_COMMAND}")
    return [resolve_subprocess_command(opencode_command), "models"]


def portable_opencode_evidence_argv(argv: list[str], *, opencode_command: str) -> list[str]:
    if not argv:
        raise SystemExit("opencode argv must not be empty")
    if opencode_command != COMPETITION_OPENCODE_COMMAND:
        raise SystemExit(f"opencode_command must be {COMPETITION_OPENCODE_COMMAND}")
    evidence_argv = [str(item) for item in argv]
    evidence_argv[0] = opencode_command
    for index, item in enumerate(evidence_argv[:-1]):
        if item == "--dir":
            evidence_argv[index + 1] = "."
            break
    return evidence_argv


def opencode_command_argv_matches(command_arg: Any, expected_command: str) -> bool:
    if not isinstance(command_arg, str) or not command_arg:
        return False
    if command_arg == expected_command:
        return True
    command_name = command_arg.replace("\\", "/").rsplit("/", 1)[-1]
    command_stem = command_name.rsplit(".", 1)[0]
    expected = expected_command.casefold()
    return command_name.casefold() == expected or command_stem.casefold() == expected


def opencode_models_argv_matches(value: Any, *, expected_command: str) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    return opencode_command_argv_matches(value[0], expected_command) and value[1] == "models"


def require_opencode_string_argv(
    value: Any,
    *,
    label: str,
    report_path: Path,
    repo_root: Path,
) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise SystemExit(
            f"{label} must be a non-empty string list: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    for argument in value:
        if LOCAL_ABSOLUTE_PATH_TEXT.search(argument):
            raise SystemExit(
                f"{label} must be portable and must not contain local absolute paths: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
    return value


def validate_opencode_run_argv_binding(
    value: Any,
    *,
    label: str,
    launch_policy: dict[str, Any],
    report_path: Path,
    repo_root: Path,
) -> list[str]:
    argv = require_opencode_string_argv(value, label=label, report_path=report_path, repo_root=repo_root)
    if len(argv) < 3 or not opencode_command_argv_matches(argv[0], launch_policy["opencode_command"]) or argv[1] != "run":
        raise SystemExit(
            f"{label} must run opencode run: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    flags: dict[str, str] = {}
    bool_flags: set[str] = set()
    prompt: list[str] = []
    index = 2
    while index < len(argv):
        item = argv[index]
        if not item.startswith("--"):
            prompt = argv[index:]
            break
        if item == "--dangerously-skip-permissions":
            if item in bool_flags:
                raise SystemExit(
                    f"{label} duplicate {item}: "
                    f"{repo_relative(report_path, repo_root=repo_root)}"
                )
            bool_flags.add(item)
            index += 1
            continue
        if item in flags:
            raise SystemExit(
                f"{label} duplicate {item}: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        if index + 1 >= len(argv) or argv[index + 1].startswith("--"):
            raise SystemExit(
                f"{label} {item} must have a value: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        flags[item] = argv[index + 1]
        index += 2
    if len(prompt) != 1 or not prompt[0].strip():
        raise SystemExit(
            f"{label} prompt must be the final non-empty argv item: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    required_flags = {"--dir", "--format", "--variant", "--model"}
    missing = sorted(required_flags - flags.keys())
    if missing:
        raise SystemExit(
            f"{label} missing {' '.join(missing)}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    allowed_flags = set(required_flags)
    if launch_policy.get("opencode_agent") is not None:
        allowed_flags.add("--agent")
    unexpected_flags = sorted(set(flags) - allowed_flags)
    if unexpected_flags:
        raise SystemExit(
            f"{label} has unexpected flags: {' '.join(unexpected_flags)}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--dir"] != ".":
        raise SystemExit(
            f"{label} --dir must be portable repo root .: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--format"] != "json":
        raise SystemExit(
            f"{label} --format must be json: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--variant"] != launch_policy["opencode_variant"]:
        raise SystemExit(
            f"{label} --variant must be {launch_policy['opencode_variant']}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if flags["--model"] != launch_policy["opencode_model"]:
        raise SystemExit(
            f"{label} --model must be {launch_policy['opencode_model']}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    expected_agent = launch_policy.get("opencode_agent")
    if expected_agent is None and "--agent" in flags:
        raise SystemExit(
            f"{label} --agent must be absent: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    if expected_agent is not None and flags.get("--agent") != expected_agent:
        raise SystemExit(
            f"{label} --agent must be {expected_agent}: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    skip_permissions_present = "--dangerously-skip-permissions" in bool_flags
    if skip_permissions_present != bool(launch_policy.get("opencode_skip_permissions")):
        raise SystemExit(
            f"{label} --dangerously-skip-permissions must match launch_policy: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    return argv


def validate_opencode_model_probe_log_hashes(
    model_availability: dict[str, Any],
    *,
    repo_root: Path,
    report_path: Path,
) -> None:
    logs = model_availability.get("logs")
    if not isinstance(logs, dict):
        raise SystemExit(
            "opencode preflight model availability logs are missing: "
            f"{repo_relative(report_path, repo_root=repo_root)}"
        )
    for stream in ("stdout", "stderr"):
        log_path_text = logs.get(stream)
        if not isinstance(log_path_text, str) or not log_path_text:
            raise SystemExit(
                f"opencode preflight model availability {stream} log is missing: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        log_path = repo_path(Path(log_path_text), repo_root=repo_root)
        if not log_path.is_file():
            raise SystemExit(
                f"opencode preflight model availability {stream} log does not exist: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        expected_sha256 = model_availability.get(f"{stream}_sha256")
        log_text = log_path.read_text(encoding="utf-8")
        actual_sha256 = sha256_text(log_text)
        if expected_sha256 != actual_sha256:
            raise SystemExit(
                f"opencode preflight model availability {stream} hash mismatch: "
                f"{repo_relative(report_path, repo_root=repo_root)}"
            )
        if stream == "stdout":
            required_model = str(model_availability.get("required_model", ""))
            if not opencode_models_output_mentions_required_model(log_text, required_model):
                raise SystemExit(
                    f"opencode preflight model availability stdout missing {required_model}: "
                    f"{repo_relative(report_path, repo_root=repo_root)}"
                )


def opencode_model_id_matches_required(model_id: str, required_model: str) -> bool:
    candidate = model_id.strip().strip("`'\"*,")
    if candidate == required_model:
        return True
    if "/" in candidate:
        return candidate.rsplit("/", 1)[1] == required_model
    return False


def opencode_models_output_mentions_required_model(stdout: str, required_model: str) -> bool:
    for line in stdout.splitlines():
        for token in re.split(r"\s+", line.strip()):
            if token and opencode_model_id_matches_required(token, required_model):
                return True
    return False


def opencode_models_output_sample(stdout: str, *, limit: int = 40) -> list[str]:
    sample: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        sample.append(stripped[:240])
        if len(sample) >= limit:
            break
    return sample


def run_opencode_model_availability_probe(
    *,
    opencode_command: str,
    opencode_model: str | None,
    logs_dir: Path,
    opencode_process_env: dict[str, str],
    timeout_seconds: int,
    command_runner: Any,
    repo_root: Path,
    opencode_allow_non_competition_model: bool = False,
) -> dict[str, Any]:
    if opencode_model is None:
        opencode_model = COMPETITION_OPENCODE_MODEL
    if opencode_model != COMPETITION_OPENCODE_MODEL and not opencode_allow_non_competition_model:
        raise SystemExit(f"opencode_model must be {COMPETITION_OPENCODE_MODEL}")
    argv = build_opencode_models_argv(opencode_command=opencode_command)
    report_argv = portable_opencode_evidence_argv(
        argv,
        opencode_command=opencode_command,
    )
    started = time.monotonic()
    try:
        if command_runner is subprocess.run:
            completed = run_captured_process_with_timeout(
                argv,
                cwd=repo_root,
                timeout_seconds=timeout_seconds,
                env=opencode_process_env,
            )
        else:
            completed = command_runner(
                argv,
                cwd=repo_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=timeout_seconds,
                env=opencode_process_env,
            )
    except subprocess.TimeoutExpired as exc:
        completed = completed_process_from_timeout(argv, exc, timeout_seconds)
    except OSError as exc:
        completed = subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}\n",
        )
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    stdout_path = logs_dir / "opencode-models.stdout.log"
    stderr_path = logs_dir / "opencode-models.stderr.log"
    atomic_write_text(stdout_path, stdout)
    atomic_write_text(stderr_path, stderr)
    returncode = int(completed.returncode)
    timed_out = completed_process_timed_out(completed)
    model_listed = returncode == 0 and opencode_models_output_mentions_required_model(stdout, opencode_model)
    if model_listed:
        status = "available"
        failure_reason = ""
    elif returncode == 0:
        status = "unavailable"
        failure_reason = "required_model_not_listed"
    elif timed_out:
        status = "probe_failed"
        failure_reason = "models_command_timeout"
    else:
        status = "probe_failed"
        failure_reason = "models_command_failed"
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "failure_reason": failure_reason,
        "opencode_command": opencode_command,
        "required_model": opencode_model,
        "argv": report_argv,
        "process_returncode": returncode,
        "elapsed_seconds": int(time.monotonic() - started),
        "model_listed": model_listed,
        "listed_model_sample": opencode_models_output_sample(stdout),
        "stdout_sha256": sha256_text(stdout),
        "stderr_sha256": sha256_text(stderr),
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
        "evidence_boundary": "model availability probe is a launch gate only; it is not semantic acceptance",
    }
    if timed_out:
        result["timed_out"] = True
        result["timeout_seconds"] = timeout_seconds
    return result


def opencode_contract_not_observed(
    *,
    worker_command: list[str],
    summary_path: Path,
    reason: str,
    repo_root: Path,
) -> dict[str, Any]:
    expected_worker_command_line = shell_command_line(worker_command)
    return {
        "expected_worker_command_line": expected_worker_command_line,
        "expected_summary_path": repo_relative(summary_path, repo_root=repo_root),
        "expected_worker_command_sha256": sha256_text(expected_worker_command_line),
        "executed_shell_command_count": 0,
        "executed_shell_commands": [],
        "first_tool_name": "",
        "first_shell_command": "",
        "first_shell_tool_name": "",
        "first_shell_workdir_status": "not_observed",
        "expected_workdir_status": "repo_root",
        "first_shell_command_matches_worker_command": False,
        "first_shell_workdir_matches_repo_root": False,
        "tools_before_first_shell": [],
        "contract_failure_reason": reason,
        "worker_command_seen": False,
        "summary_exists": summary_path.exists(),
        "status": "not-observed",
    }


def write_opencode_not_launched_session_evidence(
    *,
    evidence_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    root_cause_key: str,
    opencode_runtime_env: dict[str, Any],
    repo_root: Path,
) -> dict[str, str]:
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "not-launched",
        "root_cause_key": root_cause_key,
        "process_returncode": None,
        "stdout_path": repo_relative(stdout_path, repo_root=repo_root),
        "stderr_path": repo_relative(stderr_path, repo_root=repo_root),
        "opencode_runtime_env": opencode_runtime_env,
        "evidence_boundary": "OpenCode run was not launched because a preflight launch gate failed",
    }
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def portable_python_script_argv(script: str, *args: str) -> list[str]:
    return [*portable_python_command_argv(), "-B", script, *args]


def portable_python_module_argv(module: str, *args: str) -> list[str]:
    return [PORTABLE_PYTHON_COMMAND, "-B", "-m", module, *args]


def portable_python_command_argv() -> list[str]:
    global _RESOLVED_PYTHON_COMMAND
    override = os.environ.get(PYTHON_COMMAND_OVERRIDE_ENV)
    if override:
        return shlex.split(override, posix=os.name != "nt")
    if _RESOLVED_PYTHON_COMMAND is not None:
        return list(_RESOLVED_PYTHON_COMMAND)
    candidates: list[list[str]] = [[PORTABLE_PYTHON_COMMAND], ["python"]]
    if os.name == "nt":
        candidates.append(["py", "-3"])
    for candidate in candidates:
        if python_command_is_runnable(candidate):
            _RESOLVED_PYTHON_COMMAND = candidate
            return list(candidate)
    _RESOLVED_PYTHON_COMMAND = [PORTABLE_PYTHON_COMMAND]
    return list(_RESOLVED_PYTHON_COMMAND)


def python_command_is_runnable(candidate: list[str]) -> bool:
    try:
        completed = subprocess.run(
            [*candidate, "-B", "-c", "import sys"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return int(completed.returncode) == 0


def shell_command_line(argv: list[str]) -> str:
    return shlex.join([str(item) for item in argv])


def build_opencode_run_argv(
    *,
    opencode_command: str,
    opencode_model: str | None,
    opencode_agent: str | None,
    opencode_variant: str,
    opencode_skip_permissions: bool,
    worker_command: list[str],
    request_path: Path,
    summary_path: Path,
    repo_root: Path,
    handoff_contract_path: Path | None = None,
    opencode_allow_non_competition_model: bool = False,
) -> list[str]:
    launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    command_line = shell_command_line(worker_command)
    prompt_lines = [
        "Execute this assigned C-to-Rust worker exactly once.",
        "Use the shell/bash tool to run exactly the Command line string below.",
        "The first shell/bash/powershell/cmd tool call must be exactly the Command line string.",
        "Do not run init-run, assign-slice, retry-worker, or any other substitute harness command.",
        "Do not inspect an existing summary before running the command.",
        "The harness has already removed any stale expected summary before launching OpenCode.",
        "Run the repo-local deterministic command below, then stop.",
        "Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.",
        "Do not explore files, spawn subagents, or infer a different slice before executing the command.",
        "Do not run substitute diagnostics instead of the command.",
        "Do not treat chat output as evidence; the required artifact is the competition-run-summary JSON.",
        f"Command: {json.dumps(worker_command)}",
        f"Command line: {command_line}",
        f"Request: {repo_relative(request_path, repo_root=repo_root)}",
        f"Expected summary: {repo_relative(summary_path, repo_root=repo_root)}",
    ]
    if handoff_contract_path is not None:
        prompt_lines.extend(
            [
                "Handoff contract is audit metadata; do not inspect it before the first command.",
                f"Handoff contract: {repo_relative(handoff_contract_path, repo_root=repo_root)}",
            ]
        )
    prompt = build_opencode_prompt(prompt_lines)
    resolved_opencode_command = resolve_subprocess_command(launch_policy["opencode_command"])
    argv = [
        resolved_opencode_command,
        "run",
        "--dir",
        str(repo_root),
        "--format",
        "json",
        "--variant",
        launch_policy["opencode_variant"],
    ]
    argv.extend(["--model", launch_policy["opencode_model"]])
    argv.extend(["--agent", launch_policy["opencode_agent"]])
    if launch_policy["opencode_skip_permissions"]:
        argv.append("--dangerously-skip-permissions")
    argv.append(prompt)
    return argv


def build_opencode_preflight_argv(
    *,
    opencode_command: str,
    opencode_model: str | None,
    opencode_agent: str | None,
    opencode_variant: str,
    opencode_skip_permissions: bool,
    marker_command: list[str],
    marker_path: Path,
    contract_path: Path,
    repo_root: Path,
    opencode_allow_non_competition_model: bool = False,
) -> list[str]:
    launch_policy = opencode_launch_policy(
        opencode_command=opencode_command,
        opencode_model=opencode_model,
        opencode_agent=opencode_agent,
        opencode_variant=opencode_variant,
        opencode_skip_permissions=opencode_skip_permissions,
        opencode_allow_non_competition_model=opencode_allow_non_competition_model,
    )
    command_line = shell_command_line(marker_command)
    prompt = build_opencode_prompt(
        [
            "Execute this OpenCode preflight command exactly once.",
            "Use the shell/bash tool to run exactly the Command line string below.",
            "The first shell/bash/powershell/cmd tool call must be exactly the Command line string.",
            "Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.",
            "Do not inspect repository files or infer a different task before executing the command.",
            "Do not run init-run, assign-slice, run-worker, retry-worker, or any substitute harness command.",
            "After the command exits, stop immediately; do not run a second shell/read/list command.",
            "The required artifact is the preflight marker JSON, not chat output.",
            f"Command: {json.dumps(marker_command)}",
            f"Command line: {command_line}",
            f"Expected marker: {repo_relative(marker_path, repo_root=repo_root)}",
            "Handoff contract is audit metadata; do not inspect it before the first command.",
            f"Handoff contract: {repo_relative(contract_path, repo_root=repo_root)}",
        ]
    )
    resolved_opencode_command = resolve_subprocess_command(launch_policy["opencode_command"])
    argv = [
        resolved_opencode_command,
        "run",
        "--dir",
        str(repo_root),
        "--format",
        "json",
        "--variant",
        launch_policy["opencode_variant"],
    ]
    argv.extend(["--model", launch_policy["opencode_model"]])
    argv.extend(["--agent", launch_policy["opencode_agent"]])
    if launch_policy["opencode_skip_permissions"]:
        argv.append("--dangerously-skip-permissions")
    argv.append(prompt)
    return argv


def resolve_subprocess_command(command: str) -> str:
    if not command:
        raise SystemExit("opencode command must not be empty")
    if "/" in command or "\\" in command or Path(command).is_absolute():
        return command
    return shutil.which(command) or command


def build_opencode_prompt(prompt_lines: list[str]) -> str:
    return " ".join(line.strip() for line in prompt_lines if line.strip())


def verify_opencode_contract_execution(
    *,
    session_evidence: dict[str, Any],
    worker_command: list[str],
    summary_path: Path,
    repo_root: Path,
    allow_post_contract_artifact_inspection: bool = False,
) -> dict[str, Any]:
    expected_worker_command_line = shell_command_line(worker_command)
    tool_trace = extract_opencode_tool_trace(session_evidence)
    executed_shell_commands = extract_opencode_shell_commands(session_evidence)
    exact_worker_command_seen = any(
        command_matches_for_contract(command, expected_worker_command_line) for command in executed_shell_commands
    )
    first_shell_command = executed_shell_commands[0] if executed_shell_commands else ""
    first_tool_name = str(tool_trace[0]["tool"]) if tool_trace else ""
    first_shell_index = next(
        (index for index, item in enumerate(tool_trace) if item.get("is_shell_command")),
        None,
    )
    first_shell_tool_name = str(tool_trace[first_shell_index]["tool"]) if first_shell_index is not None else ""
    first_shell_workdir = (
        str(tool_trace[first_shell_index].get("workdir", "")) if first_shell_index is not None else ""
    )
    tools_before_first_shell = [
        str(item["tool"]) for item in tool_trace[:first_shell_index]
    ] if first_shell_index is not None else [str(item["tool"]) for item in tool_trace[:20]]
    first_shell_command_matches_worker_command = (
        bool(first_shell_command) and command_matches_for_contract(first_shell_command, expected_worker_command_line)
    )
    summary_exists = summary_path.exists()
    workdir_reported = bool(first_shell_workdir)
    workdir_matches_repo_root = opencode_workdir_matches_repo_root(first_shell_workdir, repo_root=repo_root)
    workdir_inferred_from_expected_artifact = (
        not workdir_reported
        and first_shell_command_matches_worker_command
        and summary_exists
    )
    workdir_satisfies_contract = workdir_matches_repo_root or workdir_inferred_from_expected_artifact
    post_contract_shell_commands = executed_shell_commands[1:] if first_shell_command_matches_worker_command else []
    post_contract_artifact_inspection_only = (
        allow_post_contract_artifact_inspection
        and bool(post_contract_shell_commands)
        and summary_exists
        and all(
            is_post_contract_artifact_inspection_command(
                command,
                artifact_path=summary_path,
                repo_root=repo_root,
            )
            for command in post_contract_shell_commands
        )
    )
    shell_count_satisfies_contract = len(executed_shell_commands) == 1 or post_contract_artifact_inspection_only
    status = "not-observed"
    if executed_shell_commands:
        status = (
            "executed"
            if (
                first_shell_command_matches_worker_command
                and workdir_satisfies_contract
                and not tools_before_first_shell
                and shell_count_satisfies_contract
            )
            else "not-executed"
        )
    contract_failure_reason = ""
    if status == "not-observed":
        contract_failure_reason = "no_shell_command_observed"
    elif status == "not-executed":
        if tools_before_first_shell:
            contract_failure_reason = "tool_before_first_shell_command"
        elif not workdir_satisfies_contract:
            contract_failure_reason = "opencode_workdir_mismatch"
        elif len(executed_shell_commands) > 1 and first_shell_command_matches_worker_command:
            contract_failure_reason = (
                "extra_shell_command_after_contract"
                if not allow_post_contract_artifact_inspection
                else "non_artifact_inspection_shell_command_after_contract"
            )
        else:
            contract_failure_reason = (
                "first_shell_command_mismatch_worker_command_seen_later"
                if exact_worker_command_seen
                else "first_shell_command_mismatch"
            )
    return {
        "expected_worker_command_line": expected_worker_command_line,
        "expected_summary_path": repo_relative(summary_path, repo_root=repo_root),
        "expected_worker_command_sha256": sha256_text(expected_worker_command_line),
        "executed_shell_command_count": len(executed_shell_commands),
        "executed_shell_commands": executed_shell_commands[:20],
        "post_contract_shell_command_count": len(post_contract_shell_commands),
        "post_contract_shell_commands": post_contract_shell_commands[:20],
        "allow_post_contract_artifact_inspection": allow_post_contract_artifact_inspection,
        "post_contract_artifact_inspection_only": post_contract_artifact_inspection_only,
        "first_tool_name": first_tool_name,
        "first_shell_command": first_shell_command,
        "first_shell_tool_name": first_shell_tool_name,
        "first_shell_workdir_status": (
            "repo_root"
            if workdir_matches_repo_root
            else "repo_root_inferred_from_expected_artifact"
            if workdir_inferred_from_expected_artifact
            else "non_repo_root"
        ),
        "expected_workdir_status": "repo_root",
        "first_shell_command_matches_worker_command": first_shell_command_matches_worker_command,
        "first_shell_workdir_matches_repo_root": workdir_satisfies_contract,
        "first_shell_workdir_reported": workdir_reported,
        "first_shell_workdir_inferred_from_expected_artifact": workdir_inferred_from_expected_artifact,
        "tools_before_first_shell": tools_before_first_shell[:20],
        "contract_failure_reason": contract_failure_reason,
        "worker_command_seen": exact_worker_command_seen,
        "summary_exists": summary_exists,
        "status": status,
    }


def is_post_contract_artifact_inspection_command(
    command: str,
    *,
    artifact_path: Path,
    repo_root: Path,
) -> bool:
    compact = " ".join(command.strip().split())
    lower = compact.lower()
    if any(token in lower for token in (";", "&&", "||", ">", " set-content", " remove-item", " del ", " rm ")):
        return False
    rel_posix = repo_relative(artifact_path, repo_root=repo_root)
    rel_windows = rel_posix.replace("/", "\\")
    artifact_abs = str(artifact_path)
    normalized_command = compact.replace("\\", "/")
    normalized_candidates = {
        rel_posix,
        rel_windows.replace("\\", "/"),
        artifact_abs.replace("\\", "/"),
    }
    if not any(candidate and candidate in normalized_command for candidate in normalized_candidates):
        return False
    allowed_prefixes = (
        "get-item -literalpath ",
        "test-path -literalpath ",
        "get-content -literalpath ",
        "dir ",
        "ls ",
        "type ",
        "cat ",
    )
    return lower.startswith(allowed_prefixes)


def extract_opencode_tool_trace(session_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    events = opencode_session_events(session_evidence)
    tools: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        tool = str(part.get("tool", "")).lower().strip()
        if not tool:
            continue
        command = ""
        state = part.get("state")
        if isinstance(state, dict):
            tool_input = state.get("input")
            if isinstance(tool_input, dict):
                raw_command = tool_input.get("command") or tool_input.get("cmd")
                if isinstance(raw_command, str):
                    command = raw_command.strip()
                raw_workdir = tool_input.get("workdir") or tool_input.get("cwd")
                workdir = raw_workdir.strip() if isinstance(raw_workdir, str) else ""
            else:
                workdir = ""
        else:
            workdir = ""
        tools.append(
            {
                "tool": tool,
                "command": command,
                "workdir": workdir,
                "is_shell_command": tool in {"bash", "shell", "cmd", "powershell"} and bool(command),
            }
        )
    return tools


def opencode_workdir_matches_repo_root(workdir: str, *, repo_root: Path) -> bool:
    if not workdir:
        return False
    try:
        observed = normalize_windows_extended_path(Path(workdir).resolve())
        expected = normalize_windows_extended_path(repo_root.resolve())
    except OSError:
        return False
    return observed == expected


def extract_opencode_shell_commands(session_evidence: dict[str, Any]) -> list[str]:
    events = opencode_session_events(session_evidence)
    commands: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        part = event.get("part")
        if not isinstance(part, dict):
            continue
        tool = str(part.get("tool", "")).lower()
        if tool not in {"bash", "shell", "cmd", "powershell"}:
            continue
        state = part.get("state")
        if not isinstance(state, dict):
            continue
        tool_input = state.get("input")
        if not isinstance(tool_input, dict):
            continue
        command = tool_input.get("command") or tool_input.get("cmd")
        if isinstance(command, str) and command.strip():
            commands.append(command.strip())
    return commands


def opencode_session_events(session_evidence: dict[str, Any]) -> list[Any]:
    events = session_evidence.get("session_events")
    if isinstance(events, list):
        return events
    session = session_evidence.get("session")
    if isinstance(session, list):
        return session
    if isinstance(session, dict):
        if "part" in session or "type" in session:
            return [session]
        events = session.get("events")
        if isinstance(events, list):
            return events
    return []


def parse_opencode_stdout_session(stdout: str) -> dict[str, Any]:
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as error:
        events = []
        jsonl_error = None
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as line_error:
                jsonl_error = line_error
                break
        if events and jsonl_error is None:
            return {
                "parsed": True,
                "format": "jsonl",
                "session_events": events,
            }
        return {
            "parsed": False,
            "parse_error": str(jsonl_error or error),
            "raw_output": stdout[:20000],
        }
    return {
        "parsed": True,
        "format": "json",
        "session": parsed,
    }


def normalize_command_for_contract(command: str) -> str:
    return " ".join(command.strip().split())


def command_matches_for_contract(observed_command: str, expected_command: str) -> bool:
    if normalize_command_for_contract(observed_command) == normalize_command_for_contract(expected_command):
        return True
    observed_argv = shell_argv_for_contract(observed_command)
    expected_argv = shell_argv_for_contract(expected_command)
    return bool(observed_argv) and observed_argv == expected_argv


def shell_argv_for_contract(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return []


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_blocked_worker_summary(
    *,
    run_id: str,
    proof_class: str,
    worker_id: str,
    request: dict[str, Any],
    root_cause_key: str,
    process_returncode: int,
    exit_code: int,
    elapsed_seconds: int,
    summary_path: Path,
    metrics_path: Path,
    opencode_contract_verification: dict[str, Any] | None,
    handoff_contract: dict[str, Any] | None,
    opencode_session_evidence: dict[str, Any] | None,
    repo_root: Path,
) -> None:
    target_id = str(request.get("target_id", "unknown"))
    slice_id = str(request.get("slice_id", "unknown"))
    unit_status = {
        "unit_id": f"{target_id}/{slice_id}",
        "source": "opencode-worker",
        "status": "blocked",
        "compiled": False,
        "semantic_pass": False,
        "refused": False,
        "blocked": True,
        "failed": False,
        "root_cause_key": root_cause_key,
        "process_returncode": process_returncode,
        "exit_code": exit_code,
        "worker_id": worker_id,
    }
    if opencode_contract_verification is not None:
        unit_status["opencode_contract_verification"] = opencode_contract_verification
    if handoff_contract is not None:
        unit_status["handoff_contract"] = handoff_contract
    if opencode_session_evidence is not None:
        unit_status["opencode_session_evidence"] = opencode_session_evidence

    metrics = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "proof_class": proof_class,
        "units_total": 1,
        "units_converged": 0,
        "units_baseline_only": 0,
        "unsafe_reduction": {
            "status": "not_measured",
            "baseline_total_unsafe": None,
            "current_total_unsafe": None,
            "reduced_by": None,
            "ratio": 0.0,
        },
        "avg_repair_rounds": 0.0,
        "auto_recovery_rate": 0.0,
        "human_interventions": 0,
        "always_compiles": False,
        "always_equivalent": False,
        "fail_closed_count": 1,
        "root_cause_counts": {root_cause_key: 1},
        "wall_clock_seconds": max(0, elapsed_seconds),
        "llm_calls": 1,
        "per_unit_statuses": [unit_status],
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(metrics_path, metrics)

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "proof_class": proof_class,
        "profile_id": PROFILE_ID,
        "profile_sha256": sha256_file(repo_root / "config" / "competition-env" / "environment.json"),
        "clang_source": "missing",
        "cargo_mirror_activation": {
            "method": "CARGO_HOME",
            "path": "config/competition-env/cargo",
            "config_file": "config/competition-env/cargo/config.toml",
        },
        "elapsed_seconds": max(0, elapsed_seconds),
        "translator_version": "opencode-agent-harness",
        "slices": {
            "attempted": 1,
            "typed_ir_generated": 0,
            "compiled": 0,
            "semantic_pass": 0,
            "refused": 0,
            "blocked": 1,
            "failed": 0,
        },
        "unsafe_budget": {
            "status": "passed",
            "total_first_party_non_test_unsafe": 0,
            "ratio": 0.0,
        },
        "workflow_metrics": {
            "path": metrics_path.name,
            "sha256": sha256_file(metrics_path),
        },
        "artifact_roots": [
            "target/competition-out/evidence",
            "target/competition-out/summary",
            "target/competition-out/logs",
        ],
        "final_gate": {
            "status": "blocked",
            "validator": "opencode_agent_harness.py run-worker --mode opencode",
        },
    }
    atomic_write_json(summary_path, summary)


def write_opencode_handoff_contract(
    *,
    run_id: str,
    worker_id: str,
    attempt_number: int,
    request_path: Path,
    summary_path: Path,
    contract_path: Path,
    worker_command: list[str],
    opencode_argv: list[str],
    launch_policy: dict[str, Any],
    repo_root: Path,
    opencode_runtime_env: dict[str, Any] | None = None,
    assignment_request_path: Path | None = None,
) -> dict[str, str]:
    if not opencode_argv:
        raise SystemExit("opencode argv must not be empty")
    contract = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt": attempt_number,
        "runner_kind": "opencode-run",
        "request_path": repo_relative(request_path, repo_root=repo_root),
        "expected_summary_path": repo_relative(summary_path, repo_root=repo_root),
        "worker_command": worker_command,
        "worker_command_line": shell_command_line(worker_command),
        "worker_command_sha256": sha256_text(shell_command_line(worker_command)),
        "opencode_argv": opencode_argv,
        "opencode_command_line": shell_command_line(opencode_argv),
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "prompt": str(opencode_argv[-1]),
        "evidence_boundary": "chat output is diagnostic only; semantic acceptance requires the expected summary and validators",
    }
    if opencode_runtime_env is not None:
        contract["opencode_runtime_env"] = opencode_runtime_env
    if assignment_request_path is not None:
        contract["assignment_request_path"] = repo_relative(assignment_request_path, repo_root=repo_root)
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(contract_path, contract)
    return {"path": repo_relative(contract_path, repo_root=repo_root), "sha256": sha256_file(contract_path)}


def write_opencode_preflight_contract(
    *,
    run_id: str,
    contract_path: Path,
    marker_path: Path,
    marker_command: list[str],
    opencode_argv: list[str],
    launch_policy: dict[str, Any],
    repo_root: Path,
    opencode_runtime_env: dict[str, Any] | None = None,
) -> dict[str, str]:
    if not opencode_argv:
        raise SystemExit("opencode argv must not be empty")
    contract = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "runner_kind": "opencode-preflight",
        "expected_marker_path": repo_relative(marker_path, repo_root=repo_root),
        "worker_command": marker_command,
        "worker_command_line": shell_command_line(marker_command),
        "worker_command_sha256": sha256_text(shell_command_line(marker_command)),
        "opencode_argv": opencode_argv,
        "opencode_command_line": shell_command_line(opencode_argv),
        "launch_policy": launch_policy,
        "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        "prompt": str(opencode_argv[-1]),
        "evidence_boundary": "preflight proves exact-command compliance only; semantic acceptance requires worker summary and validators",
    }
    if opencode_runtime_env is not None:
        contract["opencode_runtime_env"] = opencode_runtime_env
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(contract_path, contract)
    return {"path": repo_relative(contract_path, repo_root=repo_root), "sha256": sha256_file(contract_path)}


def write_opencode_session_evidence(
    *,
    completed: subprocess.CompletedProcess[str],
    evidence_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    repo_root: Path,
    opencode_runtime_env: dict[str, Any] | None = None,
) -> dict[str, str]:
    stdout = completed.stdout or ""
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "process_returncode": int(completed.returncode),
        "stdout_path": repo_relative(stdout_path, repo_root=repo_root),
        "stderr_path": repo_relative(stderr_path, repo_root=repo_root),
        "stdout_sha256": sha256_file(stdout_path),
        "stderr_sha256": sha256_file(stderr_path),
    }
    if opencode_runtime_env is not None:
        evidence["opencode_runtime_env"] = opencode_runtime_env
    evidence.update(parse_opencode_stdout_session(stdout))
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(evidence_path, evidence)
    return {"path": repo_relative(evidence_path, repo_root=repo_root), "sha256": sha256_file(evidence_path)}


def write_merge_plan(
    *,
    db_path: Path,
    run_id: str,
    out_root: Path,
    proof_class: str,
    worker_summary_paths: list[str] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
    if worker_summary_paths is None:
        with closing(connect(db_path)) as connection:
            ensure_schema(connection)
            rows = connection.execute(
                """
                select repo_rel_path from artifacts
                where run_id=? and kind='competition-run-summary'
                order by repo_rel_path
                """,
                (run_id,),
            ).fetchall()
        summaries = [row[0] for row in rows]
    else:
        summaries = [
            repo_relative(repo_path(Path(summary), repo_root=repo_root), repo_root=repo_root)
            for summary in worker_summary_paths
        ]
    argv = portable_python_script_argv("validation/tools/run_competition.py")
    for summary in summaries:
        argv.extend(["--worker-summary", summary])
    argv.extend(["--out-root", repo_relative(out_root, repo_root=repo_root), "--proof-class", proof_class, "--run-id", run_id])
    merge_plan = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "path": repo_relative(out_root / "harness" / "merge-plan.json", repo_root=repo_root),
        "worker_summaries": summaries,
        "argv": argv,
        "validator": "validation/tools/validate_competition_run_summary.py",
    }
    merge_path = out_root / "harness" / "merge-plan.json"
    merge_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(merge_path, merge_plan)
    return merge_plan


def finalize_run(
    *,
    db_path: Path,
    run_id: str,
    status: str,
    summary_path: Path,
    final_gate_status: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    summary_path = repo_path(summary_path, repo_root=repo_root)
    summary_rel = repo_relative(summary_path, repo_root=repo_root)
    summary_hash = sha256_file(summary_path)
    now = now_text()
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        cursor = connection.execute(
            """
            update runs
            set status=?, ended_at=?, summary_path=?, summary_sha256=?,
                final_gate_status=coalesce(?, final_gate_status)
            where run_id=?
            """,
            (status, now, summary_rel, summary_hash, final_gate_status, run_id),
        )
        if cursor.rowcount == 0:
            raise SystemExit(f"unknown run_id: {run_id}")
        record_event(
            connection,
            run_id=run_id,
            event_type="run_finalized",
            payload={
                "status": status,
                "final_gate_status": final_gate_status,
                "summary_path": summary_rel,
                "summary_sha256": summary_hash,
            },
        )
        connection.commit()
    return {
        "status": "finalized",
        "run_id": run_id,
        "summary_path": summary_rel,
        "summary_sha256": summary_hash,
    }


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        pragma journal_mode = wal;
        create table if not exists profiles(
          profile_id text primary key,
          profile_path text not null,
          profile_sha256 text not null,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists runs(
          run_id text primary key,
          out_root text not null,
          proof_class text not null,
          profile_id text not null,
          profile_sha256 text not null,
          schema_version integer not null,
          status text not null,
          started_at text not null,
          ended_at text,
          final_gate_status text,
          summary_path text,
          summary_sha256 text,
          payload_json text not null
        );
        create table if not exists agents(
          agent_id text primary key,
          run_id text not null,
          runtime text not null,
          worker_name text not null,
          role text not null,
          isolated_out_root text not null,
          status text not null,
          created_at text not null
        );
        create table if not exists agent_tasks(
          task_id text primary key,
          run_id text not null,
          agent_id text not null,
          target_id text not null,
          slice_id text not null,
          phase text not null,
          status text not null,
          attempt integer not null,
          allowed_paths_json text not null,
          started_at text,
          ended_at text,
          error_key text
        );
        create table if not exists slices(
          target_id text not null,
          slice_id text not null,
          source_repo_root_rel text not null,
          source_file_rel text not null,
          function_name text not null,
          source_commit text not null,
          slice_spec_path text,
          slice_spec_sha256 text,
          fixture_path text,
          fixture_hash text,
          payload_json text not null,
          primary key(target_id, slice_id)
        );
        create table if not exists candidates(
          candidate_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          source_kind text not null,
          semantic_pass integer not null default 0,
          artifact_path text,
          artifact_sha256 text,
          payload_json text not null
        );
        create table if not exists gates(
          gate_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          gate_name text not null,
          status text not null,
          is_blocking integer not null,
          evidence_path text,
          evidence_sha256 text,
          payload_json text not null
        );
        create table if not exists artifacts(
          artifact_id integer primary key autoincrement,
          run_id text not null,
          agent_id text,
          target_id text,
          slice_id text,
          kind text not null,
          repo_rel_path text not null unique,
          sha256 text not null,
          status text not null,
          semantic_role text not null,
          schema_name text,
          payload_status text,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists artifact_links(
          link_id integer primary key autoincrement,
          run_id text not null,
          from_artifact_path text not null,
          to_artifact_path text not null,
          relation text not null,
          payload_json text not null
        );
        create table if not exists events(
          event_id integer primary key autoincrement,
          run_id text not null,
          event_type text not null,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists leases(
          resource_key text primary key,
          run_id text not null,
          lease_owner text not null,
          status text not null,
          expires_at text not null,
          heartbeat_at text not null,
          fencing_token integer not null
        );
        create table if not exists context_packs(
          context_pack_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          depth integer not null,
          max_tokens integer not null,
          artifact_path text not null,
          artifact_sha256 text not null,
          payload_json text not null
        );
        create table if not exists repair_hints(
          hint_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          root_cause_key text not null,
          status text not null,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists metrics(
          metric_id integer primary key autoincrement,
          run_id text not null,
          metric_name text not null,
          metric_value real not null,
          payload_json text not null,
          created_at text not null
        );
        """
    )


def assignment_file_path(db_path: Path, worker_id: str) -> Path:
    out_root = db_path.parent.parent
    return out_root / "harness" / "assignments" / f"{worker_id}.json"


def run_proof_class(db_path: Path, run_id: str) -> str:
    connection = connect(db_path)
    try:
        row = connection.execute("select proof_class from runs where run_id=?", (run_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise SystemExit(f"unknown run_id: {run_id}")
    return str(row[0])


def assigned_worker_out_root_rel(connection: sqlite3.Connection, *, run_id: str, worker_id: str) -> str:
    row = connection.execute(
        "select isolated_out_root from agents where run_id=? and agent_id=?",
        (run_id, worker_id),
    ).fetchone()
    if row is None:
        raise SystemExit(f"worker is not assigned in run {run_id}: {worker_id}")
    return str(row[0])


def assigned_worker_summary_path(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    worker_id: str,
    repo_root: Path,
) -> Path:
    out_root_rel = assigned_worker_out_root_rel(connection, run_id=run_id, worker_id=worker_id)
    return repo_path(Path(out_root_rel), repo_root=repo_root) / "summary" / "competition-run-summary.json"


def discover_top_level_function_names(text: str) -> list[str]:
    masked = mask_comments_and_strings(text)
    names: list[str] = []
    seen: set[str] = set()
    index = 0
    while index < len(masked):
        if masked[index] != "{":
            index += 1
            continue
        prefix = masked[:index].rstrip()
        if not prefix.endswith(")"):
            match_end = find_matching(masked, index, "{", "}")
            index = match_end + 1 if match_end is not None else index + 1
            continue
        close_paren = len(prefix) - 1
        open_paren = find_matching_reverse(masked, close_paren, "(", ")")
        if open_paren is None:
            index += 1
            continue
        name_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", masked[:open_paren].rstrip())
        if name_match is None:
            index += 1
            continue
        name = name_match.group(1)
        if name not in C_STATEMENT_KEYWORDS and name not in seen:
            names.append(name)
            seen.add(name)
        match_end = find_matching(masked, index, "{", "}")
        index = match_end + 1 if match_end is not None else index + 1
    return names


C_STATEMENT_KEYWORDS = {
    "do",
    "else",
    "for",
    "if",
    "switch",
    "while",
}


def find_matching_reverse(text: str, close_index: int, open_char: str, close_char: str) -> int | None:
    depth = 0
    for index in range(close_index, -1, -1):
        char = text[index]
        if char == close_char:
            depth += 1
        elif char == open_char:
            depth -= 1
            if depth == 0:
                return index
    return None


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=30)
    connection.execute("pragma foreign_keys = on")
    connection.execute("pragma busy_timeout = 30000")
    return connection


def record_event(connection: sqlite3.Connection, *, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
    connection.execute(
        "insert into events(run_id, event_type, payload_json, created_at) values (?, ?, ?, ?)",
        (run_id, event_type, json.dumps(payload, sort_keys=True), now_text()),
    )


def repo_path(path: Path, *, repo_root: Path = REPO_ROOT) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
    else:
        checked_relative_path(path_text(path))
        resolved = (repo_root / path).resolve()
    resolved = normalize_windows_extended_path(resolved)
    repo_resolved = normalize_windows_extended_path(repo_root.resolve())
    try:
        resolved.relative_to(repo_resolved)
    except ValueError as error:
        raise SystemExit(f"path must stay inside repository: {path}") from error
    return resolved


def normalize_windows_extended_path(path: Path) -> Path:
    text = str(path)
    if text.startswith("\\\\?\\"):
        return Path(text[4:])
    return path


def checked_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise SystemExit(f"path must be a non-empty POSIX relative path: {value}")
    if value.startswith("/") or value.startswith("~"):
        raise SystemExit(f"path must be relative to repository: {value}")
    if len(value) >= 2 and value[1] == ":":
        raise SystemExit(f"path must not contain a drive prefix: {value}")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise SystemExit(f"path must not escape repository: {value}")
    return path


def path_text(path: Path) -> str:
    return PurePosixPath(*path.parts).as_posix()


def slug_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    if not slug:
        raise SystemExit(f"cannot build id slug from empty value: {value!r}")
    return slug


def repo_relative(path: Path, *, repo_root: Path = REPO_ROOT) -> str:
    resolved = normalize_windows_extended_path(path.resolve())
    repo_resolved = normalize_windows_extended_path(repo_root.resolve())
    try:
        return resolved.relative_to(repo_resolved).as_posix()
    except ValueError as error:
        raise SystemExit(f"path must stay inside repository: {path}") from error


def sha256_file(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in LF_STABLE_TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            fd = None
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
