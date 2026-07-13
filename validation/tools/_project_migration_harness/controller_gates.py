from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .gate_authority import (
    candidate_authority,
    candidate_kind,
    candidate_verdict_payload,
    require_portable_id,
)
from .gate_diagnostics import normalize_gate_evidence
from .gate_evidence import write_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .ledger_candidate_state import latest_candidate_records


def record_candidate_gate(
    *, ledger: ProjectLedger, out_root: Path, out_root_rel: str,
    run_id: str, unit_id: str, candidate_artifact_id: str,
    record_id: str, kind: str, gate_family: str, status: str,
    verifier_id: str, diagnostics: list[Mapping[str, Any]],
) -> dict[str, Any]:
    require_portable_id(record_id, "record_id")
    expected_kind = candidate_kind(gate_family)
    if kind != expected_kind:
        raise ValueError("candidate gate kind is fixed by its family")
    if status != "failed":
        raise LedgerError(
            "direct gate recording cannot grant a pass; a host-owned verifier runner is required"
        )
    candidate = _candidate(ledger, run_id, unit_id, candidate_artifact_id)
    normalized = normalize_gate_evidence(
        gate_family=gate_family,
        status="failed",
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=str(candidate["content_sha256"]),
        diagnostics=diagnostics,
    )
    authority = candidate_authority(gate_family)
    evidence = candidate_verdict_payload(
        run_id=run_id,
        unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=str(candidate["content_sha256"]),
        gate_family=gate_family,
        status="failed",
        diagnostics=normalized["diagnostics"],
        candidate_set_sha256=None,
        source_evidence=(),
    )
    reference = write_content_addressed_json(
        out_root, f"candidate/{gate_family}", evidence
    )
    evidence_path = f"{out_root_rel}/{reference['path']}"
    ledger.record_candidate_failure(
        record_id=record_id,
        run_id=run_id,
        unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        evidence_path=evidence_path,
        evidence_sha256=reference["sha256"],
        gate_family=gate_family,
        metadata={"diagnostic_count": len(normalized["diagnostics"])},
    )
    state = next(
        (item for item in ledger.unit_states(run_id) if item["unit_id"] == unit_id),
        None,
    )
    if state is None:
        raise LedgerError("migration unit does not exist")
    if state["status"] != "retry-ready":
        ledger.mark_verification_failed(
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            failed_record_id=record_id,
        )
    return {
        "schema_version": 1,
        "status": "recorded",
        "record_id": record_id,
        "kind": kind,
        "gate_family": gate_family,
        "gate_status": "failed",
        "authority_id": authority,
        "candidate_artifact_id": candidate_artifact_id,
        "evidence": {**reference, "path": evidence_path},
        "semantic_gate": False,
        "proof_boundary": "fail-closed CLI path; passing verdicts require a host verifier adapter",
    }


def promote_verified_candidate(
    *, ledger: ProjectLedger, run_id: str, unit_id: str,
    candidate_artifact_id: str, verifier_record_id: str, gate_record_id: str,
) -> dict[str, Any]:
    ledger.promote_last_good_from_verification(
        run_id=run_id,
        unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        verifier_record_id=verifier_record_id,
        gate_record_id=gate_record_id,
    )
    return {
        "schema_version": 1,
        "status": "last-good",
        "run_id": run_id,
        "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "semantic_gate": True,
        "proof_boundary": "candidate-level host verifier and gate only",
    }


def promote_current_verified_candidate(
    *, ledger: ProjectLedger, run_id: str, unit_id: str,
    candidate_artifact_id: str,
) -> dict[str, Any]:
    with ledger.connect() as connection:
        records = latest_candidate_records(
            connection, run_id, unit_id, candidate_artifact_id,
        )
    by_family = {str(row["gate_family"]): row for row in records}
    final = by_family.get("final-verification")
    verifier = by_family.get("compile")
    if final is None or verifier is None:
        raise LedgerError("candidate promotion requires current compile and final records")
    return promote_verified_candidate(
        ledger=ledger, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        verifier_record_id=str(verifier["record_id"]),
        gate_record_id=str(final["record_id"]),
    )


def _candidate(
    ledger: ProjectLedger, run_id: str, unit_id: str, artifact_id: str
) -> dict[str, Any]:
    rows = ledger.orchestration_rows(run_id)["artifacts"]
    matches = [
        item for item in rows
        if item["unit_id"] == unit_id and item["artifact_id"] == artifact_id
    ]
    if len(matches) != 1 or matches[0]["status"] != "candidate":
        raise LedgerError("candidate artifact is not available for host verification")
    return matches[0]


__all__ = [
    "promote_current_verified_candidate", "promote_verified_candidate",
    "record_candidate_gate",
]
