from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_metadata
from .artifact_verification import verify_artifact_reference
from .ledger_run_contract import derive_migration_contract
from .orchestration_facts import read_artifact_reference
from .runtime_binding import compute_portfolio_binding


MAX_PORTFOLIO_ARTIFACT_BYTES = 512 * 1024 * 1024


def prepare_run_metadata(
    database_path: Path, metadata: Mapping[str, Any] | None, *, run_id: str,
    dag_sha256: str, assignments: list[Mapping[str, Any]],
    units: list[Mapping[str, Any]], portfolio_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    result = dict(metadata or {})
    artifacts = result.get("artifacts")
    reference = artifacts.get("portfolio") if isinstance(artifacts, Mapping) else None
    if reference is None:
        return result
    if not isinstance(reference, Mapping):
        raise ValueError("portfolio artifact reference is invalid")
    portfolio = _bound_portfolio(
        database_path, reference, portfolio_payload=portfolio_payload,
    )
    binding = compute_portfolio_binding(portfolio)
    if binding["run_id"] != run_id or binding["dag_sha256"] != dag_sha256:
        raise ValueError("portfolio run/DAG binding does not match create_run")
    expected_assignments = sorted(
        (str(item["unit_id"]), str(item["worker_id"]), str(item["role"]),
         str(item["out_root"]), int(item["max_attempts"])) for item in assignments
    )
    actual_assignments = sorted(
        (str(item["unit_id"]), str(item["worker_id"]), str(item["role"]),
         str(item["out_root"]), int(item["max_attempts"]))
        for item in portfolio["assignments"]
    )
    expected_units = sorted(
        (str(item["unit_id"]), str(item["group_id"]), int(item["wave_index"]),
         str(item["content_sha256"])) for item in units
    )
    actual_units = sorted(
        (str(item["unit_id"]), str(item["group_id"]), int(item["wave_index"]),
         str(item["content_sha256"])) for item in portfolio["ledger_units"]
    )
    if expected_assignments != actual_assignments or expected_units != actual_units:
        raise ValueError("portfolio assignment/unit binding does not match create_run")
    result["runtime_binding"] = binding
    migration_contract, _manifest = derive_migration_contract(
        database_path, artifacts, run_id=run_id, dag_sha256=dag_sha256,
        units=units,
    )
    result["migration_contract"] = migration_contract
    return result


def _bound_portfolio(
    database_path: Path, reference: Mapping[str, Any], *,
    portfolio_payload: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    if portfolio_payload is None:
        try:
            portfolio = json.loads(
                read_artifact_reference(
                    database_path.parent.parent, reference,
                ).decode("utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("portfolio artifact cannot bind the run") from error
        if not isinstance(portfolio, Mapping):
            raise ValueError("portfolio artifact must be an object")
        return portfolio
    digest, size = canonical_json_metadata(portfolio_payload)
    if (
        reference.get("sha256") != digest
        or reference.get("size_bytes") != size
        or size > MAX_PORTFOLIO_ARTIFACT_BYTES
    ):
        raise ValueError("in-memory portfolio does not match its artifact")
    verify_artifact_reference(
        database_path.parent.parent,
        reference,
        max_bytes=MAX_PORTFOLIO_ARTIFACT_BYTES,
    )
    return portfolio_payload


__all__ = ["MAX_PORTFOLIO_ARTIFACT_BYTES", "prepare_run_metadata"]
