from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from .artifacts import checked_relative_path, content_sha256, write_json_artifact
from .build_ir import translation_units_for_index
from .build_ir_validation import verify_build_ir_artifact
from .c_index import index_translation_units
from .context_pages import build_context_pages
from .discovery import discover_project
from .generated_closure import materialize_build_ir_stage
from .ledger import ProjectLedger, SCHEMA_VERSION as LEDGER_SCHEMA_VERSION
from .migration_graph import build_migration_graph
from .orchestrator_context import ContextPortfolioError, build_context_portfolio
from .scheduler import schedule_portfolio

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
    try:
        build_stage = materialize_build_ir_stage(source, output, discovery, artifacts)
    except (OSError, TypeError, ValueError):
        return _blocked(output, artifacts, "build_ir_contract_invalid")
    if build_stage["verification"].get("status") != "verified":
        return _blocked(output, artifacts, "build_ir_verification_blocked")
    build_ir = build_stage["build_ir"]
    generated_closure = build_stage["closure"]
    closure_verification = build_stage["closure_verification"]
    closure_ready = bool(build_stage["closure_ready"])

    project_key = content_sha256({
        "build_ir": artifacts["build_ir"],
        "semantic_sha256": build_ir["semantic_sha256"],
        "build_closure_policy": "required" if require_build_closure else "bounded-source",
    })
    effective_run_id = run_id or f"project-{project_key[:16]}"
    if RUN_ID_RE.fullmatch(effective_run_id) is None:
        raise ValueError("run_id must be a bounded portable identifier")

    c_index = _stage("c_index", lambda: index_translation_units(
        source, translation_units_for_index(build_ir),
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

    admission = verify_build_ir_artifact(source, output, artifacts["build_ir"])
    artifacts["build_ir_worker_admission"] = write_json_artifact(
        output, "plan/build-ir-worker-admission.json", admission)
    build_ir_ready = admission.get("status") == "verified"
    try:
        dag, portfolio, page_refs, materialization_ref = build_context_portfolio(
            contexts, graph, output=output, out_rel=out_rel,
            run_id=effective_run_id, project_key=project_key,
            max_concurrency=max_concurrency, max_attempts=max_attempts,
            context_page_bytes=context_page_bytes,
            context_page_tokens=context_page_tokens,
            context_group_pages=context_group_pages,
            closure_admitted=build_ir_ready and (
                closure_ready or not require_build_closure
            ),
        )
        artifacts["context_materialization"] = materialization_ref
    except ContextPortfolioError as error:
        return _blocked(output, artifacts, error.stage)
    artifacts["portfolio_dag"] = write_json_artifact(output, "plan/portfolio-dag.json", dag)
    artifacts["portfolio"] = write_json_artifact(output, "plan/portfolio.json", portfolio)

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
        "build_ir": {
            "status": "bound" if build_ir_ready else "blocked",
            "artifact": artifacts["build_ir"],
            "verification": artifacts["build_ir_verification"],
            "worker_admission": artifacts["build_ir_worker_admission"],
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    artifacts["integration_manifest"] = write_json_artifact(
        output, "plan/integration-manifest.json", integration_manifest,
    )

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
        portfolio=portfolio,
        max_concurrency=max_concurrency,
        max_attempts=max_attempts,
        metadata={"artifacts": artifacts, "page_count": len(page_refs)},
    )
    unit_states = ledger.unit_states(effective_run_id)
    schedule = schedule_portfolio(portfolio, unit_states, {})
    artifacts["initial_schedule"] = write_json_artifact(
        output, "plan/initial-schedule.json", schedule,
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
            "schema_version": LEDGER_SCHEMA_VERSION,
            "resume_policy": "create_or_verify_immutable_inputs",
        },
        "portfolio": portfolio,
        "scheduler": {
            "status": schedule["status"],
            "ready_worker_ids": [
                item["worker_id"] for item in schedule["ready"]
            ],
            "deferred_count": len(schedule["deferred"]),
        },
        "execution": {
            "model_launched": False,
            "cargo_executed": False,
            "build_ir_ready": build_ir_ready,
            "build_ir_semantic_sha256": build_ir["semantic_sha256"],
            "build_ir_blockers": admission.get("blockers", []),
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
                if build_ir_ready and (closure_ready or not require_build_closure)
                else ("resolve_generated_build_closure_blockers" if build_ir_ready
                      else "resolve_build_ir_blockers")
            ),
        },
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "proof_class": "project-plan-only",
            "build_ir_verified": build_ir_ready,
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
