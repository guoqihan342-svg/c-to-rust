from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .candidate_pool_selection import load_candidate_pool
from .gate_evidence import read_content_addressed_json
from .gate_candidate_sets import assert_verification_candidate_set
from .ledger_schema import atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import TransitionAuthority, load_unit_projection
from .ledger_transition_commands import host_verification_failed_command
from .ledger_transition_policy import stable_transition_command_id


class CandidateStateMixin:
    def mark_verification_failed(
        self, *, run_id: str, unit_id: str, candidate_artifact_id: str,
        failed_record_id: str, expected_candidate_set_sha256: str | None = None,
    ) -> None:
        self.mark_verification_failures(
            run_id=run_id,
            failures=[{
                "unit_id": unit_id,
                "candidate_artifact_id": candidate_artifact_id,
                "failed_record_id": failed_record_id,
            }],
            expected_candidate_set_sha256=expected_candidate_set_sha256,
        )

    def mark_verification_failures(
        self, *, run_id: str, failures: Sequence[Mapping[str, str]],
        expected_candidate_set_sha256: str | None = None,
    ) -> None:
        if (
            isinstance(failures, (str, bytes)) or not isinstance(failures, Sequence)
            or not failures
        ):
            raise LedgerError("verification failure batch is invalid")
        normalized = []
        seen = set()
        for failure in failures:
            if not isinstance(failure, Mapping) or set(failure) != {
                "unit_id", "candidate_artifact_id", "failed_record_id",
            }:
                raise LedgerError("verification failure batch is invalid")
            item = {key: str(failure[key]) for key in failure}
            if not all(item.values()) or item["unit_id"] in seen:
                raise LedgerError("verification failure batch is invalid")
            seen.add(item["unit_id"])
            normalized.append(item)
        with self.connect() as connection, atomic(connection):
            if expected_candidate_set_sha256 is not None:
                assert_verification_candidate_set(
                    connection, run_id, expected_candidate_set_sha256,
                    database_path=self.path,
                )
            authority = TransitionAuthority(connection)
            for failure in sorted(normalized, key=lambda item: item["unit_id"]):
                self._mark_one_verification_failed(
                    connection, authority, run_id=run_id,
                    expected_candidate_set_sha256=expected_candidate_set_sha256,
                    **failure,
                )

    def _mark_one_verification_failed(
        self, connection: Any, authority: TransitionAuthority, *, run_id: str,
        unit_id: str, candidate_artifact_id: str, failed_record_id: str,
        expected_candidate_set_sha256: str | None,
    ) -> None:
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
        evidence = read_content_addressed_json(
            self.path, str(failed["evidence_path"]), str(failed["evidence_sha256"])
        )
        if (
            expected_candidate_set_sha256 is not None
            and evidence.get("candidate_set_sha256")
            != expected_candidate_set_sha256
        ):
            raise LedgerError(
                "failed verification changed its candidate set binding"
            )
        command_id = stable_transition_command_id(
            "host-verification-failed", run_id, unit_id, failed_record_id,
        )
        expected = authority.bound_unit_expected(
            run_id=run_id, unit_id=unit_id,
            command_kind="host_verification_failed", command_id=command_id,
        ) or load_unit_projection(connection, run_id, unit_id)
        authority.apply(
            host_verification_failed_command(
                command_id=command_id,
                run_id=run_id, unit_id=unit_id, expected=expected,
                evidence_sha256=str(failed["evidence_sha256"]),
                attempt_id=str(failed["attempt_id"]),
                candidate_artifact_id=candidate_artifact_id,
            )
        )


def candidate_row(
    connection: Any, run_id: str, unit_id: str, artifact_id: str, *, active: bool = False,
) -> Any:
    selected = load_candidate_pool(connection, run_id, unit_id)["selected_candidate"]
    row = connection.execute(
        """select a.attempt_id,a.worker_id,a.fencing_token,a.status,a.content_sha256,
                  a.repo_rel_path,a.metadata_json as artifact_metadata_json,
                  t.status as attempt_status,t.role,t.metadata_json as attempt_metadata_json,
                   r.completion_status as run_status
           from artifacts a join attempts t on t.attempt_id=a.attempt_id
           join project_runs r on r.run_id=a.run_id
           where a.run_id=? and a.unit_id=? and a.artifact_id=?""",
        (run_id, unit_id, artifact_id),
    ).fetchone()
    if (
        selected is None
        or selected["artifact_id"] != artifact_id
        or not row
        or row["status"] != "candidate"
        or row["attempt_status"] != "completed"
        or row["role"] not in {"translator", "repairer"}
        or (active and row["run_status"] != "active")
    ):
        raise LedgerError("host verification requires the host-selected completed candidate")
    return row


def latest_candidate_records(
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


__all__ = ["CandidateStateMixin", "candidate_row", "latest_candidate_records"]
