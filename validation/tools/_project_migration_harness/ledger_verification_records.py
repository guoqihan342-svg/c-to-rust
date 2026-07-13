from __future__ import annotations

from typing import Any, Mapping

from .artifacts import canonical_json_bytes
from .candidate_semantic_evidence import revalidate_candidate_semantic_verdict
from .gate_authority import (
    CANDIDATE_GATE_FAMILIES,
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    require_portable_id,
    validate_candidate_verdict,
)
from .gate_candidate_sets import (
    assert_verification_candidate_set,
    candidate_set_members,
)
from .gate_evidence import read_content_addressed_json
from .ledger_candidate_state import (
    candidate_row,
    latest_candidate_records,
)
from .ledger_schema import _json, _now_text, _require_repo_path, _require_sha256, atomic
from .ledger_security import LedgerError
from .ledger_verification_sources import verify_candidate_sources


def record_derived_verification(
    ledger: Any, *, record_id: str, run_id: str, unit_id: str,
    candidate_artifact_id: str, kind: str, status: str, verifier_id: str,
    evidence_path: str, evidence_sha256: str, gate_family: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> int:
    require_portable_id(record_id, "record_id")
    family = gate_family or str((metadata or {}).get("gate_family", ""))
    if family not in CANDIDATE_GATE_FAMILIES or status not in {"passed", "failed"}:
        raise ValueError("host verification family/status is invalid")
    if kind != candidate_kind(family) or verifier_id != candidate_authority(family):
        raise LedgerError("candidate verifier identity is fixed by the host gate family")
    evidence_path = _require_repo_path(evidence_path, "evidence_path")
    evidence_sha256 = _require_sha256(evidence_sha256, "evidence_sha256")
    with ledger.connect() as connection, atomic(connection):
        candidate = candidate_row(
            connection, run_id, unit_id, candidate_artifact_id,
        )
        payload = read_content_addressed_json(
            ledger.path, evidence_path, evidence_sha256,
        )
        candidate_set = payload.get("candidate_set_sha256")
        if candidate_set is not None and not isinstance(candidate_set, str):
            raise LedgerError("candidate gate candidate set binding is invalid")
        if status == "passed" and candidate_set is None:
            raise LedgerError("candidate pass is missing its verification candidate set")
        if candidate_set is not None:
            assert_verification_candidate_set(
                connection, run_id, candidate_set, database_path=ledger.path,
            )
            members = candidate_set_members(connection, run_id, candidate_set)
            if not any(
                item["unit_id"] == unit_id
                and item["artifact_id"] == candidate_artifact_id
                and item["content_sha256"] == candidate["content_sha256"]
                for item in members
            ):
                raise LedgerError(
                    "candidate pass is outside its verification candidate set"
                )
        validate_candidate_verdict(
            payload,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            candidate_sha256=str(candidate["content_sha256"]),
            gate_family=family,
            candidate_set_sha256=candidate_set,
            status=status,
            verifier_id=verifier_id,
            kind=kind,
        )
        verify_candidate_sources(ledger, connection, payload, status=status)
        if family == "final-verification" and status == "passed":
            _verify_final_prerequisites(
                ledger, connection, payload, run_id, unit_id,
                candidate_artifact_id, str(candidate["content_sha256"]),
                str(candidate_set),
            )
        metadata_json = _json(metadata)
        existing = connection.execute(
            "select * from verifier_records where record_id=?", (record_id,),
        ).fetchone()
        if existing is not None:
            expected = {
                "run_id": run_id,
                "unit_id": unit_id,
                "candidate_artifact_id": candidate_artifact_id,
                "gate_family": family,
                "kind": kind,
                "status": status,
                "verifier_id": verifier_id,
                "evidence_path": evidence_path,
                "evidence_sha256": evidence_sha256,
                "metadata_json": metadata_json,
            }
            if any(existing[key] != value for key, value in expected.items()):
                raise LedgerError(
                    "candidate verifier record id replay changed its binding"
                )
            return int(existing["gate_epoch"])
        epoch = int(connection.execute(
            """select coalesce(max(gate_epoch),0)+1 from verifier_records
               where run_id=? and unit_id=? and candidate_artifact_id=? and gate_family=?""",
            (run_id, unit_id, candidate_artifact_id, family),
        ).fetchone()[0])
        connection.execute(
            """insert into verifier_records(record_id,run_id,unit_id,candidate_artifact_id,
               gate_family,gate_epoch,kind,status,verifier_id,evidence_path,evidence_sha256,
               finished_at,metadata_json) values (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record_id, run_id, unit_id, candidate_artifact_id, family, epoch, kind,
             status, verifier_id, evidence_path, evidence_sha256, _now_text(),
             metadata_json),
        )
        return epoch


def _verify_final_prerequisites(
    ledger: Any, connection: Any, payload: Mapping[str, Any], run_id: str,
    unit_id: str, candidate_artifact_id: str, candidate_sha256: str,
    candidate_set: str,
) -> None:
    prerequisites = {
        str(row["gate_family"]): row
        for row in latest_candidate_records(
            connection, run_id, unit_id, candidate_artifact_id,
        )
        if row["gate_family"] in CANDIDATE_REQUIRED_GATES
    }
    if set(prerequisites) != CANDIDATE_REQUIRED_GATES or any(
        row["status"] != "passed"
        or row["kind"] != candidate_kind(family_name)
        or row["verifier_id"] != candidate_authority(family_name)
        for family_name, row in prerequisites.items()
    ):
        raise LedgerError("final candidate gate requires every latest host verifier pass")
    validated = {}
    for family_name, row in prerequisites.items():
        prerequisite = read_content_addressed_json(
            ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"]),
        )
        validate_candidate_verdict(
            prerequisite,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
            candidate_sha256=candidate_sha256,
            gate_family=family_name,
            candidate_set_sha256=candidate_set,
            status="passed",
            verifier_id=str(row["verifier_id"]),
            kind=str(row["kind"]),
        )
        verify_candidate_sources(
            ledger, connection, prerequisite, status="passed",
        )
        if family_name != "compile" and not revalidate_candidate_semantic_verdict(
            ledger, prerequisite, connection=connection,
        ):
            raise LedgerError(
                "final candidate gate requires strict host semantic evidence"
            )
        validated[family_name] = prerequisite
    expected_sources = sorted(({
        "path": str(prerequisites[name]["evidence_path"]),
        "sha256": str(prerequisites[name]["evidence_sha256"]),
        "size_bytes": len(canonical_json_bytes(validated[name])),
    } for name in CANDIDATE_REQUIRED_GATES), key=lambda item: item["path"])
    actual_sources = sorted(
        payload["source_evidence"], key=lambda item: item["path"],
    )
    if actual_sources != expected_sources:
        raise LedgerError(
            "final candidate gate is not bound to the latest prerequisite evidence"
        )


__all__ = ["record_derived_verification"]
