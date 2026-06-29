#!/usr/bin/env python3
"""OpenCode-only multi-agent harness ledger.

This module intentionally stays below the semantic validator. It records
worker assignments, leases, artifacts, and merge plans so OpenCode can resume
and audit parallel work, while correctness remains owned by on-disk evidence
and the existing validators.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path, PurePosixPath
import sqlite3
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "config" / "competition-env" / "environment.json"
DB_REL_PATH = Path("state") / "opencode-agent-harness.sqlite3"
SCHEMA_VERSION = 1
PROFILE_ID = "huawei-competition-ubuntu-24.04"


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
    assign_parser.add_argument("--source-file", required=True)
    assign_parser.add_argument("--function", required=True)
    assign_parser.add_argument("--source-commit", required=True)
    assign_parser.add_argument("--compiler-command-source")
    assign_parser.add_argument("--include-path", action="append", default=[])
    assign_parser.add_argument("--define", action="append", default=[])
    assign_parser.add_argument("--reuse-accepted-evidence", action="store_true")
    assign_parser.add_argument("--accepted-evidence-root")
    assign_parser.add_argument("--slice-spec")
    assign_parser.add_argument("--out-root", type=Path, required=True)
    assign_parser.add_argument("--lease-ttl-seconds", type=int, default=3600)

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
            source_file=args.source_file,
            function=args.function,
            source_commit=args.source_commit,
            compiler_command_source=args.compiler_command_source,
            include_paths=args.include_path,
            defines=args.define,
            reuse_accepted_evidence=args.reuse_accepted_evidence,
            accepted_evidence_root=args.accepted_evidence_root,
            slice_spec=args.slice_spec,
            out_root=args.out_root,
            lease_ttl_seconds=args.lease_ttl_seconds,
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
    return int(result.get("exit_code", 0)) if args.command == "run-worker" else 0


def init_run(
    *,
    out_root: Path,
    run_id: str,
    proof_class: str,
    repo_root: Path = REPO_ROOT,
) -> Path:
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


def assign_slice(
    *,
    db_path: Path,
    run_id: str,
    worker_id: str,
    target_id: str,
    slice_id: str,
    source_repo_root: Path,
    source_file: str,
    function: str,
    source_commit: str,
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
    resource_key = f"slice:{target_id}/{slice_id}"
    task_id = f"{run_id}:{worker_id}:{target_id}:{slice_id}"
    now = now_text()
    expires_at = str(int(time.time()) + lease_ttl_seconds)
    assignment = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "role": "slice-worker",
        "out_root": repo_relative(out_root, repo_root=repo_root),
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
            "command": "python validation/tools/run_competition.py",
            "out_root": repo_relative(out_root, repo_root=repo_root),
            "reuse_accepted_evidence": reuse_accepted_evidence,
        },
    }
    if compiler_command_source_rel:
        assignment["slice"]["compiler_command_source"] = compiler_command_source_rel
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
        "out_root": repo_relative(out_root, repo_root=repo_root),
        "run_id": f"{run_id}-{worker_id}",
    }
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
        active_owner = connection.execute(
            "select lease_owner from leases where resource_key=? and status='active'",
            (resource_key,),
        ).fetchone()
        if active_owner is not None and active_owner[0] != worker_id:
            raise SystemExit(f"active lease already exists for {resource_key}: {active_owner[0]}")

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
                repo_relative(out_root, repo_root=repo_root),
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
                json.dumps([repo_relative(out_root, repo_root=repo_root)], sort_keys=True),
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
        assignment_path.write_text(json.dumps(assignment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        request_path = assignment_path.with_name(f"{worker_id}-request.json")
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        record_event(connection, run_id=run_id, event_type="assignment_created", payload=assignment)
        connection.commit()
    return assignment


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
    summary = load_json(summary_path)
    status = str(summary.get("final_gate", {}).get("status", "failed"))
    summary_hash = sha256_file(summary_path)
    summary_rel = repo_relative(summary_path, repo_root=repo_root)
    now = now_text()
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        connection.execute(
            """
            insert into artifacts(run_id, agent_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(repo_rel_path) do update set
              sha256=excluded.sha256,
              status=excluded.status,
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
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    assignment_path = assignment_file_path(db_path, worker_id)
    request_path = assignment_path.with_name(f"{worker_id}-request.json")
    if not request_path.exists():
        raise SystemExit(f"worker request does not exist: {repo_relative(request_path, repo_root=repo_root)}")
    request = load_json(request_path)
    if not request.get("out_root"):
        raise SystemExit("worker out_root is required in request")
    worker_out_root = repo_path(Path(str(request.get("out_root", ""))), repo_root=repo_root)
    summary_path = worker_out_root / "summary" / "competition-run-summary.json"
    logs_dir = worker_out_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    report_dir = worker_out_root / "harness"
    report_dir.mkdir(parents=True, exist_ok=True)

    worker_command = [
        sys.executable,
        "scripts/c2rust-migrator.py",
        "--phase",
        "migrate",
        "--input",
        repo_relative(request_path, repo_root=repo_root),
    ]
    if mode == "deterministic":
        argv = worker_command
        runner_kind = "repo-local-c2rust-migrator"
    elif mode == "opencode":
        argv = build_opencode_run_argv(
            opencode_command=opencode_command,
            opencode_model=opencode_model,
            opencode_agent=opencode_agent,
            opencode_variant=opencode_variant,
            opencode_skip_permissions=opencode_skip_permissions,
            worker_command=worker_command,
            request_path=request_path,
            summary_path=summary_path,
            repo_root=repo_root,
        )
        runner_kind = "opencode-run"
    else:
        raise SystemExit(f"unsupported worker mode: {mode}")

    completed = command_runner(
        argv,
        cwd=repo_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    stdout_path = logs_dir / "harness-worker-executor.stdout.log"
    stderr_path = logs_dir / "harness-worker-executor.stderr.log"
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")

    recorded: dict[str, Any] | None = None
    summary_status = "missing-summary"
    if summary_path.exists():
        recorded = record_worker_summary(
            db_path=db_path,
            run_id=run_id,
            worker_id=worker_id,
            summary_path=summary_path,
            repo_root=repo_root,
        )
        summary = load_json(summary_path)
        summary_status = str(summary.get("final_gate", {}).get("status", "failed"))

    effective_exit_code = int(completed.returncode)
    if effective_exit_code == 0 and (recorded is None or summary_status != "passed"):
        effective_exit_code = 1
    status = "recorded" if recorded is not None else "failed"
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "mode": mode,
        "runner_kind": runner_kind,
        "request_path": repo_relative(request_path, repo_root=repo_root),
        "summary_path": repo_relative(summary_path, repo_root=repo_root),
        "summary_status": summary_status,
        "recorded": recorded is not None,
        "exit_code": effective_exit_code,
        "process_returncode": int(completed.returncode),
        "argv": argv,
        "logs": {
            "stdout": repo_relative(stdout_path, repo_root=repo_root),
            "stderr": repo_relative(stderr_path, repo_root=repo_root),
        },
    }
    report_path = report_dir / "run-worker-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        task_status = summary_status if recorded is not None else "failed"
        connection.execute(
            "update leases set status=?, heartbeat_at=? where run_id=? and lease_owner=?",
            (task_status, now_text(), run_id, worker_id),
        )
        record_event(
            connection,
            run_id=run_id,
            event_type="worker_executed",
            payload={
                "worker_id": worker_id,
                "mode": mode,
                "runner_kind": runner_kind,
                "exit_code": effective_exit_code,
                "process_returncode": int(completed.returncode),
                "summary_path": repo_relative(summary_path, repo_root=repo_root),
                "summary_status": summary_status,
                "recorded": recorded is not None,
                "report_path": repo_relative(report_path, repo_root=repo_root),
            },
        )
        connection.commit()

    result = dict(report)
    result["report_path"] = repo_relative(report_path, repo_root=repo_root)
    if recorded is not None:
        result["record_worker_summary"] = recorded
    return result


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
) -> list[str]:
    if not opencode_command:
        raise SystemExit("opencode command must not be empty")
    prompt = "\n".join(
        [
            "Execute this assigned C-to-Rust worker exactly once.",
            "Run the repo-local deterministic command below, then stop.",
            "Do not treat chat output as evidence; the required artifact is the competition-run-summary JSON.",
            f"Command: {json.dumps(worker_command)}",
            f"Request: {repo_relative(request_path, repo_root=repo_root)}",
            f"Expected summary: {repo_relative(summary_path, repo_root=repo_root)}",
        ]
    )
    argv = [
        opencode_command,
        "run",
        "--dir",
        str(repo_root),
        "--format",
        "json",
        "--variant",
        opencode_variant,
    ]
    if opencode_model:
        argv.extend(["--model", opencode_model])
    if opencode_agent:
        argv.extend(["--agent", opencode_agent])
    if opencode_skip_permissions:
        argv.append("--dangerously-skip-permissions")
    argv.append(prompt)
    return argv


def write_merge_plan(
    *,
    db_path: Path,
    run_id: str,
    out_root: Path,
    proof_class: str,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    out_root = repo_path(out_root, repo_root=repo_root)
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
    argv = [sys.executable, "validation/tools/run_competition.py"]
    for summary in summaries:
        argv.extend(["--worker-summary", summary])
    argv.extend(["--out-root", repo_relative(out_root, repo_root=repo_root), "--proof-class", proof_class, "--run-id", run_id])
    merge_plan = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_summaries": summaries,
        "argv": argv,
        "validator": "validation/tools/validate_competition_run_summary.py",
    }
    merge_path = out_root / "harness" / "merge-plan.json"
    merge_path.parent.mkdir(parents=True, exist_ok=True)
    merge_path.write_text(json.dumps(merge_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("pragma foreign_keys = on")
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
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as error:
        raise SystemExit(f"path must stay inside repository: {path}") from error
    return resolved


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


def repo_relative(path: Path, *, repo_root: Path = REPO_ROOT) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError as error:
        raise SystemExit(f"path must stay inside repository: {path}") from error


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())
