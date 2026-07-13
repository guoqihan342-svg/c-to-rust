from __future__ import annotations

import json
import time
from typing import Any

from .ledger_project_repair_core import (
    ProjectRepairTransitionResult, attempt_scope, require_identity,
)
from .ledger_schema import _now_text, _require_sha256, atomic
from .ledger_security import LedgerError
from .project_interface_contract import (
    coordinator_receipt_accepts_repair_candidate,
)
from .project_repair_policy import ProjectRepairProjection


class ProjectRepairCandidateMixin:
    def recover_attempt(
        self, *, attempt_id: str, command_id: str, expected_version: int,
        evidence_sha256: str, worker_id: str | None = None,
        recovered_at_epoch: int | None = None,
        result_known: bool = False,
        recovered_at: str | None = None,
    ) -> ProjectRepairTransitionResult:
        return self._close_abandoned_attempt(
            attempt_id=attempt_id, command_id=command_id,
            expected_version=expected_version, evidence_sha256=evidence_sha256,
            worker_id=worker_id, recovered_at_epoch=recovered_at_epoch,
            result_known=result_known,
            finished_at=recovered_at,
        )

    def rollback_candidate(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
        command_id: str, expected_version: int, evidence_sha256: str,
        created_at: str | None = None,
    ) -> ProjectRepairTransitionResult:
        return self._candidate_transition(
            run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
            command_id=command_id, expected_version=expected_version,
            evidence_sha256=evidence_sha256,
            kind="candidate_rolled_back", preserve_candidate=False,
            created_at=created_at,
        )

    def resolve_candidate(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
        command_id: str, expected_version: int,
        coordinator_receipt_sha256: str, created_at: str | None = None,
    ) -> ProjectRepairTransitionResult:
        require_identity(run_id, "run_id")
        require_identity(repair_id, "repair_id")
        require_identity(command_id, "command_id")
        _require_sha256(queue_sha256, "queue_sha256")
        _require_sha256(coordinator_receipt_sha256, "coordinator_receipt_sha256")
        with atomic(self.connection):
            receipt = self.connection.execute(
                """select status,rust_project_ir_sha256,receipt_json
                   from project_interface_receipts
                   where run_id=? and coordinator_receipt_sha256=?""",
                (run_id, coordinator_receipt_sha256),
            ).fetchone()
            source = self.connection.execute(
                """select receipts.receipt_json,items.diagnostic_sha256
                   from project_interface_receipts receipts
                   join project_repair_items items on items.run_id=receipts.run_id
                     and items.project_repair_queue_sha256=
                         receipts.project_repair_queue_sha256
                   where items.run_id=? and items.project_repair_queue_sha256=?
                     and items.repair_id=?""",
                (run_id, queue_sha256, repair_id),
            ).fetchone()
            candidate_sha = None if receipt is None else receipt["rust_project_ir_sha256"]
            replay = self._event_replay(
                run_id, command_id, queue_sha256, repair_id,
                kind="candidate_recoordinated", expected_status="candidate-ready",
                expected_version=expected_version, target_status="resolved",
                evidence_sha256=coordinator_receipt_sha256, attempt_id=None,
                candidate_ir_sha256=candidate_sha,
                reason="project_repair_candidate_recoordinated",
            )
            if replay is not None:
                return replay
            previous = self._expected(
                run_id, queue_sha256, repair_id, "candidate-ready", expected_version,
            )
            try:
                accepted = bool(
                    receipt is not None and source is not None
                    and coordinator_receipt_accepts_repair_candidate(
                        json.loads(source["receipt_json"]),
                        json.loads(receipt["receipt_json"]),
                        diagnostic_sha256=str(source["diagnostic_sha256"]),
                    )
                )
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                raise LedgerError(
                    "project repair re-coordination receipt is invalid"
                ) from error
            if (
                receipt is None or not accepted
                or receipt["rust_project_ir_sha256"] != previous.candidate_ir_sha256
            ):
                raise LedgerError(
                    "project repair candidate lacks target-reducing re-coordination"
                )
            return self._candidate_transition_locked(
                run_id, queue_sha256, repair_id, command_id, previous,
                coordinator_receipt_sha256, "resolved", "candidate_recoordinated",
                True, created_at or _now_text(),
            )

    def _close_abandoned_attempt(self, **values: Any) -> ProjectRepairTransitionResult:
        attempt_id = require_identity(values["attempt_id"], "attempt_id")
        command_id = require_identity(values["command_id"], "command_id")
        evidence = _require_sha256(values["evidence_sha256"], "evidence_sha256")
        result_known = values.get("result_known", False)
        if not isinstance(result_known, bool):
            raise ValueError("project repair result_known must be boolean")
        reason = (
            "project_repair_attempt_recovered_known"
            if result_known else "project_repair_attempt_recovered"
        )
        with atomic(self.connection):
            attempt = self._attempt(attempt_id)
            run_id, queue_sha, repair_id = attempt_scope(attempt)
            max_attempts = self._item_max_attempts(run_id, queue_sha, repair_id)
            target = (
                "exhausted" if int(attempt["ordinal"]) >= max_attempts
                else "retry-ready"
            )
            replay = self._event_replay(
                run_id, command_id, queue_sha, repair_id, kind="attempt_recovered",
                expected_status="running", expected_version=values["expected_version"],
                target_status=target, evidence_sha256=evidence,
                attempt_id=attempt_id, candidate_ir_sha256=None,
                reason=reason,
            )
            if replay is not None:
                return replay
            worker_id = values.get("worker_id")
            if worker_id is not None:
                require_identity(worker_id, "worker_id")
            recovered_epoch = values.get("recovered_at_epoch")
            if recovered_epoch is None:
                recovered_epoch = int(time.time())
            if (
                isinstance(recovered_epoch, bool)
                or not isinstance(recovered_epoch, int)
                or recovered_epoch < 0
            ):
                raise ValueError("project repair recovered_at_epoch is invalid")
            if worker_id is not None and worker_id != attempt["worker_id"]:
                raise LedgerError("project repair recovery changed worker binding")
            if int(attempt["command_started"]) == 1 and not result_known:
                raise LedgerError("project repair command outcome requires reconciliation")
            if result_known and int(attempt["command_started"]) != 1:
                raise LedgerError("known project repair result has no launch intent")
            if result_known and worker_id != attempt["worker_id"]:
                raise LedgerError("known project repair result requires its worker")
            if result_known:
                self._require_artifact_evidence(
                    run_id=run_id, queue_sha256=queue_sha, repair_id=repair_id,
                    evidence_sha256=evidence, attempt_id=attempt_id,
                )
            if (
                recovered_epoch < int(attempt["lease_expires_at"])
                and worker_id != attempt["worker_id"]
            ):
                raise LedgerError("project repair attempt lease is still active")
            previous = self._expected(
                run_id, queue_sha, repair_id, "running", values["expected_version"],
            )
            if previous.active_attempt_id != attempt_id or attempt["status"] != "running":
                raise LedgerError("project repair attempt is not recoverable")
            timestamp = values.get("finished_at") or _now_text()
            updated = self.connection.execute(
                """update project_repair_attempts set status='recovered',
                   error_key='project_repair_recovered',finished_at=?
                   where attempt_id=? and status='running'""",
                (timestamp, attempt_id),
            )
            if updated.rowcount != 1:
                raise LedgerError("project repair recovery lost its running attempt")
            current = ProjectRepairProjection(
                target, previous.version + 1, previous.attempt_count,
                previous.max_attempts, None, None,
            )
            return self._append_and_project(
                run_id, queue_sha, repair_id, command_id, "attempt_recovered",
                reason, evidence, attempt_id,
                previous, current, timestamp,
            )

    def _candidate_transition(self, **values: Any) -> ProjectRepairTransitionResult:
        require_identity(values["run_id"], "run_id")
        require_identity(values["repair_id"], "repair_id")
        require_identity(values["command_id"], "command_id")
        _require_sha256(values["queue_sha256"], "queue_sha256")
        with atomic(self.connection):
            evidence = _require_sha256(
                values["evidence_sha256"], "evidence_sha256",
            )
            target = self._command_target(values["run_id"], values["command_id"])
            previous: ProjectRepairProjection | None = None
            if target is None:
                previous = self._expected(
                    values["run_id"], values["queue_sha256"], values["repair_id"],
                    "candidate-ready", values["expected_version"],
                )
                target = (
                    "exhausted"
                    if previous.attempt_count >= previous.max_attempts
                    else "retry-ready"
                )
            elif target not in {"retry-ready", "exhausted"}:
                raise LedgerError("project repair rollback replay target is invalid")
            candidate = None
            replay = self._event_replay(
                values["run_id"], values["command_id"], values["queue_sha256"],
                values["repair_id"], kind=values["kind"],
                expected_status="candidate-ready",
                expected_version=values["expected_version"],
                target_status=target, evidence_sha256=evidence,
                attempt_id=None, candidate_ir_sha256=candidate,
                reason=f"project_repair_{values['kind']}",
            )
            if replay is not None:
                return replay
            if previous is None:
                raise LedgerError("project repair rollback replay disappeared")
            self._require_artifact_evidence(
                run_id=values["run_id"], queue_sha256=values["queue_sha256"],
                repair_id=values["repair_id"], evidence_sha256=evidence,
            )
            return self._candidate_transition_locked(
                values["run_id"], values["queue_sha256"], values["repair_id"],
                values["command_id"], previous,
                evidence,
                target, values["kind"],
                values["preserve_candidate"], values.get("created_at") or _now_text(),
            )

    def _candidate_transition_locked(
        self, run_id: str, queue_sha: str, repair_id: str, command_id: str,
        previous: ProjectRepairProjection, evidence: str, target: str, kind: str,
        preserve: bool, timestamp: str,
    ) -> ProjectRepairTransitionResult:
        candidate = previous.candidate_ir_sha256 if preserve else None
        current = ProjectRepairProjection(
            target, previous.version + 1, previous.attempt_count,
            previous.max_attempts, None, candidate,
        )
        return self._append_and_project(
            run_id, queue_sha, repair_id, command_id, kind,
            f"project_repair_{kind}", evidence, None, previous, current, timestamp,
        )

    def _item_max_attempts(
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


__all__ = ["ProjectRepairCandidateMixin"]
