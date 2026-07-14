from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .artifact_write_once import write_once_json_artifact
from .context_plan_indexes import prepare_plan_context_indexes
from .generated_closure import apply_generated_closure_admission
from .orchestration_model import portfolio_dag
from .portfolio import plan_portfolio


class ContextPortfolioError(ValueError):
    def __init__(self, stage: str) -> None:
        super().__init__(stage)
        self.stage = stage


def build_context_portfolio(
    contexts: Mapping[str, Any], graph: Mapping[str, Any], *,
    output: Path, out_rel: str, run_id: str, project_key: str,
    max_concurrency: int, max_attempts: int, context_page_bytes: int,
    context_page_tokens: int, context_group_pages: int,
    closure_admitted: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    try:
        bindings, page_proofs, index_summary = prepare_plan_context_indexes(
            contexts, out_root=output, out_root_rel=out_rel,
            max_page_bytes=context_page_bytes * context_group_pages,
        )
        dag = portfolio_dag(
            graph, bindings, run_id=run_id, project_key=project_key
        )
        portfolio = plan_portfolio(
            dag, out_root=out_rel, max_concurrency=max_concurrency,
            max_attempts=max_attempts,
            context_byte_budget=context_page_bytes * context_group_pages,
            context_token_budget=context_page_tokens * context_group_pages,
            context_page_limit=context_group_pages,
            context_page_proof_set=page_proofs,
        )
        portfolio = apply_generated_closure_admission(
            portfolio, closure_ready=closure_admitted
        )
    except (OSError, ValueError) as error:
        raise ContextPortfolioError("portfolio_contract_invalid") from error
    try:
        page_refs = []
        report = {
            "schema_version": 1,
            "policy": "plan_catalog_only",
            "logical_group_count": int(index_summary["logical_group_count"]),
            "selected_group_ids": [],
            "selected_group_count": 0,
            "logical_page_count": int(index_summary["logical_page_count"]),
            "materialized_page_count": 0,
            "omitted_blocked_page_count": int(index_summary["logical_page_count"]),
            "claim_boundary": {
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
            },
        }
        digest = content_sha256(report)
        materialization = write_once_json_artifact(
            output,
            f"context/materializations/plan-catalog-{digest[:24]}.json",
            report,
        )
    except (OSError, ValueError) as error:
        raise ContextPortfolioError("context_materialization_invalid") from error
    return dag, portfolio, page_refs, materialization


__all__ = ["ContextPortfolioError", "build_context_portfolio"]
