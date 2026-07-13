from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Mapping

from .ledger_schema import _json, _now_text, _require_repo_path, _require_sha256, atomic
from .ledger_security import (
    LedgerError, assert_no_semantic_claims, sanitize_error_key,
)
from .ledger_transition_authority import (
    TransitionAuthority, load_run_projection, load_unit_projection,
)
from .ledger_transition_commands import (
    attempt_finished_command, terminal_worker_run_failed_command,
)
from .ledger_transition_policy import UnitState, transition_evidence_sha256


ARTIFACT_STATES = {"written", "candidate", "diagnostic", "reviewed", "failed", "blocked"}
WORKER_STATES = {"candidate-ready", "gate-pending", "retry-ready", "failed", "blocked"}


class ArtifactLedgerMixin:
    def record_artifact(
        self, *, run_id: str, unit_id: str, owner: str, fencing_token: int,
        artifact_id: str, attempt_id: str | None, kind: str, repo_rel_path: str,
        content_sha256: str, status: str, metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if not attempt_id:
            raise ValueError("artifact must be attempt-bound")
        with self.connect() as connection, atomic(connection):
            attempt = self._running_attempt(connection, attempt_id, owner, fencing_token)
            _insert_artifact(
                connection, attempt=attempt, run_id=run_id, unit_id=unit_id,
                owner=owner, fencing_token=fencing_token, artifact_id=artifact_id,
                attempt_id=attempt_id, kind=kind, repo_rel_path=repo_rel_path,
                content_sha256=content_sha256, status=status, metadata=metadata,
            )

    def record_artifact_and_finish(
        self, *, run_id: str, unit_id: str, owner: str, fencing_token: int,
        artifact_id: str, attempt_id: str, kind: str, repo_rel_path: str,
        content_sha256: str, artifact_status: str, next_status: str,
        metadata: Mapping[str, Any] | None = None, terminal: bool = False,
        fail_run: bool = False,
    ) -> None:
        if next_status not in WORKER_STATES:
            raise ValueError("worker next_status is invalid")
        if fail_run and not terminal:
            raise ValueError("fail_run requires a terminal result")
        with self.connect() as connection, atomic(connection):
            attempt = self._running_attempt(connection, attempt_id, owner, fencing_token)
            digest = _insert_artifact(
                connection, attempt=attempt, run_id=run_id, unit_id=unit_id,
                owner=owner, fencing_token=fencing_token, artifact_id=artifact_id,
                attempt_id=attempt_id, kind=kind, repo_rel_path=repo_rel_path,
                content_sha256=content_sha256, status=artifact_status, metadata=metadata,
            )
            timestamp = _now_text()
            connection.execute(
                """update attempts set status='completed',output_sha256=?,error_key=null,
                   finished_at=? where attempt_id=?""", (digest, timestamp, attempt_id),
            )
            expected = load_unit_projection(connection, run_id, unit_id)
            authority = TransitionAuthority(connection)
            authority.apply(
                attempt_finished_command(
                    run_id=run_id, unit_id=unit_id, expected=expected,
                    target=UnitState(
                        next_status, "terminal" if terminal else "awaiting_gate",
                    ),
                    reason="terminal_worker_result" if terminal else "attempt_completed",
                    evidence_sha256=digest, attempt_id=attempt_id,
                    fencing_token=fencing_token,
                ),
                created_at=timestamp,
            )
            if fail_run:
                run = load_run_projection(connection, run_id)
                if run.status == "active":
                    authority.apply_run(
                        terminal_worker_run_failed_command(
                            run_id=run_id, unit_id=unit_id, expected=run,
                            evidence_sha256=digest,
                            attempt_id=attempt_id, fencing_token=fencing_token,
                        ),
                        created_at=timestamp,
                    )
                elif run.status != "failed":
                    raise LedgerError("terminal worker result cannot overwrite run state")

    def finish_attempt(
        self, *, attempt_id: str, owner: str, fencing_token: int, status: str,
        next_status: str, output_sha256: str | None = None,
        error_key: str | None = None,
    ) -> None:
        if status not in {"completed", "failed", "blocked"} or next_status not in WORKER_STATES:
            raise ValueError("worker attempt status transition is not permitted")
        if status == "completed" and output_sha256 is None:
            raise ValueError("completed attempts require output_sha256")
        with self.connect() as connection, atomic(connection):
            attempt = self._running_attempt(connection, attempt_id, owner, fencing_token)
            digest = _require_sha256(output_sha256, "output_sha256") if output_sha256 else None
            if status == "completed" and not connection.execute(
                "select 1 from artifacts where attempt_id=? and content_sha256=?",
                (attempt_id, digest),
            ).fetchone():
                raise LedgerError("completed attempt output must match an attempt-bound artifact")
            timestamp = _now_text()
            safe_error_key = sanitize_error_key(error_key)
            connection.execute(
                """update attempts set status=?,output_sha256=?,error_key=?,finished_at=?
                   where attempt_id=?""",
                (status, digest, safe_error_key, timestamp, attempt_id),
            )
            terminal = status == "blocked" or next_status == "blocked"
            resumable = "terminal" if terminal else (
                "awaiting_gate" if status == "completed" else "retryable"
            )
            run_id, unit_id = str(attempt["run_id"]), str(attempt["unit_id"])
            expected = load_unit_projection(connection, run_id, unit_id)
            evidence = digest or transition_evidence_sha256({
                "attempt_id": attempt_id,
                "attempt_status": status,
                "error_key": safe_error_key,
            })
            TransitionAuthority(connection).apply(
                attempt_finished_command(
                    run_id=run_id, unit_id=unit_id, expected=expected,
                    target=UnitState(next_status, resumable),
                    reason=f"attempt_{status}", evidence_sha256=evidence,
                    attempt_id=attempt_id, fencing_token=fencing_token,
                ),
                created_at=timestamp,
            )

    def completed_orchestration_rows(
        self, run_id: str,
    ) -> dict[str, list[dict[str, Any]]]:
        with self.connect() as connection:
            artifacts = connection.execute(
                """select a.rowid as sequence,a.* from artifacts a join attempts t
                   on t.attempt_id=a.attempt_id and t.fencing_token=a.fencing_token
                   where a.run_id=? and t.status='completed' order by a.rowid""", (run_id,),
            ).fetchall()
            verifications = connection.execute(
                "select rowid as sequence,* from verifier_records where run_id=? order by rowid",
                (run_id,),
            ).fetchall()
        return {
            "artifacts": [dict(row) for row in artifacts],
            "verifications": [dict(row) for row in verifications],
        }

    def point_last_good(self, **_: Any) -> None:
        raise LedgerError("worker-controlled last-good is disabled; use host verification APIs")


def _insert_artifact(
    connection: Any, *, attempt: Mapping[str, Any], run_id: str, unit_id: str,
    owner: str, fencing_token: int, artifact_id: str, attempt_id: str,
    kind: str, repo_rel_path: str, content_sha256: str, status: str,
    metadata: Mapping[str, Any] | None,
) -> str:
    if status not in ARTIFACT_STATES:
        raise ValueError("artifact status is invalid")
    assert_no_semantic_claims({"kind": kind, "metadata": metadata or {}})
    if attempt["run_id"] != run_id or attempt["unit_id"] != unit_id:
        raise LedgerError("artifact run/unit must match its attempt")
    assignment = connection.execute(
        "select out_root from assignments where run_id=? and unit_id=? and worker_id=?",
        (run_id, unit_id, owner),
    ).fetchone()
    if assignment is None:
        raise LedgerError("artifact assignment is unavailable")
    path = _require_repo_path(repo_rel_path, "repo_rel_path")
    root = PurePosixPath(assignment["out_root"])
    if root not in PurePosixPath(path).parents:
        raise LedgerError("artifact path must stay under the assigned out_root")
    digest = _require_sha256(content_sha256, "content_sha256")
    connection.execute(
        """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,worker_id,
           fencing_token,kind,repo_rel_path,content_sha256,status,created_at,metadata_json)
           values (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, artifact_id, unit_id, attempt_id, owner, fencing_token, kind,
         path, digest, status, _now_text(), _json(metadata)),
    )
    return digest


__all__ = ["ArtifactLedgerMixin"]
