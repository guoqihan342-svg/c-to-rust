from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_authority import (
    PROJECT_GATE_KINDS,
    project_authority,
    require_portable_id,
    validate_project_summary,
)
from .gate_candidate_sets import (
    assert_current_candidate_set,
    bind_current_candidate_set,
    bind_verification_candidate_set,
)
from .gate_evidence import (
    read_content_addressed_json,
)
from .ledger_schema import _json, _now_text, _require_repo_path, _require_sha256, atomic
from .ledger_project_diagnostics import insert_project_diagnostic_intake
from .ledger_security import LedgerError
from .project_gate_bindings import require_cargo_integration_binding
from .project_gate_source_verification import verify_project_sources


class ProjectGateMixin:
    def bind_current_candidate_set(self, *, run_id: str) -> str:
        with self.connect() as connection, atomic(connection):
            return bind_current_candidate_set(
                connection, run_id, database_path=self.path,
            )

    def bind_verification_candidate_set(
        self, *, run_id: str, scope: str = "wave-provisional",
    ) -> str:
        with self.connect() as connection, atomic(connection):
            return bind_verification_candidate_set(
                connection, run_id, database_path=self.path, scope=scope,
            )

    def record_project_gate(
        self, *, record_id: str, run_id: str, gate_kind: str, status: str,
        candidate_set_sha256: str, verifier_id: str, evidence_path: str,
        evidence_sha256: str, metadata: Mapping[str, Any] | None = None,
        expected_gate_epoch: int | None = None,
        diagnostic_intake_reference: Mapping[str, Any] | None = None,
    ) -> int:
        require_portable_id(record_id, "record_id")
        if gate_kind not in PROJECT_GATE_KINDS or status not in {"passed", "failed"}:
            raise ValueError("project gate kind/status is invalid")
        if verifier_id != project_authority(gate_kind):
            raise LedgerError("project gate verifier identity is fixed by the host")
        candidate_set = _require_sha256(candidate_set_sha256, "candidate_set_sha256")
        evidence_path = _require_repo_path(evidence_path, "evidence_path")
        evidence_sha256 = _require_sha256(evidence_sha256, "evidence_sha256")
        with self.connect() as connection, atomic(connection):
            requirement = connection.execute(
                """select 1 from project_gate_requirements
                   where run_id=? and gate_kind=? and required=1""",
                (run_id, gate_kind),
            ).fetchone()
            if not requirement:
                raise LedgerError("project gate is not registered for this run")
            assert_current_candidate_set(
                connection, run_id, candidate_set, database_path=self.path,
            )
            payload = read_content_addressed_json(self.path, evidence_path, evidence_sha256)
            validate_project_summary(
                payload,
                run_id=run_id,
                gate_kind=gate_kind,
                status=status,
                candidate_set_sha256=candidate_set,
                verifier_id=verifier_id,
            )
            verify_project_sources(
                self,
                payload,
                run_id=run_id,
                gate_kind=gate_kind,
                candidate_set_sha256=candidate_set,
                status=status,
            )
            if gate_kind == "final-verification" and status == "passed":
                _require_latest_project_passes(
                    self, connection, run_id, candidate_set, include_final=False
                )
            epoch = int(connection.execute(
                """select coalesce(max(gate_epoch),0)+1 from project_gate_records
                   where run_id=? and candidate_set_sha256=? and gate_kind=?""",
                (run_id, candidate_set, gate_kind),
            ).fetchone()[0])
            if expected_gate_epoch is not None and epoch != expected_gate_epoch:
                raise LedgerError("project gate epoch changed before host recording")
            connection.execute(
                """insert into project_gate_records(record_id,run_id,gate_kind,gate_epoch,status,
                   candidate_set_sha256,verifier_id,evidence_path,evidence_sha256,finished_at,
                   metadata_json) values (?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, run_id, gate_kind, epoch, status, candidate_set, verifier_id,
                 evidence_path, evidence_sha256, _now_text(), _json(metadata)),
            )
            if diagnostic_intake_reference is not None:
                insert_project_diagnostic_intake(
                    connection, database_path=self.path,
                    reference=diagnostic_intake_reference,
                )
            return epoch

    def project_gate_bundle_sources(
        self, *, run_id: str, candidate_set_sha256: str,
    ) -> list[dict[str, Any]]:
        candidate_set = _require_sha256(candidate_set_sha256, "candidate_set_sha256")
        with self.connect() as connection, atomic(connection, immediate=False):
            assert_current_candidate_set(
                connection, run_id, candidate_set, database_path=self.path,
            )
            records = _require_latest_project_passes(
                self, connection, run_id, candidate_set, include_final=False
            )
            result = []
            for row, payload in records:
                result.append({
                    "path": str(row["evidence_path"]),
                    "sha256": str(row["evidence_sha256"]),
                    "size_bytes": len(canonical_json_bytes(payload)),
                })
            return result

def _latest_project_records(
    connection: Any, run_id: str, candidate_set_sha256: str,
) -> list[Any]:
    return connection.execute(
        """select p.*,p.rowid as ledger_rowid from project_gate_records p
           where p.run_id=? and p.candidate_set_sha256=?
             and p.gate_epoch=(select max(newer.gate_epoch) from project_gate_records newer
                 where newer.run_id=p.run_id
                   and newer.candidate_set_sha256=p.candidate_set_sha256
                   and newer.gate_kind=p.gate_kind)
           order by p.gate_kind""",
        (run_id, candidate_set_sha256),
    ).fetchall()


def _require_latest_project_passes(
    ledger: Any, connection: Any, run_id: str, candidate_set_sha256: str,
    *, include_final: bool,
) -> list[tuple[Any, Mapping[str, Any]]]:
    required = set(PROJECT_GATE_KINDS)
    if not include_final:
        required.remove("final-verification")
    rows = _latest_project_records(connection, run_id, candidate_set_sha256)
    by_kind = {str(row["gate_kind"]): row for row in rows if row["gate_kind"] in required}
    if set(by_kind) != required:
        raise LedgerError("project gate bundle is incomplete at its latest epochs")
    verified = []
    for kind in sorted(required):
        row = by_kind[kind]
        if row["status"] != "passed" or row["verifier_id"] != project_authority(kind):
            raise LedgerError("a latest project gate is not a host-owned pass")
        payload = read_content_addressed_json(
            ledger.path, str(row["evidence_path"]), str(row["evidence_sha256"])
        )
        validate_project_summary(
            payload,
            run_id=run_id,
            gate_kind=kind,
            status="passed",
            candidate_set_sha256=candidate_set_sha256,
            verifier_id=str(row["verifier_id"]),
        )
        verify_project_sources(
            ledger,
            payload,
            run_id=run_id,
            gate_kind=kind,
            candidate_set_sha256=candidate_set_sha256,
            status="passed",
        )
        verified.append((row, payload))
    require_cargo_integration_binding(ledger, verified)
    if include_final:
        by_kind = {str(row["gate_kind"]): (row, payload) for row, payload in verified}
        final_row, final_payload = by_kind["final-verification"]
        nonfinal = [
            (row, payload) for kind, (row, payload) in by_kind.items()
            if kind != "final-verification"
        ]
        if int(final_row["ledger_rowid"]) <= max(int(row["ledger_rowid"]) for row, _ in nonfinal):
            raise LedgerError("final project gate predates a latest prerequisite gate")
        expected_sources = sorted(
            ({
                "path": str(row["evidence_path"]),
                "sha256": str(row["evidence_sha256"]),
                "size_bytes": len(canonical_json_bytes(payload)),
            } for row, payload in nonfinal),
            key=lambda item: item["path"],
        )
        actual_sources = sorted(final_payload["source_evidence"], key=lambda item: item["path"])
        if actual_sources != expected_sources:
            raise LedgerError("final project gate is not bound to the latest prerequisite evidence")
    return verified


__all__ = ["PROJECT_GATE_KINDS", "ProjectGateMixin"]
