from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .gate_authority import (
    derive_project_observation,
    project_authority,
    project_summary_payload,
)
from .gate_evidence import write_content_addressed_json
from .ledger import ProjectLedger


def record_host_project_observation(
    *, ledger: ProjectLedger, out_root: Path, out_root_rel: str,
    run_id: str, gate_kind: str, candidate_set_sha256: str,
    observation: Mapping[str, Any], diagnostic_codes: list[str] | None = None,
) -> dict[str, Any]:
    current_set = ledger.bind_current_candidate_set(run_id=run_id)
    if current_set != candidate_set_sha256:
        raise ValueError("host project verifier candidate set drifted")
    raw_payload = {
        "schema_version": 1,
        "artifact_kind": "host-project-gate-observation",
        "authority_id": project_authority(gate_kind),
        "run_id": run_id,
        "gate_kind": gate_kind,
        "candidate_set_sha256": current_set,
        "observation": dict(observation),
    }
    status = derive_project_observation(
        raw_payload,
        run_id=run_id,
        gate_kind=gate_kind,
        candidate_set_sha256=current_set,
    )
    raw = write_content_addressed_json(out_root, f"raw/{gate_kind}", raw_payload)
    raw_full = {**raw, "path": f"{out_root_rel}/{raw['path']}"}
    summary = project_summary_payload(
        run_id=run_id,
        gate_kind=gate_kind,
        status=status,
        candidate_set_sha256=current_set,
        source_evidence=[raw_full],
        diagnostic_codes=diagnostic_codes or [],
    )
    evidence = write_content_addressed_json(
        out_root, f"project/{gate_kind}", summary
    )
    evidence_full = f"{out_root_rel}/{evidence['path']}"
    record_id = _next_record_id(
        ledger, run_id=run_id, gate_kind=gate_kind,
        candidate_set_sha256=current_set,
    )
    epoch = ledger.record_project_gate(
        record_id=record_id,
        run_id=run_id,
        gate_kind=gate_kind,
        status=status,
        candidate_set_sha256=current_set,
        verifier_id=project_authority(gate_kind),
        evidence_path=evidence_full,
        evidence_sha256=str(evidence["sha256"]),
        metadata={
            "host_adapter": True,
            "raw_observation_sha256": raw["sha256"],
        },
    )
    return {
        "schema_version": 1,
        "status": "recorded",
        "gate_kind": gate_kind,
        "gate_status": status,
        "gate_epoch": epoch,
        "record_id": record_id,
        "authority_id": project_authority(gate_kind),
        "candidate_set_sha256": current_set,
        "raw_observation": raw_full,
        "evidence": {**evidence, "path": evidence_full},
        "semantic_gate": False,
    }


def record_host_project_final(
    *, ledger: ProjectLedger, out_root: Path, out_root_rel: str,
    run_id: str,
) -> dict[str, Any]:
    candidate_set = ledger.bind_current_candidate_set(run_id=run_id)
    sources = ledger.project_gate_bundle_sources(
        run_id=run_id, candidate_set_sha256=candidate_set
    )
    summary = project_summary_payload(
        run_id=run_id,
        gate_kind="final-verification",
        status="passed",
        candidate_set_sha256=candidate_set,
        source_evidence=sources,
    )
    evidence = write_content_addressed_json(
        out_root, "project/final-verification", summary
    )
    full_path = f"{out_root_rel}/{evidence['path']}"
    record_id = _next_record_id(
        ledger, run_id=run_id, gate_kind="final-verification",
        candidate_set_sha256=candidate_set,
    )
    epoch = ledger.record_project_gate(
        record_id=record_id,
        run_id=run_id,
        gate_kind="final-verification",
        status="passed",
        candidate_set_sha256=candidate_set,
        verifier_id=project_authority("final-verification"),
        evidence_path=full_path,
        evidence_sha256=str(evidence["sha256"]),
        metadata={"host_adapter": True, "source_evidence_count": len(sources)},
    )
    return {
        "schema_version": 1,
        "status": "recorded",
        "gate_kind": "final-verification",
        "gate_status": "passed",
        "gate_epoch": epoch,
        "record_id": record_id,
        "candidate_set_sha256": candidate_set,
        "evidence": {**evidence, "path": full_path},
        "semantic_gate": False,
    }


def _next_record_id(
    ledger: ProjectLedger, *, run_id: str, gate_kind: str,
    candidate_set_sha256: str,
) -> str:
    with ledger.connect() as connection:
        row = connection.execute(
            """select coalesce(max(gate_epoch),0) from project_gate_records
               where run_id=? and gate_kind=? and candidate_set_sha256=?""",
            (run_id, gate_kind, candidate_set_sha256),
        ).fetchone()
    epoch = int(row[0]) + 1
    return f"host-{gate_kind}-{candidate_set_sha256[:12]}-{epoch}"


__all__ = ["record_host_project_final", "record_host_project_observation"]
