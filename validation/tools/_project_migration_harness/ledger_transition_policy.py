from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_ID = re.compile(r"^[a-z][a-z0-9_.:-]{0,191}$")
_REASON = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")

UNIT_RESUMABLE_STATES = {
    "pending": frozenset({"ready"}),
    "running": frozenset({"in_progress"}),
    "candidate-ready": frozenset({"awaiting_gate", "retryable", "terminal"}),
    "gate-pending": frozenset({"awaiting_gate", "retryable", "terminal"}),
    "retry-ready": frozenset({"awaiting_gate", "retryable", "terminal"}),
    "failed": frozenset({"awaiting_gate", "retryable", "terminal"}),
    "blocked": frozenset({"terminal"}),
    "resume-ready": frozenset({"last_good"}),
    "completed": frozenset({"terminal"}),
    "cancelled": frozenset({"terminal"}),
    "exhausted": frozenset({"exhausted"}),
}

UNIT_TRANSITIONS = {
    "pending": frozenset({"running", "blocked", "cancelled"}),
    "running": frozenset({
        "pending", "running", "candidate-ready", "gate-pending", "retry-ready",
        "failed", "blocked", "resume-ready", "cancelled", "exhausted",
    }),
    "candidate-ready": frozenset({
        "running", "gate-pending", "retry-ready", "resume-ready", "completed",
    }),
    "gate-pending": frozenset({
        "running", "retry-ready", "resume-ready", "completed",
    }),
    "retry-ready": frozenset({"running", "blocked", "cancelled", "exhausted"}),
    "failed": frozenset({"running", "retry-ready", "blocked", "cancelled", "exhausted"}),
    "resume-ready": frozenset({"running", "retry-ready", "completed", "cancelled"}),
    "blocked": frozenset(),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "exhausted": frozenset(),
}

RUN_TRANSITIONS = {
    "active": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}


@dataclass(frozen=True, slots=True)
class UnitState:
    status: str
    resumable_status: str

    def __post_init__(self) -> None:
        allowed = UNIT_RESUMABLE_STATES.get(self.status)
        if allowed is None or self.resumable_status not in allowed:
            raise ValueError("unit status/resumable_status pair is invalid")


@dataclass(frozen=True, slots=True)
class TransitionCommand:
    command_id: str
    run_id: str
    unit_id: str
    expected: UnitState
    target: UnitState
    reason: str
    evidence_sha256: str
    attempt_id: str | None = None
    fencing_token: int | None = None
    clear_last_good_if: str | None = None
    set_last_good_artifact_id: str | None = None

    def __post_init__(self) -> None:
        _validate_command_common(
            self.command_id, self.run_id, self.reason, self.evidence_sha256,
            self.attempt_id, self.fencing_token,
        )
        if not _identity(self.unit_id):
            raise ValueError("transition unit_id is invalid")
        if self.clear_last_good_if is not None and not _identity(self.clear_last_good_if):
            raise ValueError("clear_last_good_if is invalid")
        if self.set_last_good_artifact_id is not None and not _identity(
            self.set_last_good_artifact_id
        ):
            raise ValueError("set_last_good_artifact_id is invalid")
        if self.clear_last_good_if and self.set_last_good_artifact_id:
            raise ValueError("last-good projection cannot clear and set simultaneously")


@dataclass(frozen=True, slots=True)
class RunTransitionCommand:
    command_id: str
    run_id: str
    anchor_unit_id: str
    expected_status: str
    target_status: str
    reason: str
    evidence_sha256: str
    attempt_id: str | None = None
    fencing_token: int | None = None

    def __post_init__(self) -> None:
        _validate_command_common(
            self.command_id, self.run_id, self.reason, self.evidence_sha256,
            self.attempt_id, self.fencing_token,
        )
        if not _identity(self.anchor_unit_id):
            raise ValueError("run transition anchor_unit_id is invalid")
        if self.expected_status not in RUN_TRANSITIONS or self.target_status not in RUN_TRANSITIONS:
            raise ValueError("run transition status is invalid")


def assert_transition_allowed(command: TransitionCommand) -> None:
    if command.target.status not in UNIT_TRANSITIONS[command.expected.status]:
        raise ValueError(
            f"unit transition is not permitted: "
            f"{command.expected.status}->{command.target.status}"
        )


def assert_run_transition_allowed(command: RunTransitionCommand) -> None:
    if command.target_status not in RUN_TRANSITIONS[command.expected_status]:
        raise ValueError(
            f"run transition is not permitted: "
            f"{command.expected_status}->{command.target_status}"
        )


def attempt_started_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: UnitState, input_sha256: str,
) -> TransitionCommand:
    return TransitionCommand(
        command_id=stable_transition_command_id(
            "attempt-started", run_id, unit_id, attempt_id,
        ),
        run_id=run_id, unit_id=unit_id, expected=expected,
        target=UnitState("running", "in_progress"), reason="attempt_started",
        evidence_sha256=input_sha256, attempt_id=attempt_id,
        fencing_token=fencing_token,
    )


def worker_command_started_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: UnitState, metadata: Mapping[str, Any],
) -> TransitionCommand:
    evidence = transition_evidence_sha256({
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "request_sha256": metadata.get("request_sha256"),
        "preflight_sha256": metadata.get("preflight_sha256"),
    })
    return TransitionCommand(
        command_id=stable_transition_command_id(
            "worker-command-started", run_id, unit_id, attempt_id,
        ),
        run_id=run_id, unit_id=unit_id, expected=expected, target=expected,
        reason="worker_command_started", evidence_sha256=evidence,
        attempt_id=attempt_id, fencing_token=fencing_token,
    )


def lease_recovery_command(
    *, run_id: str, unit_id: str, row: Any, attempt_count: int,
    started: bool, expected: UnitState, target: UnitState, reason: str,
) -> TransitionCommand:
    return TransitionCommand(
        command_id=stable_transition_command_id(
            "lease-recovery", run_id, unit_id, row["attempt_id"],
        ),
        run_id=run_id, unit_id=unit_id, expected=expected, target=target,
        reason=reason,
        evidence_sha256=transition_evidence_sha256({
            "attempt_id": row["attempt_id"], "attempt_count": attempt_count,
            "max_attempts": row["max_attempts"], "started": started,
            "lease_status": row["lease_status"],
            "lease_expires_at": row["expires_at"],
        }),
        attempt_id=str(row["attempt_id"]),
        fencing_token=int(row["fencing_token"]),
    )


def lease_recovery_run_command(
    *, run_id: str, rows: list[Any], clock: int,
) -> RunTransitionCommand:
    anchor = rows[0]
    attempt_ids = [str(row["attempt_id"]) for row in rows]
    return RunTransitionCommand(
        command_id=stable_transition_command_id(
            "lease-recovery-run-failed", run_id, attempt_ids,
        ),
        run_id=run_id, anchor_unit_id=str(anchor["unit_id"]),
        expected_status="active", target_status="failed",
        reason="worker_command_result_unknown",
        evidence_sha256=transition_evidence_sha256({
            "attempt_ids": attempt_ids, "clock": clock,
        }),
        attempt_id=str(anchor["attempt_id"]),
        fencing_token=int(anchor["fencing_token"]),
    )


def prelaunch_cancel_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: UnitState, metadata: Mapping[str, Any],
) -> TransitionCommand:
    target = UnitState(
        str(metadata["previous_status"]),
        str(metadata["previous_resumable_status"]),
    )
    evidence = transition_evidence_sha256({
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "previous_status": target.status,
        "previous_resumable_status": target.resumable_status,
        "request_sha256": metadata.get("request_sha256"),
        "preflight_sha256": metadata.get("preflight_sha256"),
    })
    return TransitionCommand(
        command_id=stable_transition_command_id(
            "prelaunch-attempt-cancelled", run_id, unit_id, attempt_id,
        ),
        run_id=run_id, unit_id=unit_id, expected=expected, target=target,
        reason="prelaunch_attempt_cancelled", evidence_sha256=evidence,
        fencing_token=fencing_token,
    )


def stable_transition_command_id(action: str, *identity: Any) -> str:
    if _REASON.fullmatch(action) is None:
        raise ValueError("transition command action is invalid")
    digest = transition_evidence_sha256({"action": action, "identity": list(identity)})
    return f"{action}:{digest}"


def transition_evidence_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_command_common(
    command_id: str, run_id: str, reason: str, evidence_sha256: str,
    attempt_id: str | None, fencing_token: int | None,
) -> None:
    if _COMMAND_ID.fullmatch(command_id) is None or not _identity(run_id):
        raise ValueError("transition command_id/run_id is invalid")
    if _REASON.fullmatch(reason) is None or _SHA256.fullmatch(evidence_sha256) is None:
        raise ValueError("transition reason/evidence_sha256 is invalid")
    if attempt_id is not None and not _identity(attempt_id):
        raise ValueError("transition attempt_id is invalid")
    if fencing_token is not None and fencing_token < 1:
        raise ValueError("transition fencing_token must be positive")


def _identity(value: Any) -> bool:
    return (
        isinstance(value, str) and 0 < len(value) <= 512
        and not any(character in value for character in "\x00\r\n")
    )


__all__ = [
    "RUN_TRANSITIONS", "RunTransitionCommand", "TransitionCommand",
    "UNIT_RESUMABLE_STATES", "UNIT_TRANSITIONS", "UnitState",
    "assert_run_transition_allowed", "assert_transition_allowed",
    "attempt_started_command", "prelaunch_cancel_command",
    "lease_recovery_command", "lease_recovery_run_command",
    "stable_transition_command_id", "transition_evidence_sha256",
    "worker_command_started_command",
]
