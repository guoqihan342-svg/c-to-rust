from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_authority import (
    CANDIDATE_GATE_FAMILIES,
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    validate_candidate_verdict,
)
from .gate_candidate_sets import candidate_set_manifest
from .gate_evidence import read_content_addressed_json
from .ledger_candidate_state import latest_candidate_records
from .ledger_security import LedgerError
from .ledger_verifier import _verify_candidate_sources


def require_project_final_candidate_passes(
    ledger: Any, connection: Any, run_id: str, candidate_set_sha256: str,
) -> None:
    manifest = candidate_set_manifest(
        connection, run_id, candidate_set_sha256,
    )
    if manifest.get("scope") != "project-final":
        raise LedgerError("project completion requires a project-final candidate set")
    for member in manifest["members"]:
        _require_member_passes(
            ledger, connection, run_id, candidate_set_sha256, member,
        )


def _require_member_passes(
    ledger: Any, connection: Any, run_id: str, candidate_set_sha256: str,
    member: Mapping[str, str],
) -> None:
    unit_id = member["unit_id"]
    artifact_id = member["artifact_id"]
    candidate_sha256 = member["content_sha256"]
    records = latest_candidate_records(
        connection, run_id, unit_id, artifact_id,
    )
    by_family = {str(row["gate_family"]): row for row in records}
    if set(by_family) != CANDIDATE_GATE_FAMILIES:
        raise LedgerError(
            "project-final candidate gate bundle is incomplete"
        )
    payloads: dict[str, Mapping[str, Any]] = {}
    for family in sorted(CANDIDATE_GATE_FAMILIES):
        row = by_family[family]
        if (
            row["status"] != "passed"
            or row["kind"] != candidate_kind(family)
            or row["verifier_id"] != candidate_authority(family)
        ):
            raise LedgerError(
                "project-final candidate gate is not a host-owned pass"
            )
        payload = read_content_addressed_json(
            ledger.path,
            str(row["evidence_path"]),
            str(row["evidence_sha256"]),
        )
        validate_candidate_verdict(
            payload,
            run_id=run_id,
            unit_id=unit_id,
            candidate_artifact_id=artifact_id,
            candidate_sha256=candidate_sha256,
            gate_family=family,
            candidate_set_sha256=candidate_set_sha256,
            status="passed",
            verifier_id=str(row["verifier_id"]),
            kind=str(row["kind"]),
        )
        _verify_candidate_sources(
            ledger, connection, payload, status="passed",
        )
        payloads[family] = payload
    _require_fresh_final(by_family, payloads)


def _require_fresh_final(
    records: Mapping[str, Any], payloads: Mapping[str, Mapping[str, Any]],
) -> None:
    final = records["final-verification"]
    prerequisites = [records[family] for family in CANDIDATE_REQUIRED_GATES]
    if int(final["ledger_rowid"]) <= max(
        int(row["ledger_rowid"]) for row in prerequisites
    ):
        raise LedgerError(
            "project-final candidate final gate predates a prerequisite"
        )
    expected = sorted(({
        "path": str(records[family]["evidence_path"]),
        "sha256": str(records[family]["evidence_sha256"]),
        "size_bytes": len(canonical_json_bytes(payloads[family])),
    } for family in CANDIDATE_REQUIRED_GATES), key=lambda item: item["path"])
    actual = sorted(
        payloads["final-verification"]["source_evidence"],
        key=lambda item: item["path"],
    )
    if actual != expected:
        raise LedgerError(
            "project-final candidate final gate is stale"
        )


__all__ = ["require_project_final_candidate_passes"]
