from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_frontier_gate import require_attempt_context_frontier
from .ledger_schema import _json, _now_text, _require_sha256, atomic
from .ledger_security import LedgerError
from .ledger_run_state import require_active_completion
from .ledger_transition_authority import TransitionAuthority, load_unit_projection
from .ledger_transition_commands import worker_command_started_command


class RuntimeAttemptLaunchMixin:
    def authorize_command_launch(
        self, *, attempt_id: str, owner: str, fencing_token: int,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            run = connection.execute(
                "select run_id from attempts where attempt_id=?", (attempt_id,),
            ).fetchone()
            require_active_completion(
                connection, str(run["run_id"]) if run else "",
                action="provider launch authorization",
            )
            attempt = self._running_attempt(
                connection, attempt_id, owner, fencing_token,
            )
            metadata = _attempt_metadata(connection, attempt_id)
            if metadata.get("command_started") is True:
                raise LedgerError("worker command was already started for this attempt")
            require_attempt_context_frontier(
                connection, run_id=str(attempt["run_id"]),
                unit_id=str(attempt["unit_id"]), attempt_metadata=metadata,
            )
            authorization = _launch_authorization(
                attempt_id=attempt_id, attempt=attempt, metadata=metadata,
            )
            existing = metadata.get("launch_authorization")
            if existing is not None and existing != authorization:
                raise LedgerError("worker launch authorization binding drifted")
            metadata["launch_authorization"] = authorization
            metadata.setdefault("launch_authorized_at", _now_text())
            connection.execute(
                "update attempts set metadata_json=? where attempt_id=?",
                (_json(metadata), attempt_id),
            )

    def mark_command_started(
        self, *, attempt_id: str, owner: str, fencing_token: int,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            run = connection.execute(
                "select run_id from attempts where attempt_id=?", (attempt_id,),
            ).fetchone()
            require_active_completion(
                connection, str(run["run_id"]) if run else "",
                action="provider command start",
            )
            attempt = self._running_attempt(
                connection, attempt_id, owner, fencing_token,
            )
            metadata = _attempt_metadata(connection, attempt_id)
            if metadata.get("command_started") is True:
                raise LedgerError("worker command was already started for this attempt")
            claim = metadata.get("launch_claim")
            if isinstance(claim, Mapping):
                if metadata.get("launch_authorization") != _launch_authorization(
                    attempt_id=attempt_id, attempt=attempt, metadata=metadata,
                ):
                    raise LedgerError("worker command has no current launch authorization")
            elif metadata.get("launch_authorization") is not None:
                raise LedgerError("legacy attempt carries a launch authorization")
            require_attempt_context_frontier(
                connection, run_id=str(attempt["run_id"]),
                unit_id=str(attempt["unit_id"]), attempt_metadata=metadata,
            )
            timestamp = _now_text()
            metadata["command_started"] = True
            metadata["command_started_at"] = timestamp
            connection.execute(
                "update attempts set metadata_json=? where attempt_id=?",
                (_json(metadata), attempt_id),
            )
            run_id, unit_id = str(attempt["run_id"]), str(attempt["unit_id"])
            command = worker_command_started_command(
                run_id=run_id, unit_id=unit_id, attempt_id=attempt_id,
                fencing_token=fencing_token,
                expected=load_unit_projection(connection, run_id, unit_id),
                metadata=metadata,
            )
            TransitionAuthority(connection).apply(command, created_at=timestamp)


def _attempt_metadata(connection: Any, attempt_id: str) -> dict[str, Any]:
    row = connection.execute(
        "select metadata_json from attempts where attempt_id=?", (attempt_id,),
    ).fetchone()
    try:
        metadata = json.loads(row[0]) if row is not None else None
    except json.JSONDecodeError as error:
        raise LedgerError("attempt metadata is invalid JSON") from error
    if not isinstance(metadata, dict):
        raise LedgerError("attempt metadata must be an object")
    return metadata


def _launch_authorization(
    *, attempt_id: str, attempt: Mapping[str, Any], metadata: Mapping[str, Any],
) -> dict[str, Any]:
    request_sha256 = metadata.get("request_sha256")
    preflight_sha256 = metadata.get("preflight_sha256")
    claim = metadata.get("launch_claim")
    schedule_sha256 = metadata.get("schedule_sha256")
    if not isinstance(claim, Mapping):
        raise LedgerError("worker launch evidence binding is incomplete")
    try:
        request_sha256 = _require_sha256(request_sha256, "request_sha256")
        preflight_sha256 = _require_sha256(preflight_sha256, "preflight_sha256")
        schedule_sha256 = _require_sha256(schedule_sha256, "schedule_sha256")
        claim_sha256 = _require_sha256(claim.get("sha256"), "launch_claim_sha256")
    except ValueError as error:
        raise LedgerError("worker launch evidence binding is incomplete") from error
    payload = {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "run_id": attempt["run_id"],
        "unit_id": attempt["unit_id"],
        "worker_id": attempt["worker_id"],
        "fencing_epoch": attempt["fencing_token"],
        "request_sha256": request_sha256,
        "preflight_sha256": preflight_sha256,
        "launch_claim_sha256": claim_sha256,
        "schedule_sha256": schedule_sha256,
    }
    return {**payload, "sha256": content_sha256(payload)}


__all__ = ["RuntimeAttemptLaunchMixin"]
