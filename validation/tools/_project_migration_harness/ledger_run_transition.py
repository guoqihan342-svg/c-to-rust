from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_ID = re.compile(r"^[a-z][a-z0-9_.:-]{0,191}$")
_KIND = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_REASON = re.compile(r"^[a-z][a-z0-9_.-]{0,95}$")
RUN_STATUSES = frozenset({
    "active", "finalizing", "completed", "failed", "cancelled",
})
RUN_COMMAND_POLICIES = {
    "terminal_worker_run_failed": (
        frozenset({("active", "failed")}),
        frozenset({"terminal_worker_result"}), "fenced",
    ),
    "lease_recovery_run_failed": (
        frozenset({("active", "failed")}),
        frozenset({"worker_command_result_unknown"}), "fenced",
    ),
    "project_run_finalizing": (
        frozenset({("active", "finalizing")}),
        frozenset({"project_completion_frozen"}), "none",
    ),
    "project_run_completed": (
        frozenset({("finalizing", "completed"), ("active", "completed")}),
        frozenset({"project_gate_bundle_passed"}), "none",
    ),
}
_BINDING_KEYS = {
    "cohort_sha256", "generation_sha256", "gate_bundle_sha256",
    "invariant_sha256", "receipt_sha256",
}


def _version(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("transition state version is invalid")


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256 and all(
        character.isalnum() or character in "-_.:" for character in value
    )


@dataclass(frozen=True, slots=True)
class CompletionProjection:
    epoch: int = 0
    cohort_sha256: str | None = None
    generation_sha256: str | None = None
    gate_bundle_sha256: str | None = None
    invariant_sha256: str | None = None
    receipt_sha256: str | None = None

    def __post_init__(self) -> None:
        _version(self.epoch)
        for value in self.binding().values():
            if value is not None and _SHA256.fullmatch(value) is None:
                raise ValueError("run completion binding is invalid")

    def binding(self) -> dict[str, str | None]:
        return {
            "cohort_sha256": self.cohort_sha256,
            "generation_sha256": self.generation_sha256,
            "gate_bundle_sha256": self.gate_bundle_sha256,
            "invariant_sha256": self.invariant_sha256,
            "receipt_sha256": self.receipt_sha256,
        }

    def payload(self) -> dict[str, Any]:
        return {"epoch": self.epoch, **self.binding()}

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> "CompletionProjection":
        if value == {} or value is None:
            return cls()
        if not isinstance(value, Mapping) or set(value) != {"epoch", *_BINDING_KEYS}:
            raise ValueError("run completion projection payload is invalid")
        return cls(epoch=value["epoch"], **{key: value[key] for key in _BINDING_KEYS})


EMPTY_COMPLETION = CompletionProjection()


@dataclass(frozen=True, slots=True)
class RunProjection:
    status: str
    version: int
    completion: CompletionProjection = EMPTY_COMPLETION

    def __post_init__(self) -> None:
        if self.status not in RUN_STATUSES:
            raise ValueError("run status is invalid")
        _version(self.version)
        values = list(self.completion.binding().values())
        if self.status in {"active", "failed", "cancelled"}:
            valid = self.completion.epoch == 0 and all(value is None for value in values)
        elif self.status == "finalizing":
            valid = (
                self.completion.epoch > 0
                and all(value is not None for value in values[:-1])
                and self.completion.receipt_sha256 is None
            )
        else:
            valid = (
                self.completion == EMPTY_COMPLETION
                or self.completion.epoch > 0 and all(value is not None for value in values)
            )
        if not valid:
            raise ValueError("run status/completion projection is invalid")


@dataclass(frozen=True, slots=True)
class RunTransitionCommand:
    command_kind: str
    command_id: str
    run_id: str
    anchor_unit_id: str
    expected_status: str
    expected_version: int
    target_status: str
    reason: str
    evidence_sha256: str
    attempt_id: str | None = None
    fencing_token: int | None = None
    expected_completion: CompletionProjection = EMPTY_COMPLETION
    target_completion: CompletionProjection = EMPTY_COMPLETION

    def __post_init__(self) -> None:
        if (
            _KIND.fullmatch(self.command_kind) is None
            or _COMMAND_ID.fullmatch(self.command_id) is None
            or not _identity(self.run_id) or not _identity(self.anchor_unit_id)
            or _REASON.fullmatch(self.reason) is None
            or _SHA256.fullmatch(self.evidence_sha256) is None
        ):
            raise ValueError("run transition command fields are invalid")
        RunProjection(self.expected_status, self.expected_version, self.expected_completion)
        RunProjection(self.target_status, self.expected_version + 1, self.target_completion)
        if self.attempt_id is not None and not _identity(self.attempt_id):
            raise ValueError("run transition attempt_id is invalid")
        if self.fencing_token is not None and (
            isinstance(self.fencing_token, bool) or self.fencing_token < 1
        ):
            raise ValueError("run transition fencing_token is invalid")


def assert_run_transition_allowed(command: RunTransitionCommand) -> None:
    policy = RUN_COMMAND_POLICIES.get(command.command_kind)
    if policy is None:
        raise ValueError("run transition command kind is not registered")
    edges, reasons, attempt_binding = policy
    if (command.expected_status, command.target_status) not in edges:
        raise ValueError("run transition is not permitted for its command kind")
    if command.reason not in reasons:
        raise ValueError("run transition reason is not permitted for its command kind")
    _assert_attempt_binding(command, attempt_binding)
    if (
        command.expected_status == "active" and command.target_status == "completed"
        and (
            command.expected_completion != EMPTY_COMPLETION
            or command.target_completion != EMPTY_COMPLETION
        )
    ):
        raise ValueError("legacy completion edge cannot carry finalization bindings")


def _assert_attempt_binding(command: RunTransitionCommand, mode: str) -> None:
    if mode == "none" and (command.attempt_id is not None or command.fencing_token is not None):
        raise ValueError("transition kind cannot bind an attempt")
    if mode == "fenced" and (
        command.attempt_id is None or command.fencing_token is None
    ):
        raise ValueError("transition kind requires an attempt and fence")


__all__ = [
    "CompletionProjection", "EMPTY_COMPLETION", "RUN_COMMAND_POLICIES",
    "RUN_STATUSES", "RunProjection", "RunTransitionCommand",
    "assert_run_transition_allowed",
]
