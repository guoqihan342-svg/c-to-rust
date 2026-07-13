from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .ledger_transition_policy import (
    RunProjection, RunTransitionCommand, TransitionCommand, UnitProjection,
    UnitState, stable_transition_command_id, transition_evidence_sha256,
)


def attempt_started_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: UnitProjection, input_sha256: str,
) -> TransitionCommand:
    return _unit(
        "attempt_started", "attempt-started", run_id, unit_id, expected,
        UnitState("running", "in_progress"), "attempt_started", input_sha256,
        attempt_id=attempt_id, fencing_token=fencing_token,
        identity=(attempt_id,),
    )


def attempt_started_command_id(
    *, run_id: str, unit_id: str, attempt_id: str,
) -> str:
    return stable_transition_command_id(
        "attempt-started", run_id, unit_id, attempt_id,
    )


def worker_command_started_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: UnitProjection, metadata: Mapping[str, Any],
) -> TransitionCommand:
    evidence = transition_evidence_sha256({
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "request_sha256": metadata.get("request_sha256"),
        "preflight_sha256": metadata.get("preflight_sha256"),
    })
    return _unit(
        "worker_command_started", "worker-command-started", run_id, unit_id,
        expected, expected.state, "worker_command_started", evidence,
        attempt_id=attempt_id, fencing_token=fencing_token,
        identity=(attempt_id,),
    )


def prelaunch_cancel_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: UnitProjection, previous: UnitProjection,
    metadata: Mapping[str, Any],
) -> TransitionCommand:
    evidence = transition_evidence_sha256({
        "attempt_id": attempt_id,
        "fencing_token": fencing_token,
        "previous_status": previous.state.status,
        "previous_resumable_status": previous.state.resumable_status,
        "previous_state_version": previous.version,
        "request_sha256": metadata.get("request_sha256"),
        "preflight_sha256": metadata.get("preflight_sha256"),
    })
    return _unit(
        "prelaunch_attempt_cancelled", "prelaunch-attempt-cancelled",
        run_id, unit_id, expected, previous.state, "prelaunch_attempt_cancelled",
        evidence, attempt_id=attempt_id, fencing_token=fencing_token,
        identity=(attempt_id,),
    )


def lease_recovery_command(
    *, run_id: str, unit_id: str, row: Any, attempt_count: int,
    started: bool, expected: UnitProjection, target: UnitState,
) -> TransitionCommand:
    kind = "started_attempt_recovery" if started else "lease_expired_recovery"
    reason = "worker_command_result_unknown" if started else "lease_expired_recovered"
    evidence = transition_evidence_sha256({
        "attempt_id": row["attempt_id"],
        "attempt_count": attempt_count,
        "max_attempts": row["max_attempts"],
        "started": started,
        "lease_status": row["lease_status"],
        "lease_expires_at": row["expires_at"],
    })
    return _unit(
        kind, "lease-recovery", run_id, unit_id, expected, target, reason,
        evidence, attempt_id=str(row["attempt_id"]),
        fencing_token=int(row["fencing_token"]), identity=(row["attempt_id"],),
    )


def lease_recovery_run_command(
    *, run_id: str, rows: list[Any], clock: int, expected: RunProjection,
) -> RunTransitionCommand:
    anchor = rows[0]
    attempt_ids = [str(row["attempt_id"]) for row in rows]
    return _run(
        "lease_recovery_run_failed", "lease-recovery-run-failed", run_id,
        str(anchor["unit_id"]), expected, "failed",
        "worker_command_result_unknown",
        transition_evidence_sha256({"attempt_ids": attempt_ids, "clock": clock}),
        attempt_id=str(anchor["attempt_id"]),
        fencing_token=int(anchor["fencing_token"]), identity=(attempt_ids,),
    )


def attempt_finished_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: UnitProjection, target: UnitState, reason: str,
    evidence_sha256: str,
) -> TransitionCommand:
    return _unit(
        "attempt_finished", "attempt-finished", run_id, unit_id, expected,
        target, reason, evidence_sha256, attempt_id=attempt_id,
        fencing_token=fencing_token, identity=(attempt_id,),
    )


def terminal_worker_run_failed_command(
    *, run_id: str, unit_id: str, attempt_id: str, fencing_token: int,
    expected: RunProjection, evidence_sha256: str,
) -> RunTransitionCommand:
    return _run(
        "terminal_worker_run_failed", "terminal-worker-run-failed", run_id,
        unit_id, expected, "failed", "terminal_worker_result", evidence_sha256,
        attempt_id=attempt_id, fencing_token=fencing_token,
        identity=(unit_id, attempt_id),
    )


def host_verification_failed_command(
    *, command_id: str, run_id: str, unit_id: str, expected: UnitProjection,
    evidence_sha256: str, attempt_id: str, candidate_artifact_id: str,
) -> TransitionCommand:
    return TransitionCommand(
        command_kind="host_verification_failed", command_id=command_id,
        run_id=run_id, unit_id=unit_id, expected=expected.state,
        expected_version=expected.version,
        target=UnitState("retry-ready", "retryable"),
        reason="host_verification_failed", evidence_sha256=evidence_sha256,
        attempt_id=attempt_id, clear_last_good_if=candidate_artifact_id,
    )


def host_verifier_promoted_command(
    *, command_id: str, run_id: str, unit_id: str, expected: UnitProjection,
    evidence_sha256: str, attempt_id: str, candidate_artifact_id: str,
) -> TransitionCommand:
    return TransitionCommand(
        command_kind="host_verifier_promoted", command_id=command_id,
        run_id=run_id, unit_id=unit_id, expected=expected.state,
        expected_version=expected.version,
        target=UnitState("resume-ready", "last_good"),
        reason="host_verifier_promoted", evidence_sha256=evidence_sha256,
        attempt_id=attempt_id, set_last_good_artifact_id=candidate_artifact_id,
    )


def project_unit_completed_command(
    *, run_id: str, unit_id: str, expected: UnitProjection,
    candidate_set_sha256: str,
) -> TransitionCommand:
    return _unit(
        "project_unit_completed", "project-unit-completed", run_id, unit_id,
        expected, UnitState("completed", "terminal"),
        "project_gate_bundle_passed", candidate_set_sha256,
        identity=(candidate_set_sha256,),
    )


def project_run_completed_command(
    *, run_id: str, anchor_unit_id: str, expected: RunProjection,
    candidate_set_sha256: str,
) -> RunTransitionCommand:
    return _run(
        "project_run_completed", "project-run-completed", run_id,
        anchor_unit_id, expected, "completed", "project_gate_bundle_passed",
        candidate_set_sha256, identity=(candidate_set_sha256,),
    )


def _unit(
    kind: str, action: str, run_id: str, unit_id: str,
    expected: UnitProjection, target: UnitState, reason: str, evidence: str,
    *, attempt_id: str | None = None, fencing_token: int | None = None,
    identity: tuple[Any, ...] = (),
) -> TransitionCommand:
    return TransitionCommand(
        command_kind=kind,
        command_id=stable_transition_command_id(
            action, run_id, unit_id, *identity,
        ),
        run_id=run_id, unit_id=unit_id, expected=expected.state,
        expected_version=expected.version, target=target, reason=reason,
        evidence_sha256=evidence, attempt_id=attempt_id,
        fencing_token=fencing_token,
    )


def _run(
    kind: str, action: str, run_id: str, anchor: str,
    expected: RunProjection, target: str, reason: str, evidence: str,
    *, attempt_id: str | None = None, fencing_token: int | None = None,
    identity: tuple[Any, ...] = (),
) -> RunTransitionCommand:
    return RunTransitionCommand(
        command_kind=kind,
        command_id=stable_transition_command_id(action, run_id, *identity),
        run_id=run_id, anchor_unit_id=anchor,
        expected_status=expected.status, expected_version=expected.version,
        target_status=target, reason=reason, evidence_sha256=evidence,
        attempt_id=attempt_id, fencing_token=fencing_token,
    )


__all__ = [
    "attempt_finished_command", "attempt_started_command",
    "attempt_started_command_id",
    "host_verification_failed_command", "host_verifier_promoted_command",
    "lease_recovery_command", "lease_recovery_run_command",
    "prelaunch_cancel_command", "project_run_completed_command",
    "project_unit_completed_command", "terminal_worker_run_failed_command",
    "worker_command_started_command",
]
