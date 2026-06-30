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
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools.extract_source_slice import find_matching, mask_comments_and_strings

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
    plan_parser.add_argument("--source-commit", required=True)
    plan_parser.add_argument("--require-source-commit")
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
            source_commit=args.source_commit,
            require_source_commit=args.require_source_commit,
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
    return int(result.get("exit_code", 0)) if args.command in {"run-worker", "retry-worker", "run-plan"} else 0


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
    source_repository: str | None = None,
    source_branch: str | None = None,
    source_file: str,
    function: str,
    source_commit: str,
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
            "command": "python validation/tools/run_competition.py",
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
        assignment_path.write_text(json.dumps(assignment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        request_path = assignment_path.with_name(f"{worker_id}-request.json")
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    functions = discover_top_level_function_names(source_path.read_text(encoding="utf-8"))
    if limit is not None:
        if limit < 1:
            raise SystemExit("plan-source-file --limit must be positive")
        functions = functions[:limit]
    if not functions:
        raise SystemExit(f"no top-level function definitions discovered in {source_file_rel}")

    units: list[dict[str, str]] = []
    for index, function in enumerate(functions, start=1):
        function_slug = slug_id(function)
        worker_id = f"{worker_prefix}-{index:03d}-{function_slug}"
        slice_id = f"{slice_id_prefix}-{function_slug}"
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
            require_source_commit=require_source_commit,
            compiler_command_source=compiler_command_source,
            include_paths=include_paths,
            defines=defines,
            reuse_accepted_evidence=reuse_accepted_evidence,
            accepted_evidence_root=accepted_evidence_root,
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
            }
        )

    plan_path = out_root / "harness" / "plans" / f"{target_id}-{slug_id(Path(source_file_rel).stem)}-workers.json"
    plan = {
        "schema_version": SCHEMA_VERSION,
        "status": "planned",
        "run_id": run_id,
        "target_id": target_id,
        "source_repo_root": source_repo_root_rel,
        "source_file": source_file_rel,
        "source_sha256": sha256_file(source_path),
        "source_commit": source_commit,
        "slice_id_prefix": slice_id_prefix,
        "worker_prefix": worker_prefix,
        "plan_path": repo_relative(plan_path, repo_root=repo_root),
        "units": units,
    }
    if source_repository:
        plan["source_repository"] = source_repository
    if source_branch:
        plan["source_branch"] = source_branch
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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

    started = time.monotonic()
    worker_results = []
    ordered_summary_paths: list[str] = []
    failed_workers = 0
    for index, unit in enumerate(units, start=1):
        if not isinstance(unit, dict) or not isinstance(unit.get("worker_id"), str) or not unit["worker_id"]:
            raise SystemExit(f"run-plan unit {index} missing worker_id")
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
            command_runner=command_runner,
            repo_root=repo_root,
        )
        worker_result = {
            "worker_id": unit["worker_id"],
            "slice_id": unit.get("slice_id"),
            "function": unit.get("function"),
            "exit_code": int(result.get("exit_code", 1)),
            "summary_status": result.get("summary_status"),
            "summary_path": result.get("summary_path"),
            "report_path": result.get("report_path"),
            "recorded": bool(result.get("recorded")),
        }
        if worker_result["exit_code"] != 0:
            failed_workers += 1
        if worker_result["recorded"] and worker_result["summary_path"]:
            ordered_summary_paths.append(str(worker_result["summary_path"]))
        worker_results.append(worker_result)

    merge_plan = write_merge_plan(
        db_path=db_path,
        run_id=run_id,
        out_root=out_root,
        proof_class=proof_class,
        worker_summary_paths=ordered_summary_paths,
        repo_root=repo_root,
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": "completed" if failed_workers == 0 else "failed",
        "run_id": run_id,
        "mode": mode,
        "plan_path": repo_relative(plan_path, repo_root=repo_root),
        "worker_count": len(worker_results),
        "failed_workers": failed_workers,
        "exit_code": 0 if failed_workers == 0 else 1,
        "elapsed_seconds": int(time.monotonic() - started),
        "workers": worker_results,
        "merge_plan": merge_plan,
    }
    report_path = out_root / "harness" / "run-plan-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
          sha256=excluded.sha256,
          status=excluded.status,
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
    attempt_number: int = 1,
    retry_of: str | None = None,
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
    rollback_evidence = None
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
        summary_path.unlink()

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
        handoff_contract = None
    elif mode == "opencode":
        handoff_contract_path = report_dir / "opencode-handoff-contract.json"
        argv = build_opencode_run_argv(
            opencode_command=opencode_command,
            opencode_model=opencode_model,
            opencode_agent=opencode_agent,
            opencode_variant=opencode_variant,
            opencode_skip_permissions=opencode_skip_permissions,
            worker_command=worker_command,
            request_path=request_path,
            summary_path=summary_path,
            handoff_contract_path=handoff_contract_path,
            repo_root=repo_root,
        )
        runner_kind = "opencode-run"
        handoff_contract = write_opencode_handoff_contract(
            run_id=run_id,
            worker_id=worker_id,
            attempt_number=attempt_number,
            request_path=request_path,
            summary_path=summary_path,
            contract_path=handoff_contract_path,
            worker_command=worker_command,
            opencode_argv=argv,
            repo_root=repo_root,
        )
    else:
        raise SystemExit(f"unsupported worker mode: {mode}")

    try:
        completed = command_runner(
            argv,
            cwd=repo_root,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
    except OSError as exc:
        completed = subprocess.CompletedProcess(
            argv,
            127,
            stdout="",
            stderr=f"{type(exc).__name__}: {exc}\n",
        )
    stdout_path = logs_dir / "harness-worker-executor.stdout.log"
    stderr_path = logs_dir / "harness-worker-executor.stderr.log"
    stdout_path.write_text(completed.stdout or "", encoding="utf-8")
    stderr_path.write_text(completed.stderr or "", encoding="utf-8")
    opencode_session_evidence = None
    if mode == "opencode":
        opencode_session_evidence = write_opencode_session_evidence(
            completed=completed,
            evidence_path=logs_dir / "opencode-session-evidence.json",
            stdout_path=stdout_path,
            stderr_path=stderr_path,
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

    synthetic_failure_root_cause = None
    rejected_summary_evidence = None
    opencode_contract_failed = (
        opencode_contract_verification is not None
        and opencode_contract_verification.get("status") != "executed"
        and int(completed.returncode) == 0
    )
    if opencode_contract_failed:
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
    elif not summary_path.exists():
        provisional_root_cause = worker_failure_root_cause(
            process_returncode=int(completed.returncode),
            recorded=False,
            summary_status="missing-summary",
            opencode_contract_verification=opencode_contract_verification,
        )
        if provisional_root_cause == "opencode_contract_not_executed":
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
    report_path = report_dir / "run-worker-report.json"
    repair_hint = None
    if effective_exit_code != 0:
        root_cause_key = synthetic_failure_root_cause or worker_failure_root_cause(
            process_returncode=int(completed.returncode),
            recorded=recorded is not None,
            summary_status=summary_status,
            opencode_contract_verification=opencode_contract_verification,
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
            retry_of=retry_of,
            rollback_evidence=rollback_evidence,
            rejected_summary_evidence=rejected_summary_evidence,
            handoff_contract=handoff_contract,
            opencode_session_evidence=opencode_session_evidence,
            opencode_contract_verification=opencode_contract_verification,
        )
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "worker_id": worker_id,
        "attempt": attempt_number,
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
    if handoff_contract is not None:
        report["handoff_contract"] = handoff_contract
    if opencode_session_evidence is not None:
        report["opencode_session_evidence"] = opencode_session_evidence
    if opencode_contract_verification is not None:
        report["opencode_contract_verification"] = opencode_contract_verification
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
        }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

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
    command_runner: Any = subprocess.run,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    db_path = repo_path(db_path, repo_root=repo_root)
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        hint = load_open_repair_hint(connection, run_id=run_id, worker_id=worker_id, hint_id=hint_id)
        attempts = hint.get("attempts")
        attempt_number = len(attempts) + 1 if isinstance(attempts, list) else 2

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
        command_runner=command_runner,
        repo_root=repo_root,
        attempt_number=attempt_number,
        retry_of=str(hint["hint_id"]),
    )
    hint_status = (
        "revalidated_passed"
        if int(result.get("exit_code", 1)) == 0 and result.get("summary_status") == "passed"
        else "revalidated_failed"
    )
    with closing(connect(db_path)) as connection:
        ensure_schema(connection)
        mark_repair_hint_revalidated(
            connection,
            hint_id=str(hint["hint_id"]),
            status=hint_status,
            result=result,
        )
        connection.commit()

    retry_result = dict(result)
    retry_result["hint_id"] = hint["hint_id"]
    retry_result["hint_status"] = hint_status
    return retry_result


def worker_failure_root_cause(
    *,
    process_returncode: int,
    recorded: bool,
    summary_status: str,
    opencode_contract_verification: dict[str, Any] | None = None,
) -> str:
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
    retry_command = [
        sys.executable,
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
    ]
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
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
) -> list[str]:
    if not opencode_command:
        raise SystemExit("opencode command must not be empty")
    command_line = subprocess.list2cmdline(worker_command)
    prompt_lines = [
        "Execute this assigned C-to-Rust worker exactly once.",
        "Use the shell/bash tool to run exactly the Command line string below.",
        "The first shell/bash/powershell/cmd tool call must be exactly the Command line string.",
        "Do not run init-run, assign-slice, retry-worker, or any other substitute harness command.",
        "Do not inspect an existing summary before running the command.",
        "Delete the expected summary file if it already exists, then execute the command exactly once.",
        "Run the repo-local deterministic command below, then stop.",
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
                "Read the handoff contract before running the command.",
                f"Handoff contract: {repo_relative(handoff_contract_path, repo_root=repo_root)}",
            ]
        )
    prompt = "\n".join(prompt_lines)
    resolved_opencode_command = resolve_subprocess_command(opencode_command)
    argv = [
        resolved_opencode_command,
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


def resolve_subprocess_command(command: str) -> str:
    if not command:
        raise SystemExit("opencode command must not be empty")
    if "/" in command or "\\" in command or Path(command).is_absolute():
        return command
    return shutil.which(command) or command


def verify_opencode_contract_execution(
    *,
    session_evidence: dict[str, Any],
    worker_command: list[str],
    summary_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    expected_worker_command_line = subprocess.list2cmdline(worker_command)
    executed_shell_commands = extract_opencode_shell_commands(session_evidence)
    normalized_expected = normalize_command_for_contract(expected_worker_command_line)
    exact_worker_command_seen = any(
        normalize_command_for_contract(command) == normalized_expected for command in executed_shell_commands
    )
    first_shell_command = executed_shell_commands[0] if executed_shell_commands else ""
    first_shell_command_matches_worker_command = (
        bool(first_shell_command) and normalize_command_for_contract(first_shell_command) == normalized_expected
    )
    status = "not-observed"
    if executed_shell_commands:
        status = "executed" if first_shell_command_matches_worker_command else "not-executed"
    return {
        "expected_worker_command_line": expected_worker_command_line,
        "expected_summary_path": repo_relative(summary_path, repo_root=repo_root),
        "expected_worker_command_sha256": sha256_text(expected_worker_command_line),
        "executed_shell_command_count": len(executed_shell_commands),
        "executed_shell_commands": executed_shell_commands[:20],
        "first_shell_command": first_shell_command,
        "first_shell_command_matches_worker_command": first_shell_command_matches_worker_command,
        "worker_command_seen": exact_worker_command_seen,
        "summary_exists": summary_path.exists(),
        "status": status,
    }


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


def normalize_command_for_contract(command: str) -> str:
    return " ".join(command.strip().split())


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
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

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
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    repo_root: Path,
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
        "worker_command_line": subprocess.list2cmdline(worker_command),
        "worker_command_sha256": sha256_text(subprocess.list2cmdline(worker_command)),
        "opencode_argv": opencode_argv,
        "opencode_command_line": subprocess.list2cmdline(opencode_argv),
        "prompt": str(opencode_argv[-1]),
        "evidence_boundary": "chat output is diagnostic only; semantic acceptance requires the expected summary and validators",
    }
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": repo_relative(contract_path, repo_root=repo_root), "sha256": sha256_file(contract_path)}


def write_opencode_session_evidence(
    *,
    completed: subprocess.CompletedProcess[str],
    evidence_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    repo_root: Path,
) -> dict[str, str]:
    stdout = completed.stdout or ""
    evidence: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "process_returncode": int(completed.returncode),
        "stdout_path": repo_relative(stdout_path, repo_root=repo_root),
        "stderr_path": repo_relative(stderr_path, repo_root=repo_root),
    }
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
            evidence.update(
                {
                    "parsed": True,
                    "format": "jsonl",
                    "session_events": events,
                }
            )
        else:
            evidence.update(
                {
                    "parsed": False,
                    "parse_error": str(jsonl_error or error),
                    "raw_output": stdout[:20000],
                }
            )
    else:
        evidence.update(
            {
                "parsed": True,
                "format": "json",
                "session": parsed,
            }
        )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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


def slug_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    if not slug:
        raise SystemExit(f"cannot build id slug from empty value: {value!r}")
    return slug


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
