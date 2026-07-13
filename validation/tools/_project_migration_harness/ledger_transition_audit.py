from __future__ import annotations

import json
import sqlite3
from typing import Any, Mapping

from .ledger_security import LedgerError


LEGACY_UNIT_PREFIX = "fsm-v1:"
UNIT_PREFIX = "fsm-unit-v2:"
RUN_PREFIX = "fsm-run-v1:"

_LEGACY_UNIT_FIELDS = {
    "clear_last_good_if", "command_id", "evidence_sha256",
    "expected_resumable_status", "reason", "target_resumable_status",
}
_UNIT_FIELDS = _LEGACY_UNIT_FIELDS | {"set_last_good_artifact_id"}
_RUN_FIELDS = {"command_id", "evidence_sha256", "reason"}


def encode_unit_command(command: Any) -> str:
    payload = {
        "clear_last_good_if": command.clear_last_good_if,
        "command_id": command.command_id,
        "evidence_sha256": command.evidence_sha256,
        "expected_resumable_status": command.expected.resumable_status,
        "reason": command.reason,
        "set_last_good_artifact_id": command.set_last_good_artifact_id,
        "target_resumable_status": command.target.resumable_status,
    }
    return UNIT_PREFIX + _json(payload)


def encode_run_command(command: Any) -> str:
    return RUN_PREFIX + _json({
        "command_id": command.command_id,
        "evidence_sha256": command.evidence_sha256,
        "reason": command.reason,
    })


def command_rows(
    connection: sqlite3.Connection, *, run_id: str, unit_id: str | None,
    command_id: str, scope: str,
) -> list[tuple[sqlite3.Row, Mapping[str, Any]]]:
    matches = []
    if unit_id is None:
        rows = connection.execute(
            """select transition_id,unit_id,from_status,to_status,reason,attempt_id,fencing_token
               from transitions where run_id=? order by transition_id""", (run_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """select transition_id,unit_id,from_status,to_status,reason,attempt_id,fencing_token
               from transitions where run_id=? and unit_id=? order by transition_id""",
            (run_id, unit_id),
        ).fetchall()
    for row in rows:
        decoded = decode_command_reason(str(row["reason"]))
        if decoded is not None and decoded[0] == scope and decoded[1]["command_id"] == command_id:
            matches.append((row, decoded[1]))
    return matches


def decode_command_reason(value: str) -> tuple[str, Mapping[str, Any]] | None:
    if value.startswith(UNIT_PREFIX):
        return "unit", _decode(value[len(UNIT_PREFIX):], _UNIT_FIELDS)
    if value.startswith(RUN_PREFIX):
        return "run", _decode(value[len(RUN_PREFIX):], _RUN_FIELDS)
    if value.startswith(LEGACY_UNIT_PREFIX):
        payload = dict(_decode(value[len(LEGACY_UNIT_PREFIX):], _LEGACY_UNIT_FIELDS))
        payload["set_last_good_artifact_id"] = None
        return "unit", payload
    return None


def _decode(value: str, fields: set[str]) -> Mapping[str, Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise LedgerError("transition command envelope is invalid JSON") from error
    if not isinstance(payload, dict) or set(payload) != fields:
        raise LedgerError("transition command envelope fields are invalid")
    return payload


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    )


__all__ = [
    "LEGACY_UNIT_PREFIX", "RUN_PREFIX", "UNIT_PREFIX", "command_rows",
    "decode_command_reason", "encode_run_command", "encode_unit_command",
]
