from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .candidate_semantic_evidence import revalidate_candidate_semantic_verdict
from .gate_authority import (
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    candidate_verdict_payload,
)
from .gate_evidence import read_content_addressed_json, write_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .ledger_candidate_state import candidate_row, latest_candidate_records


def verify_candidate_final(
    *, ledger: ProjectLedger, out_root: Path, out_root_rel: str,
    run_id: str, unit_id: str, candidate_artifact_id: str,
    verification_scope: str = "wave-provisional",
) -> dict[str, Any]:
    candidate_set = ledger.bind_verification_candidate_set(
        run_id=run_id, scope=verification_scope,
    )
    with ledger.connect() as connection:
        candidate = candidate_row(
            connection, run_id, unit_id, candidate_artifact_id, active=True,
        )
        records = latest_candidate_records(
            connection, run_id, unit_id, candidate_artifact_id,
        )
    prerequisites = {
        str(row["gate_family"]): row for row in records
        if row["gate_family"] in CANDIDATE_REQUIRED_GATES
    }
    if set(prerequisites) != CANDIDATE_REQUIRED_GATES or any(
        row["status"] != "passed"
        or row["kind"] != candidate_kind(family)
        or row["verifier_id"] != candidate_authority(family)
        for family, row in prerequisites.items()
    ):
        raise LedgerError("candidate final verifier requires every latest prerequisite pass")
    sources = []
    for family in sorted(CANDIDATE_REQUIRED_GATES):
        row = prerequisites[family]
        payload = read_content_addressed_json(
            ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"]),
        )
        if payload.get("candidate_set_sha256") != candidate_set:
            raise LedgerError("candidate final prerequisite cohort drifted")
        if family != "compile" and not revalidate_candidate_semantic_verdict(
            ledger, payload,
        ):
            raise LedgerError(
                "candidate final requires strict host semantic evidence"
            )
        sources.append({
            "path": str(row["evidence_path"]),
            "sha256": str(row["evidence_sha256"]),
            "size_bytes": len(canonical_json_bytes(payload)),
        })
    verdict = candidate_verdict_payload(
        run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        candidate_sha256=str(candidate["content_sha256"]),
        gate_family="final-verification", status="passed", diagnostics=[],
        candidate_set_sha256=candidate_set, source_evidence=sources,
    )
    reference = write_content_addressed_json(
        out_root, "candidate/final-verification", verdict,
    )
    evidence_path = f"{out_root_rel}/{reference['path']}"
    record_id = "host-final-" + content_sha256({
        "run_id": run_id, "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_set_sha256": candidate_set,
        "prerequisite_sha256": [item["sha256"] for item in sources],
    })[:24]
    ledger._record_derived_verification(
        record_id=record_id, run_id=run_id, unit_id=unit_id,
        candidate_artifact_id=candidate_artifact_id,
        kind="gate", status="passed",
        verifier_id=candidate_authority("final-verification"),
        evidence_path=evidence_path,
        evidence_sha256=str(reference["sha256"]),
        gate_family="final-verification",
        metadata={"candidate_set_sha256": candidate_set},
    )
    return {
        "schema_version": 1, "status": "passed", "gate_status": "passed",
        "run_id": run_id, "unit_id": unit_id,
        "candidate_artifact_id": candidate_artifact_id,
        "candidate_set_sha256": candidate_set,
        "verification_scope": verification_scope, "record_id": record_id,
        "evidence": {**reference, "path": evidence_path},
        "semantic_gate": False,
        "proof_boundary": "candidate final gate only; promotion remains a separate ledger transition",
    }


__all__ = ["verify_candidate_final"]
