#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from validation.tools._project_migration_harness.controller import (
    dispatch_project_workers,
    ingest_worker_result,
    integrate_verified_project,
    prepare_next_context_frontier_wave,
    promote_current_verified_candidate,
    record_candidate_gate,
    record_project_gate_summary,
    run_and_ingest_opencode_worker,
    run_cargo_project_gates,
    verify_integrated_project,
    verify_project_cargo,
    verify_candidate_compile,
    verify_candidate_final,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_cli import run_c2rust_baseline_command
from validation.tools._project_migration_harness import project_cli_runtime
from validation.tools._project_migration_harness.gate_authority import (
    candidate_authority,
    candidate_kind,
    project_authority,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger
from validation.tools._project_migration_harness.make_dry_run_cli import run_collect_make_command
from validation.tools._project_migration_harness.project_migration_cli import (
    load_array,
    load_next_frontier_bindings,
    load_object,
    output_binding,
    parse_args,
)
from validation.tools._project_migration_harness.project_preflight_runner import (
    run_project_worker_preflight,
)
from validation.tools._project_migration_harness.project_completion_cli import (
    run_completion_cli_command,
)
from validation.tools._project_migration_harness.project_migrate_cli import (
    run_migrate_cli_command,
)
from validation.tools._project_migration_harness.project_plan_cli import (
    run_plan_cli_command,
)
from validation.tools._project_migration_harness.project_test_target_proposal_cli import (
    run_prepare_make_test_target_proposal,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
_ref = project_cli_runtime.reference


def _repo_relative(value: str) -> Path:
    return project_cli_runtime.repo_relative(value, repo_root=REPO_ROOT)

def _ledger(value: str | Path) -> ProjectLedger:
    return project_cli_runtime.ledger(value, repo_root=REPO_ROOT)

def _ledger_path(value: str | Path) -> Path:
    return project_cli_runtime.ledger_path(value, repo_root=REPO_ROOT)


def _target_path(
    value: str | Path, label: str, *, must_exist: bool = False,
) -> Path:
    return project_cli_runtime.target_path(
        value, label, repo_root=REPO_ROOT, must_exist=must_exist,
    )


def _target_relative(value: str | Path, label: str) -> str:
    return project_cli_runtime.target_relative(value, label, repo_root=REPO_ROOT)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    command = args.command
    if command == "collect-make-facts":
        result = run_collect_make_command(args)
    elif command == "prepare-make-test-target-proposal":
        result = run_prepare_make_test_target_proposal(
            args, harness_root=REPO_ROOT,
        )
    elif command == "c2rust-baseline":
        result = run_c2rust_baseline_command(args, harness_root=REPO_ROOT)
    elif command == "migrate":
        result = run_migrate_cli_command(args, harness_root=REPO_ROOT)
    elif command == "plan":
        result = run_plan_cli_command(args, harness_root=REPO_ROOT)
    elif command == "dispatch":
        plan_path = _target_path(args.plan, "plan", must_exist=True)
        plan = load_object(plan_path)
        ledger_path, out_rel = output_binding(
            plan, plan_path=plan_path, harness_root=REPO_ROOT
        )
        out_root = REPO_ROOT.joinpath(*out_rel.parts)
        result = dispatch_project_workers(
            project_cli_runtime.load_bound_portfolio(plan, out_root),
            ledger=ProjectLedger(_ledger_path(ledger_path)),
            harness_root=REPO_ROOT,
            out_root=out_root,
            out_root_rel=out_rel.as_posix(),
            lease_ttl_seconds=args.lease_ttl_seconds,
        )
    elif command == "prepare-next-context-frontier-wave":
        plan, ledger_path, out_rel, refs, latest_path, latest_ref = (
            load_next_frontier_bindings(args, harness_root=REPO_ROOT)
        )
        result = prepare_next_context_frontier_wave(
            load_object(_target_path(
                refs["portfolio"]["path"], "portfolio", must_exist=True,
            )),
            portfolio_reference=refs["portfolio"],
            latest_dag=load_object(latest_path),
            latest_dag_reference=latest_ref,
            context_bundle=load_object(_target_path(
                refs["context_pages"]["path"], "context-pages", must_exist=True,
            )),
            context_bundle_reference=refs["context_pages"],
            completed_wave_index=args.completed_wave_index,
            failure_evidence=load_array(_target_path(
                args.failure_evidence, "failure-evidence", must_exist=True,
            )),
            expansion_queries=load_array(_target_path(
                args.expansion_queries, "expansion-queries", must_exist=True,
            )),
            ledger=ProjectLedger(_ledger_path(ledger_path)),
            harness_root=REPO_ROOT,
            out_root=REPO_ROOT.joinpath(*out_rel.parts),
            out_root_rel=out_rel.as_posix(),
        )
    elif command == "preflight":
        out_root_rel = _target_relative(args.out_root, "out-root")
        result = run_project_worker_preflight(
            harness_root=REPO_ROOT,
            out_root_rel=out_root_rel,
            run_id=args.run_id,
            logical_model=args.logical_model,
            resolved_model=args.resolved_model,
            timeout_seconds=args.timeout_seconds,
        )
    elif command == "run-worker":
        result = run_and_ingest_opencode_worker(
            _ref(args.request_path, args.request_sha256),
            _ref(args.preflight_path, args.preflight_sha256),
            ledger=_ledger(args.db),
            harness_root=REPO_ROOT,
            logical_model=args.logical_model,
            resolved_model=args.resolved_model,
            opencode_command="opencode",
            timeout_seconds=args.timeout_seconds,
        )
    elif command == "ingest":
        result = ingest_worker_result(
            load_object(args.response),
            ledger=_ledger(args.db),
            harness_root=REPO_ROOT,
            run_id=args.run_id,
            worker_id=args.worker_id,
            attempt_id=args.attempt_id,
            fencing_token=args.fencing_token,
        )
    elif command == "record-candidate-gate":
        out_root = _repo_relative(args.out_root)
        result = record_candidate_gate(
            ledger=_ledger(args.db),
            out_root=out_root,
            out_root_rel=args.out_root,
            run_id=args.run_id,
            unit_id=args.unit_id,
            candidate_artifact_id=args.candidate_artifact_id,
            record_id=args.record_id,
            kind=candidate_kind(args.gate_family),
            gate_family=args.gate_family,
            status="failed",
            verifier_id=candidate_authority(args.gate_family),
            diagnostics=load_array(args.diagnostics),
        )
    elif command == "promote":
        result = promote_current_verified_candidate(
            ledger=_ledger(args.db),
            run_id=args.run_id,
            unit_id=args.unit_id,
            candidate_artifact_id=args.candidate_artifact_id,
        )
    elif command == "integrate-verified":
        result = integrate_verified_project(
            load_object(args.manifest),
            ledger=_ledger(args.db),
            run_id=args.run_id,
            candidate_root=args.candidate_root,
            candidate_root_rel=args.candidate_root_rel,
            project_root=args.project_root,
        )
    elif command == "cargo-verify":
        result = run_cargo_project_gates(
            args.project_root,
            runtime_root=args.runtime_root,
            cargo_command=args.cargo_command,
            timeout_seconds=args.timeout_seconds,
        )
    elif command == "verify-integration":
        out_root = _repo_relative(args.out_root)
        result = verify_integrated_project(
            ledger=_ledger(args.db),
            run_id=args.run_id,
            project_root=args.project_root,
            out_root=out_root,
            out_root_rel=args.out_root,
        )
    elif command == "verify-cargo":
        out_root = _repo_relative(args.out_root)
        result = verify_project_cargo(
            ledger=_ledger(args.db),
            run_id=args.run_id,
            project_root=args.project_root,
            runtime_root=args.runtime_root,
            out_root=out_root,
            out_root_rel=args.out_root,
            timeout_seconds=args.timeout_seconds,
        )
    elif command == "verify-candidate-compile":
        candidate_root = _target_path(args.candidate_root, "candidate-root", must_exist=True)
        result = verify_candidate_compile(
            ledger=_ledger(args.db),
            run_id=args.run_id,
            unit_id=args.unit_id,
            candidate_artifact_id=args.candidate_artifact_id,
            candidate_root=candidate_root,
            candidate_root_rel=candidate_root.relative_to(REPO_ROOT).as_posix(),
            quarantine_root=_target_path(args.quarantine_root, "quarantine-root"),
            runtime_root=_target_path(args.runtime_root, "runtime-root"),
            out_root=_repo_relative(args.out_root),
            out_root_rel=args.out_root,
            timeout_seconds=args.timeout_seconds,
        )
    elif command == "verify-candidate-final":
        result = verify_candidate_final(
            ledger=_ledger(args.db),
            out_root=_repo_relative(args.out_root),
            out_root_rel=args.out_root,
            run_id=args.run_id,
            unit_id=args.unit_id,
            candidate_artifact_id=args.candidate_artifact_id,
        )
    elif command == "record-project-gate":
        out_root = _repo_relative(args.out_root)
        ledger = _ledger(args.db)
        candidate_set_sha256 = ledger.bind_current_candidate_set(run_id=args.run_id)
        result = record_project_gate_summary(
            ledger=ledger,
            out_root=out_root,
            out_root_rel=args.out_root,
            run_id=args.run_id,
            record_id=args.record_id,
            gate_kind=args.gate_kind,
            status="failed",
            candidate_set_sha256=candidate_set_sha256,
            verifier_id=project_authority(args.gate_kind),
            source_evidence=load_array(args.source_evidence),
        )
    elif command in {"complete", "run-to-completion"}:
        result = run_completion_cli_command(command, args, harness_root=REPO_ROOT)
    else:
        result = {
            "schema_version": 1,
            "status": "recorded",
            "run_id": args.run_id,
            "units": _ledger(args.db).unit_states(args.run_id),
        }
    displayed = project_cli_runtime.display_result(command, result)
    print(json.dumps(displayed, indent=2, sort_keys=True))
    return project_cli_runtime.exit_code(result, command=command)


if __name__ == "__main__":
    raise SystemExit(main())
