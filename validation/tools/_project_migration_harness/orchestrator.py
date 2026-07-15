from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .artifacts import checked_relative_path, content_sha256, write_json_artifact
from .build_adapter import (
    BuildInputSelectionLike, materialize_selected_build_ir_stage,
)
from .build_ir import translation_units_for_index
from .build_ir_validation import verify_build_ir_artifact
from .c_index import index_translation_units
from .c_compilation_fact_bundle import collect_c_compilation_fact_bundle
from .context_pages import build_context_pages
from .discovery import discover_project
from .migration_graph import build_migration_graph
from . import orchestrator_native_link as native_link_stage
from .orchestrator_context import ContextPortfolioError, build_context_portfolio
from .orchestrator_finalize import finalize_project_plan
from .orchestrator_stages import (
    blocked_plan as _blocked,
    contract_error,
    run_stage as _stage,
)

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
PROJECT_PROFILES = {"competition", "development"}


def plan_project(
    repo_root: str | Path,
    *,
    harness_root: str | Path,
    out_root: str,
    compile_database: str | Path | None = None,
    make_report: BuildInputSelectionLike | None = None,
    run_id: str | None = None,
    source_commit: str = "unversioned",
    max_units: int = 10_000,
    max_concurrency: int = 4,
    max_attempts: int = 5,
    context_page_bytes: int = 16_384,
    context_page_tokens: int = 4_096,
    context_group_pages: int = 32,
    require_build_closure: bool = False,
    profile: str = "development",
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
    if profile not in PROJECT_PROFILES:
        raise ValueError("profile must be competition or development")
    artifacts: dict[str, dict[str, Any]] = {}
    discovery = discover_project(
        source_input, compile_database=compile_database, max_units=max_units,
        make_report=make_report,
    )
    artifacts["discovery"] = write_json_artifact(output, "plan/discovery.json", discovery)
    if discovery.get("status") != "ready":
        return _blocked(output, artifacts, "discovery_blocked")
    source = source_input.resolve(strict=True)
    try:
        build_stage = materialize_selected_build_ir_stage(
            source, output, discovery, artifacts, make_report, profile,
        )
    except (OSError, TypeError, ValueError) as error:
        artifacts["build_ir_contract_error"] = write_json_artifact(
            output,
            "plan/build-ir-contract-error.json",
            contract_error("build_ir", error),
        )
        return _blocked(output, artifacts, "build_ir_contract_invalid")
    if build_stage["verification"].get("status") != "verified":
        return _blocked(output, artifacts, "build_ir_verification_blocked")
    build_ir = build_stage["build_ir"]
    generated_closure = build_stage["closure"]
    closure_verification = build_stage["closure_verification"]
    closure_ready = bool(build_stage["closure_ready"])
    del build_stage
    admission = verify_build_ir_artifact(source, output, artifacts["build_ir"])
    artifacts["build_ir_worker_admission"] = write_json_artifact(
        output, "plan/build-ir-worker-admission.json", admission,
    )
    if admission.get("status") != "verified":
        return _blocked(output, artifacts, "build_ir_worker_admission_blocked")
    build_ir_ready = True
    native_link_context, artifacts["native_link_context"] = native_link_stage.prepare_native_link_plan(
        build_ir, artifacts["build_ir"], profile=profile, output=output,
    )

    compilation_facts = _stage("c_compilation_facts", lambda: (
        collect_c_compilation_fact_bundle(
            repo_root=source,
            out_root=output,
            build_ir=build_ir,
            profile=profile,
        )
    ))
    if compilation_facts is None:
        return _blocked(output, artifacts, "c_compilation_fact_contract_invalid")
    artifacts["c_compilation_facts"] = write_json_artifact(
        output, "plan/c-compilation-facts.json", compilation_facts,
    )

    c_index = _stage("c_index", lambda: index_translation_units(
        source,
        translation_units_for_index(build_ir),
        compilation_fact_bundle=compilation_facts,
        build_ir_semantic_sha256=build_ir["semantic_sha256"],
    ))
    if c_index is None:
        return _blocked(output, artifacts, "c_index_contract_invalid")
    artifacts["c_index"] = write_json_artifact(output, "plan/c-index.json", c_index)
    if c_index.get("status") not in {"ready", "ready_with_boundaries"}:
        return _blocked(output, artifacts, "c_index_blocked")

    project_key = content_sha256({
        "build_ir": artifacts["build_ir"],
        "semantic_sha256": build_ir["semantic_sha256"],
        "generated_build_closure": artifacts["generated_build_closure"],
        "generated_build_closure_verification": artifacts[
            "generated_build_closure_verification"
        ],
        "c_compilation_fact_bundle_sha256": compilation_facts["bundle_sha256"],
        "c_index": artifacts["c_index"],
        "build_closure_policy": "required" if require_build_closure else "bounded-source",
        "profile": profile,
    })
    effective_run_id = run_id or f"project-{project_key[:16]}"
    if RUN_ID_RE.fullmatch(effective_run_id) is None:
        raise ValueError("run_id must be a bounded portable identifier")
    del discovery

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
    del c_index

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
    del contexts, graph
    artifacts["portfolio_dag"] = write_json_artifact(output, "plan/portfolio-dag.json", dag)
    artifacts["portfolio"] = write_json_artifact(output, "plan/portfolio.json", portfolio)

    return finalize_project_plan(
        output=output, out_rel=out_rel, artifacts=artifacts, profile=profile,
        dag=dag, portfolio=portfolio, page_count=len(page_refs),
        run_id=effective_run_id, project_key=project_key,
        source_commit=source_commit, max_concurrency=max_concurrency,
        max_attempts=max_attempts, closure_ready=closure_ready,
        require_build_closure=require_build_closure,
        build_ir_ready=build_ir_ready, build_ir=build_ir,
        admission=admission, native_link_context=native_link_context,
        compilation_facts=compilation_facts,
        generated_closure=generated_closure,
        closure_verification=closure_verification,
    )


__all__ = ["plan_project"]
