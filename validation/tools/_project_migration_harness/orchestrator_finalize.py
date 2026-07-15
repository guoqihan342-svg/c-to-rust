from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256, write_json_artifact
from .ledger import ProjectLedger, SCHEMA_VERSION as LEDGER_SCHEMA_VERSION
from . import orchestrator_native_link as native_link_stage
from .project_cli_runtime import display_result
from .scheduler import schedule_portfolio


def finalize_project_plan(
    *, output: Path, out_rel: str, artifacts: dict[str, dict[str, Any]],
    profile: str, dag: Mapping[str, Any], portfolio: Mapping[str, Any],
    page_count: int, run_id: str, project_key: str, source_commit: str,
    max_concurrency: int, max_attempts: int, closure_ready: bool,
    require_build_closure: bool, build_ir_ready: bool,
    build_ir: Mapping[str, Any], admission: Mapping[str, Any],
    native_link_context: Mapping[str, Any],
    compilation_facts: Mapping[str, Any],
    generated_closure: Mapping[str, Any],
    closure_verification: Mapping[str, Any],
) -> dict[str, Any]:
    artifacts["integration_manifest"] = write_json_artifact(
        output, "plan/integration-manifest.json",
        _integration_manifest(
            profile, dag, artifacts, closure_ready, build_ir_ready,
            portfolio,
        ),
    )
    ledger = ProjectLedger(output / "state/project-migration.sqlite3")
    ledger.create_or_resume_run(
        run_id=run_id, project_key=project_key, source_commit=source_commit,
        dag_sha256=portfolio["dag_sha256"], units=portfolio["ledger_units"],
        assignments=_ledger_assignments(portfolio), portfolio=portfolio,
        max_concurrency=max_concurrency, max_attempts=max_attempts,
        metadata={"artifacts": artifacts, "page_count": page_count},
    )
    schedule = schedule_portfolio(portfolio, ledger.unit_states(run_id), {})
    artifacts["initial_schedule"] = write_json_artifact(
        output, "plan/initial-schedule.json", schedule,
    )
    plan = _plan(
        out_rel=out_rel, artifacts=artifacts, profile=profile,
        portfolio=portfolio, schedule=schedule, run_id=run_id,
        project_key=project_key, source_commit=source_commit,
        closure_ready=closure_ready,
        require_build_closure=require_build_closure,
        build_ir_ready=build_ir_ready, build_ir=build_ir,
        admission=admission, native_link_context=native_link_context,
        compilation_facts=compilation_facts,
        generated_closure=generated_closure,
        closure_verification=closure_verification,
    )
    plan["plan_sha256"] = content_sha256(plan)
    write_json_artifact(
        output, "project-migration-plan.json", display_result("plan", plan),
    )
    return plan


def _integration_manifest(
    profile: str, dag: Mapping[str, Any],
    artifacts: Mapping[str, Mapping[str, Any]],
    closure_ready: bool, build_ir_ready: bool,
    portfolio: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": 1, "profile": profile,
        "dag": {
            group["group_id"]: list(group["dependencies"])
            for group in dag["groups"]
        },
        "dag_order": [
            group_id for wave in dag["waves"] for group_id in wave["group_ids"]
        ],
        "unsafe_policy": {
            "allow_unsafe": True, "max_total": None, "max_per_group": None,
        },
        "generated_build_closure": {
            "status": "bound" if closure_ready else "blocked",
            "closure": artifacts["generated_build_closure"],
            "verification": artifacts["generated_build_closure_verification"],
        },
        "build_ir": {
            "status": "bound" if build_ir_ready else "blocked",
            "artifact": artifacts["build_ir"],
            "verification": artifacts["build_ir_verification"],
            "worker_admission": artifacts["build_ir_worker_admission"],
        },
        "c_compilation_facts": {
            "status": "bound", "artifact": artifacts["c_compilation_facts"],
        },
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    ledger_units = portfolio.get("ledger_units")
    if not isinstance(ledger_units, list):
        raise ValueError("portfolio ledger units are unavailable")
    group_hashes = {
        item.get("unit_id"): item.get("content_sha256")
        for item in ledger_units if isinstance(item, Mapping)
    }
    if set(group_hashes) != {group["group_id"] for group in dag["groups"]}:
        raise ValueError("portfolio ledger units do not cover migration groups")
    scopes = {
        group["group_id"]: {
            "group_content_sha256": str(group_hashes[group["group_id"]]),
            "scope_sha256": str(group["target_scope"]["scope_sha256"]),
        }
        for group in dag["groups"]
        if isinstance(group.get("target_scope"), Mapping)
    }
    if len(scopes) == len(dag["groups"]):
        payload["migration_graph"] = dict(artifacts["migration_graph"])
        payload["target_scopes"] = scopes
    return payload


def _ledger_assignments(portfolio: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "unit_id": item["unit_id"], "worker_id": item["worker_id"],
            "role": item["role"], "out_root": item["isolated_out_root"],
            "max_attempts": item["max_attempts"],
        }
        for item in portfolio["assignments"]
    ]


def _plan(
    *, out_rel: str, artifacts: Mapping[str, Mapping[str, Any]], profile: str,
    portfolio: Mapping[str, Any], schedule: Mapping[str, Any], run_id: str,
    project_key: str, source_commit: str, closure_ready: bool,
    require_build_closure: bool, build_ir_ready: bool,
    build_ir: Mapping[str, Any], admission: Mapping[str, Any],
    native_link_context: Mapping[str, Any],
    compilation_facts: Mapping[str, Any],
    generated_closure: Mapping[str, Any],
    closure_verification: Mapping[str, Any],
) -> dict[str, Any]:
    policy = "required" if require_build_closure else "bounded-source"
    portfolio_execution = portfolio.get("execution")
    candidate_only = (
        isinstance(portfolio_execution, Mapping)
        and portfolio_execution.get("build_closure_admission") == "candidate-only"
    )
    return {
        "schema_version": 1, "status": portfolio["status"], "profile": profile,
        "run_id": run_id, "project_key": project_key,
        "source_commit": source_commit, "artifacts": dict(artifacts),
        "ledger": {
            "path": f"{out_rel}/state/project-migration.sqlite3",
            "status": "bound", "schema_version": LEDGER_SCHEMA_VERSION,
            "resume_policy": "create_or_verify_immutable_inputs",
        },
        "portfolio": dict(portfolio),
        "scheduler": {
            "status": schedule["status"],
            "ready_worker_ids": [item["worker_id"] for item in schedule["ready"]],
            "deferred_count": len(schedule["deferred"]),
        },
        "execution": {
            "profile": profile, "model_launched": False,
            "cargo_executed": False, "make_executed": False,
            "build_ir_ready": build_ir_ready,
            "build_ir_semantic_sha256": build_ir["semantic_sha256"],
            "native_link_config_resolved": admission.get("native_link_config_resolved"),
            **native_link_stage.native_link_execution_summary(native_link_context),
            "build_ir_blockers": admission.get("blockers", []),
            "compiler_syntax_witness_status": compilation_facts["status"],
            "compiler_syntax_witness_passed": compilation_facts["summary"]["passed"],
            "compiler_syntax_witness_total": compilation_facts["summary"]["total"],
            "build_closure_ready": closure_ready,
            "build_closure_policy": policy,
            "build_closure_blockers": _unique_blockers(
                generated_closure.get("blockers", []),
                closure_verification.get("blockers", []),
            ),
            **({
                "candidate_admission_scope": "candidate-only",
                "candidate_generation_allowed": True,
                "candidate_promotion_allowed": False,
            } if candidate_only else {}),
            "next_action": (
                "materialize_condition_eligible_worker_requests"
                if build_ir_ready and closure_ready
                else "dispatch_candidate_only_workers"
                if build_ir_ready and candidate_only and schedule["ready"]
                else "resolve_generated_build_closure_blockers"
                if build_ir_ready else "resolve_build_ir_blockers"
            ),
        },
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
            "proof_class": "project-plan-only",
            "competition_profile": profile == "competition",
            "build_ir_verified": build_ir_ready,
            "generated_build_closure_complete": closure_ready,
            "build_closure_policy": policy,
            **({"candidate_admission_scope": "candidate-only"} if candidate_only else {}),
        },
    }


def _unique_blockers(*groups: Any) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for blocker in (item for group in groups for item in group):
        identity = content_sha256(blocker)
        if identity not in seen:
            seen.add(identity)
            result.append(blocker)
    return result


__all__ = ["finalize_project_plan"]
