from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from .ledger_run_transition import (
    RUN_COMMAND_POLICIES, RUN_STATUSES, RunProjection, RunTransitionCommand,
    assert_run_transition_allowed,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_ID = re.compile(r"^[a-z][a-z0-9_.:-]{0,191}$")
_KIND = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
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

_ATTEMPT_SOURCES = {
    "pending", "candidate-ready", "gate-pending", "retry-ready",
    "failed", "resume-ready",
}
_WORKER_RESULTS = {
    "candidate-ready", "gate-pending", "retry-ready", "failed", "blocked",
}


@dataclass(frozen=True, slots=True)
class UnitCommandPolicy:
    edges: frozenset[tuple[str, str]]
    reasons: frozenset[str]
    last_good_mode: str = "none"
    attempt_binding: str = "none"


UNIT_COMMAND_POLICIES = {
    "attempt_started": UnitCommandPolicy(
        frozenset((source, "running") for source in _ATTEMPT_SOURCES),
        frozenset({"attempt_started"}), attempt_binding="fenced",
    ),
    "worker_command_started": UnitCommandPolicy(
        frozenset({("running", "running")}),
        frozenset({"worker_command_started"}), attempt_binding="fenced",
    ),
    "prelaunch_attempt_cancelled": UnitCommandPolicy(
        frozenset(("running", target) for target in _ATTEMPT_SOURCES),
        frozenset({"prelaunch_attempt_cancelled"}), attempt_binding="fenced",
    ),
    "lease_expired_recovery": UnitCommandPolicy(
        frozenset({("running", "retry-ready"), ("running", "exhausted")}),
        frozenset({"lease_expired_recovered"}), attempt_binding="attempt",
    ),
    "started_attempt_recovery": UnitCommandPolicy(
        frozenset({("running", "blocked")}),
        frozenset({"worker_command_result_unknown"}), attempt_binding="fenced",
    ),
    "attempt_finished": UnitCommandPolicy(
        frozenset(("running", target) for target in _WORKER_RESULTS),
        frozenset({
            "attempt_completed", "attempt_failed", "attempt_blocked",
            "terminal_worker_result",
        }),
        attempt_binding="fenced",
    ),
    "host_verification_failed": UnitCommandPolicy(
        frozenset((source, "retry-ready") for source in {
            "candidate-ready", "gate-pending", "resume-ready",
        }),
        frozenset({"host_verification_failed"}),
        last_good_mode="clear", attempt_binding="attempt",
    ),
    "host_verifier_promoted": UnitCommandPolicy(
        frozenset({
            ("candidate-ready", "resume-ready"),
            ("gate-pending", "resume-ready"),
        }),
        frozenset({"host_verifier_promoted"}),
        last_good_mode="set", attempt_binding="attempt",
    ),
    "project_unit_completed": UnitCommandPolicy(
        frozenset({("resume-ready", "completed")}),
        frozenset({"project_gate_bundle_passed"}),
    ),
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
class UnitProjection:
    state: UnitState
    version: int

    def __post_init__(self) -> None:
        _version(self.version)


@dataclass(frozen=True, slots=True)
class TransitionCommand:
    command_kind: str
    command_id: str
    run_id: str
    unit_id: str
    expected: UnitState
    expected_version: int
    target: UnitState
    reason: str
    evidence_sha256: str
    attempt_id: str | None = None
    fencing_token: int | None = None
    clear_last_good_if: str | None = None
    set_last_good_artifact_id: str | None = None

    def __post_init__(self) -> None:
        _validate_common(self)
        _version(self.expected_version)
        if not _identity(self.unit_id):
            raise ValueError("transition unit_id is invalid")
        for value, label in (
            (self.clear_last_good_if, "clear_last_good_if"),
            (self.set_last_good_artifact_id, "set_last_good_artifact_id"),
        ):
            if value is not None and not _identity(value):
                raise ValueError(f"{label} is invalid")
        if self.clear_last_good_if and self.set_last_good_artifact_id:
            raise ValueError("last-good projection cannot clear and set simultaneously")


def assert_transition_allowed(command: TransitionCommand) -> None:
    policy = UNIT_COMMAND_POLICIES.get(command.command_kind)
    if policy is None:
        raise ValueError("unit transition command kind is not registered")
    if (command.expected.status, command.target.status) not in policy.edges:
        raise ValueError("unit transition is not permitted for its command kind")
    if command.reason not in policy.reasons:
        raise ValueError("unit transition reason is not permitted for its command kind")
    _assert_attempt_binding(command, policy.attempt_binding)
    if policy.last_good_mode == "none" and (
        command.clear_last_good_if or command.set_last_good_artifact_id
    ):
        raise ValueError("unit transition kind cannot change last-good")
    if policy.last_good_mode == "clear" and (
        not command.clear_last_good_if or command.set_last_good_artifact_id
    ):
        raise ValueError("unit transition kind requires a last-good clear binding")
    if policy.last_good_mode == "set" and (
        not command.set_last_good_artifact_id or command.clear_last_good_if
    ):
        raise ValueError("unit transition kind requires a last-good set binding")


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


def _validate_common(command: Any) -> None:
    if _KIND.fullmatch(command.command_kind) is None:
        raise ValueError("transition command kind is invalid")
    if _COMMAND_ID.fullmatch(command.command_id) is None or not _identity(command.run_id):
        raise ValueError("transition command_id/run_id is invalid")
    if _REASON.fullmatch(command.reason) is None or _SHA256.fullmatch(
        command.evidence_sha256
    ) is None:
        raise ValueError("transition reason/evidence_sha256 is invalid")
    if command.attempt_id is not None and not _identity(command.attempt_id):
        raise ValueError("transition attempt_id is invalid")
    if command.fencing_token is not None and (
        isinstance(command.fencing_token, bool) or command.fencing_token < 1
    ):
        raise ValueError("transition fencing_token is invalid")


def _assert_attempt_binding(command: Any, mode: str) -> None:
    if mode == "none" and (
        command.attempt_id is not None or command.fencing_token is not None
    ):
        raise ValueError("transition kind cannot bind an attempt")
    if mode == "attempt" and command.attempt_id is None:
        raise ValueError("transition kind requires an attempt binding")
    if mode == "fenced" and (
        command.attempt_id is None or command.fencing_token is None
    ):
        raise ValueError("transition kind requires an attempt and fence")


def _version(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("transition state version is invalid")


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256 and all(
        character.isalnum() or character in "-_.:" for character in value
    )


__all__ = [
    "RUN_COMMAND_POLICIES", "RUN_STATUSES", "RunProjection",
    "RunTransitionCommand", "TransitionCommand", "UNIT_COMMAND_POLICIES",
    "UNIT_RESUMABLE_STATES", "UnitProjection", "UnitState",
    "assert_run_transition_allowed", "assert_transition_allowed",
    "stable_transition_command_id", "transition_evidence_sha256",
]
