from __future__ import annotations

import json
import time
from typing import Any

from .ledger_schema import _now_text, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import TransitionAuthority, load_unit_projection
from .ledger_transition_commands import (
    attempt_started_command_id, prelaunch_cancel_command,
)


class PrelaunchCancellationMixin:
    def cancel_prelaunch_attempt(
        self, *, attempt_id: str, owner: str, fencing_token: int,
    ) -> None:
        with self.connect() as connection, atomic(connection):
            attempt = self._running_attempt(
                connection, attempt_id, owner, fencing_token,
            )
            metadata = _object_json(connection.execute(
                "select metadata_json from attempts where attempt_id=?", (attempt_id,),
            ).fetchone()[0])
            if metadata.get("command_started") is True:
                raise LedgerError("started worker command requires manual reconciliation")
            if connection.execute(
                "select 1 from artifacts where attempt_id=?", (attempt_id,),
            ).fetchone():
                raise LedgerError("prelaunch attempt unexpectedly owns an artifact")
            run_id, unit_id = str(attempt["run_id"]), str(attempt["unit_id"])
            authority = TransitionAuthority(connection)
            previous = authority.bound_unit_expected(
                run_id=run_id, unit_id=unit_id,
                command_kind="attempt_started",
                command_id=attempt_started_command_id(
                    run_id=run_id, unit_id=unit_id, attempt_id=attempt_id,
                ),
            )
            if previous is None:
                raise LedgerError("prelaunch attempt has no immutable start event")
            command = prelaunch_cancel_command(
                run_id=run_id, unit_id=unit_id, attempt_id=attempt_id,
                fencing_token=fencing_token,
                expected=load_unit_projection(connection, run_id, unit_id),
                previous=previous, metadata=metadata,
            )
            timestamp = _now_text()
            authority.apply(command, created_at=timestamp)
            updated = connection.execute(
                """update attempts set status='cancelled',error_key='prelaunch_cancelled',
                   finished_at=? where attempt_id=? and status='running'""",
                (timestamp, attempt_id),
            )
            if updated.rowcount != 1:
                raise LedgerError("prelaunch cancellation lost its running attempt")
            connection.execute(
                """update leases set status='released',heartbeat_at=?
                   where run_id=? and unit_id=?""",
                (int(time.time()), run_id, unit_id),
            )


def _object_json(value: Any) -> dict[str, Any]:
    try:
        result = json.loads(value) if isinstance(value, str) else None
    except json.JSONDecodeError as error:
        raise LedgerError("attempt metadata is invalid JSON") from error
    if not isinstance(result, dict):
        raise LedgerError("attempt metadata must be an object")
    return result


__all__ = ["PrelaunchCancellationMixin"]
