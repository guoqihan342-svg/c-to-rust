from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .artifacts import checked_relative_path, content_sha256, write_json_artifact
from .c_index import index_translation_units
from .context_pages import build_context_pages
from .discovery import discover_project
from .generated_closure import (
    apply_generated_closure_admission,
    verify_generated_build_closure,
)
from .ledger import ProjectLedger
from .migration_graph import build_migration_graph
from .orchestration_model import materialize_context_indexes, portfolio_dag
from .portfolio import plan_portfolio
from .scheduler import schedule_portfolio
from .worker_requests import materialize_worker_requests


RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")


def plan_project(
    repo_root: str | Path,
    *,
    harness_root: str | Path,
    out_root: str,
    compile_database: str | Path | None = None,
    run_id: str | None = None,
    source_commit: str = "unversioned",
    max_units: int = 10_000,
    max_concurrency: int = 4,
    max_attempts: int = 5,
    context_page_bytes: int = 16_384,
    context_page_tokens: int = 4_096,
    context_group_pages: int = 32,
    require_build_closure: bool = False,
) -> dict[str, Any]:
    harness = Path(harness_root).resolve(strict=True)
    source_input = Path(repo_root)
    out_rel = checked_relative_path(out_root.rstrip("/"))
    output = (harness / Path(*Path(out_rel).parts)).resolve()
    try:
        output.relative_to(harness)
    except ValueError as error:
        raise ValueError("out_root must stay inside harness_root") from error

    if (
        isinstance(context_group_pages, bool)
        or not isinstance(context_group_pages, int)
        or not 1 <= context_group_pages <= 64
    ):
        raise ValueError("context_group_pages must be an integer from 1 to 64")
    if not isinstance(require_build_closure, bool):
        raise ValueError("require_build_closure must be boolean")
    artifacts: dict[str, dict[str, Any]] = {}
    discovery = discover_project(
        source_input, compile_database=compile_database, max_units=max_units
    )
    artifacts["discovery"] = write_json_artifact(output, "plan/discovery.json", discovery)
    if discovery.get("status") != "ready":
        return _blocked(output, artifacts, "discovery_blocked")
    source = source_input.resolve(strict=True)
    generated_closure = discovery.get("generated_build_closure", {})
    artifacts["generated_build_closure"] = write_json_artifact(
        output, "plan/generated-build-closure.json", generated_closure
    )
    closure_verification = verify_generated_build_closure(source, generated_closure)
    artifacts["generated_build_closure_verification"] = write_json_artifact(
        output,
        "plan/generated-build-closure-verification.json",
        closure_verification,
    )
    closure_ready = (
        generated_closure.get("status") == "ready"
        and closure_verification.get("status") == "verified"
    )

    project_key = content_sha256({
        "compile_database": discovery.get("compile_database"),
        "sources": [unit.get("source") for unit in discovery.get("translation_units", [])],
        "generated_build_closure": generated_closure,
        "generated_build_closure_verification": closure_verification,
        "build_closure_policy": "required" if require_build_closure else "bounded-source",
    })
    effective_run_id = run_id or f"project-{project_key[:16]}"
    if RUN_ID_RE.fullmatch(effective_run_id) is None:
        raise ValueError("run_id must be a bounded portable identifier")

    c_index = _stage("c_index", lambda: index_translation_units(
        source, discovery["translation_units"],
    ))
    if c_index is None:
        return _blocked(output, artifacts, "c_index_contract_invalid")
    artifacts["c_index"] = write_json_artifact(output, "plan/c-index.json", c_index)
    if c_index.get("status") not in {"ready", "ready_with_boundaries"}:
        return _blocked(output, artifacts, "c_index_blocked")

    graph = _stage("migration_graph", lambda: build_migration_graph(c_index))
    if graph is None:
        return _blocked(output, artifacts, "migration_graph_contract_invalid")
    artifacts["migration_graph"] = write_json_artifact(
        output, "plan/migration-graph.json", graph,
    )
    if graph.get("status") not in {"ready", "ready_with_boundaries"}:
        return _blocked(output, artifacts, "migration_graph_blocked")

    contexts = _stage("context_pages", lambda: build_context_pages(
        c_index,
        graph,
        max_page_bytes=context_page_bytes,
        max_page_tokens=context_page_tokens,
    ))
    if contexts is None:
        return _blocked(output, artifacts, "context_pages_contract_invalid")
    artifacts["context_pages"] = write_json_artifact(
        output, "plan/context-pages.json", contexts,
    )
    if contexts.get("status") not in {"ready", "ready_with_boundaries"}:
        return _blocked(output, artifacts, "context_pages_blocked")

    try:
        context_bindings, page_refs = materialize_context_indexes(
            contexts, out_root=output, out_root_rel=out_rel,
        )
        dag = portfolio_dag(
            graph, context_bindings, run_id=effective_run_id, project_key=project_key,
        )
        portfolio = plan_portfolio(
            dag,
            out_root=out_rel,
            max_concurrency=max_concurrency,
            max_attempts=max_attempts,
            context_byte_budget=context_page_bytes * context_group_pages,
            context_token_budget=context_page_tokens * context_group_pages,
            context_page_limit=context_group_pages,
            context_page_root=harness,
        )
        portfolio = apply_generated_closure_admission(
            portfolio,
            closure_ready=closure_ready or not require_build_closure,
        )
    except (OSError, ValueError) as error:
        _ = error
        return _blocked(output, artifacts, "portfolio_contract_invalid")
    artifacts["portfolio_dag"] = write_json_artifact(output, "plan/portfolio-dag.json", dag)
    artifacts["portfolio"] = write_json_artifact(output, "plan/portfolio.json", portfolio)

    ledger = ProjectLedger(output / "state/project-migration.sqlite3")
    ledger_assignments = [
        {
            "unit_id": item["unit_id"],
            "worker_id": item["worker_id"],
            "role": item["role"],
            "out_root": item["isolated_out_root"],
            "max_attempts": item["max_attempts"],
        }
        for item in portfolio["assignments"]
    ]
    ledger.create_or_resume_run(
        run_id=effective_run_id,
        project_key=project_key,
        source_commit=source_commit,
        dag_sha256=portfolio["dag_sha256"],
        units=portfolio["ledger_units"],
        assignments=ledger_assignments,
        max_concurrency=max_concurrency,
        max_attempts=max_attempts,
        metadata={"artifacts": artifacts, "page_count": len(page_refs)},
    )
    integration_manifest = {
        "schema_version": 1,
        "dag": {
            group["group_id"]: list(group["dependencies"])
            for group in dag["groups"]
        },
        "dag_order": [
            group_id for wave in dag["waves"] for group_id in wave["group_ids"]
        ],
        "unsafe_policy": {
            "allow_unsafe": True,
            "max_total": None,
            "max_per_group": None,
        },
        "generated_build_closure": {
            "status": "bound" if closure_ready else "blocked",
            "closure": artifacts["generated_build_closure"],
            "verification": artifacts["generated_build_closure_verification"],
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    artifacts["integration_manifest"] = write_json_artifact(
        output, "plan/integration-manifest.json", integration_manifest,
    )
    unit_states = ledger.resume_units(effective_run_id)
    schedule = schedule_portfolio(portfolio, unit_states, {})
    request_refs = materialize_worker_requests(
        schedule, out_root=output, out_root_rel=out_rel,
    )
    artifacts["initial_schedule"] = write_json_artifact(
        output, "plan/initial-schedule.json", schedule,
    )
    artifacts["initial_worker_requests"] = write_json_artifact(
        output, "plan/initial-worker-requests.json", request_refs,
    )
    plan = {
        "schema_version": 1,
        "status": portfolio["status"],
        "run_id": effective_run_id,
        "project_key": project_key,
        "source_commit": source_commit,
        "artifacts": artifacts,
        "ledger": {
            "path": f"{out_rel}/state/project-migration.sqlite3",
            "status": "bound",
            "schema_version": 2,
            "resume_policy": "create_or_verify_immutable_inputs",
        },
        "portfolio": portfolio,
        "scheduler": {
            "status": schedule["status"],
            "ready_worker_ids": [item["worker_id"] for item in request_refs],
            "deferred_count": len(schedule["deferred"]),
        },
        "execution": {
            "model_launched": False,
            "cargo_executed": False,
            "build_closure_ready": closure_ready,
            "build_closure_policy": (
                "required" if require_build_closure else "bounded-source"
            ),
            "build_closure_blockers": [
                *generated_closure.get("blockers", []),
                *closure_verification.get("blockers", []),
            ],
            "next_action": (
                "materialize_condition_eligible_worker_requests"
                if closure_ready or not require_build_closure
                else "resolve_generated_build_closure_blockers"
            ),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "proof_class": "project-plan-only",
            "generated_build_closure_complete": closure_ready,
            "build_closure_policy": (
                "required" if require_build_closure else "bounded-source"
            ),
        },
    }
    plan["plan_sha256"] = content_sha256(plan)
    write_json_artifact(output, "project-migration-plan.json", plan)
    return plan


def _stage(name: str, operation: Callable[[], dict[str, Any]]) -> dict[str, Any] | None:
    try:
        return operation()
    except (OSError, UnicodeError, ValueError):
        _ = name
        return None


def _blocked(
    output: Path,
    artifacts: dict[str, dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    result = {
        "schema_version": 1,
        "status": "blocked",
        "blockers": [reason],
        "artifacts": artifacts,
        "execution": {"model_launched": False, "cargo_executed": False},
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "proof_class": "project-plan-only",
        },
    }
    result["plan_sha256"] = content_sha256(result)
    write_json_artifact(output, "project-migration-plan.json", result)
    return result


__all__ = ["plan_project"]
