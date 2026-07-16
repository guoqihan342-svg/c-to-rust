from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .gate_candidate_sets import (
    assert_current_candidate_set, candidate_set_manifest,
)
from .gate_evidence import read_content_addressed_json
from .ledger_project_gates import _require_latest_project_passes
from .ledger_schema import _require_sha256
from .ledger_security import LedgerError
from .project_final_barrier import require_project_final_candidate_passes


def reopen_completion_context(
    ledger: Any, connection: Any, *, run_id: str,
    candidate_set_sha256: str,
    completed: bool = False,
) -> dict[str, Any]:
    candidate_set = _require_sha256(
        candidate_set_sha256, "candidate_set_sha256",
    )
    if completed:
        _assert_completed_cohort(connection, run_id, candidate_set)
    else:
        assert_current_candidate_set(
            connection, run_id, candidate_set, database_path=ledger.path,
        )
    require_project_final_candidate_passes(
        ledger, connection, run_id, candidate_set,
    )
    records = _require_latest_project_passes(
        ledger, connection, run_id, candidate_set, include_final=True,
    )
    if len({str(row["verifier_id"]) for row, _ in records}) < 2:
        raise LedgerError("project completion requires independent host authorities")
    generation = _integration_generation(
        ledger, run_id, candidate_set, records,
    )
    gate_bundle = content_sha256({
        "schema_version": 1,
        "run_id": run_id,
        "cohort_sha256": candidate_set,
        "generation_sha256": generation,
        "records": [
            {
                "gate_kind": str(row["gate_kind"]),
                "gate_epoch": int(row["gate_epoch"]),
                "record_id": str(row["record_id"]),
                "verifier_id": str(row["verifier_id"]),
                "evidence_sha256": str(row["evidence_sha256"]),
            }
            for row, _ in records
        ],
    })
    return {
        "cohort_sha256": candidate_set,
        "generation_sha256": generation,
        "gate_bundle_sha256": gate_bundle,
        "records": records,
    }


def _integration_generation(
    ledger: Any, run_id: str, candidate_set: str,
    records: list[tuple[Any, Mapping[str, Any]]],
) -> str:
    matches = [payload for row, payload in records if row["gate_kind"] == "integration"]
    if len(matches) != 1:
        raise LedgerError("completion integration generation is missing or ambiguous")
    sources = matches[0].get("source_evidence")
    if not isinstance(sources, list) or len(sources) != 1:
        raise LedgerError("completion integration generation source is invalid")
    source = sources[0]
    if not isinstance(source, Mapping):
        raise LedgerError("completion integration generation source is invalid")
    raw = read_content_addressed_json(
        ledger.path, str(source.get("path")), str(source.get("sha256")),
    )
    observation = raw.get("observation")
    try:
        generation = _require_sha256(
            observation.get("manifest_sha256")
            if isinstance(observation, Mapping) else "",
            "completion_generation_sha256",
        )
    except ValueError as error:
        raise LedgerError("completion integration generation binding is invalid") from error
    if (
        raw.get("artifact_kind") != "host-project-gate-observation"
        or raw.get("run_id") != run_id
        or raw.get("gate_kind") != "integration"
        or raw.get("candidate_set_sha256") != candidate_set
        or not isinstance(observation, Mapping)
        or observation.get("managed_project_unchanged") is not True
        or observation.get("interface_complete") is not True
    ):
        raise LedgerError("completion integration generation binding drifted")
    return generation


def _assert_completed_cohort(
    connection: Any, run_id: str, candidate_set: str,
) -> None:
    manifest = candidate_set_manifest(connection, run_id, candidate_set)
    if manifest.get("scope") != "project-final":
        raise LedgerError("completed project cohort is not project-final")
    expected = {
        (item["unit_id"], item["artifact_id"]) for item in manifest["members"]
    }
    actual = {
        (str(row["unit_id"]), str(row["last_good_artifact_id"]))
        for row in connection.execute(
            """select unit_id,last_good_artifact_id from migration_units
               where run_id=? and status='completed'
               and resumable_status='terminal'""", (run_id,),
        ).fetchall()
    }
    if actual != expected:
        raise LedgerError("completed project cohort drifted from last-good units")


__all__ = ["reopen_completion_context"]
