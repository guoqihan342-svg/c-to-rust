from __future__ import annotations

import json
from typing import Any

from .execution_evidence import validate_provider_execution_evidence
from .ledger_security import LedgerError


def require_candidate_provider_execution(
    ledger: Any, connection: Any, *, run_id: str, unit_id: str,
    candidate_artifact_id: str,
) -> None:
    candidate = connection.execute(
        """select a.attempt_id,a.worker_id,a.fencing_token,t.role,
                  t.metadata_json as attempt_metadata_json
           from artifacts a join attempts t on t.attempt_id=a.attempt_id
           where a.run_id=? and a.unit_id=? and a.artifact_id=?
             and a.kind='rust-candidate' and a.status='candidate'""",
        (run_id, unit_id, candidate_artifact_id),
    ).fetchone()
    if candidate is None:
        raise LedgerError("candidate provider execution owner is missing")
    try:
        metadata = json.loads(str(candidate["attempt_metadata_json"]))
    except json.JSONDecodeError as error:
        raise LedgerError("candidate attempt metadata is invalid") from error
    if not isinstance(metadata, dict):
        raise LedgerError("candidate attempt metadata is invalid")
    rows = connection.execute(
        """select * from artifacts where run_id=? and unit_id=? and attempt_id=?
           and kind='provider-execution' and status='written' order by rowid""",
        (run_id, unit_id, candidate["attempt_id"]),
    ).fetchall()
    if metadata.get("command_started") is True and len(rows) != 1:
        raise LedgerError(
            "model-started candidate requires one provider execution artifact"
        )
    if not rows:
        return
    if len(rows) != 1:
        raise LedgerError("candidate provider execution artifact is ambiguous")
    try:
        validate_provider_execution_evidence(
            ledger.path,
            dict(rows[0]),
            run_id=run_id,
            unit_id=unit_id,
            attempt_id=str(candidate["attempt_id"]),
            worker_id=str(candidate["worker_id"]),
            fencing_token=int(candidate["fencing_token"]),
            role=str(candidate["role"]),
        )
    except (OSError, ValueError, LedgerError) as error:
        raise LedgerError("provider execution evidence revalidation failed") from error


__all__ = ["require_candidate_provider_execution"]
