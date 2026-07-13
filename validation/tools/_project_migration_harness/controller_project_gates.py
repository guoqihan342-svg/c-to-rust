from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_authority import (
    PROJECT_GATE_KINDS,
    derive_project_observation,
    project_authority,
    project_summary_payload,
    require_portable_id,
)
from .gate_evidence import (
    require_host_raw_reference,
    write_content_addressed_json,
)
from .ledger import LedgerError, ProjectLedger
from .orchestration_facts import read_artifact_reference


def record_project_gate_summary(
    *, ledger: ProjectLedger, out_root: Path, out_root_rel: str,
    run_id: str, record_id: str, gate_kind: str, status: str,
    candidate_set_sha256: str, verifier_id: str,
    source_evidence: Sequence[Mapping[str, Any]],
    diagnostic_codes: Sequence[str] = (),
) -> dict[str, Any]:
    require_portable_id(record_id, "record_id")
    if gate_kind not in PROJECT_GATE_KINDS:
        raise ValueError("project gate kind is invalid")
    if status not in {"passed", "failed"}:
        raise ValueError("legacy status is invalid")
    current_set = ledger.bind_current_candidate_set(run_id=run_id)
    if candidate_set_sha256 != current_set:
        raise LedgerError("caller candidate set is not the current immutable last-good set")
    authority = project_authority(gate_kind)
    if gate_kind == "final-verification":
        references = ledger.project_gate_bundle_sources(
            run_id=run_id, candidate_set_sha256=current_set
        )
        derived_status = "passed"
    else:
        references, payloads = _source_observations(
            out_root,
            out_root_rel,
            gate_kind,
            source_evidence,
        )
        if len(payloads) != 1:
            raise LedgerError("project gate requires one fixed-schema host observation")
        derived_status = derive_project_observation(
            payloads[0],
            run_id=run_id,
            gate_kind=gate_kind,
            candidate_set_sha256=current_set,
        )
        if derived_status == "passed":
            raise LedgerError(
                "direct project gate recording cannot grant a pass; run the host verifier adapter"
            )
    summary = project_summary_payload(
        run_id=run_id,
        gate_kind=gate_kind,
        status=derived_status,
        candidate_set_sha256=current_set,
        source_evidence=references,
        diagnostic_codes=diagnostic_codes,
    )
    reference = write_content_addressed_json(
        out_root, f"project/{gate_kind}", summary
    )
    full_path = f"{out_root_rel}/{reference['path']}"
    epoch = ledger.record_project_gate(
        record_id=record_id,
        run_id=run_id,
        gate_kind=gate_kind,
        status=derived_status,
        candidate_set_sha256=current_set,
        verifier_id=authority,
        evidence_path=full_path,
        evidence_sha256=reference["sha256"],
        metadata={"source_evidence_count": len(references)},
    )
    return {
        "schema_version": 1,
        "status": "recorded",
        "record_id": record_id,
        "gate_kind": gate_kind,
        "gate_epoch": epoch,
        "gate_status": derived_status,
        "authority_id": authority,
        "candidate_set_sha256": current_set,
        "evidence": {**reference, "path": full_path},
        "semantic_gate": False,
        "proof_boundary": "status and verifier identity derived by fixed host gate adapters",
    }


def complete_verified_project(
    *, ledger: ProjectLedger, run_id: str, candidate_set_sha256: str,
) -> dict[str, Any]:
    current_set = ledger.bind_current_candidate_set(run_id=run_id)
    if candidate_set_sha256 != current_set:
        raise LedgerError("completion candidate set is stale or caller-supplied")
    ledger.complete_project_run(
        run_id=run_id, candidate_set_sha256=current_set
    )
    return {
        "schema_version": 1,
        "status": "completed",
        "run_id": run_id,
        "candidate_set_sha256": current_set,
        "semantic_gate": True,
        "proof_boundary": "latest host-owned project gates on the current immutable candidate set",
    }


def _source_observations(
    out_root: Path,
    out_root_rel: str,
    gate_kind: str,
    source_evidence: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(source_evidence, Sequence) or len(source_evidence) != 1:
        raise LedgerError("project gate requires exactly one host observation")
    harness_root = _root(out_root, out_root_rel)
    references: list[dict[str, Any]] = []
    payloads: list[dict[str, Any]] = []
    for source in source_evidence:
        data = read_artifact_reference(harness_root, source)
        reference = {
            "path": str(source["path"]),
            "sha256": str(source["sha256"]),
            "size_bytes": len(data),
        }
        require_host_raw_reference(reference, gate_kind)
        try:
            payload = json.loads(data.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise LedgerError("host project gate observation is not JSON") from error
        if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
            raise LedgerError("host project gate observation is not canonical JSON")
        references.append(reference)
        payloads.append(payload)
    return references, payloads


def _root(out_root: Path, out_root_rel: str) -> Path:
    parts = tuple(Path(out_root_rel).parts)
    candidate = out_root.resolve()
    for _ in parts:
        candidate = candidate.parent
    if candidate.joinpath(*parts).resolve() != out_root.resolve():
        raise ValueError("out_root/out_root_rel binding is inconsistent")
    return candidate


__all__ = ["complete_verified_project", "record_project_gate_summary"]
