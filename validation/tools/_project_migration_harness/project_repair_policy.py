from __future__ import annotations

from dataclasses import dataclass

from .ledger_security import LedgerError


REPAIR_STATUSES = frozenset({
    "queued", "running", "candidate-ready", "retry-ready", "resolved",
    "failed", "exhausted", "cancelled",
})
_TRANSITIONS = {
    ("queued", "running"),
    ("queued", "cancelled"),
    ("retry-ready", "running"),
    ("retry-ready", "cancelled"),
    ("running", "candidate-ready"),
    ("running", "retry-ready"),
    ("running", "failed"),
    ("running", "exhausted"),
    ("running", "cancelled"),
    ("candidate-ready", "retry-ready"),
    ("candidate-ready", "exhausted"),
    ("candidate-ready", "resolved"),
    ("candidate-ready", "failed"),
    ("candidate-ready", "cancelled"),
}


@dataclass(frozen=True, slots=True)
class ProjectRepairProjection:
    status: str
    version: int
    attempt_count: int
    max_attempts: int
    active_attempt_id: str | None
    candidate_ir_sha256: str | None


def assert_project_repair_transition(
    previous: ProjectRepairProjection,
    current: ProjectRepairProjection,
    *, command_kind: str,
) -> None:
    if previous.status not in REPAIR_STATUSES or current.status not in REPAIR_STATUSES:
        raise LedgerError("project repair transition contains an invalid state")
    if (previous.status, current.status) not in _TRANSITIONS:
        raise LedgerError("project repair state transition is not allowed")
    if current.version != previous.version + 1:
        raise LedgerError("project repair transition version is not contiguous")
    if current.max_attempts != previous.max_attempts:
        raise LedgerError("project repair attempt budget changed")
    if command_kind == "attempt_started":
        _assert_started(previous, current)
    elif command_kind in {"attempt_completed", "attempt_failed", "attempt_recovered"}:
        _assert_attempt_finished(previous, current, command_kind)
    elif command_kind == "candidate_rolled_back":
        _assert_rollback(previous, current)
    elif command_kind == "candidate_recoordinated":
        _assert_recoordinated(previous, current)
    elif command_kind == "repair_cancelled":
        _assert_cancelled(previous, current)
    else:
        raise LedgerError("project repair command kind is invalid")


def _assert_started(
    previous: ProjectRepairProjection, current: ProjectRepairProjection,
) -> None:
    if (
        previous.status not in {"queued", "retry-ready"}
        or current.status != "running"
        or previous.active_attempt_id is not None
        or current.active_attempt_id is None
        or current.attempt_count != previous.attempt_count + 1
        or current.attempt_count > current.max_attempts
        or previous.candidate_ir_sha256 is not None
        or current.candidate_ir_sha256 is not None
    ):
        raise LedgerError("project repair attempt-start projection is invalid")


def _assert_attempt_finished(
    previous: ProjectRepairProjection, current: ProjectRepairProjection,
    command_kind: str,
) -> None:
    if (
        previous.status != "running"
        or previous.active_attempt_id is None
        or current.active_attempt_id is not None
        or current.attempt_count != previous.attempt_count
        or previous.candidate_ir_sha256 is not None
    ):
        raise LedgerError("project repair attempt-finish projection is invalid")
    if command_kind == "attempt_completed":
        if current.status != "candidate-ready" or current.candidate_ir_sha256 is None:
            raise LedgerError("completed project repair has no IR candidate")
        return
    expected = "exhausted" if current.attempt_count >= current.max_attempts else "retry-ready"
    if current.status not in {expected, "failed", "cancelled"}:
        raise LedgerError("failed project repair has an invalid recovery state")
    if current.candidate_ir_sha256 is not None:
        raise LedgerError("failed project repair retained an IR candidate")


def _assert_rollback(
    previous: ProjectRepairProjection, current: ProjectRepairProjection,
) -> None:
    if (
        previous.status != "candidate-ready"
        or previous.candidate_ir_sha256 is None
        or current.status != (
            "exhausted" if current.attempt_count >= current.max_attempts
            else "retry-ready"
        )
        or current.candidate_ir_sha256 is not None
        or current.active_attempt_id is not None
        or current.attempt_count != previous.attempt_count
    ):
        raise LedgerError("project repair rollback projection is invalid")


def _assert_recoordinated(
    previous: ProjectRepairProjection, current: ProjectRepairProjection,
) -> None:
    if (
        previous.status != "candidate-ready"
        or previous.candidate_ir_sha256 is None
        or current.status != "resolved"
        or current.candidate_ir_sha256 != previous.candidate_ir_sha256
        or current.active_attempt_id is not None
        or current.attempt_count != previous.attempt_count
    ):
        raise LedgerError("project repair re-coordination projection is invalid")


def _assert_cancelled(
    previous: ProjectRepairProjection, current: ProjectRepairProjection,
) -> None:
    if (
        current.status != "cancelled"
        or current.active_attempt_id is not None
        or current.attempt_count != previous.attempt_count
        or current.candidate_ir_sha256 is not None
    ):
        raise LedgerError("project repair cancellation projection is invalid")


__all__ = [
    "ProjectRepairProjection", "REPAIR_STATUSES",
    "assert_project_repair_transition",
]
