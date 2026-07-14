from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .context_frontier_reference import context_frontier_reference as reference
from .context_frontier_refresh_reopen import read_canonical_reference
from .context_frontier_wave import validate_context_expansion_query
from .portfolio_integrity import canonical_dag, canonical_group


def validate_context_frontier_wave_inputs(
    portfolio: Mapping[str, Any], *,
    portfolio_reference: Mapping[str, Any],
    latest_dag: Mapping[str, Any], latest_dag_reference: Mapping[str, Any],
    context_bundle: Mapping[str, Any], context_bundle_reference: Mapping[str, Any],
    completed_wave_index: int, ledger: Any, harness_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    binding = ledger.require_portfolio_binding(portfolio)
    _reopen_equal(harness_root, portfolio_reference, portfolio, "portfolio")
    _reopen_equal(harness_root, latest_dag_reference, latest_dag, "latest DAG")
    _reopen_equal(
        harness_root, context_bundle_reference, context_bundle, "context bundle",
    )
    runtime_dag = _portfolio_bound_dag(latest_dag, portfolio)
    _require_completed_wave(
        ledger, str(portfolio.get("run_id")), runtime_dag, completed_wave_index,
    )
    return binding, runtime_dag


def failure_evidence_map(
    values: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result = {str(item.get("sha256")): item for item in values}
    if len(result) != len(values):
        raise ValueError("context frontier failure evidence is duplicated")
    return result


def expansion_query_map(
    values: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result = {}
    for value in values:
        query = validate_context_expansion_query(value)
        current = result.get(query["unit_id"])
        if current is None or query["query_epoch"] > current["query_epoch"]:
            result[query["unit_id"]] = query
    return result


def _require_completed_wave(
    ledger: Any, run_id: str, dag: Mapping[str, Any], wave_index: int,
) -> None:
    waves = dag.get("waves")
    if not isinstance(waves, list) or wave_index >= len(waves):
        raise ValueError("context frontier completed wave is missing")
    raw = waves[wave_index]
    expected = set(raw.get("group_ids", [])) if isinstance(raw, Mapping) else set()
    states = {
        item["unit_id"]: item for item in ledger.unit_states(run_id)
        if item.get("unit_id") in expected
    }
    if set(states) != expected or any(
        item.get("status") != "resume-ready"
        or item.get("resumable_status") != "last_good"
        or not isinstance(item.get("last_good_artifact_id"), str)
        for item in states.values()
    ):
        raise ValueError("context frontier previous wave is not last-good complete")
    ordered = sorted(expected)
    placeholders = ",".join("?" for _ in ordered)
    with ledger.connect() as connection:
        busy = connection.execute(
            f"""select 1 from migration_units u where u.run_id=?
               and u.unit_id in ({placeholders}) and (
                 exists(select 1 from leases l where l.run_id=u.run_id
                        and l.unit_id=u.unit_id and l.status='active') or
                 exists(select 1 from attempts a where a.run_id=u.run_id
                        and a.unit_id=u.unit_id and a.status='running')) limit 1""",
            (run_id, *ordered),
        ).fetchone()
    if busy is not None:
        raise ValueError("context frontier completed wave is not quiescent")


def _reopen_equal(
    root: Path, artifact: Mapping[str, Any], value: Mapping[str, Any], label: str,
) -> None:
    if read_canonical_reference(root, reference(artifact)) != dict(value):
        raise ValueError(f"context frontier {label} artifact drifted")


def _portfolio_bound_dag(
    dag: Mapping[str, Any], portfolio: Mapping[str, Any],
) -> dict[str, Any]:
    assignments = portfolio.get("assignments")
    groups = dag.get("groups")
    if not isinstance(assignments, list) or not isinstance(groups, list):
        raise ValueError("context frontier runtime DAG inputs are invalid")
    contexts: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise ValueError("context frontier runtime assignment is invalid")
        unit_id, context = assignment.get("unit_id"), assignment.get("context")
        if not isinstance(unit_id, str) or not isinstance(context, Mapping):
            raise ValueError("context frontier runtime assignment context is invalid")
        canonical_context = {
            key: value for key, value in context.items()
            if key not in {"byte_budget", "token_budget"}
        }
        previous = contexts.setdefault(unit_id, canonical_context)
        if previous != canonical_context:
            raise ValueError("context frontier runtime assignment contexts drifted")
    rebound = []
    for raw in groups:
        if not isinstance(raw, Mapping):
            raise ValueError("context frontier runtime DAG group is invalid")
        group_id, dependencies = raw.get("group_id"), raw.get("dependencies")
        if (
            not isinstance(group_id, str)
            or group_id not in contexts
            or not isinstance(dependencies, list)
        ):
            raise ValueError("context frontier runtime DAG group binding is invalid")
        payload, digest = canonical_group(raw, dependencies, contexts[group_id])
        rebound.append({**payload, "content_sha256": digest})
    payload = {**dict(dag), "groups": rebound}
    payload["dag_sha256"] = canonical_dag(payload, rebound)
    if payload["dag_sha256"] != portfolio.get("dag_sha256"):
        raise ValueError("context frontier runtime DAG does not match portfolio")
    return payload


__all__ = [
    "expansion_query_map", "failure_evidence_map",
    "validate_context_frontier_wave_inputs",
]
