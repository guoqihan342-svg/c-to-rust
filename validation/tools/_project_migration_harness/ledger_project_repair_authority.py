from __future__ import annotations

import hashlib
import re
import time
from typing import Any, Mapping

from .ledger_project_repair_budget import ProjectRepairBudgetAuthority
from .ledger_project_repair_candidate import ProjectRepairCandidateMixin
from .ledger_project_repair_core import (
    ProjectRepairCore, ProjectRepairTransitionResult, attempt_scope,
    require_identity,
)
from .ledger_schema import _json, _now_text, _require_sha256, atomic
from .ledger_security import LedgerError, assert_no_secrets, sanitize_error_key
from .ledger_run_state import require_active_completion
from .project_repair_policy import ProjectRepairProjection


_WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class ProjectRepairAuthority(ProjectRepairCandidateMixin, ProjectRepairCore):
    def start_attempt(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
        command_id: str, expected_status: str, expected_version: int,
        worker_id: str, input_sha256: str,
        metadata: Mapping[str, Any] | None = None,
        lease_ttl_seconds: int = 900, now_epoch: int | None = None,
        created_at: str | None = None,
    ) -> ProjectRepairTransitionResult:
        require_identity(run_id, "run_id")
        require_identity(repair_id, "repair_id")
        require_identity(command_id, "command_id")
        _require_sha256(queue_sha256, "queue_sha256")
        _require_sha256(input_sha256, "input_sha256")
        _require_worker(worker_id)
        if (
            isinstance(lease_ttl_seconds, bool)
            or not isinstance(lease_ttl_seconds, int)
            or not 30 <= lease_ttl_seconds <= 3_600
        ):
            raise ValueError("project repair lease_ttl_seconds is invalid")
        epoch = int(time.time()) if now_epoch is None else now_epoch
        if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
            raise ValueError("project repair now_epoch is invalid")
        assert_no_secrets(metadata or {}, "project_repair_attempt.metadata")
        metadata_json = _json(metadata)
        attempt_id = _attempt_id(run_id, queue_sha256, repair_id, command_id)
        with atomic(self.connection):
            require_active_completion(
                self.connection, run_id, action="project repair attempt",
            )
            replay = self._event_replay(
                run_id, command_id, queue_sha256, repair_id,
                kind="attempt_started", expected_status=expected_status,
                expected_version=expected_version, target_status="running",
                evidence_sha256=input_sha256, attempt_id=attempt_id,
                candidate_ir_sha256=None, reason="project_repair_attempt_started",
            )
            if replay is not None:
                self._assert_attempt_binding(
                    attempt_id, worker_id=worker_id, input_sha256=input_sha256,
                    status=None, metadata_json=metadata_json,
                    lease_ttl_seconds=lease_ttl_seconds,
                )
                return replay
            latest = self.connection.execute(
                """select project_repair_queue_sha256
                   from project_interface_receipts where run_id=?
                   order by receipt_epoch desc limit 1""", (run_id,),
            ).fetchone()
            if latest is None or latest[0] != queue_sha256:
                raise LedgerError("project repair attempt requires the latest receipt queue")
            running = self.connection.execute(
                """select attempt_id from project_repair_attempts
                   where run_id=? and status='running' limit 1""", (run_id,),
            ).fetchone()
            if running is not None:
                raise LedgerError("another project repair attempt is already running")
            previous = self._expected(
                run_id, queue_sha256, repair_id, expected_status, expected_version,
            )
            if previous.status not in {"queued", "retry-ready"}:
                raise LedgerError("project repair item is not ready for an attempt")
            if previous.attempt_count >= previous.max_attempts:
                raise LedgerError("project repair attempt budget is exhausted")
            ProjectRepairBudgetAuthority(self.connection).start_attempt(
                run_id=run_id, queue_sha256=queue_sha256,
                repair_id=repair_id,
                expected_attempt_count=previous.attempt_count,
            )
            timestamp = created_at or _now_text()
            self.connection.execute(
                """insert into project_repair_attempts(
                   attempt_id,run_id,project_repair_queue_sha256,repair_id,
                   ordinal,worker_id,status,input_sha256,output_ir_sha256,error_key,
                   lease_ttl_seconds,lease_expires_at,command_started,
                   command_started_at,started_at,finished_at,metadata_json)
                   values (?,?,?,?,?,?,'running',?,null,null,?,?,0,null,?,null,?)""",
                (
                    attempt_id, run_id, queue_sha256, repair_id,
                    previous.attempt_count + 1, worker_id, input_sha256,
                    lease_ttl_seconds, epoch + lease_ttl_seconds,
                    timestamp, metadata_json,
                ),
            )
            current = ProjectRepairProjection(
                "running", previous.version + 1, previous.attempt_count + 1,
                previous.max_attempts, attempt_id, None,
            )
            return self._append_and_project(
                run_id, queue_sha256, repair_id, command_id,
                "attempt_started", "project_repair_attempt_started",
                input_sha256, attempt_id, previous, current, timestamp,
            )

    def mark_command_started(
        self, *, attempt_id: str, worker_id: str, expected_version: int,
        started_at: str | None = None,
    ) -> bool:
        require_identity(attempt_id, "attempt_id")
        _require_worker(worker_id)
        with atomic(self.connection):
            attempt = self._attempt(attempt_id)
            run_id, queue_sha, repair_id = attempt_scope(attempt)
            require_active_completion(
                self.connection, run_id, action="project repair provider start",
            )
            projection = self._expected(
                run_id, queue_sha, repair_id, "running", expected_version,
            )
            if (
                projection.active_attempt_id != attempt_id
                or attempt["status"] != "running"
                or attempt["worker_id"] != worker_id
            ):
                raise LedgerError("project repair command start changed attempt binding")
            if int(attempt["command_started"]) == 1:
                return False
            ProjectRepairBudgetAuthority(self.connection).claim_provider_call(
                run_id=run_id,
            )
            updated = self.connection.execute(
                """update project_repair_attempts
                   set command_started=1,command_started_at=?
                   where attempt_id=? and status='running' and command_started=0""",
                (started_at or _now_text(), attempt_id),
            )
            if updated.rowcount != 1:
                raise LedgerError("project repair command start lost its active attempt")
            return True

    def finish_attempt(
        self, *, attempt_id: str, command_id: str, expected_version: int,
        worker_id: str, outcome: str, evidence_sha256: str,
        output_ir_sha256: str | None = None, error_key: str | None = None,
        finished_at: str | None = None,
    ) -> ProjectRepairTransitionResult:
        require_identity(attempt_id, "attempt_id")
        require_identity(command_id, "command_id")
        _require_sha256(evidence_sha256, "evidence_sha256")
        _require_worker(worker_id)
        if outcome not in {"completed", "failed", "cancelled", "unknown"}:
            raise ValueError("project repair attempt outcome is invalid")
        if outcome == "completed":
            _require_sha256(str(output_ir_sha256), "output_ir_sha256")
            if error_key is not None:
                raise ValueError("completed project repair cannot have an error key")
        elif output_ir_sha256 is not None:
            raise ValueError("failed project repair cannot have an IR candidate")
        if outcome == "unknown" and error_key is None:
            raise ValueError("unknown project repair result requires an error key")
        stored_error = sanitize_error_key(error_key) if outcome != "completed" else None
        with atomic(self.connection):
            attempt = self._attempt(attempt_id)
            run_id, queue_sha, repair_id = attempt_scope(attempt)
            if attempt["worker_id"] != worker_id:
                raise LedgerError("project repair attempt worker binding changed")
            kind, target = _finish_target(
                outcome, int(attempt["ordinal"]), self._max_attempts_for_scope(
                    run_id, queue_sha, repair_id,
                ),
            )
            candidate = str(output_ir_sha256) if outcome == "completed" else None
            attempt_status = "failed" if outcome == "unknown" else outcome
            reason = (
                "project_repair_attempt_result_unknown"
                if outcome == "unknown" else f"project_repair_attempt_{outcome}"
            )
            replay = self._event_replay(
                run_id, command_id, queue_sha, repair_id, kind=kind,
                expected_status="running", expected_version=expected_version,
                target_status=target, evidence_sha256=evidence_sha256,
                attempt_id=attempt_id, candidate_ir_sha256=candidate, reason=reason,
            )
            if replay is not None:
                self._assert_attempt_binding(
                    attempt_id, worker_id=worker_id,
                    input_sha256=str(attempt["input_sha256"]),
                    status=attempt_status, output_ir_sha256=candidate,
                    error_key=stored_error, check_error_key=True,
                )
                return replay
            self._require_artifact_evidence(
                run_id=run_id, queue_sha256=queue_sha, repair_id=repair_id,
                evidence_sha256=evidence_sha256, attempt_id=attempt_id,
            )
            if candidate is not None:
                self._require_candidate_ir_artifact(
                    attempt_id=attempt_id, candidate_ir_sha256=candidate,
                )
            previous = self._expected(
                run_id, queue_sha, repair_id, "running", expected_version,
            )
            if previous.active_attempt_id != attempt_id or attempt["status"] != "running":
                raise LedgerError("project repair attempt is not active")
            timestamp = finished_at or _now_text()
            updated = self.connection.execute(
                """update project_repair_attempts set status=?,output_ir_sha256=?,
                   error_key=?,finished_at=? where attempt_id=? and status='running'""",
                (attempt_status, candidate, stored_error, timestamp, attempt_id),
            )
            if updated.rowcount != 1:
                raise LedgerError("project repair attempt projection lost its running state")
            current = ProjectRepairProjection(
                target, previous.version + 1, previous.attempt_count,
                previous.max_attempts, None, candidate,
            )
            return self._append_and_project(
                run_id, queue_sha, repair_id, command_id, kind, reason,
                evidence_sha256, attempt_id, previous, current, timestamp,
            )

    def _max_attempts_for_scope(
        self, run_id: str, queue_sha: str, repair_id: str,
    ) -> int:
        row = self.connection.execute(
            """select max_attempts from project_repair_items where run_id=?
               and project_repair_queue_sha256=? and repair_id=?""",
            (run_id, queue_sha, repair_id),
        ).fetchone()
        if row is None:
            raise LedgerError("project repair item does not exist")
        return int(row[0])


def _finish_target(outcome: str, ordinal: int, max_attempts: int) -> tuple[str, str]:
    if outcome == "completed":
        return "attempt_completed", "candidate-ready"
    if outcome == "cancelled":
        return "repair_cancelled", "cancelled"
    if outcome == "unknown":
        return "attempt_failed", "failed"
    return "attempt_failed", "exhausted" if ordinal >= max_attempts else "retry-ready"


def _attempt_id(run_id: str, queue_sha: str, repair_id: str, command_id: str) -> str:
    encoded = "\x00".join((run_id, queue_sha, repair_id, command_id)).encode("utf-8")
    return f"project-repair-attempt-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _require_worker(value: Any) -> str:
    if not isinstance(value, str) or _WORKER_ID.fullmatch(value) is None:
        raise ValueError("project repair worker_id is invalid")
    return value


__all__ = ["ProjectRepairAuthority", "ProjectRepairTransitionResult"]
