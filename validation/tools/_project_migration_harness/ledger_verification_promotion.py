from __future__ import annotations

from typing import Any

from .candidate_semantic_evidence import revalidate_candidate_semantic_verdict
from .candidate_admission_ledger import require_semantic_candidate_admission
from .candidate_provider_execution import require_candidate_provider_execution
from .gate_authority import (
    CANDIDATE_GATE_FAMILIES,
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    validate_candidate_verdict,
)
from .gate_candidate_sets import bind_verification_candidate_set
from .gate_evidence import read_content_addressed_json
from .ledger_candidate_state import candidate_row, latest_candidate_records
from .ledger_schema import _now_text, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import TransitionAuthority, load_unit_projection
from .ledger_transition_commands import host_verifier_promoted_command
from .ledger_transition_policy import (
    stable_transition_command_id, transition_evidence_sha256,
)
from .ledger_verification_sources import verify_candidate_sources


def promote_last_good(
    ledger: Any, *, run_id: str, unit_id: str, candidate_artifact_id: str,
    verifier_record_id: str, gate_record_id: str,
) -> None:
    if verifier_record_id == gate_record_id:
        raise LedgerError("last-good promotion requires distinct verifier and gate records")
    with ledger.connect() as connection, atomic(connection):
        candidate = candidate_row(
            connection, run_id, unit_id, candidate_artifact_id, active=True,
        )
        require_semantic_candidate_admission(
            ledger, connection, run_id, dict(candidate),
        )
        candidate_set = bind_verification_candidate_set(
            connection, run_id, database_path=ledger.path,
        )
        require_candidate_provider_execution(
            ledger, connection,
            run_id=run_id, unit_id=unit_id,
            candidate_artifact_id=candidate_artifact_id,
        )
        records = latest_candidate_records(
            connection, run_id, unit_id, candidate_artifact_id,
        )
        by_family = {str(row["gate_family"]): row for row in records}
        if set(by_family) != CANDIDATE_GATE_FAMILIES:
            raise LedgerError("last-good promotion requires every latest candidate gate")
        verifier = next(
            (row for row in records if row["record_id"] == verifier_record_id), None,
        )
        final = by_family.get("final-verification")
        if (
            verifier is None
            or verifier["gate_family"] not in CANDIDATE_REQUIRED_GATES
            or final is None
            or final["record_id"] != gate_record_id
            or int(final["ledger_rowid"]) <= max(
                int(by_family[family]["ledger_rowid"])
                for family in CANDIDATE_REQUIRED_GATES
            )
        ):
            raise LedgerError(
                "promotion requires a fresh final gate after every latest verifier decision"
            )
        for family, row in by_family.items():
            if (
                row["status"] != "passed"
                or row["kind"] != candidate_kind(family)
                or row["verifier_id"] != candidate_authority(family)
            ):
                raise LedgerError("a latest candidate gate is not a host-owned pass")
            payload = read_content_addressed_json(
                ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"]),
            )
            validate_candidate_verdict(
                payload,
                run_id=run_id,
                unit_id=unit_id,
                candidate_artifact_id=candidate_artifact_id,
                candidate_sha256=str(candidate["content_sha256"]),
                gate_family=family,
                candidate_set_sha256=candidate_set,
                status="passed",
                verifier_id=str(row["verifier_id"]),
                kind=str(row["kind"]),
            )
            verify_candidate_sources(
                ledger, connection, payload, status="passed",
            )
            if family in CANDIDATE_REQUIRED_GATES - {"compile"} and not (
                revalidate_candidate_semantic_verdict(
                    ledger, payload, connection=connection,
                )
            ):
                raise LedgerError(
                    "last-good promotion requires strict host semantic evidence"
                )
        if verifier["verifier_id"] == final["verifier_id"]:
            raise LedgerError("final verification must use an independent host authority")
        command_id = stable_transition_command_id(
            "host-verifier-promoted", run_id, unit_id, candidate_artifact_id,
            gate_record_id,
        )
        authority = TransitionAuthority(connection)
        expected = authority.bound_unit_expected(
            run_id=run_id, unit_id=unit_id,
            command_kind="host_verifier_promoted", command_id=command_id,
        ) or load_unit_projection(connection, run_id, unit_id)
        now = _now_text()
        evidence = transition_evidence_sha256({
            "candidate_artifact_id": candidate_artifact_id,
            "candidate_sha256": candidate["content_sha256"],
            "candidate_set_sha256": candidate_set,
            "verifier_record_id": verifier_record_id,
            "gate_record_id": gate_record_id,
        })
        authority.apply(
            host_verifier_promoted_command(
                command_id=command_id, run_id=run_id, unit_id=unit_id,
                expected=expected, evidence_sha256=evidence,
                attempt_id=str(candidate["attempt_id"]),
                candidate_artifact_id=candidate_artifact_id,
            ),
            created_at=now,
        )
__all__ = ["promote_last_good"]
