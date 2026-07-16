from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .candidate_semantic_evidence import revalidate_candidate_semantic_verdict
from .gate_candidate_sets import candidate_set_members
from .gate_evidence import read_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .ledger_candidate_state import latest_candidate_records
from .project_host_gates import record_host_project_observation


def record_project_candidate_aggregate_gates(
    *, ledger: ProjectLedger, run_id: str, out_root: Path,
    out_root_rel: str, candidate_set_sha256: str,
    candidate_members: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    aggregates = _validated_aggregates(
        ledger, run_id=run_id, candidate_set_sha256=candidate_set_sha256,
        candidate_members=candidate_members,
    )
    negative = record_host_project_observation(
        ledger=ledger, out_root=out_root, out_root_rel=out_root_rel,
        run_id=run_id, gate_kind="negative",
        candidate_set_sha256=candidate_set_sha256,
        observation={
            "case_count": aggregates["negative_case_count"],
            "unexpected_accept_count": aggregates["unexpected_accept_count"],
        },
        diagnostic_codes=(
            [] if aggregates["unexpected_accept_count"] == 0
            else ["project-negative-check-failed"]
        ),
    )
    unsafe_abi = record_host_project_observation(
        ledger=ledger, out_root=out_root, out_root_rel=out_root_rel,
        run_id=run_id, gate_kind="unsafe-alias-abi",
        candidate_set_sha256=candidate_set_sha256,
        observation={
            "check_count": aggregates["unsafe_abi_check_count"],
            "violation_count": aggregates["unsafe_abi_violation_count"],
        },
        diagnostic_codes=(
            [] if aggregates["unsafe_abi_violation_count"] == 0
            else ["project-unsafe-alias-abi-failed"]
        ),
    )
    passed = all(
        item.get("gate_status") == "passed" for item in (negative, unsafe_abi)
    )
    return {
        "schema_version": 1,
        "artifact_kind": "project-candidate-gate-aggregation",
        "status": "passed" if passed else "failed",
        "candidate_set_sha256": candidate_set_sha256,
        "aggregates": aggregates,
        "project_gate_records": {
            "negative": negative, "unsafe_alias_abi": unsafe_abi,
        },
        "semantic_gate": False,
    }


def _validated_aggregates(
    ledger: ProjectLedger, *, run_id: str, candidate_set_sha256: str,
    candidate_members: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    with ledger.connect() as connection:
        expected = candidate_set_members(connection, run_id, candidate_set_sha256)
        supplied = sorted(({
            "unit_id": str(item.get("unit_id")),
            "artifact_id": str(item.get("artifact_id")),
            "content_sha256": str(item.get("content_sha256")),
        } for item in candidate_members), key=lambda item: item["unit_id"])
        if supplied != expected:
            raise LedgerError("project candidate aggregate cohort drifted")
        totals = {
            "negative_case_count": 0,
            "unexpected_accept_count": 0,
            "unsafe_abi_check_count": 0,
            "unsafe_abi_violation_count": 0,
        }
        for member in expected:
            records = latest_candidate_records(
                connection, run_id, member["unit_id"], member["artifact_id"],
            )
            by_family = {str(row["gate_family"]): row for row in records}
            observations = {
                family: _passed_observation(
                    ledger, connection, by_family.get(family),
                    candidate_set_sha256,
                )
                for family in ("negative", "unsafe-alias", "abi-layout")
            }
            totals["negative_case_count"] += int(
                observations["negative"]["case_count"]
            )
            totals["unexpected_accept_count"] += int(
                observations["negative"]["unexpected_accept_count"]
            )
            totals["unsafe_abi_check_count"] += int(
                observations["unsafe-alias"]["unsafe_site_count"]
            ) + int(observations["abi-layout"]["check_count"])
            totals["unsafe_abi_violation_count"] += int(
                observations["unsafe-alias"]["unproven_alias_count"]
            ) + int(observations["abi-layout"]["mismatch_count"])
    return totals


def _passed_observation(
    ledger: ProjectLedger, connection: Any, row: Any,
    candidate_set_sha256: str,
) -> Mapping[str, Any]:
    if row is None or row["status"] != "passed":
        raise LedgerError("project candidate aggregate requires current passes")
    verdict = read_content_addressed_json(
        ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"]),
    )
    if (
        verdict.get("candidate_set_sha256") != candidate_set_sha256
        or not revalidate_candidate_semantic_verdict(
            ledger, verdict, connection=connection,
        )
    ):
        raise LedgerError("project candidate aggregate evidence is untrusted")
    source = verdict["source_evidence"][0]
    raw = read_content_addressed_json(
        ledger.path, str(source["path"]), str(source["sha256"]),
    )
    observation = raw.get("observation")
    if not isinstance(observation, Mapping):
        raise LedgerError("project candidate aggregate observation is invalid")
    return observation


__all__ = ["record_project_candidate_aggregate_gates"]
