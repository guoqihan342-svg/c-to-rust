from __future__ import annotations

import json
from typing import Any, Mapping

from .execution_evidence import validate_provider_execution_evidence
from .gate_authority import (
    CANDIDATE_GATE_FAMILIES,
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    require_portable_id,
    validate_candidate_verdict,
)
from .gate_evidence import read_content_addressed_json
from .ledger_schema import _json, _now_text, _require_repo_path, _require_sha256, atomic
from .ledger_security import LedgerError


class HostVerifierMixin:
    def record_host_verification(
        self, *, record_id: str, run_id: str, unit_id: str, candidate_artifact_id: str,
        kind: str, status: str, verifier_id: str, evidence_path: str,
        evidence_sha256: str, gate_family: str | None = None,
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
        with self.connect() as connection, atomic(connection):
            candidate = _candidate(connection, run_id, unit_id, candidate_artifact_id)
            payload = read_content_addressed_json(self.path, evidence_path, evidence_sha256)
            validate_candidate_verdict(
                payload,
                run_id=run_id,
                unit_id=unit_id,
                candidate_artifact_id=candidate_artifact_id,
                candidate_sha256=str(candidate["content_sha256"]),
                gate_family=family,
                status=status,
                verifier_id=verifier_id,
                kind=kind,
            )
            if family == "final-verification" and status == "passed":
                prerequisites = {
                    str(row["gate_family"]): row
                    for row in _latest_candidate_records(
                        connection, run_id, unit_id, candidate_artifact_id
                    )
                    if row["gate_family"] in CANDIDATE_REQUIRED_GATES
                }
                if set(prerequisites) != CANDIDATE_REQUIRED_GATES or any(
                    row["status"] != "passed"
                    or row["kind"] != candidate_kind(family_name)
                    or row["verifier_id"] != candidate_authority(family_name)
                    for family_name, row in prerequisites.items()
                ):
                    raise LedgerError(
                        "final candidate gate requires every latest host verifier pass"
                    )
                for family_name, row in prerequisites.items():
                    prerequisite = read_content_addressed_json(
                        self.path,
                        str(row["evidence_path"]),
                        str(row["evidence_sha256"]),
                    )
                    validate_candidate_verdict(
                        prerequisite,
                        run_id=run_id,
                        unit_id=unit_id,
                        candidate_artifact_id=candidate_artifact_id,
                        candidate_sha256=str(candidate["content_sha256"]),
                        gate_family=family_name,
                        status="passed",
                        verifier_id=str(row["verifier_id"]),
                        kind=str(row["kind"]),
                    )
            epoch = int(connection.execute(
                """select coalesce(max(gate_epoch),0)+1 from verifier_records
                   where run_id=? and unit_id=? and candidate_artifact_id=? and gate_family=?""",
                (run_id, unit_id, candidate_artifact_id, family),
            ).fetchone()[0])
            connection.execute(
                """insert into verifier_records(record_id,run_id,unit_id,candidate_artifact_id,
                   gate_family,gate_epoch,kind,status,verifier_id,evidence_path,evidence_sha256,
                   finished_at,metadata_json) values (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, run_id, unit_id, candidate_artifact_id, family, epoch, kind, status,
                 verifier_id, evidence_path, evidence_sha256, _now_text(), _json(metadata)),
            )
            return epoch

    def promote_last_good_from_verification(
        self, *, run_id: str, unit_id: str, candidate_artifact_id: str,
        verifier_record_id: str, gate_record_id: str,
    ) -> None:
        if verifier_record_id == gate_record_id:
            raise LedgerError("last-good promotion requires distinct verifier and gate records")
        with self.connect() as connection, atomic(connection):
            candidate = _candidate(connection, run_id, unit_id, candidate_artifact_id, active=True)
            execution_rows = connection.execute(
                """select * from artifacts where run_id=? and unit_id=? and attempt_id=?
                   and kind='provider-execution' and status='written' order by rowid""",
                (run_id, unit_id, candidate["attempt_id"]),
            ).fetchall()
            attempt_metadata = json.loads(str(candidate["attempt_metadata_json"]))
            command_started = (
                isinstance(attempt_metadata, dict)
                and attempt_metadata.get("command_started") is True
            )
            if command_started and len(execution_rows) != 1:
                raise LedgerError("model-started candidate requires one provider execution artifact")
            if execution_rows:
                if len(execution_rows) != 1:
                    raise LedgerError("candidate provider execution artifact is ambiguous")
                try:
                    validate_provider_execution_evidence(
                        self.path,
                        dict(execution_rows[0]),
                        run_id=run_id,
                        unit_id=unit_id,
                        attempt_id=str(candidate["attempt_id"]),
                        worker_id=str(candidate["worker_id"]),
                        fencing_token=int(candidate["fencing_token"]),
                        role=str(candidate["role"]),
                    )
                except (OSError, ValueError) as error:
                    raise LedgerError("provider execution evidence revalidation failed") from error
            records = _latest_candidate_records(
                connection, run_id, unit_id, candidate_artifact_id
            )
            by_family = {str(row["gate_family"]): row for row in records}
            if set(by_family) != CANDIDATE_GATE_FAMILIES:
                raise LedgerError("last-good promotion requires every latest candidate gate")
            verifier = next(
                (row for row in records if row["record_id"] == verifier_record_id), None
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
                    self.path, str(row["evidence_path"]), str(row["evidence_sha256"])
                )
                validate_candidate_verdict(
                    payload,
                    run_id=run_id,
                    unit_id=unit_id,
                    candidate_artifact_id=candidate_artifact_id,
                    candidate_sha256=str(candidate["content_sha256"]),
                    gate_family=family,
                    status="passed",
                    verifier_id=str(row["verifier_id"]),
                    kind=str(row["kind"]),
                )
            if verifier["verifier_id"] == final["verifier_id"]:
                raise LedgerError("final verification must use an independent host authority")
            unit = connection.execute(
                "select status from migration_units where run_id=? and unit_id=?", (run_id, unit_id),
            ).fetchone()
            if not unit:
                raise LedgerError("migration unit does not exist")
            now = _now_text()
            connection.execute(
                """update migration_units set last_good_artifact_id=?,status='resume-ready',
                   resumable_status='last_good',updated_at=? where run_id=? and unit_id=?""",
                (candidate_artifact_id, now, run_id, unit_id),
            )
            connection.execute(
                """insert into transitions(run_id,unit_id,from_status,to_status,reason,attempt_id,
                   fencing_token,created_at) values (?,?,?,'resume-ready','host_verifier_promoted',?,null,?)""",
                (run_id, unit_id, unit["status"], candidate["attempt_id"], now),
            )

    def mark_verification_failed(
        self, *, run_id: str, unit_id: str, candidate_artifact_id: str,
        failed_record_id: str,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            failed = connection.execute(
                """select v.status,v.gate_family,v.evidence_path,v.evidence_sha256,
                          a.attempt_id,a.content_sha256,t.status as attempt_status
                   from verifier_records v join artifacts a
                     on a.run_id=v.run_id and a.artifact_id=v.candidate_artifact_id
                    and a.unit_id=v.unit_id
                   join attempts t on t.attempt_id=a.attempt_id
                   where v.record_id=? and v.run_id=? and v.unit_id=?
                     and v.candidate_artifact_id=?
                     and v.gate_epoch=(select max(newer.gate_epoch) from verifier_records newer
                         where newer.run_id=v.run_id and newer.unit_id=v.unit_id
                           and newer.candidate_artifact_id=v.candidate_artifact_id
                           and newer.gate_family=v.gate_family)""",
                (failed_record_id, run_id, unit_id, candidate_artifact_id),
            ).fetchone()
            if not failed or failed["status"] != "failed" or failed["attempt_status"] != "completed":
                raise LedgerError("retry requires the latest failed host verification record")
            read_content_addressed_json(
                self.path, str(failed["evidence_path"]), str(failed["evidence_sha256"])
            )
            unit = connection.execute(
                "select status from migration_units where run_id=? and unit_id=?", (run_id, unit_id),
            ).fetchone()
            if not unit:
                raise LedgerError("migration unit does not exist")
            now = _now_text()
            connection.execute(
                """update migration_units set status='retry-ready',resumable_status='retryable',
                   last_good_artifact_id=case when last_good_artifact_id=? then null
                                              else last_good_artifact_id end,
                   updated_at=? where run_id=? and unit_id=?""",
                (candidate_artifact_id, now, run_id, unit_id),
            )
            connection.execute(
                """insert into transitions(run_id,unit_id,from_status,to_status,reason,
                   attempt_id,fencing_token,created_at)
                   values (?,?,?,'retry-ready','host_verification_failed',?,null,?)""",
                (run_id, unit_id, unit["status"], failed["attempt_id"], now),
            )


def _candidate(
    connection: Any, run_id: str, unit_id: str, artifact_id: str, *, active: bool = False,
) -> Any:
    row = connection.execute(
        """select a.attempt_id,a.worker_id,a.fencing_token,a.status,a.content_sha256,
                  t.status as attempt_status,t.role,t.metadata_json as attempt_metadata_json,
                  r.status as run_status
           from artifacts a join attempts t on t.attempt_id=a.attempt_id
           join project_runs r on r.run_id=a.run_id
           where a.run_id=? and a.unit_id=? and a.artifact_id=?
             and a.rowid=(select max(newer.rowid) from artifacts newer
                 where newer.run_id=a.run_id and newer.unit_id=a.unit_id
                   and newer.status='candidate')""",
        (run_id, unit_id, artifact_id),
    ).fetchone()
    if (
        not row
        or row["status"] != "candidate"
        or row["attempt_status"] != "completed"
        or row["role"] not in {"translator", "repairer"}
        or (active and row["run_status"] != "active")
    ):
        raise LedgerError("host verification requires the latest completed candidate")
    return row


def _latest_candidate_records(
    connection: Any, run_id: str, unit_id: str, candidate_artifact_id: str,
) -> list[Any]:
    return connection.execute(
        """select v.*,v.rowid as ledger_rowid from verifier_records v
           where v.run_id=? and v.unit_id=? and v.candidate_artifact_id=?
             and v.gate_epoch=(select max(newer.gate_epoch) from verifier_records newer
                 where newer.run_id=v.run_id and newer.unit_id=v.unit_id
                   and newer.candidate_artifact_id=v.candidate_artifact_id
                   and newer.gate_family=v.gate_family)
           order by v.gate_family""",
        (run_id, unit_id, candidate_artifact_id),
    ).fetchall()


__all__ = ["CANDIDATE_REQUIRED_GATES", "HostVerifierMixin"]
