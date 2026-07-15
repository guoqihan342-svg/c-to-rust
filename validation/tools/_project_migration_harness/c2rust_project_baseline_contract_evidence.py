from __future__ import annotations

from pathlib import Path
from typing import Any

from .c2rust_project_baseline_evidence import write_cas_artifact
from .c2rust_project_baseline_scenarios import (
    BoundBaselineScenarioContract, bind_baseline_scenario_contract,
)


def bind_execution_contract(
    repository: Path, path: Path | None,
) -> BoundBaselineScenarioContract | None:
    return (
        None if path is None
        else bind_baseline_scenario_contract(repository, path)
    )


def materialize_contract_source(
    out_root: Path, bound: BoundBaselineScenarioContract | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if bound is None:
        return None, None
    source_ref = write_cas_artifact(
        out_root, "scenario-contract-source", bound.source_bytes, suffix="json",
    )
    return {
        "status": "source-bound",
        "path": bound.source_path,
        "source_ref": source_ref,
        "normalized_ref": None,
        "semantic_sha256": None,
        "wrapper_count": None,
        "scenario_count": None,
    }, source_ref


__all__ = ["bind_execution_contract", "materialize_contract_source"]
